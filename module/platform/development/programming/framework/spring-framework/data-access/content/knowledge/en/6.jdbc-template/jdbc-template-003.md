# JdbcTemplate Is Safe to Share Once Configured, but Callbacks Still Need Proper Design

## 1. Two Different Safety Concepts

In Spring JDBC, a `JdbcTemplate` can be created once, fully configured, then injected into multiple repositories/services and used concurrently by many requests. Spring's API documentation states clearly: **a `JdbcTemplate` instance is thread-safe once configured**.

However, that statement **does not guarantee** that every object the template uses is thread-safe. In particular, the callbacks you pass to `query`, `update`, or `execute` are still **application code**. If a callback writes to the same shared `ArrayList`, `StringBuilder`, counter, or stateful object across requests, race conditions, corrupted data, or cross-request result leaks can still occur.

Three questions must be separated:

1. **Can the template be shared?** Yes, after stable configuration and safe publication. A singleton `JdbcTemplate` bean is the standard pattern.
2. **In what sense are JDBC resources shared?** `DataSource` is the source of connections; each operation acquires resources via Spring's mechanism and closes/releases them at the proper time. A `ResultSet` or `PreparedStatement` must never be shared arbitrarily across threads.
3. **Are callbacks safe?** It depends on the *state* they read/write, the objects they capture, the lifetime of that state, and whether state or `ResultSet` escapes the operation.

This article focuses on the third distinction, though understanding all three is necessary to avoid concluding "having `JdbcTemplate` automatically eliminates concurrency bugs."

### 1.1. What Does JdbcTemplate Actually Hold?

`JdbcTemplate` holds a reference to a `DataSource` and configuration settings such as `SQLException` translation, `fetchSize`, `maxRows`, and `queryTimeout`. It coordinates JDBC operations and invokes callbacks; it is **not** a fixed `ResultSet` or `Connection` that all requests mutate together.

Typical usage:

```java
@Configuration(proxyBeanMethods = false)
class JdbcConfiguration {
    @Bean
    JdbcTemplate jdbcTemplate(DataSource dataSource) {
        JdbcTemplate template = new JdbcTemplate(dataSource);
        template.setQueryTimeout(10); // Configured once when creating the bean.
        return template;
    }
}
```

This is an **illustrative snippet**, requiring imports for `@Configuration`, `@Bean`, `DataSource`, `JdbcTemplate`, and an existing `DataSource` bean; it is not a standalone program. Spring creates the bean and injects the same instance into multiple DAOs. Configuration setters are invoked before the instance starts being used concurrently.

**Do not** call `template.setQueryTimeout(...)`, `setFetchSize(...)`, `setMaxRows(...)`, or `setDataSource(...)` per request on an active singleton. Doing so mutates shared configuration; other requests may observe the new values unexpectedly. If different settings are needed, choose per-case APIs/statements or create separately configured templates; do not turn global setters into "per-request settings".

### 1.2. Execution Flow of an Operation

```text
Request A                           Request B
   |                                   |
   v                                   v
BookRepository                     BookRepository
   |                                   |
   +-------------+---------------------+
                 |
         Same JdbcTemplate
       (stable configuration)
                 |
        +--------+--------+
        |                 |
   Query A            Query B
   params A           params B
   callback A         callback B
   ResultSet A        ResultSet B
        |                 |
        +--------+--------+
                 |
        DataSource / pool
                 |
        JDBC driver / database
```

Both branches share the **template object**; query data and processing resources for each operation must still remain properly isolated. With a standard connection pool, each operation typically borrows and returns a connection; when a Spring-managed transaction is active, `JdbcTemplate` participates in the connection bound to the transaction on the current thread. Do not infer that every operation *always* gets a brand-new physical connection: pools can reuse connections, and statements within the same transaction can share the same connection.

## 2. Callback Lifecycle and Resource Ownership

A Spring JDBC callback typically runs **synchronously within the JDBC call**. The template coordinates creating/preparing the statement, executing it, iterating over data where appropriate, and cleaning up resources it manages. The callback only performs the work permitted by its contract.

