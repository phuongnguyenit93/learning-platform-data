# DataSource Is the Connection Source

> **Core principle:** In JDBC, `javax.sql.DataSource` is the **connection source** (*connection factory*); `java.sql.Connection` is the **object the application obtains to perform work with the database**. Spring typically manages a shared `DataSource` bean, while `Connection` instances are borrowed and released per unit of work or per transaction scope. Do not equate a `DataSource` with a single physical connection.

This lesson explains the `DataSource → Connection` contract, the difference between direct connections and connection pools, how `JdbcTemplate` uses the connection source, and the rules for acquiring and releasing connections in Spring transactions.

## 1. Understanding the Roles of the Two JDBC Interfaces

Two key Java types:

```java
import javax.sql.DataSource;
import java.sql.Connection;
```

`javax.sql.DataSource` belongs to the JDBC standard in Java SE, even when the program uses Spring Framework 6, Spring Boot 3, and other Jakarta libraries. **There is no standard `jakarta.sql.DataSource` type replacing it.**

| Component | Role | Typical Lifecycle |
| --- | --- | --- |
| `DataSource` | Configures/routes to a DB source and provides a `Connection` when requested | Shared application bean; may manage a pool |
| `Connection` | Handle for a JDBC session: creates statements, configures transactions, `commit`/`rollback` | Borrowed per unit of work or transaction, then returned/closed |
| `PreparedStatement` | Sends an SQL statement with bound parameters over a `Connection` | Used for a statement then closed |
| `ResultSet` | Reads result rows returned by a statement | Used while iterating then closed |
| `JdbcTemplate` | Spring JDBC API that uses a `DataSource` to execute SQL and manage many resources | Usually injected as a shared bean |

Execution flow:

```text
Application / Repository / JdbcTemplate
                |
                | requests DB connection
                v
             DataSource
                |
                | getConnection()
                v
             Connection
                |
                +--> PreparedStatement --> SQL --> ResultSet
                |
                +--> commit / rollback if owning transaction
                |
                +--> close / release
                       |
                       +--> with pool: typically returns connection to pool
                       +--> without pool: typically closes physical connection
```

`DataSource` has no `executeQuery` API. To send SQL, the application needs to use a `Connection` and a statement, or use a higher-level layer like `JdbcTemplate` so Spring handles that part.

### The `getConnection()` Contract

```java
Connection connection = dataSource.getConnection();
```

The standard `DataSource.getConnection()` method returns a `Connection` and can throw `SQLException` if the DB is unreachable, the pool is exhausted, or the configuration is wrong. The interface also has a `getConnection(String username, String password)` variant, but in Spring, credentials are normally placed in the `DataSource` configuration rather than passed repeatedly in every DAO.

**What `getConnection()` does not promise:** that each call always creates a new socket or physical database session. It may return a handle representing a connection reused from a pool. Creating, keeping, validating, and releasing connections depends on the implementation.

## 2. Why Do We Need the `DataSource` Abstraction?

Traditional JDBC can use `DriverManager`:

```java
import java.sql.Connection;
import java.sql.DriverManager;

Connection connection = DriverManager.getConnection(
    "jdbc:postgresql://localhost:5432/app",
    "app_user",
    "secret"
);
```

The snippet above only illustrates how to obtain a connection and **does not close resources yet**. Placing URLs, passwords, and `DriverManager.getConnection(...)` throughout DAOs makes the application hard to configure per environment, optimize connection pooling, test, and manage transactions centrally. In practice, never hard-code passwords in source code.

With `DataSource`, the DAO depends only on the interface:

```java
import javax.sql.DataSource;

public final class CustomerDao {
    private final DataSource dataSource;

    public CustomerDao(DataSource dataSource) {
        this.dataSource = dataSource;
    }
}
```

`CustomerDao` receives the connection source via its constructor. Whoever provides the `DataSource` could be the Spring container, an application server/JNDI, or manual program initialization. The DAO does not need to know specifically whether the database uses a HikariCP pool, a direct connection mechanism, or which JDBC driver, as long as the implementation adheres to the JDBC contract.

Benefits:

1. **Separates configuration from business logic:** query code does not contain environment details.
2. **Pool reuse:** multiple requests access the DB through one connection source, avoiding unnecessary new sockets.
3. **Spring transaction integration:** the transaction manager can identify which `DataSource` supplies the connection for a JDBC transaction.
4. **Environment-based substitution:** the same DAO receives a data source for H2 in tests, PostgreSQL in staging, or production without modifying logic.
5. **Improved control:** centralizes connection limits, timeouts, metrics, logging, and lifecycle management.

**`DataSource` is only an abstraction.** Pooling, transaction-awareness, multi-DB routing, or monitoring are all handled by the corresponding implementations, proxies, or infrastructure components.

## 3. Direct Connections vs. Connection Pools

### 3.1. Non-Pooled DataSource

Spring's `DriverManagerDataSource` and `SimpleDriverDataSource` provide connections through the driver without a connection pool. With this style, each borrow typically creates a new physical connection; `close()` closes that connection. They are convenient for small examples or tests, but are not a good default choice for services handling many requests because establishing a DB connection consumes time and resources.

### 3.2. Pooled DataSource

With `spring-boot-starter-jdbc`, HikariCP is normally brought into the dependency graph and prioritized by Spring Boot as the pool if there is no custom configuration. The actual object may be a `HikariDataSource`, but the DAO should depend on the `DataSource` type.

A pool manages **multiple physical connections**. When code calls `getConnection()`, the pool lends out a handle. When code calls `close()` on the handle, the pool typically reclaims the handle so the physical connection can be used for another task.

```text
  Spring context
      |
      v
DataSource (pool)
      |
      +--> Connection 1 ----> request A uses ---> close() ---> pool
      |
      +--> Connection 2 ----> request B uses ---> close() ---> pool
      |
      +--> Connection 3 ----> request C uses ---> close() ---> pool
      |
      +--> Request D waits if no connection is available
```

**Why is `close()` still mandatory with a pool?** Because `close()` means returning ownership of the handle. If code does not return it, the pool can be exhausted and new requests will block or fail with a timeout. Calling `Connection.close()` on a pooled handle does not necessarily close the physical connection.

Do not store a `Connection` as a shared field in a singleton `@Repository` and share it across multiple threads. A connection carries its own state such as `autoCommit`, isolation, transaction, and session, and should not be shared concurrently across requests. `DataSource` is typically shared; `Connection` is managed per unit of work/transaction.

| Event | `DataSource` | `Connection` |
| --- | --- | --- |
| Application startup | Bean is configured; pool may initialize connections eagerly or on demand | A connection is not necessarily borrowed by the application yet |
| Query processing | Issues or lends a handle | Executes SQL via statements |
| Query completion | Continues serving other work | Returned to pool or closed depending on implementation |
| Shutdown | Container closes pool per bean lifecycle | No resources left borrowed indefinitely |

## 4. Plain JDBC: Obtaining, Using, and Closing a Connection Properly

The following snippet is a Java 17+ class compilable with the JDK. It is a library component that requires a `DataSource` provided at runtime and a `notes(id, title)` table in the database; **it is not a standalone program with `main`**.

**`NoteReader.java`:**

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Optional;
import javax.sql.DataSource;

public final class NoteReader {
    private final DataSource dataSource;

    public NoteReader(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public Optional<String> findTitle(long id) throws SQLException {
        String sql = "SELECT title FROM notes WHERE id = ?";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, id);

            try (ResultSet result = statement.executeQuery()) {
                return result.next()
                    ? Optional.ofNullable(result.getString("title"))
                    : Optional.empty();
            }
        }
    }
}
```

Compile check command:

```bash
javac --release 17 NoteReader.java
```

Spring is not needed on the classpath to compile this file because `DataSource` and `Connection` belong to the JDK. However, actually calling `findTitle` requires a driver/pool, a DB, and a provided `DataSource` instance.

Analysis:

- `dataSource.getConnection()` borrows a connection. It may wait on the pool or access the DB and throw `SQLException`.
- `PreparedStatement` uses `?` and `statement.setLong(1, id)` to bind parameters instead of concatenating values into the SQL string.
- `try-with-resources` ensures `ResultSet`, `PreparedStatement`, and then `Connection` are closed even if an exception or early `return` occurs.
- If it is a pool, `close()` typically returns the connection to the pool. If non-pooled, it typically closes the physical connection.
- This is **plain JDBC outside a Spring-managed transaction**. When raw JDBC needs to participate in a Spring transaction, see `DataSourceUtils` in Section 7.

## 5. Spring Boot Can Auto-Configure DataSource

The following example uses **Java 17+, Spring Boot 3.3+, and in-memory H2** so it can actually run without setting up PostgreSQL. Create a standard Spring Boot Gradle application with Boot's plugin and dependency management. In `build.gradle`, add:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
}
```

