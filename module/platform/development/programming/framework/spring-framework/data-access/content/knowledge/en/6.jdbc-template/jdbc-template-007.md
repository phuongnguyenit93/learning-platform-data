# ConnectionCallback for Scenarios Requiring Low-Level JDBC Access

## 1. When Do You Need ConnectionCallback?

With Spring JDBC, most data operations should use built-in **JdbcTemplate** methods such as query, queryForObject, update, and batchUpdate. These methods handle acquiring connections, closing JDBC resources, binding parameters, iterating ResultSets, and translating SQL errors, leaving services and repositories free from manual resource management.

However, some scenarios require using **java.sql.Connection** directly: reading DatabaseMetaData; creating SQL Arrays/Structs; calling vendor-specific APIs; or executing a specialized sequence of JDBC operations on the same Connection that convenience methods do not express cleanly. **ConnectionCallback<T>** is JdbcTemplate's extension point for this. Spring supplies the callback with a Connection and lets it return a fully processed result T.

After this lesson, you should be able to answer:

1. How is ConnectionCallback invoked, and who is responsible for acquiring/releasing the Connection?
2. Why can you use PreparedStatement, ResultSet, and DatabaseMetaData inside the callback and still participate in a Spring transaction?
3. Which resources must be closed with try-with-resources, and which operations must never be performed on a Spring-managed Connection?
4. How is SQLException translated into DataAccessException?
5. When do you choose ConnectionCallback instead of RowMapper, ResultSetExtractor, PreparedStatementCallback, or JdbcTemplate.update?
6. Why does running multiple SQL statements inside a single callback not guarantee atomicity if the service has no transaction boundary?

This article uses **Java 21, Spring Boot 3.3.5, and H2** for the runnable example. The scope is synchronous Spring JDBC; reactive/R2DBC manages transaction contexts differently.

## 2. Contract of ConnectionCallback<T>

In package org.springframework.jdbc.core, ConnectionCallback is a functional interface. Conceptually, it has the shape:

~~~java
@FunctionalInterface
interface ConnectionCallback<T> {
    T doInConnection(Connection connection) throws SQLException;
}
~~~

This is a **simplified illustrative signature**, not an interface to define in your project. The real interface belongs to Spring and may also declare DataAccessException; SQLException is allowed to be thrown because the callback is a low-level JDBC entry point.

JdbcTemplate has an execute(ConnectionCallback<T>) overload. For example, reading the database product name via Connection:

~~~java
String productName = jdbcTemplate.execute(
        (ConnectionCallback<String>) connection ->
                connection.getMetaData().getDatabaseProductName());
~~~

This snippet assumes JdbcTemplate jdbcTemplate exists and org.springframework.jdbc.core.ConnectionCallback is imported. An explicit cast **(ConnectionCallback<String>)** helps Java resolve the execute overload unambiguously because JdbcTemplate also has overloads taking Statement callbacks.

Spring's execute method is designed to:

- Acquire a Connection via Spring JDBC, reusing the Connection bound to the current transaction if the DataSource/transaction manager matches.
- Invoke the callback with that Connection; JdbcTemplate typically wraps the Connection in a proxy that prevents direct closing and prepares Statements per template configuration.
- Allow the callback to read metadata, create PreparedStatements, process ResultSets, and return materialized objects or collections.
- Catch SQLException escaping the callback and translate it into the **org.springframework.dao.DataAccessException** hierarchy (unchecked).
- Release the Connection when the callback finishes, without prematurely committing/rolling back a service-managed transaction.

Thus, this API provides Connection-level control while preserving Spring's resource management contract.

## 3. Resource Flow During Execution

~~~text
Application / Controller
    |
    v
Service @Transactional
    |
    v
Repository
    |
    v
JdbcTemplate.execute(ConnectionCallback<T>)
    |
    +-- DataSourceUtils / Spring JDBC acquires appropriate Connection
    |     +-- Active transaction on same DataSource: bound Connection
    |     +-- No transaction: borrow a connection for this execution
    |
    +-- callback runs with Connection
    |     +-- getMetaData()
    |     +-- prepareStatement(...), bind parameters
    |     +-- executeQuery() / executeUpdate()
    |     +-- read ResultSet / generated keys
    |     +-- close ResultSet, PreparedStatement
    |     +-- return DTO / scalar T
    |
    +-- JdbcTemplate translates SQLException into DataAccessException
    +-- Spring releases Connection
    |
    v
Service receives T
    |
    +-- transaction ends -> commit or rollback
    |
    v