| Callback | Receives | Primary responsibility | State notes |
| --- | --- | --- | --- |
| `PreparedStatementCreator` | `Connection` | Creates and returns a `PreparedStatement` with the needed SQL/options | Do not store the connection in a field for later use |
| `PreparedStatementSetter` | `PreparedStatement` | Binds parameters via `setXxx(...)` | Do not execute/close the statement yourself; avoid capturing mutable data modified concurrently |
| `RowMapper<T>` | `ResultSet` at the **current row** and `rowNum` | Builds one `T` from **one row** | Best kept stateless; **do not call `rs.next()`** |
| `RowCallbackHandler` | `ResultSet` at the **current row** | Processes each row, typically updating an accumulator | Any accumulator must be isolated **per invocation**; **do not call `rs.next()`** |
| `ResultSetExtractor<T>` | `ResultSet` to process the **entire result set** | Explicitly iterates `while (rs.next())` and returns `T` | Aggregation state should be a local variable or fresh per-call callback |
| `PreparedStatementCallback<T>` | Created `PreparedStatement` | Executes custom statement operations and extracts a result | Properly manage resources opened inside the callback; do not close the statement owned by the template |

In `RowMapper` and `RowCallbackHandler`, **`JdbcTemplate` already controls cursor positioning** before calling the callback. Calling `rs.next()` there skips rows or causes unpredictable behavior. Conversely, `ResultSetExtractor` is responsible for iterating over the result set; failing to call `rs.next()` when needed means no rows are read.

`RowMapper`'s `rowNum` starts at 0 for each result iteration. Do not use `rowNum` as a business ID or durable database order. Result ordering depends on `ORDER BY` in SQL.

**Resource rule:** never return or store the `ResultSet`, `PreparedStatement`, or `Connection` received in a callback for use after `JdbcTemplate` finishes. The template closes/releases the resources it manages; escaped references may already be invalid. If a callback opens its own streams/files/network resources, manage their lifecycles yourself; the template does not know about extra resources you open.

## 3. RowMapper: Choose Stateless for Safety and Reuse

`RowMapper<T>` takes one row and returns a Java object. A good mapper is usually a pure function of the data read from the current row, safely reusable across queries and threads:

```java
// Illustrative snippet; record and imports are needed in the application:
record Book(long id, String title) {}

RowMapper<Book> mapper = (rs, rowNum) ->
        new Book(rs.getLong("id"), rs.getString("title"));

List<Book> books = jdbc.query(
        "SELECT id, title FROM books ORDER BY id", mapper);
```

In this example, `mapper` holds no counter, accumulating list, or external cursor. Two concurrent calls using the same mapper share no temporary results created by the mapper. `JdbcTemplate` allocates a separate result list for each `query` call.

If a mapper is used frequently, declare it as:

```java
private static final RowMapper<Book> BOOK_MAPPER =
        (rs, rowNum) -> new Book(
                rs.getLong("id"),
                rs.getString("title"));
```

This is a **field declaration snippet**, not a standalone Java class. Making the field `final` keeps the reference to the mapper constant, but **`final` does not by itself make the referenced object thread-safe**. It is the mapper logic not mutating shared state that makes reuse safe.

### 3.1. Bad Design: Mapper Accumulating Shared Mutable State

```java
// Anti-pattern illustration; DO NOT use in multi-request code.
final class UnsafeBookMapper implements RowMapper<Book> {
    private int mappedRows = 0;
    private final List<String> recentTitles = new ArrayList<>();

    @Override
    public Book mapRow(ResultSet rs, int rowNum) throws SQLException {
        mappedRows++;
        recentTitles.add(rs.getString("title"));
        return new Book(rs.getLong("id"), rs.getString("title"));
    }
}
```

If a singleton repository shares `UnsafeBookMapper`, concurrent requests can execute `mappedRows++` (non-atomic) or `add` into the same `ArrayList` (not thread-safe). Results mix across queries, counts are wrong, or collection internals break. Even with `synchronized`, sharing `recentTitles` makes "whose request's results are these?" ambiguous.

There is no need to store lists or counts inside the mapper when `JdbcTemplate.query(...)` already returns `List<Book>`. If shared metrics are desired, design them as a separate responsibility with an appropriate synchronization model, never as business query results.

### 3.2. Reading Null Values and Handling Errors

A proper callback must also map data types accurately:

```java
// RowMapper snippet illustrating a nullable parent_id column:
Long parentId = rs.getObject("parent_id", Long.class);
// Unlike rs.getLong(...): for SQL NULL, getLong returns 0 and requires checking rs.wasNull().
```

`SQLException` thrown in `mapRow` can be caught by Spring JDBC and translated via `SQLExceptionTranslator` into the unchecked `DataAccessException` hierarchy. Do not swallow `SQLException` and replace it with an "empty" DTO as if it were valid data. Business errors and infrastructure failures must remain distinct.

