# Do Not Store Connection in Singleton Fields or Share Across Threads

In Spring Data Access, a JDBC `Connection` should not be stored as a **field of a Spring singleton bean** and should not be passed to multiple threads for concurrent use. A `Connection` represents a stateful session with the database: it holds the active transaction, `autoCommit` mode, isolation level, schema/catalog, open statements, and resources. When multiple requests or threads operate on the same connection simultaneously, they inadvertently share **the same session and transaction boundary**; closing or mutating state in one place can break work in another.

Practical rule:

> **Share stably configured `DataSource` and `JdbcTemplate` instances; let each task borrow a `Connection` when needed and return/release it at the right time.** In a Spring transaction, let `JdbcTemplate` and the transaction manager manage the thread-bound connection. Do not store `Connection`, `Statement`, or `ResultSet` in singletons or caches for arbitrary reuse.

This article focuses on **synchronous JDBC** (Spring Framework, `DataSource`, `JdbcTemplate`, and JDBC transaction managers), while pointing out the boundary with asynchronous tasks. Do not overgeneralize that every JDBC driver fails the instant two threads call one `Connection`: some drivers have internal synchronization. The core issue is that JDBC **does not guarantee transaction/session independence** for two tasks sharing one connection, and concurrent access support varies by driver.

## 1. Distinguishing Shared Objects from Short-Lived Resources

| Object | Role | Should It Be Stored in a Singleton and Shared? |
| --- | --- | --- |
| `DataSource` | Connection provider; may use a connection pool such as HikariCP. | **Yes**, typically a singleton Spring bean configured once. |
| `JdbcTemplate` | SQL execution tool; acquires and releases resources via Spring. | **Yes**, thread-safe once configured; avoid mutating settings on an active instance. |
| Stateless per-request `Repository`/`Service` | Coordinates business logic and DB access. | **Yes**, typically a singleton; dependencies are final and immutable where appropriate. |
| `Connection` | JDBC session with transaction and session state. | **No**—do not keep as a shared field; borrow per task or transaction. |
| `PreparedStatement`/`Statement` | SQL statement tied to a connection, with parameters/cursor/state. | **No**—do not share across requests/threads. |
| `ResultSet` | Cursor over a statement's results; lifecycle tied to JDBC resources. | **No**—do not share or return outside resource scope unless handled properly. |
| Fully read immutable DTO/record | Plain Java data snapshot holding no JDBC handles. | **Yes, if appropriate**, provided data is not sensitive or request-state-bound and design allows. |

A `DataSource` may open a fresh connection per call or be backed by a pool. A pooled `DataSource` is a component that **manages many connections**, not a single `Connection` for all threads to use concurrently. Each borrow typically receives its own logical handle; upon return, the pool can reuse the physical connection sequentially.

### 1.1. How many instances does a singleton Spring bean have?

By default, a Spring bean with `singleton` scope has **one instance per Spring IoC container**, and multiple requests can call methods on that instance concurrently. Spring **does not automatically add locks** around singleton methods and does not create separate per-thread fields.

For example, in a singleton `@Repository`, a `private final JdbcTemplate jdbc;` field is a safe shared dependency once the template is stably configured. By contrast, a `private Connection connection;` field becomes a shared handle across concurrent requests. `final` only fixes **the object reference**, not making the underlying JDBC object thread-safe.

## 2. Why Does Sharing a Connection Cause Bugs?

### 2.1. Transaction state belongs to the Connection, not individual SQL calls

Normally, a JDBC `Connection` has an `autoCommit` property. If `setAutoCommit(false)` is set, statements executed on that connection join the active transaction until `commit()` or `rollback()`. Two threads using **the same connection** do not get two independent JDBC transactions merely because they are different threads.

Risky scenario:

```text
Thread A                       Shared Connection                    Thread B
   |                                  |                                  |
   |-- setAutoCommit(false) --------->|                                  |
   |-- UPDATE accounts ... ---------->|  tx T already holds change A     |
   |                                  |<--------- UPDATE orders ... -----|
   |                                  |  change B also enters tx T       |
   |-- rollback() ------------------->|                                  |
   |                                  |  rolls back both A and B         |
   |                                  |                                  |
```

If B believes its update was independent of A, the business outcome will be wrong. If B calls `commit()`, it is even worse: B can commit A's unfinished work. Changing `autoCommit` mid-transaction can also commit the active transaction under JDBC rules.

