# Resource Ownership Rules in JdbcTemplate Callbacks

## 1. Why Must Resource Ownership Be Clearly Defined?

In plain JDBC, developers typically take responsibility for the lifecycle of `Connection`, `Statement`, `PreparedStatement`, and `ResultSet`: acquiring/creating, using, and closing them in `finally` or `try-with-resources`. When moving to Spring Framework's `JdbcTemplate`, part of that responsibility is **transferred to the template**. If a callback still closes resources managed by Spring, it can break the running operation or transaction boundary. Conversely, if a callback creates new resources itself assuming Spring will close everything for it, the application can leak cursors or statements.

A concise rule, which must be understood per API:

> **Whoever creates a resource or is assigned lifecycle management by the API contract is responsible for closing or releasing it.** `JdbcTemplate` normally owns the resources it creates or supplies directly. A callback owns any extra resources it opens itself, unless it hands them over to the template under the contract. A `Stream` return value notably transfers stream-closing responsibility to the caller.

After this lesson, you will be able to:

1. Distinguish resources **temporarily lent by the template to a callback**, resources **opened by the callback itself**, and resources **escaping the call scope**.
2. Correctly use `RowMapper`, `RowCallbackHandler`, `ResultSetExtractor`, `PreparedStatementCreator`, `PreparedStatementSetter`, `PreparedStatementCallback`, `StatementCallback`, and `ConnectionCallback`.
3. Know when you **must not close** `Connection`, `Statement`, and `ResultSet` yourself, and when you **must actively close them** with `try-with-resources`.
4. Understand that Spring releasing a connection inside a transaction does not necessarily mean immediately closing the physical connection.
5. Use `queryForStream` safely without returning a `ResultSet` or a stream taken directly from a JDBC callback after the statement has closed.
6. Run a Java 17 example with Spring JDBC and H2 to verify these contracts, including a transaction rollback.

**Lesson scope:** the main topic is *ownership and resource lifecycle in JdbcTemplate callbacks*. `DataSource` configuration, transaction propagation, and ORM strategies are mentioned only where they affect ownership.

## 2. Three Resource Tiers in the JDBC Flow

```text
DataSource (Spring bean / connection pool)
     │
     ├─ borrow Connection
     │      │
     │      ├─ create Statement / PreparedStatement / CallableStatement
     │      │      │
     │      │      └─ run SQL, obtain ResultSet
     │      │
     │      └─ when done: release connection to the proper owner
     │
     └─ continue serving other calls
```

- **`DataSource`** is usually a shared bean. Closing a borrowed `Connection` differs from closing the `DataSource` itself or the entire pool.
- **`Connection`** represents a JDBC session and transaction state. It may be a pool handle/proxy. Spring may retain the connection until the transaction ends.
- **`Statement` and subclasses** hold JDBC resources associated with SQL execution, potentially with an attached cursor/result set.
- **`ResultSet`** normally depends on an open statement and connection. It is not an independent Java collection usable after the underlying resources close.
- **`Stream<T>` returned by `JdbcTemplate.queryForStream`** is lazy: the stream may hold open JDBC resources and therefore the caller must close the stream after use.

**Do not equate:** "Closing a JDBC handle" and "closing a physical connection" are two different things. With a connection pool, `Connection.close()` usually returns the handle to the pool; with a Spring transaction, the template may simply release the handle and let the transaction manager decide when to return/close the connection. That does not make calling `close()` on a callback-borrowed object valid.

## 3. What Does JdbcTemplate Take Responsibility For?

A common call:

```java
List<String> names = jdbcTemplate.query(
        "SELECT name FROM users ORDER BY id",
        (rs, rowNum) -> rs.getString("name"));
```

In this standard `query` method, responsibilities are split as follows:

1. The user supplies the SQL and how to map one row.
2. `JdbcTemplate` acquires a connection via Spring's transaction-aware infrastructure.
3. `JdbcTemplate` creates a statement, executes the query, and obtains the result set.
4. `JdbcTemplate` iterates the result set, invoking `RowMapper` on each current row.
5. The callback only **reads the needed data** and constructs a Java value (here a `String`).
6. After the call, the template closes `ResultSet`/`Statement` internally, then releases `Connection` per transaction context.
7. If JDBC throws a `SQLException`, the template performs exception translation into the appropriate `DataAccessException` hierarchy. A runtime exception thrown by the callback propagates; with an active transaction, rollback follows transaction manager/interceptor rules.