## 4. RowCallbackHandler: Often Stateful, but State Must Belong to Each Invocation

`RowCallbackHandler` is suitable when you want to process rows one by one without necessarily building a `List<T>` via `RowMapper`, such as recording statistics, summing totals, or forwarding each row to a controlled sink. The handler often holds state to accumulate values, but each call should own **independent state**.

### 4.1. Right Way: Local Accumulator

```java
List<String> names = new ArrayList<>();
RowCallbackHandler handler = rs -> names.add(rs.getString("title"));
jdbc.query("SELECT title FROM books ORDER BY id", handler);

// names is private to this call, read only after query returns.
```

This is a **snippet**, assuming `jdbc` and the `books` table exist, with imports for `List`, `ArrayList`, and `RowCallbackHandler`. The lambda captures a mutable list, but in this usage the list **is created fresh inside the invocation** and the callback runs synchronously with no other thread modifying it; therefore it is appropriate.

The key point is not "lambdas are always safe" or "callbacks must be completely immutable." **A mutable accumulator is completely valid when it belongs to a single operation and is not shared concurrently.**

### 4.2. Wrong Way: Keeping RowCallbackHandler as a Singleton with Shared Results

```java
// Snippet illustrating a bug in a singleton DAO, not a standalone runnable example.
class UnsafeTitlesDao {
    private final JdbcTemplate jdbc;
    private final List<String> allTitles = new ArrayList<>();

    UnsafeTitlesDao(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    List<String> loadTitles() {
        allTitles.clear();
        jdbc.query("SELECT title FROM books", (RowCallbackHandler) rs ->
                allTitles.add(rs.getString("title")));
        return allTitles;
    }
}
```

Suppose request A has just added "Java" when request B calls `clear()`; A can lose data. Then B adds "Spring" into the same list; the two calls' results are mixed. The fact that both the DAO bean and `JdbcTemplate` are singletons does not make the `allTitles` field correct.

**Better fix:** create `List<String> titles = new ArrayList<>()` inside `loadTitles()`, pass a handler using that local list, and return it after `query` finishes. When simply turning each row into an element of a list, you can write directly:

```java
List<String> titles = jdbc.query(
        "SELECT title FROM books ORDER BY id",
        (rs, rowNum) -> rs.getString("title"));
```

Why is `RowMapper` usually preferable here? It clearly expresses "each row → one String", and `JdbcTemplate` manages the result collection per invocation; the code maintains less state.

### 4.3. Do Not Control the Cursor in RowCallbackHandler

```java
// Wrong when using RowCallbackHandler:
RowCallbackHandler wrong = rs -> {
    while (rs.next()) {          // Disrupts the loop managed by JdbcTemplate.
        System.out.println(rs.getString("title"));
    }
};

// Right: only read the current row.
RowCallbackHandler right = rs ->
        System.out.println(rs.getString("title"));
```

These are illustrative snippets; `JdbcTemplate` iterates over the `ResultSet` itself when given a `RowCallbackHandler`, so `right` is called once for each row.

## 5. ResultSetExtractor: Actively Iterating Over the Full Result Set

`ResultSetExtractor<T>` fits when the result is not simply "one T per row"—for example, returning an aggregate, building a tree from `JOIN` data, grouping parent-child records, or computing statistics.

```java
ResultSetExtractor<Map<Long, List<String>>> extractor = rs -> {
    Map<Long, List<String>> childrenByParent = new LinkedHashMap<>();

    while (rs.next()) {
        long parentId = rs.getLong("parent_id");
        String child = rs.getString("child_name");
        childrenByParent
                .computeIfAbsent(parentId, id -> new ArrayList<>())
                .add(child);
    }
    return childrenByParent;
};

Map<Long, List<String>> groups = jdbc.query(
        "SELECT parent_id, child_name FROM child ORDER BY parent_id, child_name",
        extractor);
```

This is a **snippet** requiring Java collections imports, the extractor interface, the `child` table, and `jdbc`. `extractor` itself retains no data across queries: `childrenByParent` is created **each time the lambda method is invoked**.

Conversely, if you store the `Map` as a field of a singleton `ResultSetExtractor` and reuse it across queries, races and state contamination still happen. An extractor can be safely reused if **it is stateless and every accumulator is created inside `extractData`**.