### 2.2. Session state and cursors cross-contaminate

Beyond commit/rollback, a connection carries state such as:

- `setTransactionIsolation(...)`: transaction isolation level; another thread may run under unintended isolation.
- `setReadOnly(...)`: hint/control for read-only mode depending on driver/DB.
- `setCatalog(...)`, `setSchema(...)`: DB/schema context for queries.
- `setAutoCommit(...)`: transaction mode for the entire connection.
- Temporary tables, session variables, locks, statements, and cursors: lifecycle and support depend on DBMS/driver.
- `close()`: resource is closed/returned to the pool; the old connection object is no longer a valid handle for the running task.

A `PreparedStatement` holds its own parameters and state. If a singleton stores it and threads A and B concurrently call `setLong(1, ...)` then `executeUpdate()`, bound values can be overwritten. A `ResultSet` has a cursor moved by `next()`; two threads reading it together can skip rows, hit invalid state, or trigger driver errors. **Do not use `synchronized` as a substitute for a resource ownership model**: locking can serialize and slow down all requests without solving long-held transactions, resource leaks, or the need for independent transactions.

### 2.3. One thread closes while another is still using it

```text
A: connection.prepareStatement(...)
B: connection.close()
A: statement.executeQuery()  --> may receive SQLException / invalidated statement
```

With HikariCP, `close()` on a logical connection usually **returns the handle to the pool**. At that point, a request C can borrow the underlying physical connection; A no longer owns the old handle. Thus, "already using a connection pool" does not make sharing one `Connection` safe.

## 3. Anti-Pattern: Storing Connection in a Singleton Field

This example is **deliberately wrong to help identify the design flaw**; do not use it in applications:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

import org.springframework.stereotype.Repository;

@Repository
public class UnsafeEventRepository {
    private final Connection sharedConnection; // WRONG: singleton holds a single JDBC session

    public UnsafeEventRepository(DataSource dataSource) throws SQLException {
        this.sharedConnection = dataSource.getConnection(); // borrowed at startup
    }

    public void addEvent(long id, String message) throws SQLException {
        try (PreparedStatement ps = sharedConnection.prepareStatement(
                "INSERT INTO audit_event(id, message) VALUES (?, ?)")) {
            ps.setLong(1, id);
            ps.setString(2, message);
            ps.executeUpdate();
        }
    }
}
```

Problems:

1. Multiple requests call `addEvent()` on **the same** `sharedConnection`.
2. Transaction and session state are shared; there is no connection-level isolation between requests.
3. The connection is held for the entire bean lifecycle, occupying a pool slot with no clear release point. If the bean shuts down without calling `close()`, the pool/DB has to clean up an abandoned resource.
4. If the connection drops due to a network issue or DB timeout, every request using this field can fail together.
5. Creating a fresh `PreparedStatement` each time **does not fix sharing the Connection**; it only avoids sharing the statement itself.

Another variant that is also wrong:

```java
private static Connection globalConnection; // WRONG: entire JVM shares one handle
```

A self-managed `ThreadLocal<Connection>` is **not a default solution either**: server threads are commonly pooled/reused, so connections can be held too long and leak pool slots, and application code conflicts with Spring's transaction lifecycle. In Spring, use `DataSourceUtils` or `JdbcTemplate` for transaction compatibility instead of binding connections to a custom ThreadLocal.

## 4. The Right Way with Raw JDBC: Borrow, Use, Close in One Scope

For JDBC code not participating in a Spring-managed transaction, keep `Connection`, `PreparedStatement`, and `ResultSet` in local variables and use **`try-with-resources`**.

`SafeEventRepository.java` below is a valid Java 17+ class requiring an externally supplied `DataSource` and an existing `audit_event(id, message)` table:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class SafeEventRepository {
    private final DataSource dataSource; // Holds only the factory/pool

    public SafeEventRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public int addEvent(long id, String message) throws SQLException {
        String sql = "INSERT INTO audit_event(id, message) VALUES (?, ?)";

        try (Connection con = dataSource.getConnection();
             PreparedStatement ps = con.prepareStatement(sql)) {
            ps.setLong(1, id);
            ps.setString(2, message);
            return ps.executeUpdate();
        }
    }
}
```

Two threads calling `addEvent()` will make **two independent Connection borrows**. The pool can issue two different physical connections when running concurrently, or reuse the same physical connection *after* one borrow finishes. The task never keeps a connection in a field.