This is only an additional `dependencies` block for an already set up Spring Boot project, not a complete `build.gradle` file.

**`src/main/resources/application.yml`:**

```yaml
spring:
  datasource:
    url: "jdbc:h2:mem:datasource_demo;DB_CLOSE_DELAY=-1"
    driver-class-name: org.h2.Driver
    username: sa
    password: ""
    hikari:
      maximum-pool-size: 5
```

**`src/main/java/example/DataSourceDemoApplication.java`:**

```java
package example;

import java.sql.Connection;
import javax.sql.DataSource;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootApplication
public class DataSourceDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DataSourceDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(DataSource dataSource, JdbcTemplate jdbc) {
        return args -> {
            jdbc.execute("""
                CREATE TABLE notes (
                    id BIGINT PRIMARY KEY,
                    title VARCHAR(100) NOT NULL
                )
                """);
            jdbc.update(
                "INSERT INTO notes (id, title) VALUES (?, ?)",
                1L, "Learn DataSource"
            );

            Integer count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM notes", Integer.class
            );
            System.out.println("Rows = " + count);

            try (Connection connection = dataSource.getConnection()) {
                System.out.println(
                    "Connection valid = " + connection.isValid(2)
                );
            }
        };
    }
}
```

Run from the project:

```bash
./gradlew bootRun
```

On Windows, use `gradlew.bat bootRun`. If the in-memory database is fresh and has no other schema initializer, alongside Spring/Hikari logs, the program itself prints:

```text
Rows = 1
Connection valid = true
```

**Why?** Spring Boot reads `spring.datasource.*`, uses H2 and HikariCP on the classpath to create a `DataSource` bean per auto-configuration conditions. The `JdbcTemplate` bean is configured with the same data source. `CommandLineRunner` runs after the context starts; `JdbcTemplate` sequentially creates the table, inserts a row, and queries the row count. The `dataSource.getConnection()` call at the end acquires a connection handle; `isValid(2)` checks the connection for up to two seconds, and then `try-with-resources` returns the handle.

If you define a custom `@Bean DataSource`, Spring Boot's auto-configuration rules may back off in favor of the custom bean. In plain Spring Framework, a `DataSource` does not appear automatically just by adding Spring Core: you must define the bean or configure an appropriate provider.

In a production environment, replace the H2 URL/driver with a real database and use credentials from the environment or a secret manager; the demo result does not prove every DB is ready.

## 6. How Does JdbcTemplate Use DataSource?

In Spring JDBC, the commonly recommended approach is to inject `JdbcTemplate`, letting it automatically manage connections, statements, result sets, and translate many `SQLException` instances into subclasses of `DataAccessException`.

Example in the same project with the `notes` table:

**`NoteRepository.java`:**

```java
package example;

import java.util.List;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class NoteRepository {
    private final JdbcTemplate jdbc;

    public NoteRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<String> findTitles() {
        return jdbc.query(
            "SELECT title FROM notes ORDER BY id",
            (rs, rowNum) -> rs.getString("title")
        );
    }

    public int rename(long id, String title) {
        return jdbc.update(
            "UPDATE notes SET title = ? WHERE id = ?",
            title, id
        );
    }
}
```

This is a component of a Spring application with a configured `JdbcTemplate`, without its own `main`. Underneath, `JdbcTemplate` still obtains connections from `DataSource`:

```text
NoteRepository
     |
     v
JdbcTemplate --> DataSourceUtils --> DataSource --> Connection
     |
     +--> SQL, ResultSet, RowMapper, cleanup resources
```

Manual instantiation is also possible when a `dataSource` variable is already available:

```java
JdbcTemplate jdbc = new JdbcTemplate(dataSource);
```