### 5.1. Do Not Return ResultSet for Later Use

```java
// Wrong: the returned value depends on a resource about to be closed.
ResultSet leaked = jdbc.query(
        "SELECT id, title FROM books",
        (ResultSetExtractor<ResultSet>) rs -> rs);

// Right: read and package data while the callback is still active.
List<String> titles = jdbc.query(
        "SELECT title FROM books ORDER BY id",
        (rs, rowNum) -> rs.getString(1));
```

In the wrong example, once `query` completes, the template is free to close the `ResultSet`. Data must be turned into DTOs, collections, aggregates, or plain Java values **while the callback is executing**.

## 6. PreparedStatementSetter and Low-Level Callbacks: Power Comes with Responsibility

When `?` parameters are needed, the simplest option is an overload of `query`/`update`:

```java
List<Book> matching = jdbc.query(
        "SELECT id, title FROM books WHERE id >= ? ORDER BY id",
        BOOK_MAPPER,
        2L);
```

If binding control is needed, use `PreparedStatementSetter`:

```java
PreparedStatementSetter setter = ps -> ps.setLong(1, 2L);
List<Book> matching = jdbc.query(
        "SELECT id, title FROM books WHERE id >= ? ORDER BY id",
        setter,
        BOOK_MAPPER);
```

These snippets use `jdbc`/`BOOK_MAPPER` already declared in a DAO, not a standalone runnable program. `PreparedStatementSetter` only **sets parameters**; `JdbcTemplate` executes and closes the statement. If a callback modifies a different `PreparedStatement` or stores it in a field to call later, it violates the contract and is generally unsafe.

With `PreparedStatementCreator` or `PreparedStatementCallback`, there is more direct access to connections/statements; therefore you must respect their lifecycles and clean up any extra resources created. Do not close the connection or statement managed by the template. If a callback opens a `ResultSet` itself inside a low-level API, read and close it within the appropriate scope; **avoid letting unclosed JDBC API objects leak out**.

The reason Spring provides multiple callbacks is so callers can choose just enough control. You do not need to drop down to low-level APIs for a query with two parameters and a simple `RowMapper`.

## 7. Complete Java 17+ Example: One JdbcTemplate Used by Concurrent Operations

The program below demonstrates:

- One `DataSource` configured as a Spring bean; one `JdbcTemplate` with fixed configuration.
- One DAO receiving the same template bean via constructor.
- A stateless `RowMapper` reused multiple times.
- A `RowCallbackHandler` creating a local accumulator for one query.
- A `ResultSetExtractor` creating a local accumulator and calling `rs.next()` itself.
- A `PreparedStatementSetter` binding parameters for a query.
- Multiple tasks reading data concurrently through **one `JdbcTemplate`**. Display order is fixed by the order of `Future` retrieval, not by actual execution scheduling.
- A JDBC result stream closed with `try-with-resources`.

The example uses Java 17+, Spring Framework 6.2.12, and H2 2.3.232, **without requiring Spring Boot**. Versions are pinned for reproducibility, not to claim they are the latest releases.

### 7.1. Project Structure

```text
shared-jdbc-demo/
├── pom.xml
└── src/main/java/example/SharedJdbcTemplateDemo.java
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>shared-jdbc-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
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
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`src/main/java/example/SharedJdbcTemplateDemo.java`:

```java
package example;

import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.StringJoiner;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.stream.Stream;

import javax.sql.DataSource;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.PreparedStatementSetter;
import org.springframework.jdbc.core.ResultSetExtractor;
import org.springframework.jdbc.core.RowCallbackHandler;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

public class SharedJdbcTemplateDemo {
    record Book(long id, String title) {}

    static class BookDao {
        private static final RowMapper<Book> BOOK_MAPPER =
                (rs, rowNum) -> new Book(
                        rs.getLong("id"),
                        rs.getString("title"));

        private final JdbcTemplate jdbc;