When the thread exits `try`, Java invokes `close()` in reverse order (statement then connection). With a pooled source, closing the logical connection returns it to the pool when valid; with an unpooled source, it usually closes the physical connection.

This snippet only illustrates **resource ownership**. It does not automatically solve all business race conditions: two separate transactions can still update the same row, hit deadlocks, or suffer lost updates without proper locking, isolation, versioning, or atomic SQL. Independent connections are a prerequisite, not a substitute for transaction correctness.

### 4.1. When multiple SQL statements belong to one raw JDBC transaction

A single **task** may legitimately use the same Connection for multiple statements, provided it owns the connection for the transaction scope and never shares it with another thread. The example below can be a Java 17+ class in an app with a `DataSource` and an `accounts(id, balance)` table, using `BigDecimal` for money:

```java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class TransferRepository {
    private final DataSource dataSource;

    public TransferRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void transfer(long from, long to, BigDecimal amount) throws SQLException {
        try (Connection con = dataSource.getConnection()) {
            con.setAutoCommit(false);

            try {
                debit(con, from, amount);
                credit(con, to, amount);
                con.commit();
            } catch (SQLException | RuntimeException error) {
                try {
                    con.rollback();
                } catch (SQLException rollbackError) {
                    error.addSuppressed(rollbackError);
                }
                throw error;
            }
        }
    }

    private void debit(Connection con, long id, BigDecimal amount)
            throws SQLException {
        String sql = "UPDATE accounts SET balance = balance - ? WHERE id = ?";
        try (PreparedStatement ps = con.prepareStatement(sql)) {
            ps.setBigDecimal(1, amount);
            ps.setLong(2, id);
            if (ps.executeUpdate() != 1) {
                throw new SQLException("Source account not found");
            }
        }
    }

    private void credit(Connection con, long id, BigDecimal amount)
            throws SQLException {
        String sql = "UPDATE accounts SET balance = balance + ? WHERE id = ?";
        try (PreparedStatement ps = con.prepareStatement(sql)) {
            ps.setBigDecimal(1, amount);
            ps.setLong(2, id);
            if (ps.executeUpdate() != 1) {
                throw new SQLException("Destination account not found");
            }
        }
    }
}
```

`con` is passed between helper methods **within the same synchronous call**, never placed in a singleton field or handed to an executor. This code does not yet implement balance checks, negative-amount checks, deadlock handling, or business concurrency strategies; those controls are essential for real money transfers.

With a pool, after the connection is returned, the pool may reset basic JDBC state before the next borrow. The application must still commit/roll back properly, avoid leaving transactions open, and avoid mutating session state in ways the pool cannot detect.

## 5. Preferred Approach in Spring: Singleton Repository Using JdbcTemplate

Spring documents `JdbcTemplate` as **thread-safe once configured**. A singleton repository should hold `JdbcTemplate`, not `Connection`. When calling `jdbc.update(...)`/`query(...)`, the template acquires and releases connections using integration with `DataSourceUtils` and the transaction manager.

Spring 6.x / Java 17+ repository example:

```java
import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public final class EventRepository {
    private final JdbcTemplate jdbc; // Safe shared singleton once configured

    public EventRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public int addEvent(long id, String message) {
        return jdbc.update(
            "INSERT INTO audit_event(id, message) VALUES (?, ?)",
            id, message
        );
    }

    public List<Event> findAll() {
        return jdbc.query(
            "SELECT id, message FROM audit_event ORDER BY id",
            (rs, rowNum) -> new Event(
                rs.getLong("id"),
                rs.getString("message")
            )
        );
    }

    public record Event(long id, String message) {}
}
```

Key points:

- `jdbc` is a `final` field; per-call data (`id`, `message`) stays in method parameters/local variables.
- `RowMapper` extracts data into `record Event` while `ResultSet` is open, and **returns DTOs**, never returning `ResultSet` for a controller to use later.
- `JdbcTemplate` closes `Statement`/`ResultSet` and releases the connection within scope; inside a Spring-managed transaction, it can use the transaction-bound connection.
- Ensure `JdbcTemplate`/`DataSource` is configured before serving requests; do not call setters to mutate template config across active threads.
- A singleton repository **does not mean** all requests share one active physical connection.

### 5.1. Should you call DataSource.getConnection() manually in a Repository?