You **do not** write `rs.close()` or `rs.next()` inside `RowMapper` to "help" with cleanup. The template already owns cursor positioning and resource lifecycles in this overload.

### Defining Ownership Terms

| Concept | Meaning | Right action |
| --- | --- | --- |
| **Owner** | Component responsible for releasing/closing a resource at an API boundary | Perform cleanup in `finally` or `try-with-resources` |
| **Borrower** | Component lent an existing resource inside a callback | Use within callback scope; do not close when the template is owner |
| **Handoff** | Callback creates a resource and returns it to the template per contract | Do not close it before the template uses it; template cleans up after receiving |
| **Escaped resource** | Resource continuing to exist after the API returns | Receiver must manage its lifecycle when the contract returns it; notably `queryForStream` |

Do not apply "no callback ever needs to close anything" mechanically. A callback might open a new statement/result set, file, stream, or socket itself. Those extra resources do not automatically fall under `JdbcTemplate`'s responsibility.

## 4. Ownership Table by Callback Type

Read this table as a practical contract; "Spring" refers to `JdbcTemplate` or the Spring infrastructure managing the specific call.

| API / callback | Resource received | Who owns the received resource? | What must the callback do? |
| --- | --- | --- | --- |
| `RowMapper<T>` | `ResultSet` positioned at one row | Spring | Read columns and return object; no `next()`/`close()` |
| `RowCallbackHandler` | `ResultSet` at one row | Spring | Process the current row; no `next()`/`close()` |
| `ResultSetExtractor<T>` via `query(...)` | `ResultSet` from executed query | Spring | Iterate `next()` itself, extract data; do not close provided result set |
| `PreparedStatementSetter` | Already-created `PreparedStatement` | Spring | Bind parameters, optionally tweak fetch/query options per contract; do not close statement |
| `PreparedStatementCreator` | `Connection` supplied by template; callback returns `PreparedStatement` | Spring owns connection, takes ownership of returned statement | Create valid statement and hand it off; do not close connection/statement before returning |
| `PreparedStatementCallback<T>` via `execute` | Active `PreparedStatement` | Spring owns statement and connection | Run SQL; **close any ResultSets it opens itself** |
| `StatementCallback<T>` via `execute` | Active `Statement` | Spring owns statement and connection | Run SQL; **close any ResultSets it opens itself** |
| `CallableStatementCallback<T>` via `execute` | Active `CallableStatement` | Spring owns callable statement and connection | Run procedure; close ResultSets it opens itself per contract |
| `ConnectionCallback<T>` via `execute` | `Connection` supplied by template | Spring | Do not close connection; **close statements/result sets it creates itself** |
| `queryForStream(...)` | `Stream<T>` returned from the call | Caller owns the stream | Use `try-with-resources` and close stream even if not fully consumed |

**Distinguishing two `ResultSet` cases:**

- When using `jdbc.query(sql, ResultSetExtractor)`, the **template** creates and manages `ResultSet`; the callback merely borrows it.
- When using `jdbc.execute(sql, PreparedStatementCallback)`, the callback itself typically calls `ps.executeQuery()` and receives a `ResultSet`. Spring Javadoc requires **the callback to close any ResultSets it opens**, even though Spring will close the statement passed to the callback. You cannot rely on assuming "closing the statement guarantees all result sets are actually released" in every environment, because statements may be pooled.

## 5. RowMapper: Only Convert a Row into an Object

`RowMapper<T>` looks like:

```java
// Snippet in a DAO with injected JdbcTemplate.
List<UserView> users = jdbcTemplate.query(
        "SELECT id, name FROM users ORDER BY id",
        (rs, rowNum) -> new UserView(
                rs.getLong("id"),
                rs.getString("name")));
```

`UserView` here is an application-defined record or class. Each time the callback runs, `ResultSet` is already positioned on the row to process; `rowNum` is the 0-based row index in the mapped result, not the database `id` column.

**Do not do this:**

```java
// WRONG: illustrative buggy code, do not run.
(rs, rowNum) -> {
    rs.next();             // Skips a row, corrupting the template-controlled loop.
    String name = rs.getString("name");
    rs.close();            // Closes Spring's cursor inside the mapper.
    return name;
}
```

**Do this instead:** read columns of the **current row**, convert to independent Java values, and return. If handling BLOB/CLOB or binary streams, safely materialize the content within the result set's lifetime (respecting memory limits) rather than returning a stream tied to a closed cursor.