        BookDao(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        JdbcTemplate template() {
            return jdbc;
        }

        List<Book> findAll() {
            return jdbc.query(
                    "SELECT id, title FROM books ORDER BY id",
                    BOOK_MAPPER);
        }

        Optional<Book> findById(long id) {
            List<Book> results = jdbc.query(
                    "SELECT id, title FROM books WHERE id = ?",
                    BOOK_MAPPER,
                    id);
            return results.stream().findFirst();
        }

        List<String> titlesByCallback() {
            List<String> titles = new ArrayList<>();
            RowCallbackHandler handler =
                    rs -> titles.add(rs.getString("title"));

            jdbc.query(
                    "SELECT title FROM books ORDER BY id",
                    handler);
            return titles;
        }

        String titlesByExtractor() {
            ResultSetExtractor<String> extractor = rs -> {
                StringJoiner joiner = new StringJoiner(" | ");
                while (rs.next()) {
                    joiner.add(rs.getString("title"));
                }
                return joiner.toString();
            };

            return jdbc.query(
                    "SELECT title FROM books ORDER BY id",
                    extractor);
        }

        List<Book> findFrom(long minId) {
            PreparedStatementSetter setter =
                    ps -> ps.setLong(1, minId);

            return jdbc.query(
                    "SELECT id, title FROM books WHERE id >= ? ORDER BY id",
                    setter,
                    BOOK_MAPPER);
        }

        long streamedCount() {
            try (Stream<Book> stream = jdbc.queryForStream(
                    "SELECT id, title FROM books",
                    BOOK_MAPPER)) {
                return stream.count();
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class JdbcConfig {
        @Bean
        DataSource dataSource() {
            DriverManagerDataSource source = new DriverManagerDataSource();
            source.setDriverClassName("org.h2.Driver");
            source.setUrl("jdbc:h2:mem:sharedtemplate;DB_CLOSE_DELAY=-1");
            source.setUsername("sa");
            source.setPassword("");
            return source;
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource dataSource) {
            JdbcTemplate template = new JdbcTemplate(dataSource);
            template.setQueryTimeout(10); // Only call during configuration.
            return template;
        }

        @Bean
        BookDao bookDao(JdbcTemplate template) {
            return new BookDao(template);
        }
    }

    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(JdbcConfig.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            BookDao dao = context.getBean(BookDao.class);

            jdbc.execute(
                    "CREATE TABLE books (id BIGINT PRIMARY KEY, title VARCHAR(100))");
            jdbc.update("INSERT INTO books (id, title) VALUES (?, ?)", 1L, "Java");
            jdbc.update("INSERT INTO books (id, title) VALUES (?, ?)", 2L, "Spring");
            jdbc.update("INSERT INTO books (id, title) VALUES (?, ?)", 3L, "JDBC");

            System.out.println("Same bean: " + (jdbc == dao.template()));
            System.out.println("Rows: " + dao.findAll());
            System.out.println("RowCallbackHandler: " + dao.titlesByCallback());
            System.out.println("ResultSetExtractor: " + dao.titlesByExtractor());
            System.out.println("PreparedStatementSetter: " + dao.findFrom(2L));
            System.out.println("Stream count: " + dao.streamedCount());

            ExecutorService executor = Executors.newFixedThreadPool(3);
            try {
                List<Future<String>> futures = new ArrayList<>();
                for (long id = 1; id <= 3; id++) {
                    long requestedId = id;
                    futures.add(executor.submit(() ->
                            dao.findById(requestedId).orElseThrow().title()));
                }
                List<String> results = new ArrayList<>();
                for (Future<String> future : futures) {
                    results.add(future.get());
                }
                System.out.println("Parallel query results: " + results);
            } finally {
                executor.shutdown();
            }
        }
    }
}
```

Run in the directory containing `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=example.SharedJdbcTemplateDemo
```

Program `System.out.println` lines (Maven/Spring may emit additional logs depending on environment):

```text
Same bean: true
Rows: [Book[id=1, title=Java], Book[id=2, title=Spring], Book[id=3, title=JDBC]]
RowCallbackHandler: [Java, Spring, JDBC]
ResultSetExtractor: Java | Spring | JDBC
PreparedStatementSetter: [Book[id=2, title=Spring], Book[id=3, title=JDBC]]
Stream count: 3
Parallel query results: [Java, Spring, JDBC]
```

### 7.2. Precise Explanation of the Experiment

1. `JdbcConfig` creates a single `JdbcTemplate` bean in the context. `dao.template() == jdbc` proves the DAO uses that exact bean instance; `true` is only a reference comparison and does not by itself prove every callback is safe.
2. `BOOK_MAPPER` is a `static final` field with no mutable state; each `mapRow` creates a new `Book` record. The result of `findAll()` is a new list for that call.
3. `titlesByCallback` creates a new `ArrayList` on each call; it has mutable state but is not shared across invocations.
4. `titlesByExtractor` calls `rs.next()` itself, uses a local `StringJoiner`, and returns a `String`. The template still owns the `ResultSet` lifecycle.
5. `findFrom` creates a `PreparedStatementSetter` using the `minId` captured for that call, without modifying template configuration.
6. `streamedCount` uses `try-with-resources` to close the `Stream` and the underlying JDBC resources.
7. Three `Callable`s run through the same DAO/template; each task has its own `requestedId` value. The program reads `Future`s in order 1, 2, 3 so stdout is deterministic, even though the actual scheduling order of the queries is not guaranteed.
8. `DriverManagerDataSource` creates JDBC connections without a pool. It is used to keep dependencies minimal in the example; **it is not a recommended configuration for concurrent requests in production**. Under real load, use a pooled `DataSource` such as HikariCP with appropriate connection limits.
9. In-memory H2 uses `DB_CLOSE_DELAY=-1` so the database does not lose tables between connections within the same process. That is an H2 feature for the demo; do not generalize from it that all databases or drivers follow the same rule.

Reusing the template avoids repeatedly creating/configuring wrappers; it **does not guarantee** concurrent queries run at the same speed, does not merge transactions of different requests together, and does not automatically solve DB locks, contention, or consistency.

## 8. Spring Transactions and ThreadLocal: Sharing a Template vs. Sharing a Transaction

In Spring JDBC, `JdbcTemplate` can participate in a transaction by obtaining connections through `DataSourceUtils`. A standard transaction coordinated by `PlatformTransactionManager` uses thread-bound context, allowing operations on the same `DataSource` and same thread to join the active transaction.

Typical model:

```text
Thread A: @Transactional service method
          -> Transaction manager
          -> Connection bound to Thread A
          -> same JdbcTemplate calls query/update
          -> commit/rollback when service completes

Thread B: @Transactional service method
          -> Transaction manager
          -> Connection/transaction of Thread B
          -> same JdbcTemplate calls query/update
          -> B's own commit/rollback
```

**Do not** think that a singleton `JdbcTemplate` causes two threads to implicitly share one transaction. Nor should you pass a `Connection` from Thread A to Thread B to "join" A's transaction.

If a service calls `CompletableFuture.supplyAsync(...)` or `ExecutorService.submit(...)` while inside a normal `@Transactional` method, the thread-bound transaction context **does not automatically propagate to worker threads**. JDBC operations in workers may execute outside the caller's transaction unless an appropriate propagation design is used. Define transaction boundaries where execution actually runs and test concurrent scenarios.

Related notes:

- Use the same `DataSource` or properly Spring-supported proxies if `JdbcTemplate` is expected to join an active transaction.
- `@Transactional` applies through proxies by default in many configurations; self-invocation of a method within the same bean bypasses default advice.
- Rollback and isolation are policies of the transaction manager/DB; a thread-safe `JdbcTemplate` does not make a sequence of separate statements atomic.
- JDBC `Connection`, `Statement`, and `ResultSet` are not resources to keep as singleton fields in a DAO.
- With a database pool, a connection can be reused *sequentially* across requests after being returned to the pool; that does not mean concurrently sharing a borrowed connection.

## 9. Other Traps When Callbacks Are Syntactically Valid

### 9.1. Callback Captures an External Mutated Variable

A callback can have no fields and still be broken if it captures a shared mutable collection or object:

```java
// Wrong in multi-request code: list exists as a shared field.
private final List<Long> idsSeen = new ArrayList<>();

public void listIds() {
    jdbc.query(
            "SELECT id FROM books",
            (RowCallbackHandler) rs -> idsSeen.add(rs.getLong(1)));
}
```

This is a snippet inside a DAO. `RowCallbackHandler` has no syntax error; the bug lies in the **object captured by the lambda**. To fix it, create `List<Long> idsSeen` inside each method invocation or use `RowMapper<Long>` and return the list.

Even with a "thread-safe" object like `ConcurrentHashMap`, if all requests write into a shared result table, **per-request isolation semantics** are still broken even if no memory corruption occurs. Data synchronization and data isolation are two different requirements.

### 9.2. Callback Contains I/O, Network Calls, or Expensive Operations

`RowMapper` and `RowCallbackHandler` are invoked while the JDBC operation is still active; if every row triggers an HTTP API call, slow file write, arbitrary lock wait, or N+1 query, statement/connection hold times grow and pool throughput drops.

Map DB data into DTOs as cleanly and quickly as possible; run heavy processing after the query finishes when semantics allow. For very large datasets, consider streaming/fetch size/batched processing, always managing resources and transactions accordingly.

### 9.3. Treating Callbacks as Arbitrarily Asynchronous

`JdbcTemplate.query(...)` invokes callbacks synchronously to process an open `ResultSet`. Do not use this pattern:

```java
// Wrong: passing a live ResultSet to a task processed later.
RowCallbackHandler wrongAsync = rs -> {
    executor.submit(() -> consumeResultSet(rs));
};
```

This is pseudocode illustrating a bug, with `executor`/`consumeResultSet` undefined. By the time the task runs, the `ResultSet` may already be closed or the cursor moved to another row; many drivers forbid using a cursor across threads like this. **Right:** read and copy the needed data into immutable DTOs immediately inside the callback; only then hand DTOs off to a queue/executor with appropriate backpressure rules.

### 9.4. Swallowing SQL Errors or Closing Resources You Do Not Own

`JdbcTemplate` translates many JDBC errors into `DataAccessException`; callbacks can let `SQLException` propagate per their interface signatures. Catching `SQLException` yourself and returning a dummy value makes infrastructure failures look like valid data and hides diagnostic information.

Do not call `rs.close()` inside `RowMapper` or `RowCallbackHandler`; the template owns cleanup for the `ResultSet` it created. Do not close `PreparedStatement` before the template finishes using it. For other resources opened by the callback itself, use `try-with-resources` according to actual ownership.

### 9.5. Assuming Every Result-Returning Method Closes Resources Immediately

With APIs like `query(...)` that return a DTO/List after full processing, the template normally finishes cleaning up JDBC resources before returning. However, `queryForStream(...)` returns a lazy stream that can **keep JDBC resources open until the stream is closed**. Proper example:

```java
try (Stream<Book> stream = jdbc.queryForStream(
        "SELECT id, title FROM books ORDER BY id",
        BOOK_MAPPER)) {
    stream.forEach(book -> process(book));
}
```

This is an illustrative snippet requiring `Stream`, `Book`, `BOOK_MAPPER`, `process`, and `jdbc` to be defined. `Stream.close()` via `try-with-resources` is the critical point. Do not pass an open stream across threads or outside a controllable scope and neglect closing it.

### 9.6. Confusing Safety with Correctness During Data Updates

Two threads using the same `JdbcTemplate` to run:

```java
// Snippet illustrating a SQL statement in a DAO:
int updated = jdbc.update(
        "UPDATE inventory SET quantity = quantity - 1 " +
        "WHERE id = ? AND quantity > 0",
        productId);
```

The update may be safe at the `JdbcTemplate` object level, yet **business correctness** still depends on SQL and the DB. For example, checking `updated == 1`, isolation/locking, and transactions if multiple update steps must commit together. Avoid the pattern of "SELECT quantity, subtract in Java, then UPDATE" without proper concurrency control, even when everything uses one thread-safe template.

## 10. Testing to Verify Both Layers of Safety

A useful test does not just assert that the same `JdbcTemplate` bean is used. You must test **callback behavior when multiple calls interleave**, especially that results remain isolated.

### 10.1. What Should Be Verified

| What to verify | Suggested test |
| --- | --- |
| Configured singleton template | Retrieve bean from context; DAOs use the exact injected reference |
| Stateless mapper | Run multiple queries using the same mapper; each query gets its own list |
| Local handler state | Call `titlesByCallback()` repeatedly and concurrently; no data accumulates from prior runs |
| Extractor reads all rows | Test 0, 1, and many rows; results are accurate and the first row is not skipped |
| Callback does not jump cursor | With fixed data, `RowMapper`/`RowCallbackHandler` processes every row accurately |
| JDBC errors handled properly | Bad SQL/duplicate key throws appropriate `DataAccessException`, not fake DTOs |
| JDBC resources closed | Active pool connections return to expected levels; streams are closed |
| Proper transactions | Multi-step updates roll back as expected on mid-way failure |
| Proper DB concurrency | Competing updates do not cause negative stock or lost updates |
| Concurrent queries | Verify each result by ID, do not assert based on thread scheduling order |

Tests can use `@JdbcTest` with real JDBC, H2, or Testcontainers when SQL depends on dialect. To catch races, `CountDownLatch`/`CyclicBarrier` can synchronize start times across repeated runs; **a single passing test run does not prove zero races exist**.

### 10.2. Small Test Verifying Isolated Results

Example using `BookDao` from the program above:

```java
// JUnit 5 snippet, not a complete test file.
@Test
void callbackResultsDoNotLeakAcrossCalls() {
    List<String> first = dao.titlesByCallback();
    List<String> second = dao.titlesByCallback();

    assertEquals(List.of("Java", "Spring", "JDBC"), first);
    assertEquals(List.of("Java", "Spring", "JDBC"), second);
    assertNotSame(first, second);
}
```

Requires JUnit Jupiter, static imports `assertEquals`/`assertNotSame`, and `dao` backed by a DB fixture with the same three rows as the demo. This test confirms the method creates a distinct result list per call, though concurrency tests are still needed to expose bugs that only surface under multithreaded execution.

### 10.3. Using a Connection Pool During Load Testing

The demo uses `DriverManagerDataSource` to minimize dependencies and highlight template responsibilities. In multi-request server applications, `HikariDataSource` or an appropriate pool caps connections and manages timeouts and resources. Verify behavior under load with realistic pool sizes, DB latency, and connection lifetimes; if a pool has 5 connections, 100 tasks using the same template do not mean 100 DB queries execute simultaneously.

## 11. Design Decision Reference Table

| Situation | Safe to share? | Safe approach |
| --- | --- | --- |
| A configured `JdbcTemplate` bean | **Yes** | Inject singleton, never mutate config setters while requests run |
| `RowMapper<Book>` only reading current row, returning new record | **Yes** | Stateless; do not call `rs.next()` |
| `RowCallbackHandler` writing to a fresh `ArrayList` per method invocation | **Yes, per call** | Create list/callback at call site; do not share list across requests |
| `ResultSetExtractor` creating a local `Map` and iterating `rs.next()` | **Reusable** | Keep all accumulators local to each `extractData` call |
| `PreparedStatementSetter` binding only the call's own input | **Yes** | Parameters do not change while callback runs |
| `RowMapper` holding `int count` and `ArrayList` fields | **Unsafe if shared** | Keep no request state on the mapper |
| A `ResultSet`/`PreparedStatement` stored in a singleton DAO | **No** | Keep resources confined within the JDBC callback scope |
| `queryForStream` returning a lazy stream | **Only within controlled lifecycle** | `try-with-resources`, close before leaving scope |
| One singleton `JdbcTemplate` across multiple transactions/threads | **Yes, with proper config** | Transactions follow thread/resource; do not share `Connection`s manually |
| Two queries updating the same record | **Template remains thread-safe** | Ensure correctness via atomic SQL, locking/isolation/transactions |

### Self-Check Questions

1. What does "`JdbcTemplate` thread-safe once configured" guarantee, and what does it not guarantee for callbacks?
2. Why can `static final RowMapper<Book>` be shared safely in the example, whereas `static final UnsafeBookMapper` with mutable fields is still dangerous?
3. When should you use `RowMapper`, `RowCallbackHandler`, and `ResultSetExtractor`? Which one is allowed to call `rs.next()`?
4. Why is a handler holding a local `ArrayList` safe within a single call, even though `ArrayList` is not thread-safe?
5. Why should you not call `jdbcTemplate.setQueryTimeout(...)` per request on a singleton?
6. Does `@Transactional` on thread A automatically propagate the transaction to an `ExecutorService` task on thread B?
7. Why must a stream returned by `queryForStream` be closed, whereas ordinary `query` returns an already-mapped `List`?
8. If two threads share `JdbcTemplate` to decrement inventory, what else must be controlled?

**Key takeaway:** `JdbcTemplate` is designed to be **shared once configured**. Overall safety depends on your callbacks: use stateless `RowMapper`s, allocate accumulators for `RowCallbackHandler`/`ResultSetExtractor` per invocation, avoid misusing the cursor, never let JDBC resources escape their valid lifecycle, never mutate singleton configuration per request, and control transactions/concurrency at the database level.

### Official References

- Spring Framework — JDBC core: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring Framework — JdbcTemplate API (thread-safe once configured): https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html
- Spring Framework — RowMapper API: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/jdbc/core/RowMapper.html
- Spring Framework — RowCallbackHandler API: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/jdbc/core/RowCallbackHandler.html
- Spring Framework — ResultSetExtractor API: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/jdbc/core/ResultSetExtractor.html