For regular SQL CRUD, **no**: `JdbcTemplate` already handles resource steps and translates `SQLException` into Spring's exception hierarchy.

If low-level JDBC API access is needed inside a Spring transaction, use `DataSourceUtils.getConnection(dataSource)` and `DataSourceUtils.releaseConnection(con, dataSource)`. This pair knows whether a connection is already bound to the active transaction.

`LowLevelJdbcReader.java` illustrates this inside a Spring application with a configured `DataSource`:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

import org.springframework.jdbc.datasource.DataSourceUtils;

public final class LowLevelJdbcReader {
    private final DataSource dataSource;

    public LowLevelJdbcReader(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public long countEvents() {
        Connection con = DataSourceUtils.getConnection(dataSource);
        try {
            try (PreparedStatement ps = con.prepareStatement(
                    "SELECT COUNT(*) FROM audit_event");
                 ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    throw new SQLException("COUNT did not return a row");
                }
                return rs.getLong(1);
            }
        } catch (SQLException ex) {
            throw new IllegalStateException("Counting events failed", ex);
        } finally {
            DataSourceUtils.releaseConnection(con, dataSource);
        }
    }
}
```

`DataSourceUtils.releaseConnection` does not close a connection held by the transaction manager until the transaction ends; outside a transaction, it releases the connection per DataSource policy. Avoid writing `try (Connection con = dataSource.getConnection())` *inside* a Spring transaction assuming it will naturally join the active transaction; on a standard DataSource, calling the DataSource directly can obtain a different, non-transactional connection.

## 6. @Transactional: Spring Holds Connections per Transaction, Not in Bean Fields

With JDBC and `DataSourceTransactionManager`/`JdbcTransactionManager`, an imperative transaction normally binds resources **to the current thread**. Typical flow:

1. A call passes through the Spring transaction proxy into a `@Transactional` method.
2. The transaction manager prepares the JDBC transaction and manages the DataSource connection for the transaction scope.
3. `JdbcTemplate` operations on the same DataSource in **the same thread and same transaction** acquire the matching connection via `DataSourceUtils`.
4. When the transactional method finishes, Spring commits or rolls back per config and releases the connection.

```text
HTTP request A / thread A                 HTTP request B / thread B
       |                                          |
 Service @Transactional                    Service @Transactional
       |                                          |
  JdbcTemplate A                               JdbcTemplate B
       |                                          |
  DataSourceUtils                              DataSourceUtils
       |                                          |
 Connection bound to tx A                  Connection bound to tx B
       |                                          |
       +-------------- same DataSource/pool ------+
```

If A and B are executing **two independent concurrent transactions**, they must not share one active JDBC Connection. The pool issues handles per borrow within pool limits.

Example:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public final class EventService {
    private final EventRepository eventRepository;

    public EventService(EventRepository eventRepository) {
        this.eventRepository = eventRepository;
    }

    @Transactional
    public void storeTwoEvents(long firstId, long secondId) {
        eventRepository.addEvent(firstId, "first");
        eventRepository.addEvent(secondId, "second");
        // Both statements join the same transaction when tx/JdbcTemplate are configured properly.
    }
}
```

Repository/service beans can all be singletons: each call's transaction is managed by Spring, **not** stored in bean fields. If the second statement throws an unchecked exception that escapes the method, Spring's default rollback configuration normally rolls back the entire transaction; rollback rules for checked exceptions require configuration if the same behavior is desired.

**Spring proxy note:** `@Transactional` does not take effect merely because the annotation is present. Transaction management must be enabled and the call must go through the Spring proxy in default proxy mode. Another method on the same bean calling `this.storeTwoEvents(...)` (self-invocation) normally bypasses the proxy, failing to trigger the expected interception.

### 6.1. @Transactional does not make a Connection thread-safe

A transaction can legitimately encompass multiple **sequential** SQL operations on the same connection in the same thread. It does not permit multiple threads to operate concurrently on that connection. SQL statements can also hold locks, use session state, and interfere with each other.

Do not write:

```java
// WRONG: holding a transactional connection on thread A.
Connection con = DataSourceUtils.getConnection(dataSource);
executor.submit(() -> useConnection(con)); // Thread B shares the handle
```

The code above is an **error-illustration snippet**, not a complete method and lacking release logic. Passing `con` to thread B does not pass the Spring transaction context. If thread B needs DB work, pass **input data** (IDs, immutable DTOs) and let B call the repository/`JdbcTemplate` itself; when B needs its own transaction, establish a transaction via Spring at B's execution boundary.