`RowMapper` should not execute complex JDBC operations or open extra statements on the active connection: some drivers do not allow multiple active result sets on the same connection or silently close cursors. If additional queries are needed, consider a `JOIN`, batch query, or redesigning data access.

## 6. RowCallbackHandler: Invoked Per Row, Does Not Own Cursor

`RowCallbackHandler.processRow(ResultSet rs)` runs once per row after `JdbcTemplate` calls `rs.next()` and positions the cursor on the current row. Handlers are typically used for controlled accumulation or side effects.

```java
// Snippet inside a method that already has jdbcTemplate.
List<String> names = new ArrayList<>();
jdbcTemplate.query(
        "SELECT name FROM users ORDER BY id",
        (RowCallbackHandler) rs -> names.add(rs.getString("name")));
System.out.println(names);
```

**Wrong:** looping `while (rs.next())` inside the callback while `JdbcTemplate` is also looping. That skips or drops rows. Also never close `rs` inside the handler.

**State note:** a stateful handler can work **for a single `query` invocation**. Never share a single handler instance with mutable fields across multiple threads/requests without concurrency safety. If you simply want one object per row in a list, `RowMapper` is usually simpler.

## 7. ResultSetExtractor: Iterates Manually, Does Not Own Query-Supplied ResultSet

`ResultSetExtractor<T>` fits when you need an aggregated result or want to map multiple rows into a single object.

```java
// Snippet; template creates/closes ResultSet.
Integer total = jdbcTemplate.query(
        "SELECT id FROM users ORDER BY id",
        (ResultSetExtractor<Integer>) rs -> {
            int count = 0;
            while (rs.next()) {
                count++;
            }
            return count;
        });
```

In this overload:

- The callback **must call `rs.next()` itself** to iterate over rows.
- The callback **must not call `rs.close()`**, because the template is the owner.
- The return value is a Java value no longer needing a connection, such as `Integer`, DTO, `List`, or `Map`.
- If a `SQLException` occurs inside the callback, you may let it propagate so the template translates it into `DataAccessException`. Do not swallow errors and return partial results.

**Wrong example:**

```java
// WRONG: returning JDBC ResultSet to the caller after JdbcTemplate.query finishes.
ResultSet escaped = jdbcTemplate.query(
        "SELECT * FROM users",
        (ResultSetExtractor<ResultSet>) rs -> rs);
```

After `query` returns, Spring may already have closed the `ResultSet` and statement; the returned object is no longer independent data. Transform data into objects/collections **inside the callback**. This is also why you should not return an `InputStream` tied to a LOB/cursor without handling stream and backend ownership.

## 8. PreparedStatementSetter and PreparedStatementCreator: Two Different Contracts

### 8.1. PreparedStatementSetter Receives an Existing Statement

```java
// Illustrative snippet; setter does not close ps.
jdbcTemplate.update(
        "UPDATE users SET name = ? WHERE id = ?",
        ps -> {
            ps.setString(1, "Lan");
            ps.setLong(2, 5L);
        });
```

Spring created the statement and will close it after the operation. The callback only sets permitted parameters/properties. Calling `ps.executeUpdate()` inside a setter is a responsibility violation; the template executes afterward, which could run the write twice. Also never call `ps.close()`.

### 8.2. PreparedStatementCreator Creates and Hands Off a Statement

```java
// Snippet: callback creates PreparedStatement and returns it to JdbcTemplate.
// Suitable when specifying statement creation characteristics.
PreparedStatementCreator creator = connection -> {
    PreparedStatement ps = connection.prepareStatement(
            "INSERT INTO users (name) VALUES (?)");
    ps.setString(1, "Mai");
    return ps;
};
int changed = jdbcTemplate.update(creator);
```

Ownership after handoff:

1. Spring supplies `Connection`; the creator does not close the connection.
2. The creator creates `PreparedStatement` and **returns it** to the template. Do not close the statement before returning.
3. After the template executes, the template closes the statement and releases the connection.
4. If the callback opens **auxiliary resources besides the handed-off statement** (files, streams, temporary statements), the callback must still manage them.
5. If an exception occurs **before handoff** and a resource was created but not yet returned to the template, the callback must clean up resources it still owns. Keep creators short and avoid extra resources when possible.

Instead of writing a creator just to bind a couple of parameters, `update(sql, args...)` or `PreparedStatementSetter` is usually clearer.

## 9. StatementCallback and PreparedStatementCallback: Must Close Self-Opened ResultSets

### 9.1. PreparedStatementCallback