This is a code fragment inside a method/constructor that has a `dataSource` variable; the Spring container usually creates and injects the bean automatically when properly configured.

**Key takeaway:** the fact that your code does not directly call `getConnection()` does not mean `JdbcTemplate` bypasses `DataSource`. Spring performs the necessary calls underneath, helping query code avoid resource-closing bugs.

## 7. Spring Transactions: DataSource Is the Provider, Connection Is the Transactional Resource

A JDBC transaction operates on a `Connection`. When using `DataSourceTransactionManager` or `JdbcTransactionManager`, Spring obtains a connection from the right `DataSource` and can bind it to the thread processing the transaction.

```text
Call into @Transactional service via Spring proxy
                       |
            start JDBC transaction
                       |
             DataSource -> Connection
                       |
      JdbcTemplate.update(...) uses bound Connection
      JdbcTemplate.update(...) uses bound Connection
                       |
         success -> commit
         error requiring rollback -> rollback
                       |
             unbind / release Connection
```

Service example:

**`NoteWriteService.java`:**

```java
package example;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class NoteWriteService {
    private final JdbcTemplate jdbc;

    public NoteWriteService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void addPair(long firstId, long secondId) {
        jdbc.update(
            "INSERT INTO notes (id, title) VALUES (?, ?)",
            firstId, "First"
        );
        jdbc.update(
            "INSERT INTO notes (id, title) VALUES (?, ?)",
            secondId, "Second"
        );
    }
}
```

When the method is called **through a Spring proxy**, the transaction manager is properly configured for the same `DataSource`, and there is no special propagation change, both `jdbc.update` calls participate in a shared transaction. If the second statement violates the primary key and throws a runtime exception, Spring rolls back the first statement as well under the default rollback rule.

This is code to integrate into an application with transactions configured, not a standalone program with stdout. Calling `this.addPair(...)` internally from the same bean under the typical AOP proxy model can bypass transaction advice; in that case, check the call path rather than blaming `DataSource`.

### 7.1. Why Can Raw `DataSource.getConnection()` Be Wrong Inside `@Transactional`?

Inside a Spring transaction, if you use a normal data source/pool and call:

```java
Connection c = dataSource.getConnection();
```

You **must not assume** the returned handle is the connection bound to the transaction. For raw JDBC to participate properly in the transaction, Spring provides `DataSourceUtils.getConnection(dataSource)` and `DataSourceUtils.releaseConnection(connection, dataSource)`. `JdbcTemplate` already uses an equivalent mechanism internally.

**`TransactionalNoteCount.java`:**

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;
import org.springframework.jdbc.datasource.DataSourceUtils;

public final class TransactionalNoteCount {
    private final DataSource dataSource;