## 7. Async, ExecutorService, and @Async: Thread Boundaries Matter Greatly

With an imperative `PlatformTransactionManager`, transaction resources like a JDBC Connection are typically bound to the thread via `TransactionSynchronizationManager`. When you spawn a new thread inside a `@Transactional` method or use `CompletableFuture.supplyAsync`/`ExecutorService`, the calling thread's transaction **does not automatically propagate** to the worker thread.

| Scenario | What to Do |
| --- | --- |
| Request thread A calls two repository methods sequentially inside one `@Transactional` | Let `JdbcTemplate` participate in A's transaction; do not manually acquire/hold connections. |
| A uses `ExecutorService` to process many IDs | Have each task call the DAO via `JdbcTemplate` and borrow its own appropriate connection; do not pass `Connection`/`ResultSet`. |
| A wants B to share the JDBC transaction A currently has open | Do not assume a thread-bound transaction can be shared by passing objects; redesign work/transaction boundaries. |
| Background task needs its own commit/rollback | Place the transaction boundary on a service invoked through a Spring proxy on the task's thread (or use `TransactionTemplate` on that thread). |
| A already returned query results and B processes asynchronously | Pass materialized DTOs; do not pass a `ResultSet`/stream still tied to a connection. |

Task-splitting implementation example, **two snippets placed in a Spring app with `JdbcTemplate` configured**:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class AsyncCoordinator {
    private final EventRepository repository;

    public AsyncCoordinator(EventRepository repository) {
        this.repository = repository;
    }

    public void storeInBackground(long id, String message) {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        try {
            executor.submit(() -> repository.addEvent(id, message)).get();
        } catch (Exception e) {
            throw new IllegalStateException("Background insert failed", e);
        } finally {
            executor.shutdown();
        }
    }
}
```

This snippet creates a new executor solely to illustrate **not passing a Connection across threads**; production apps should use a Spring-managed executor or shared task pool rather than creating/shutting down an executor per request. Calling `get()` in the example waits for completion so external behavior remains synchronous; if true async is needed, design an API returning `CompletableFuture`/task results with clear error/lifecycle management.

If using `@Async`, configure `@EnableAsync`, place the task in a Spring bean called via proxy (no self-invocation), and remember the caller's transaction does not travel with the task thread. If the async task needs a transaction, put `@Transactional` at the task's appropriate execution boundary with an active transaction manager. **Never pass a live `Connection`, `PreparedStatement`, `ResultSet`, or `EntityManager` into the task.** This section covers synchronous JDBC; R2DBC/reactive uses a different connection and transaction context mechanism, so do not mechanically apply JDBC ThreadLocal rules.

## 8. Complete Runnable Example: Singleton JdbcTemplate, Two Independent Threads

The Spring Boot 3.3.x, Java 17+, and H2 experiment below proves **the same repository/`JdbcTemplate` bean can be called by multiple threads** without the app holding a `Connection` in a field. Two tasks insert two different IDs and then check the row count.

Create a Spring Boot Gradle (Groovy DSL) project with Spring JDBC and H2. In `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
}
```

File `src/main/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:scoped_connection_demo;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.datasource.hikari.maximum-pool-size=2
spring.main.web-application-type=none
```

File `src/main/java/example/connection/ConnectionSharingDemoApplication.java` (single file holding app and demo beans):

```java
package example.connection;

import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@SpringBootApplication
public class ConnectionSharingDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ConnectionSharingDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(JdbcTemplate jdbc, DemoRepository repository) {
        return args -> {
            jdbc.execute("""
                CREATE TABLE audit_event (
                    id INT PRIMARY KEY,
                    message VARCHAR(100) NOT NULL
                )
                """);

            ExecutorService executor = Executors.newFixedThreadPool(2);
            try {
                List<Callable<Integer>> tasks = List.of(
                    () -> repository.insert(1, "from-A"),
                    () -> repository.insert(2, "from-B")
                );

                List<Future<Integer>> futures = executor.invokeAll(tasks);
                for (Future<Integer> future : futures) {
                    if (future.get() != 1) {
                        throw new IllegalStateException("Insert was not applied");
                    }
                }

                Integer count = jdbc.queryForObject(
                    "SELECT COUNT(*) FROM audit_event", Integer.class);
                System.out.println("rowCount=" + count);
            } finally {
                executor.shutdown();
            }
        };
    }
}