```java
// RIGHT: Spring owns ps; callback owns the ResultSet returned by ps.executeQuery.
Integer count = jdbcTemplate.execute(
        "SELECT COUNT(*) FROM users WHERE id >= ?",
        (PreparedStatementCallback<Integer>) ps -> {
            ps.setLong(1, 2L);
            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    return 0;
                }
                return rs.getInt(1);
            }
        });
```

Why is there `try (ResultSet rs = ...)` without `try (PreparedStatement ps = ...)`?

- `ps` was created by the template and passed into the callback: **the template is the owner**.
- `rs` was opened by the callback itself calling `executeQuery()`: **the callback must close it**.
- If SQL execution or data reading throws `SQLException`, `try-with-resources` still closes `rs`; Spring proceeds with statement/connection cleanup and `SQLException` translation.
- Never return `rs` or a `Stream` dependent on `rs` out of the callback.

### 9.2. StatementCallback

```java
// Snippet; assumes users table exists.
Integer count = jdbcTemplate.execute(
        (StatementCallback<Integer>) statement -> {
            try (ResultSet rs = statement.executeQuery(
                    "SELECT COUNT(*) FROM users")) {
                rs.next();
                return rs.getInt(1);
            }
        });
```

With such callbacks, Spring closes `Statement` after the callback, yet any self-opened `ResultSet`s must be closed inside the callback to prevent resource leaks, especially when statements are pooled. Never use "closing a JDBC statement closes its result sets" as an excuse to skip cleanup; pooling details can keep resources alive longer than expected.

### 9.3. CallableStatementCallback

For stored procedures, `CallableStatementCallback<T>` receives a `CallableStatement` from the template. The callback can execute the procedure and read `ResultSet`/output parameters. Any result sets extracted by the callback must be released per the JDBC contract; do not close the callable statement supplied by Spring. For drivers producing multiple consecutive result sets, handle `getMoreResults`/`getUpdateCount` and each result set's lifecycle carefully.

This is an advanced use case; do not introduce stored procedures just to illustrate ownership when simple `query`/`update` suffices.

## 10. ConnectionCallback: Template Owns Connection, Callback Owns What It Creates

`JdbcTemplate.execute(ConnectionCallback<T>)` passes a JDBC `Connection` into the callback. The callback may invoke normal JDBC operations on it, but **does not own closing that connection**.

```java
// RIGHT: do not put connection in try-with-resources.
// Self-created Statement and ResultSet are closed.
Long count = jdbcTemplate.execute((ConnectionCallback<Long>) connection -> {
    try (PreparedStatement ps = connection.prepareStatement(
                 "SELECT COUNT(*) FROM users");
         ResultSet rs = ps.executeQuery()) {
        rs.next();
        return rs.getLong(1);
    }
});
```

Compare with plain JDBC:

```java
// PLAIN JDBC: code calls dataSource.getConnection() itself, so it must
// return/close that connection per the DataSource contract.
try (Connection ownConnection = dataSource.getConnection();
     PreparedStatement ps = ownConnection.prepareStatement(
             "SELECT COUNT(*) FROM users");
     ResultSet rs = ps.executeQuery()) {
    rs.next();
    System.out.println(rs.getLong(1));
}
```

The plain JDBC case above assumes no Spring-managed transaction needs to be joined. If code runs inside a Spring transaction yet opens an independent connection directly, it can run outside the transaction. Use `JdbcTemplate` or `DataSourceUtils` when transaction coordination is needed.

### Operations to Avoid on a Borrowed Connection

- Never call `connection.close()` or keep a reference beyond the callback.
- Never manually `commit()`, `rollback()`, or alter `autoCommit`, which breaks Spring-managed transactions.
- Never alter isolation/readOnly/connection state without understanding pool/transaction impacts; if legitimately changing a JDBC attribute for a task, ensure proper restoration.
- Never pass `Connection` to another thread or store it in a shared mutable field.
- Never return an open `PreparedStatement` or `ResultSet` to the caller after the callback finishes.

Some Spring versions pass a close-suppressing proxy for the connection inside `ConnectionCallback`, but that is a defensive detail. The caller's contract remains **do not close and do not manually manage transactions on a template-supplied connection**.

## 11. Special Case: queryForStream Transfers Responsibility to Caller

Most `JdbcTemplate.query` APIs return already-extracted results when the method finishes. By contrast, `queryForStream(...)` returns a **lazy and closeable `Stream<T>`** that may retain open `ResultSet`, `Statement`, and `Connection` while iterating.