    public TransactionalNoteCount(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public long count() throws SQLException {
        Connection connection = DataSourceUtils.getConnection(dataSource);
        try {
            try (PreparedStatement statement =
                     connection.prepareStatement("SELECT COUNT(*) FROM notes");
                 ResultSet result = statement.executeQuery()) {
                result.next();
                return result.getLong(1);
            }
        } finally {
            DataSourceUtils.releaseConnection(connection, dataSource);
        }
    }
}
```

This is a Java 17+ class requiring the Spring JDBC library and a `DataSource` provided at runtime. `DataSourceUtils.getConnection` retrieves the transaction-bound connection when present, or acquires a new connection when no transaction exists. `releaseConnection` decides when the handle can actually be returned/closed. **Do not use `try (Connection c = DataSourceUtils.getConnection(...))` to close a Spring-managed connection yourself;** use Spring's get/release pair as shown above.

Spring also provides `TransactionAwareDataSourceProxy` for legacy code forced to call the standard `DataSource.getConnection()` API while needing to join a Spring transaction. For new code, `JdbcTemplate` or `DataSourceUtils` is usually easier to control. `LazyConnectionDataSourceProxy` serves a different purpose: delaying borrowing a physical connection until a statement is actually needed under the right configuration.

### 7.2. Transaction Boundaries to Remember

- `@Transactional` does not mean every `Connection` in the JVM belongs to the same transaction. A transaction manager manages **only the `DataSource` it is configured with**.
- Multiple `DataSource` instances pointing to different DBs do not automatically get an atomic distributed transaction from a single annotation; proper orchestration/distributed transaction design is required.
- A thread-bound transaction does not automatically transfer to a new thread in `CompletableFuture`, `new Thread`, or `@Async`.
- Do not manually call `commit()`, `rollback()`, or modify `autoCommit` on a handle owned by a Spring transaction manager.
- `JdbcTransactionManager` is a JDBC transaction manager variant that adds commit/rollback exception translation; `DataSourceTransactionManager` also manages JDBC transactions for a single `DataSource`.

## 8. Pool Configuration: Do Not Hold Connections Longer Than Necessary

If a pool has a maximum of five connections and five tasks hold them simultaneously, the sixth request must wait (or fail on timeout). Increasing the pool size without analysis can overload the DB, especially when multiple application replicas exist.

Example HikariCP configuration in Spring Boot, using a password from the environment:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://db.example.internal:5432/app
    username: app_user
    password: "${DB_PASSWORD}"
    hikari:
      maximum-pool-size: 10
      connection-timeout: 30000
```

This is a configuration example requiring the corresponding PostgreSQL driver and DB; `db.example.internal` is just an illustrative hostname. `maximum-pool-size` limits the pool's connection count, and `connection-timeout` is the wait time to borrow a connection in milliseconds (30,000 = 30 seconds). Pool timeout differs from network connection timeout, SQL statement timeout, and transaction timeout.

Important habits:

1. **Close or release handles properly.** Standalone JDBC: `try-with-resources`; raw JDBC in a Spring transaction: `DataSourceUtils.releaseConnection`; `JdbcTemplate` manages this automatically.
2. **Avoid connection leaks.** If an exception occurs before `close()`, the pool may keep the handle marked as borrowed.
3. **Minimize connection hold time.** Do not wait on slow network APIs or user input while a transaction still holds a connection unless required by business rules.
4. **Calculate system-wide capacity.** Multiple replicas × pool max equals total potential connection demand; account for the DB server's connection limit.
5. **Monitor:** active/idle/pending counts, borrow wait time, timeouts, query time, and lock contention; do not assume every latency issue is due to insufficient pool size.
6. **Manage shutdown:** let the Spring container close the pool bean when the application stops. `DataSource` is an interface without a standard `close()` method; do not close the entire pool after each query.
7. **Do not rely on leftover connection state.** `autoCommit`, isolation, read-only, schema, or session settings are state that the framework/pool must control; code should not trust changes from a previous borrow.

Example of a *connection leak* caused by omitting `finally`:

```java
Connection c = dataSource.getConnection();
runSomeSql(c);       // If an exception occurs, c.close() may not be called
c.close();
```

`runSomeSql` here represents an existing business function, **not a standard Java method**. With standalone JDBC, use:

```java
try (Connection c = dataSource.getConnection()) {
    runSomeSql(c);
}
```

Keep in mind the separate rule for Spring transactions in Section 7. Do not rely on the garbage collector to reclaim connections in time.

## 9. Multiple DataSources: Right Source and Right Transaction Manager

An application might have one data source for a transactional DB and another data source for a reporting DB. Each bean still satisfies the `DataSource` interface, but they provide connections to different addresses.

Example of a component injected with a bean named `reportingDataSource`:

```java
import javax.sql.DataSource;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Repository;

@Repository
public final class ReportConnectionProvider {
    private final DataSource reportingDataSource;

    public ReportConnectionProvider(
        @Qualifier("reportingDataSource") DataSource reportingDataSource
    ) {
        this.reportingDataSource = reportingDataSource;
    }
}
```

This illustrative class requires a Spring context that **already defines a `reportingDataSource` bean** and does not configure the DB itself. When multiple beans exist, use `@Qualifier`, `@Primary`, and the corresponding transaction manager to avoid querying the wrong DB or applying the wrong transaction.

JPA/Hibernate is also typically configured on top of a corresponding data source, but `EntityManager` and `Connection` are different abstraction layers. Having a `DataSource` does not automatically turn it into a JPA persistence context.

## 10. Testing and Diagnosing at the Right Layer

Do not just test that the `DataSource` bean exists. The bean can initialize successfully while the DB cannot yet serve queries; some implementations defer actual connecting.

- **Wiring:** verify that `JdbcTemplate`/DAO receives the expected configured `DataSource`.
- **Connectivity:** acquire and release a `Connection`, call `isValid(timeout)` if the driver supports it, or run a small query.
- **Resource:** across multiple query rounds, active connections do not grow indefinitely and handles are returned to the pool.
- **Transaction:** with a real integration test, trigger a failure after a successful update and confirm proper rollback; use the same transaction manager and data source.
- **Multiple databases:** verify bean names/`@Qualifier` and transaction managers route properly.
- **Timeout:** distinguish a failure to borrow a connection from the pool from a failure to connect to the DB or a statement execution error.

Connectivity check inside a method with an injected `dataSource`:

```java
try (Connection connection = dataSource.getConnection()) {
    if (!connection.isValid(2)) {
        throw new IllegalStateException("Connection is not valid");
    }
}
```

This check confirms the connection appears valid at the time of inspection; it does not fully verify table write permissions, migrations, schema, or the correctness of business SQL.

### Common Misconceptions

| Misconception | Accurate Understanding |
| --- | --- |
| "DataSource itself is a connection." | `DataSource` is the provider; `Connection` is the borrowed handle. |
| "One DataSource bean means only one physical connection." | A pool can manage multiple connections concurrently. |
| "The pool will reclaim the connection automatically so close is unnecessary." | Code must still close/release handles properly. |
| "Every `getConnection()` call opens a new TCP connection." | A pool can reuse physical connections. |
| "`JdbcTemplate` does not need a DataSource because code doesn't call getConnection." | `JdbcTemplate` accesses the DB through `DataSource` underneath. |
| "`@Transactional` guarantees all JDBC calls automatically share a transaction." | Must use the right transaction manager and transaction-aware connection lookup. |
| "Just increase pool size whenever the database is slow." | Check leaks, slow queries, locks, timeouts, and DB limits first. |

## 11. Self-Check Questions

**Question 1.** Why should a singleton `@Repository` hold a `DataSource` or `JdbcTemplate` instead of holding a `Connection` as a field?

**Answer:** `DataSource`/`JdbcTemplate` are designed to be reused, whereas `Connection` carries transaction state and has a short borrow/return lifecycle. Holding a shared connection can cause invalid concurrent access, stale handles, or leaks.

**Question 2.** Does `Connection.close()` from HikariCP always close the socket to the DB?

**Answer:** No. Typically it releases the logical handle so the pool can reuse the physical connection; the application is still required to close/release the handle.

**Question 3.** If a `@Transactional` service uses `JdbcTemplate`, where is the connection selected from?

**Answer:** From the `DataSource` configured for `JdbcTemplate`/the transaction manager. `JdbcTemplate` obtains the connection via Spring's transaction-aware mechanism to use the transaction-bound connection when appropriate.

**Question 4.** How should a plain JDBC class not participating in a Spring transaction close resources?

**Answer:** Use `try-with-resources` for `Connection`, `PreparedStatement`, and `ResultSet` to ensure they are released even when an exception occurs.

**Question 5.** Why call `DataSourceUtils.releaseConnection` when using `DataSourceUtils.getConnection`?

**Answer:** Spring needs to know whether that connection is being held for an active transaction; calling `close()` directly does not fully follow the transaction-aware contract.

## 12. References

- [Java SE 21 — `javax.sql.DataSource`](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/javax/sql/DataSource.html): `Connection` provider contract, direct/pooled implementations.
- [Java SE 21 — `java.sql.Connection`](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Connection.html): statement, transaction, and `close` APIs.
- [Spring Framework — Controlling Database Connections](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html): `DataSource`, `DataSourceUtils`, transaction managers, and proxies.
- [Spring Framework — JDBC Core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): `JdbcTemplate` and JDBC resource management.
- [Spring Boot — SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html): auto-configuring `DataSource`, connection pools, HikariCP.

**Remember:** `DataSource` is **where you ask for a Connection**, while `Connection` is **the resource you use and then release**. In Spring JDBC, let `JdbcTemplate` and the transaction infrastructure manage borrowing/returning along proper transaction boundaries; when writing plain JDBC, close connections yourself with `try-with-resources`.