Caller reads T with no open Connection needed
~~~

**Who owns what?** Spring is responsible for borrowing, transaction-binding, and releasing the **Connection**. The callback is responsible for closing **Statement, PreparedStatement, ResultSet**, and specialized resources it explicitly creates. Never return a Connection, ResultSet, or Stream backed by an open ResultSet from the callback; return fully read Java data.

**A note on transactions:** A Spring-managed JDBC Connection inside a callback does not mean the callback itself opens a business transaction. Without @Transactional and with pool autoCommit=true, each SQL command may commit individually. To make multiple operations a single commit/rollback unit, place the transaction at the service boundary.

## 4. Runnable Example: Recording an Audit Event, Fetching ID and Metadata

Problem: an audit_events table stores id, category, and message. One repository method must INSERT an event, read the generated key, query COUNT(*) for that category, and fetch the database name, all inside one ConnectionCallback. Then the service is called twice: once succeeding, and once deliberately throwing an exception to verify rollback.

### 4.1. Structure and Gradle Configuration

~~~text
connection-callback-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/example/callback/
    │   ├── CallbackApplication.java
    │   ├── SaveInfo.java
    │   ├── AuditRepository.java
    │   └── AuditService.java
    └── resources/
        ├── application.properties
        └── schema.sql
~~~

File settings.gradle:

~~~groovy
rootProject.name = 'connection-callback-demo'
~~~

File build.gradle:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
}
~~~

File src/main/resources/application.properties:

~~~properties
spring.main.web-application-type=none
spring.main.banner-mode=off
spring.datasource.url=jdbc:h2:mem:callbackdemo;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
logging.level.root=ERROR
~~~

File src/main/resources/schema.sql:

~~~sql
CREATE TABLE audit_events (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    category VARCHAR(32) NOT NULL,
    message VARCHAR(200) NOT NULL
);
~~~

Spring Boot auto-configures a Hikari DataSource, JdbcTemplate, and JDBC transaction manager when the JDBC starter is present. H2 runs in memory and starts fresh for each process launch.

### 4.2. Result Record

File src/main/java/example/callback/SaveInfo.java:

~~~java
package example.callback;

public record SaveInfo(long id, int countByCategory, String database) {
}
~~~

SaveInfo holds materialized results: long, int, and String. It retains no JDBC handle or lazy object, so callers can read it after the callback finishes.

### 4.3. Repository Using ConnectionCallback

File src/main/java/example/callback/AuditRepository.java:

~~~java
package example.callback;

import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;

import org.springframework.jdbc.core.ConnectionCallback;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class AuditRepository {
    private final JdbcTemplate jdbc;

    public AuditRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public SaveInfo insertAndInspect(String category, String message) {
        return jdbc.execute((ConnectionCallback<SaveInfo>) connection -> {
            String database = connection.getMetaData()
                    .getDatabaseProductName();

            long id;
            try (PreparedStatement insert = connection.prepareStatement(
                    "INSERT INTO audit_events(category, message) VALUES (?, ?)",
                    Statement.RETURN_GENERATED_KEYS)) {

                insert.setString(1, category);
                insert.setString(2, message);

                if (insert.executeUpdate() != 1) {
                    throw new SQLException("Failed to insert one event");
                }

                try (ResultSet keys = insert.getGeneratedKeys()) {
                    if (!keys.next()) {
                        throw new SQLException("Database did not return a generated key");
                    }
                    id = keys.getLong(1);
                }
            }

            int count;
            try (PreparedStatement query = connection.prepareStatement(
                    "SELECT COUNT(*) FROM audit_events WHERE category = ?")) {

                query.setString(1, category);

                try (ResultSet rows = query.executeQuery()) {
                    if (!rows.next()) {
                        throw new SQLException("COUNT returned no result");
                    }
                    count = rows.getInt(1);
                }
            }

            return new SaveInfo(id, count, database);
        });
    }

    public int countCategory(String category) {
        Integer count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM audit_events WHERE category = ?",
                Integer.class,
                category);
        return count;
    }
}
~~~

Explanation:

1. **getMetaData():** reads DatabaseMetaData from the exact Connection supplied by Spring; in H2 the product name is H2.
2. **prepareStatement:** uses placeholders and setString to bind values, never concatenating input data into SQL.
3. **RETURN_GENERATED_KEYS:** the driver returns the database-generated key. Read the key ResultSet before closing the PreparedStatement. Key retrieval depends on driver/database support; this example suits H2.
4. **SELECT COUNT(*) on the same Connection:** within an active transaction, the query can observe the earlier uncommitted INSERT of the same transaction.
5. **try-with-resources:** guarantees ResultSet and PreparedStatement are closed even if a SQLException occurs. **Never** put Connection inside try-with-resources.
6. **SaveInfo:** is a result independent of the Connection once the callback returns.
7. **countCategory:** because only a scalar value is needed, queryForObject is simpler than writing a ConnectionCallback manually. A real application normally uses update(..., KeyHolder) if it only needs a generated key, instead of dropping to low-level APIs.

### 4.4. Service Wrapping the Callback in a Transaction

File src/main/java/example/callback/AuditService.java:

~~~java
package example.callback;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AuditService {
    private final AuditRepository repository;

    public AuditService(AuditRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public SaveInfo save(String category, String message) {
        return repository.insertAndInspect(category, message);
    }

    @Transactional
    public void saveThenRollback(String category, String message) {
        repository.insertAndInspect(category, message);
        throw new IllegalStateException("Rollback requested");
    }
}
~~~

The service defines the transaction boundary. When callers invoke the service bean through a Spring proxy, the transaction manager binds the matching Connection. JdbcTemplate uses that Connection; the transaction commits when save finishes, or rolls back when saveThenRollback throws IllegalStateException out of the method. Never call connection.commit() or connection.rollback() inside the callback.

### 4.5. Running the Application and Verifying

File src/main/java/example/callback/CallbackApplication.java:

~~~java
package example.callback;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class CallbackApplication {
    public static void main(String[] args) {
        SpringApplication.run(CallbackApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(AuditService service, AuditRepository repo) {
        return args -> {
            SaveInfo saved = service.save("INFO", "Created successfully");

            System.out.printf(
                    "Saved id=%d, INFO count=%d, DB=%s%n",
                    saved.id(),
                    saved.countByCategory(),
                    saved.database());

            try {
                service.saveThenRollback("ERROR", "Must not persist");
            } catch (IllegalStateException expected) {
                System.out.println("Rolled back failing request");
            }

            System.out.printf(
                    "After rollback: INFO=%d, ERROR=%d%n",
                    repo.countCategory("INFO"),
                    repo.countCategory("ERROR"));
        };
    }
}
~~~

Run from the project directory with **JDK 21 and a Java 21-compatible Gradle** (e.g., Gradle 8.5):

~~~bash
gradle bootRun
~~~

Three lines printed by the program on a fresh H2 run:

~~~text
Saved id=1, INFO count=1, DB=H2
Rolled back failing request
After rollback: INFO=1, ERROR=0
~~~

The first save commits, so the INFO record remains. saveThenRollback executes the ERROR INSERT via ConnectionCallback, yet the RuntimeException escaping the service causes Spring to roll back the transaction, leaving ERROR=0 afterward. Identity sequences may still increment when an INSERT rolls back, so never assume IDs are contiguous or reused.

**Why is this a valid verification?** The transaction runs on the service, and the callback uses the Connection acquired by the template from the right DataSource. If the callback used a separate raw Connection with autoCommit=true, the INSERT could commit independently and fail to roll back with the service.

## 5. Managing Connection Properly

### 5.1. Never Close the Connection Yourself

The following snippet is an **anti-example**, assuming the class has a JdbcTemplate jdbc field:

~~~java
jdbc.execute((ConnectionCallback<Integer>) connection -> {
    connection.close();  // Wrong: Connection is owned by Spring.
    return 1;
});
~~~

In current implementations, JdbcTemplate often passes a proxy suppressing close on the Connection, but do not rely on that detail to call close deliberately. Spring is responsible for releasing the Connection when the callback finishes.

**Correct** example when creating PreparedStatement and ResultSet manually:

~~~java
int total = jdbc.execute((ConnectionCallback<Integer>) connection -> {
    try (PreparedStatement statement = connection.prepareStatement(
            "SELECT COUNT(*) FROM audit_events");
         ResultSet rows = statement.executeQuery()) {
        if (!rows.next()) {
            throw new SQLException("COUNT returned no result");
        }
        return rows.getInt(1);
    }
});
~~~

This snippet belongs inside a method of a class with a JdbcTemplate jdbc field, importing PreparedStatement, ResultSet, SQLException, and ConnectionCallback. If you only want COUNT(*), queryForObject is still cleaner. The point here is distinguishing ownership: close ResultSet/Statement yourself, and let Spring release the Connection.

### 5.2. Never Commit, Rollback, or Toggle autoCommit

The commands below are **anti-examples** on a transaction-manager-owned Connection, not standalone runnable methods:

~~~java
connection.setAutoCommit(true);
connection.commit();
connection.rollback();
connection.close();
~~~

A @Transactional service must let the transaction manager decide commit/rollback. Changing isolation or readOnly inside a callback can also conflict with transaction attributes; configure those properties at the transaction boundary and understand driver capabilities before intervening.

### 5.3. Avoid Returning JDBC Handles Outside

The return value must be Java data independent of JDBC lifecycles. Never return a Connection, ResultSet, Statement, Blob locator, or Stream requiring an open ResultSet. Once execute completes, Spring may have already released resources. Read and materialize DTOs inside the callback.

For large datasets, materializing millions of rows into a List can exhaust memory; use pagination, batching, or streaming processing within the Connection-owning scope with controlled fetch size, timeouts, and cleanup. Remember fetch size is a driver hint, not a guarantee every driver streams identically.

## 6. SQLException, DataAccessException, and Rollback

ConnectionCallback is allowed to throw SQLException without wrapping every operation manually; JdbcTemplate catches and translates it into an appropriate DataAccessException. DataAccessException is an unchecked exception, so escaping a @Transactional boundary triggers rollback by default.

Conversely, if a callback catches an error and **swallows** it:

~~~java
// Anti-example: improper error handling makes callers think it succeeded.
try {
    statement.executeUpdate();
} catch (SQLException ex) {
    return 0;
}
~~~

the transaction interceptor may remain unaware of the business failure and commit partial data. If recovery handling is required, express it accurately via return values/exceptions and manage transaction state intentionally. Distinguish "row not found" (business result) from SQLException (database access failure).

Note that Spring's default rollback applies to RuntimeException/Error escaping the transaction boundary. If other code throws untranslated checked exceptions, check @Transactional rollback rules; do not assume all checked exceptions automatically roll back.

## 7. Comparing Callbacks and APIs

| API | Access level | When to use |
| --- | --- | --- |
| JdbcTemplate.query(..., RowMapper<T>) | One ResultSet row | Map each row to a DTO. |
| JdbcTemplate.query(..., ResultSetExtractor<T>) | Entire ResultSet of a query | Join rows or aggregate results. |
| JdbcTemplate.execute(sql, PreparedStatementCallback<T>) | PreparedStatement | Customize operations on an already-created statement. |
| JdbcTemplate.execute(StatementCallback<T>) | Statement | Customize a plain Statement. |
| JdbcTemplate.execute(CallableStatementCreator, CallableStatementCallback<T>) | CallableStatement | Call stored procedures with IN/OUT parameters. |
| **JdbcTemplate.execute(ConnectionCallback<T>)** | **Connection** | Metadata, SQL array/struct, vendor features, or multiple specialized JDBC statements. |
| DataSourceUtils.getConnection(dataSource) | Connection that must be manually released per rules | When manual JDBC is needed outside a template callback. |

For simple SELECT/UPDATE queries, you **do not need** ConnectionCallback; higher-level APIs require less cleanup code and are easier to test. If only retrieving a generated key, use JdbcTemplate.update with KeyHolder when suitable. ConnectionCallback shines when Connection-level access is genuinely required.

## 8. Low-Level JDBC Scenarios

**Reading DatabaseMetaData.** Use connection.getMetaData() to read product name, driver, table/column info, or JDBC capabilities. Migration/diagnostic tools may need this. Metadata calls can be slow; do not query metadata unnecessarily on every request.

**Creating SQL Array/Struct or using driver-specific APIs.** Connection.createArrayOf(typeName, elements), createStruct, or unwrap may be needed for specialized features. Type-name syntax and support depend on driver/database; java.sql.Array objects must be freed properly per their lifecycle. Never close the physical Connection yourself when using unwrap.

**Multiple statements in one callback.** You can prepare, bind, and run multiple sequential statements on the same Connection. However, the callback does not automatically form a business transaction if @Transactional is missing and the driver uses autoCommit. Choose transaction boundaries by business rules, not code nesting.

**Performance concerns.** The callback holds a Connection while running; slow operations occupy pool slots and increase latency for other requests. Avoid network calls or long file I/O inside callbacks. Cap ResultSets, set reasonable timeouts/fetch sizes, and close resources immediately when done.

**Multiple DataSources.** A JdbcTemplate using DataSource B does not automatically join a transaction manager managing DataSource A, even if both DataSources point to the same database URL. With multiple databases, managers and data-consistency strategies must be configured explicitly.

## 9. Why Not Open a Raw Connection Directly?

In synchronous JDBC transactions, Spring typically holds a ConnectionHolder in thread-bound resource context; JdbcTemplate uses DataSourceUtils to find the Connection bound to the matching DataSource. Conversely, calling DataSource.getConnection() directly on an underlying pool (such as HikariDataSource) may borrow a second Connection and run outside the service's transaction.

The following anti-example is **not a standalone runnable class**; it assumes dataSource is a raw underlying pool and JDBC imports exist:

~~~java
@Transactional
public void unsafeInsert() throws SQLException {
    try (Connection raw = dataSource.getConnection();
         PreparedStatement insert = raw.prepareStatement(
                 "INSERT INTO audit_events(category, message) VALUES (?, ?)")) {
        insert.setString(1, "OUTSIDE");
        insert.setString(2, "Independent connection");
        insert.executeUpdate();
    }
    throw new IllegalStateException("Rollback service");
}
~~~

If the raw Connection has autoCommit=true, the INSERT may commit before the Spring transaction rolls back. **Exception to remember:** TransactionAwareDataSourceProxy is designed by Spring so getConnection() is transaction-aware. Do not generalize that every DataSource.getConnection() implementation bypasses transactions; know the proxy/pool type and which DataSource the transaction manager manages.

If direct JDBC outside JdbcTemplate is unavoidable, the Spring-compatible pattern is DataSourceUtils.getConnection(dataSource) paired with DataSourceUtils.releaseConnection(connection, dataSource) in finally; do not use try-with-resources to close a Connection bound to a Spring transaction.

## 10. Common Mistakes

- **Using ConnectionCallback for every SELECT:** writing unnecessary boilerplate compared to query/RowMapper.
- **Closing the Connection inside a callback:** violates Spring's resource ownership.
- **Forgetting to close Statement/ResultSet:** leaks JDBC resources or holds cursors open too long.
- **Calling commit/rollback manually:** makes the service's transaction unreliable.
- **Catching and swallowing SQLException:** allows the service to commit despite failed operations.
- **Returning ResultSet to callers:** callers may access it after resources are closed or released.
- **Assuming multiple statements in a callback are automatically atomic:** untrue without a transaction.
- **Calling raw DataSource.getConnection() inside a transactional service:** can obtain a Connection outside the transaction.
- **Invoking @Transactional via self-invocation:** in Spring proxy mode, annotations can be bypassed on same-object calls.
- **Passing Connection to @Async or another thread:** synchronous Spring transactions generally do not propagate automatically to new threads.
- **Overusing vendor JDBC APIs without checking the driver:** metadata, generated keys, and SQL types vary by database.
- **Holding callbacks open too long:** exhausts the pool, raising latency and timeouts.

## 11. Exercises and Self-Check

1. Run the example and verify INFO=1 after commit and ERROR=0 after rollback.
2. Try a category exceeding VARCHAR(32) and verify the driver's SQLException is translated by JdbcTemplate into a DataAccessException (subtype depends on translator/driver).
3. Replace SELECT COUNT(*) in the repository with queryForObject and compare readability and the number of resources you must close manually.
4. If the service lacks @Transactional, predict what happens when the first INSERT auto-commits and a subsequent SQL statement fails.
5. Explain why the generatedKey ResultSet must be read before closing PreparedStatement.
6. When should you use ConnectionCallback instead of PreparedStatementCallback?
7. Why should the JDBC Connection inside a callback never be returned to a CompletableFuture or stored in a singleton field?
8. If JdbcTemplate and the transaction manager point to two different DataSources, can you expect a shared rollback?
9. Why does TransactionAwareDataSourceProxy change conclusions about DataSource.getConnection()?
10. Why do callbacks still need materialized DTOs and should not return a Stream still tied to a ResultSet?

**Remember:** ConnectionCallback exposes Connection-level JDBC APIs inside JdbcTemplate's infrastructure. It preserves Spring JDBC's core benefits: selecting a transaction-aware Connection, translating SQLExceptions, and releasing connections. Developers must close Statement/ResultSet properly, avoid interfering with commit/rollback, keep callbacks short-lived, and return Java data with an independent lifecycle.

### References

- Spring JDBC core: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring Transaction Management: https://docs.spring.io/spring-framework/reference/data-access/transaction.html
- JdbcTemplate Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html
- ConnectionCallback Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/ConnectionCallback.html
- DataSourceUtils Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/datasource/DataSourceUtils.html