```java
// RIGHT: stream is closed even if the pipeline errors or short-circuits.
try (Stream<String> stream = jdbcTemplate.queryForStream(
        "SELECT name FROM users ORDER BY id",
        (rs, rowNum) -> rs.getString("name"))) {
    stream.limit(10).forEach(System.out::println);
}
```

`try-with-resources` is essential even when:

- You called a terminal operation like `count()`, `findFirst()`, or `forEach()`.
- The pipeline stops after reading only part of the results.
- An exception occurs during mapping/filtering/consuming.
- You did not traverse every element.

**Never assume a terminal operation automatically calls `Stream.close()`**; standard Java Streams do not close themselves just because the pipeline finished. Never create a stream and forget to close it:

```java
// WRONG: missing close on closeable stream.
Stream<String> stream = jdbcTemplate.queryForStream(
        "SELECT name FROM users",
        (rs, rowNum) -> rs.getString("name"));
String first = stream.findFirst().orElse("unknown");
// Without closing the stream, JDBC resources may stay held.
```

**Never return a JDBC stream out of a service without an explicit ownership contract.** If a public API returns `Stream<T>`, callers must know to close it promptly; a lazy stream depends on connections and transactions that may expire. It is usually safer to extract a bounded list or process the entire stream inside the data access layer with `try-with-resources`.

`queryForRowSet` typically returns a `SqlRowSet` abstraction holding data detached from the `ResultSet` (depending on the RowSet implementation and driver capabilities). Do not confuse `SqlRowSet` with a live JDBC `ResultSet`; check the implementation contract before assuming streaming or long-term resource behavior.

## 12. Complete Java 17 Example: Observing All Callback Types

This example uses **Spring Framework 6.2.14**, **H2 2.3.232**, JDK **17+**, and Gradle. The program uses plain Spring Framework only, with no Spring Boot or external database required. `DriverManagerDataSource` is convenient for demos, not a production connection pool.

### 12.1. Project Structure

```text
jdbc-callback-ownership/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/ResourceOwnershipDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'jdbc-callback-ownership'
```

`build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.14'
    implementation 'org.springframework:spring-jdbc:6.2.14'
    runtimeOnly 'com.h2database:h2:2.3.232'
}

application {
    mainClass = 'demo.ResourceOwnershipDemo'
}
```

`src/main/java/demo/ResourceOwnershipDemo.java`:

```java
package demo;

import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Stream;
import javax.sql.DataSource;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.ConnectionCallback;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.PreparedStatementCallback;
import org.springframework.jdbc.core.ResultSetExtractor;
import org.springframework.jdbc.core.RowCallbackHandler;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.support.TransactionTemplate;

public class ResourceOwnershipDemo {

    record Job(long id, String name, boolean completed) {}

    @Configuration
    static class Config {
        @Bean
        DataSource dataSource() {
            return new DriverManagerDataSource(
                    "jdbc:h2:mem:ownership;DB_CLOSE_DELAY=-1", "sa", "");
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        TransactionTemplate transactionTemplate(DataSource dataSource) {
            return new TransactionTemplate(
                    new DataSourceTransactionManager(dataSource));
        }
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            TransactionTemplate tx = context.getBean(TransactionTemplate.class);

            jdbc.execute("""
                    CREATE TABLE jobs (
                        id BIGINT PRIMARY KEY,
                        name VARCHAR(100) NOT NULL,
                        completed BOOLEAN NOT NULL
                    )
                    """);
            jdbc.update("INSERT INTO jobs VALUES (?, ?, ?)",
                    1L, "Design", false);
            jdbc.update("INSERT INTO jobs VALUES (?, ?, ?)",
                    2L, "Coding", true);
            jdbc.update("INSERT INTO jobs VALUES (?, ?, ?)",
                    3L, "Testing", false);

            // 1) RowMapper only reads the current row, no next/close.
            List<Job> jobs = jdbc.query(
                    "SELECT id, name, completed FROM jobs ORDER BY id",
                    (rs, rowNum) -> new Job(
                            rs.getLong("id"),
                            rs.getString("name"),
                            rs.getBoolean("completed")));
            System.out.println("mapped=" + jobs.size());

            // 2) RowCallbackHandler also processes only the current row.
            List<String> names = new ArrayList<>();
            jdbc.query("SELECT name FROM jobs ORDER BY id",
                    (RowCallbackHandler) rs -> names.add(rs.getString("name")));
            System.out.println("names=" + String.join(", ", names));

            // 3) ResultSetExtractor calls next() itself, Spring closes ResultSet.
            Integer extracted = jdbc.query(
                    "SELECT id FROM jobs ORDER BY id",
                    (ResultSetExtractor<Integer>) rs -> {
                        int count = 0;
                        while (rs.next()) {
                            count++;
                        }
                        return count;
                    });
            System.out.println("extractor=" + extracted);

            // 4) Template closes PreparedStatement; callback closes ResultSet
            //    opened by ps.executeQuery() itself.
            Integer statementCount = jdbc.execute(
                    "SELECT COUNT(*) FROM jobs WHERE id >= ?",
                    (PreparedStatementCallback<Integer>) ps -> {
                        ps.setLong(1, 2L);
                        try (ResultSet rs = ps.executeQuery()) {
                            rs.next();
                            return rs.getInt(1);
                        }
                    });
            System.out.println("statementCount=" + statementCount);

            // 5) ConnectionCallback borrows connection; callback closes
            //    PreparedStatement/ResultSet it creates itself.
            Integer connectionCount = jdbc.execute(
                    (ConnectionCallback<Integer>) connection -> {
                        try (PreparedStatement ps = connection.prepareStatement(
                                     "SELECT COUNT(*) FROM jobs WHERE completed = TRUE");
                             ResultSet rs = ps.executeQuery()) {
                            rs.next();
                            return rs.getInt(1);
                        }
                    });
            System.out.println("connectionCount=" + connectionCount);

            // 6) Caller receiving Stream must close it, even after count().
            long streamCount;
            try (Stream<String> stream = jdbc.queryForStream(
                    "SELECT name FROM jobs ORDER BY id",
                    (rs, rowNum) -> rs.getString("name"))) {
                streamCount = stream.count();
            }
            System.out.println("streamCount=" + streamCount);

            // 7) Inside a transaction, JdbcTemplate only releases connection;
            //    the manager decides commit/rollback.
            try {
                tx.executeWithoutResult(status -> {
                    jdbc.execute((ConnectionCallback<Void>) connection -> {
                        try (PreparedStatement own = connection.prepareStatement(
                                "UPDATE jobs SET completed = TRUE WHERE id = 1")) {
                            own.executeUpdate();
                        }
                        return null;
                    });
                    throw new IllegalStateException("rollback example");
                });
            } catch (IllegalStateException expected) {
                // Only catching the exception intentionally thrown in the demo.
            }

            Boolean completed = jdbc.queryForObject(
                    "SELECT completed FROM jobs WHERE id = ?",
                    Boolean.class, 1L);
            System.out.println("afterRollback=" + completed);
        }
    }
}
```

In the directory containing `build.gradle`, run:

```bash
gradle run
```

If the project has the Gradle Wrapper, you can use `./gradlew run` (Linux/macOS) or `gradlew.bat run` (Windows). The output produced by `System.out` is:

```text
mapped=3
names=Design, Coding, Testing
extractor=3
statementCount=2
connectionCount=1
streamCount=3
afterRollback=false
```

The console may include additional Gradle/Spring logs. **Why are these values right?**

- Three `INSERT`s create three jobs, so `mapped=3`. Results ordered by `id` yield the three names.
- `ResultSetExtractor` counts three rows, so `extractor=3`.
- `PreparedStatementCallback` binds `id >= 2`, thus counting two jobs.
- `ConnectionCallback` counts jobs with `completed = TRUE`: only job id 2, so 1.
- The stream traverses three rows and is closed, so `streamCount=3`.
- In the final transaction, the callback creates and closes its own statement, yet **does not close the connection** supplied by the template. After the callback returns, `IllegalStateException` rolls back the transaction; job id 1 stays `completed=false`.

**Observable from the code:** where resources are closed depends not merely on `AutoCloseable`, but on ownership: `try-with-resources` surrounds self-opened ResultSets, self-created statements, and returned streams; there is no `try-with-resources` around connections, statements, or template-managed result sets borrowed by callbacks.

### 12.2. Variations to Try

1. **Detect wrong cursor usage:** put `rs.next()` inside `RowCallbackHandler`, observe skipped rows or failures. Then restore the right code.
2. **Detect missing cleanup:** remove `try-with-resources` around the self-opened `ResultSet` in `PreparedStatementCallback`; use an instrumented DataSource/pool leak metric to observe resources over time, not just a three-row test.
3. **Detect resource escape:** return `ResultSet` from `ResultSetExtractor` and access it in the caller; see why the cursor's lifetime has ended.
4. **Early stream close:** replace `stream.count()` with `stream.findFirst()`; even when reading only partially, the stream must still be closed.
5. **Do not close transaction connection:** replace the `PreparedStatement`-creating callback with `JdbcTemplate.update(...)` inside the same `TransactionTemplate`; rollback behavior must stay identical.