@Repository
class DemoRepository {
    private final JdbcTemplate jdbc;

    DemoRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    int insert(int id, String message) {
        return jdbc.update(
            "INSERT INTO audit_event(id, message) VALUES (?, ?)",
            id, message
        );
    }
}
```

Run from the project directory with Gradle wrapper:

```bash
./gradlew bootRun
```

On Windows PowerShell, use `.\gradlew.bat bootRun`. Prerequisites for running: working Java 17+, Gradle and dependencies downloadable, H2 driver on runtime classpath. In a properly prepared environment, the app prints the line produced by demo code:

```text
rowCount=2
```

Spring Boot/Hikari may print additional startup and shutdown logs. Execution order of the two tasks is not fixed, yet the two IDs differ and `Future.get()` ensures both inserts succeed before counting. The example does not claim each task necessarily used **a different physical connection**: if one task finishes first, the pool can reissue the same physical connection; what matters is that the two tasks never **shared one active Connection handle in a field**.

The app has a singleton `@Repository`, an immutable `JdbcTemplate` field, and per-call independent SQL. This is the standard pattern for HTTP controllers, jobs, and message listeners accessing a repository concurrently across threads.

## 9. Lifecycles, Connection Pools, and Misconceptions

### 9.1. Having a pool does not mean "one Connection usable by all threads"

A Hikari pool configured with `maximumPoolSize=10` can supply up to 10 physical connections concurrently for borrows from that pool, subject to DB limits and runtime conditions. If all 10 connections are active, new borrows must wait; exceeding `connectionTimeout` fails. **Do not store one borrowed connection and hand it to every thread** to "save slots": that destroys ownership boundaries, causes races, and undermines transaction correctness.

### 9.2. Can a Connection be kept in a local variable across multiple helper methods?

Yes, if all operations belong to **one controlled synchronous scope** and the caller manages commit/rollback/close. For example, `transfer(...)` in section 4 passes `Connection` from the main method into `debit(...)` and `credit(...)`. This is completely different from putting a Connection into a singleton field, cache, or async task.

### 9.3. Is replacing a singleton Connection with synchronized okay?

`synchronized` may serialize concurrent execution in a block of Java code, yet all tasks still share one session and transaction state; if other methods use the connection outside the lock, bugs remain. If the lock wraps the entire business flow and manages transactions, you have turned DB access into a serial bottleneck, defeating multi-request service design. The right way is borrowing a connection per transaction/task, using a pool, and designing isolation/locking around business requirements.

### 9.4. How long should a long transaction hold a Connection?

Only during the DB work that needs the transaction; avoid slow HTTP API calls, sleeps, large file I/O, or waiting on background tasks while needlessly holding a transaction and connection. Long transactions increase lock duration and tie up pool slots, causing timeouts for other requests.

### 9.5. What about pooled/cached PreparedStatements?

Some drivers, DBs, or pools have internal **statement caching**. That does not authorize an application to store an open `PreparedStatement` in a singleton field for multiple concurrent requests to mutate parameters on. Let the driver/pool manage caching at the proper layer while the application creates and closes statements within its usage scope.

## 10. Common Operational Errors and How to Investigate

| Symptom | Suspect | How to Fix |
| --- | --- | --- |
| `SQLException: Connection is closed` under concurrent requests | One thread closed a handle another thread still uses; singleton holds connection too long; DB dropped idle session | Inspect where `Connection` is stored/passed; switch to `DataSource`/`JdbcTemplate` and local scopes. |
| Request A rolling back makes request B's data vanish | Shared connection/transaction cross-talk | Remove shared connection fields; inspect transaction boundaries. |
| Intermittently right/wrong with identical SQL | Races on `setAutoCommit`, schema, isolation, PreparedStatement params/cursors | Isolate connections per task and keep every statement/result locally scoped. |
| Hikari timeout "Connection is not available" | Pool exhausted from long-held/leaked connections or slow SQL/transactions | Monitor active/idle/pending, transaction hold times, and resource closing paths. |
| Active connections never drop | Missing `close()` or improper release; connection stored in field/ThreadLocal | Use try-with-resources, `JdbcTemplate`, or `DataSourceUtils.releaseConnection`. |
| `@Transactional` "does not run" on internal calls | Self-invocation bypasses Spring proxy in proxy mode | Invoke via Spring-managed bean, split services, or use `TransactionTemplate`. |
| Async task queries DB and misses caller's changes | Caller's transaction hasn't committed yet; async thread runs its own transaction | Design commit ordering, post-commit events, or intentional separate transactions. |
| Data races persist after removing singleton Connection | Insufficient business transaction isolation/locking | Analyze lost updates, optimistic locking, atomic SQL, isolation, and deadlocks. |

Do not rely solely on stack traces; correlate execution flow, transaction boundaries, connection borrow/return durations, pool limits, and DB behavior. Hikari metrics like active/idle/pending are useful, yet by themselves cannot conclude whether an application logic data race exists.

## 11. Self-Check

**Question 1.** A singleton `@Repository` has a field `private final JdbcTemplate jdbc`. Two concurrent HTTP requests call `jdbc.update`. Do the two requests always use the exact same `Connection`?

**Answer:** No. Same `JdbcTemplate` does not mean same active `Connection`. The template acquires the appropriate connection from the DataSource/transaction context per operation.

**Question 2.** Does changing `private Connection con` to `private final Connection con` make it thread-safe?

**Answer:** No. `final` only prevents reassigning the reference; it does not eliminate races on the connection's mutable state.

**Question 3.** One thread calls `rollback()` while two threads share one connection with `autoCommit=false`. Does it roll back only that thread's changes?

**Answer:** No. The transaction belongs to the connection; changes from both threads in the active transaction may be rolled back.

**Question 4.** When using `DataSourceUtils.getConnection` in Spring, can you write `try (Connection con = ...)` and close it yourself like standalone JDBC?

**Answer:** You should not. Use `DataSourceUtils.releaseConnection(con, dataSource)` so Spring decides when to release it, avoiding breaking a transaction-bound connection.

**Question 5.** Does `@Transactional` on thread A automatically cover statements inside `CompletableFuture.supplyAsync` running on thread B?

**Answer:** Not in the standard thread-bound imperative transaction model. B must establish its own transaction if business logic requires it; pass data, not JDBC handles.

**Question 6.** Does using separate connections eliminate all concurrent update bugs?

**Answer:** Not yet. It eliminates session/handle-sharing bugs, yet separate transactions can still contend over data; isolation/locking/consistency must still be controlled at the DB and business levels.

## 12. Code Review Checklist

- [ ] Singletons/services/repositories have **no** fields of type `Connection`, `Statement`, `ResultSet`, or caches holding them.
- [ ] Shared beans depend on stably configured `DataSource`/`JdbcTemplate` instances.
- [ ] Raw JDBC code uses local variables and try-with-resources, closing statements/result sets/connections in the right order.
- [ ] Code using Spring-managed transactions prefers `JdbcTemplate`, or the `DataSourceUtils.getConnection/releaseConnection` pair.
- [ ] JDBC handles are never passed to `ExecutorService`, `CompletableFuture`, `@Async`, callbacks, or responses after scope ends.
- [ ] `@Transactional` boundaries are invoked through Spring proxies in default mode; neither self-invocation nor thread handoff is expected to preserve transactions automatically.
- [ ] Pools have appropriate limits and metrics; long transactions or holding connections while waiting on non-DB work are avoided.
- [ ] Concurrent queries are still checked for isolation, locking, constraints, and business-level atomicity.

## References

- [Spring Framework — Controlling Database Connections](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html): `DataSource`, `DataSourceUtils`, transaction-bound connections.
- [Spring Framework — JdbcTemplate Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html): confirms `JdbcTemplate` is thread-safe once configured.
- [Spring Framework — Understanding Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html): thread-bound imperative transactions and limits when spawning new threads.
- [Oracle JDBC Coding Tips — JDBC and Multithreading](https://docs.oracle.com/en/database/oracle/oracle-database/26/jjdbc/JDBC-coding-tips.html): recommends using connections as local variables and never sharing across threads.
- [JDK Java SE — java.sql.Connection](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Connection.html): transaction APIs, `autoCommit`, `commit`, `rollback`, `close`.

**Conclusion:** A singleton should hold **the connection provider** or **the data access tool**, not **a borrowed connection**. A Connection belongs to a controlled work/transaction scope, is used sequentially, and is returned on time; Spring and the pool coordinate this lifecycle, yet neither makes a shared JDBC Connection safe for multiple concurrent threads.