## 13. Ownership Under `@Transactional` or `TransactionTemplate`

Suppose a Spring service is intercepted by `@Transactional` and accesses the database through `JdbcTemplate`:

```text
Service method begins Spring transaction T1
    │
    ├─ JdbcTemplate.query(...)
    │    ├─ acquires bound connection T1
    │    ├─ creates/closes statement, result set
    │    └─ releases handle; T1 retains connection
    │
    ├─ JdbcTemplate.update(...)
    │    └─ uses connection T1
    │
    └─ service succeeds or throws exception
           └─ transaction manager commits/rolls back and releases connection
```

`JdbcTemplate` releases connections via transaction-aware `DataSourceUtils` infrastructure. Therefore, **never call `connection.commit()`/`rollback()` or `connection.close()` inside a callback** to "release early"; the transaction manager owns the transaction. Some handles may be proxies suppressing close, which is no excuse to break the contract.

When no Spring transaction is active, the template still acquires and returns connections properly per `DataSource`/pool, and each statement may follow driver auto-commit. **`JdbcTemplate` does not automatically open a multi-step business transaction just because you call multiple `update` methods in a row.**

When a callback throws a runtime exception:

- `JdbcTemplate` cleans up resources it owns along the error path.
- If the exception is `SQLException`, the template normally translates it into `DataAccessException`.
- If an appropriate transaction is active, Spring rolls back per `TransactionTemplate` or `@Transactional` interceptor rules; by default, the annotation rolls back on unchecked exceptions.
- If the callback **catches and swallows** the error and returns as if successful, transaction infrastructure may not know rollback is required. Design exception handling per use case, or mark rollback-only intentionally.

### Do Not Retain Resources Across Callbacks

`Connection`, `PreparedStatement`, and `ResultSet` must never be assigned to singleton fields, caches, or passed to async tasks for use after the callback returns. Otherwise:

- Statements/result sets may already be closed;
- Connections may already have returned to the pool and been lent to another request;
- The thread-bound transaction may have ended;
- Code introduces race conditions and bugs that only appear under load.

Copy needed columns into immutable DTOs/records or collections inside the callback. For large result sets, use paging, tightly scoped cursors/streams with `try-with-resources`, or proper batch processing.

## 14. Exceptions and Advanced Scenarios

### 14.1. ResultSet Opened by Code Inside StatementCallback

Per the Javadoc of `StatementCallback`/`PreparedStatementCallback`, Spring closes the statement **but does not guarantee closing the statement fully releases all opened ResultSets across every pool/driver**. Thus, ResultSets opened by the callback must be closed in `finally`/`try-with-resources`. This rule **differs** from `RowMapper`/`ResultSetExtractor` passed to `JdbcTemplate.query`.

### 14.2. Extra Statements Created Beyond the Template's Statement

If inside `ConnectionCallback` you call `connection.createStatement()` or `prepareStatement()`, that statement was created by the callback: the callback must close it. If inside a `StatementCallback` you receive statement A from the template and then use its connection to create statement B, statement B was also created by you and must be closed. Do not expect the template to track down every resource a callback might open.

### 14.3. Stream, InputStream, Reader, and LOBs

Do not confuse `queryForStream`'s Java Stream pipeline with an `InputStream` for reading BLOBs or a `Reader` for CLOBs. Large LOB data may be supplied by drivers via streams tied to the result set/connection. When using those APIs:

- Read and close streams per the API/driver contract while the result set is still open.
- If needed after the callback, store data in a location with clear ownership and bounds, or convert to `byte[]`/`String` when size permits.
- Never return a cursor-bound stream out of `RowMapper` assuming it survives independently.
- Test streaming, transaction, and memory behavior on your target driver, because in-memory H2 does not guarantee identical behavior to PostgreSQL/MySQL/Oracle.

### 14.4. BatchPreparedStatementSetter

With `JdbcTemplate.batchUpdate` and `BatchPreparedStatementSetter`, Spring holds the statement; the setter only binds values per index and provides the batch size. Never close the statement or call `executeBatch()` inside `setValues`; the template drives batch execution. Auxiliary resources created by the setter must still be cleaned up per their lifecycles.

### 14.5. Never Share a Connection Across Threads

A callback receives a connection acquired/bound for the current JDBC call. Never store it for use from `CompletableFuture`, `@Async`, or another thread: most JDBC connections are not designed for arbitrary cross-thread sharing, and synchronous Spring JDBC transactions are thread-bound. Open transactions and bind data access within the proper execution context.

## 15. Common Errors and Self-Diagnosis

| Symptom | Ownership cause | How to check / fix |
| --- | --- | --- |
| `ResultSet closed` or missing rows | Callback called `rs.close()`/`next()` violating contract | Check callback type; remove close/next from mapper/handler |
| `Statement closed` | Callback closed a template-supplied statement | Only close statements created by the callback itself |
| Connection unusable on subsequent operations | Callback wrongly closed/retained connection or mutated state | Do not manage lifecycle of template-supplied connections |
| Pool exhausted after repeated `queryForStream` | Caller failed to `close()` stream | Wrap stream in `try-with-resources` |
| Cursor leak when using `execute(PreparedStatementCallback)` | Callback failed to close self-opened ResultSet | Close result set inside the callback |
| Wrong/duplicate mapped results | `RowMapper` or handler moved cursor manually | Only read current row; use extractor if manual iteration is needed |
| Partial data persisted | Missing enclosing transaction or swallowed error | Check transaction boundary and rollback integration tests |
| `SQLException` vanishes, caller thinks it succeeded | Callback caught and ignored error | Let Spring translate errors or handle/mark rollback explicitly |
| Erratic async failures | Retained ResultSet/Connection past callback or across threads | Materialize data; acquire resources inside each task |
| High heap usage on large table reads | Callback accumulated all data without bounds | Paging, streaming with closed stream, batch processing |
| Leak persists even after closing statement | Self-opened ResultSet missed under driver/pool statement pooling | Check where result sets are actually created and close explicitly |

**Diagnostic workflow:** identify the API called (`query`, `execute`, or `queryForStream`) → note the callback type → trace who creates each resource → check `try-with-resources` sits at the right layer → test success, exception, and early-exit paths → monitor pool/driver resource metrics if available.

## 16. Code Review Checklist by Ownership

When reviewing a JDBC callback, ask in order:

1. Which `JdbcTemplate` overload am I using? Does it pass the callback a `ResultSet`, `Statement`, `PreparedStatement`, or `Connection`?
2. Did the template open this resource, or did the callback call `executeQuery()`/`prepareStatement()` to create it?
3. If the callback created the resource, did I wrap it in `try-with-resources`?
4. If the template supplied the resource, are there any contract-breaking `close()`/`commit()`/`rollback()` calls or state mutations?
5. Who controls `rs.next()`: `JdbcTemplate` (RowMapper/RowCallbackHandler) or the callback (ResultSetExtractor)?
6. Does the callback return a JDBC cursor, statement, connection, LOB stream, or object still tied to a closed resource?
7. If returning `Stream<T>` from `queryForStream`, do callers know their closing responsibility, and are short-circuit/exception paths tested?
8. Does the callback hold shared mutable state across threads or run async with borrowed handles?
9. On `SQLException`, is the template allowed to translate errors; on runtime exceptions, does the transaction roll back as intended?
10. Have I run integration tests on a production-like driver/database for critical cursor, stream, pool, or transaction paths?

**Mastery bar:** you can not only write `jdbcTemplate.query(...)`, but explain accurately why you do not close `ResultSet` in `ResultSetExtractor`, why you must close it in `PreparedStatementCallback`, and why `queryForStream` requires the caller to invoke `close()`.

## 17. References

- Spring Framework 6.2, **Data Access with JDBC** (responsibility table between Spring and application): https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc.html
- Spring Framework 6.2, **Using the JDBC Core Classes**: https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/core.html
- Spring Framework Javadoc, **JdbcTemplate**: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html
- Spring Framework Javadoc, **PreparedStatementCallback**: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jdbc/core/PreparedStatementCallback.html
- Spring Framework Javadoc, **StatementCallback**: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jdbc/core/StatementCallback.html
- Spring Framework Javadoc, **RowCallbackHandler**: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jdbc/core/RowCallbackHandler.html
- Spring Framework Javadoc, **DataSourceUtils**: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jdbc/datasource/DataSourceUtils.html

Read the contract of the exact overload and version you are using. Resource ownership is crystal clear once you know **who creates, who borrows, who closes, and when the callback scope ends**.