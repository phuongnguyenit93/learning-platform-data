# queryForStream() and the Responsibility of Closing Resource-Holding Streams

When using Spring `JdbcTemplate`, calling `queryForStream()` is convenient for reading data via the Java Stream API without eagerly allocating a large `List`. However, **the returned Stream remains tied to open JDBC resources**: typically a `ResultSet`, `Statement`/`PreparedStatement`, and a `Connection` borrowed from `DataSource`. The Stream consumer must **close the Stream itself after use**, even after exhausting `forEach()`, `count()`, or `toList()`.

The most important rule:

```java
try (Stream<OrderRow> rows = jdbc.queryForStream(
        "SELECT id, amount FROM orders ORDER BY id",
        (rs, rowNum) -> new OrderRow(
            rs.getLong("id"),
            rs.getBigDecimal("amount")
        ))) {
    return rows.limit(100).toList();
} // Stream.close() is called here, even if an exception occurs
```

The snippet above is an **illustrative method body** inside a repository that already has `JdbcTemplate jdbc` and the matching `OrderRow` record; it is not a standalone Java program. The key point is wrapping **the entire Stream processing lifetime** in `try-with-resources`, not just creation.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain why a `Stream<T>` from `JdbcTemplate.queryForStream()` differs from a normal `list.stream()`.
2. Understand when SQL executes, when rows are mapped, and when JDBC resources are released.
3. Use `try-with-resources` properly across all Stream terminal operations, including `limit()`, `findFirst()`, exceptions, and early exits.
4. Distinguish `queryForStream()` from `query(..., RowMapper)`, `RowCallbackHandler`, and `ResultSetExtractor`.
5. Keep Streams within proper transaction boundaries; avoid returning them from `@Transactional` to controllers or passing them across threads.
6. Recognize connection pool exhaustion risks and the limits of `fetchSize`, cursors, and memory accumulation.
7. Write and run a safe Spring Boot + H2 example with deterministic output.

**Context:** Spring Framework 6.x, Java 17+, synchronous JDBC. Spring JDBC has supported `queryForStream` since Spring Framework 5.3. Cursor behavior, buffering, and physical connection limits also depend on the JDBC driver and DBMS.

## 2. Regular Java Streams vs. JDBC-Backed Streams

Not every Java Stream needs closing.

```java
List<String> names = List.of("An", "Binh", "Chi");
long count = names.stream().filter(name -> name.length() > 2).count();
```

The Stream above reads data already in memory. Omitting `close()` normally holds no OS resources. By contrast:

```java
Stream<String> names = jdbc.queryForStream(
    "SELECT name FROM customer ORDER BY name",
    (rs, rowNum) -> rs.getString("name")
);
```

This second Stream reads from a live `ResultSet`. Even before any element is consumed, calling `queryForStream()` already had to create a statement and invoke JDBC query execution. The returned Stream retains access to the result set to map each row as it is consumed.

| Property | `List.stream()` | `JdbcTemplate.queryForStream()` |
| --- | --- | --- |
| Source | Collection already built in RAM | JDBC `ResultSet` and associated resources |
| Needs DB connection kept open? | No | Yes, while the Stream still needs to read |
| Responsibility to close after use? | Normally no special resource | **Yes, must close the Stream** |
| Does `toList()` auto-close source? | No collection closing needed | **Does not automatically call `close()`** |
| Safe to retain after transaction ends? | Yes, if data is fully materialized | Unsafe if still dependent on JDBC resources |
| Use `parallel()`? | Depends on computation and source | Avoid: JDBC `ResultSet`/connection is not an independent multi-thread pipeline |
| Guarantees low memory? | Data is already in RAM | No; driver may buffer all rows and terminal ops may collect into a `List` |

An easily overlooked detail: the Java Stream API has `close()` because `BaseStream` extends `AutoCloseable`, yet **terminal operations are not responsible for closing the Stream**. `findFirst()` or `limit(10).toList()` finishes the pipeline while JDBC resources can remain open.

## 3. Mechanics Under queryForStream()

Useful `JdbcTemplate` overloads:

```java
// Static SQL: uses JDBC Statement.
<T> Stream<T> queryForStream(String sql, RowMapper<T> rowMapper);

// With bound parameters: uses JDBC PreparedStatement.
<T> Stream<T> queryForStream(
    String sql, RowMapper<T> rowMapper, Object... args);

// Explicit PreparedStatement parameter control.
<T> Stream<T> queryForStream(
    String sql, PreparedStatementSetter pss, RowMapper<T> rowMapper);
```

These signatures **illustrate the API shape** (not standalone compilable methods in a project) and can be checked in `JdbcOperations`/`JdbcTemplate` Javadoc. When running with a proper JDBC driver, `RowMapper<T>` converts one `ResultSet` row into a Java value.

### 3.1. Resource Lifecycle

```text
Application/Repository              JdbcTemplate              JDBC Driver/DB
         |                                |                          |
         | queryForStream(SQL, mapper)     |                          |
         +------------------------------->| get Connection           |
         |                                +------------------------->|
         |                                | create Statement         |
         |                                | executeQuery(SQL)        |
         |                                +------------------------->|
         |<------- Stream<T> -------------| open ResultSet           |
         |                                |                          |
         | stream.filter/map/forEach      |                          |
         |      read rows on demand ------+---- ResultSet.next() --->|
         |                                |                          |
         | stream.close()                 |                          |
         +--------------------------------+--- close ResultSet ------|
         |                                |--- close Statement ------|
         |                                |--- release Connection --->|
         |                                |                          |
```

In `JdbcTemplate`'s implementation, the Stream is built from a `ResultSet` spliterator and registers cleanup work via `onClose(...)`. When the Stream closes, Spring closes the `ResultSet`, cleans up parameters if needed, closes the statement, and calls `DataSourceUtils.releaseConnection(...)`.

This leads to three key points:

- **SQL execution begins before returning the Stream.** Do not interpret "lazy" as "the DB does not receive the query until `count()`"; row mapping happens incrementally as the Stream is consumed.
- **No guarantee the driver fetches one row at a time.** Drivers may prefetch or buffer the whole result; streaming large datasets efficiently requires checking `fetchSize`, cursors, transactions, and DBMS support.
- **Closing the Stream does not always close the physical connection immediately.** Outside a transaction, `DataSourceUtils.releaseConnection` normally returns the logical connection to the pool (or closes the physical connection if unpooled). Inside an active Spring transaction, the transaction manager may retain the connection until commit/rollback.

Do not use `Stream.onClose()` to manually close a `ResultSet` or `Connection` you do not own; Spring already registers cleanup. Application code's job is to **call `close()` on the returned Stream**, typically via `try-with-resources`.

## 4. Right Pattern: try-with-resources as Ownership Boundary

`OrderRepository.java` below is a Java 17+ class for a Spring application with a `JdbcTemplate` bean and an `orders(id, customer_id, amount)` table. It compiles with Spring JDBC and needs a DB/table to run successfully:

```java
import java.math.BigDecimal;
import java.util.List;
import java.util.stream.Stream;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public final class OrderRepository {
    private final JdbcTemplate jdbc;

    public OrderRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public record OrderRow(long id, BigDecimal amount) {}

    public List<OrderRow> firstHundredFor(long customerId) {
        String sql = """
            SELECT id, amount
              FROM orders
             WHERE customer_id = ?
             ORDER BY id
            """;

        try (Stream<OrderRow> rows = jdbc.queryForStream(
                sql,
                (rs, rowNum) -> new OrderRow(
                    rs.getLong("id"),
                    rs.getBigDecimal("amount")
                ),
                customerId)) {
            return rows.limit(100).toList();
        }
    }
}
```

**Why is this right?**

1. `jdbc` is a shared singleton repository dependency, while `rows` lives strictly inside **one method invocation**.
2. `?` binds `customerId`, preventing SQL injection from string concatenation.
3. `limit(100)` stops after at most 100 Java elements; on early stop, remaining rows may never be read.
4. `return` still executes automatic `close()` before returning from the method, via the Java-generated `finally` of `try-with-resources`.
5. The returned value is a mapped `List<OrderRow>`, no longer tied to an open `ResultSet`.
6. `OrderRow` contains materialized Java types; it holds no `Connection` or `ResultSet`.

**Limitation:** Java's `limit(100)` is not equivalent to SQL `LIMIT 100` or `FETCH FIRST 100 ROWS ONLY`. The DB may still process/produce many rows to return; placing an appropriate limit in SQL alongside a deterministic `ORDER BY` is more optimal. The example uses `limit(100)` to demonstrate **short-circuit + close**.

### 4.1. Must Close Even When the Stream Is Exhausted

```java
try (Stream<OrderRepository.OrderRow> rows = jdbc.queryForStream(
        "SELECT id, amount FROM orders ORDER BY id",
        (rs, rowNum) -> new OrderRepository.OrderRow(
            rs.getLong("id"), rs.getBigDecimal("amount")
        ))) {
    long count = rows.count();
    System.out.println(count);
}
```

This snippet belongs inside a method with `JdbcTemplate jdbc` and the `orders` table. Because `count()` is a terminal operation, the Stream cannot run another pipeline; yet **only exiting the `try` block calls `close()`**. The same holds for `forEach()`, `toList()`, `reduce()`, `collect()`, `findFirst()`, `anyMatch()`, and all other terminal operations.

### 4.2. Must Close When an Exception Occurs

```java
try (Stream<OrderRepository.OrderRow> rows = jdbc.queryForStream(
        "SELECT id, amount FROM orders",
        (rs, rowNum) -> new OrderRepository.OrderRow(
            rs.getLong("id"), rs.getBigDecimal("amount")
        ))) {
    rows.forEach(row -> {
        if (row.amount().signum() < 0) {
            throw new IllegalStateException("Negative amount: " + row.id());
        }
    });
}
```

If the callback throws `IllegalStateException`, the JVM still invokes `rows.close()` when leaving the `try` block. Mapper or JDBC errors while reading the Stream can occur **when the terminal operation runs**, not necessarily during `queryForStream()`. Wrapping that entire phase in `try-with-resources` protects the resources.

### 4.3. Without try-with-resources, Use finally

If API constraints prevent using `try-with-resources` directly, ensure `close()` in `finally`:

```java
Stream<String> stream = jdbc.queryForStream(
    "SELECT name FROM customer",
    (rs, rowNum) -> rs.getString("name")
);
try {
    stream.forEach(System.out::println);
} finally {
    stream.close();
}
```

This is a **snippet inside a method with `jdbc`**; in resource safety it matches `try-with-resources`, though it is more verbose and easier to forget. Prefer the first form.

## 5. Wrong Patterns That Risk Holding Connections

### 5.1. Calling toList() and Discarding the Stream

```java
// WRONG: toList() does not automatically close a JDBC-backed Stream.
public List<String> allNames() {
    return jdbc.queryForStream(
        "SELECT name FROM customer",
        (rs, rowNum) -> rs.getString("name")
    ).toList();
}
```

If `DataSource` is pooled, the logical connection can remain marked active and fail to return to the pool promptly. Even after all elements are collected, **never rely on GC/finalizers to clean up resources**.

Fix:

```java
public List<String> allNames() {
    try (Stream<String> names = jdbc.queryForStream(
            "SELECT name FROM customer",
            (rs, rowNum) -> rs.getString("name"))) {
        return names.toList();
    }
}
```

Both snippets are **method bodies** for a repository with `JdbcTemplate jdbc` and appropriate Java imports, not standalone Java files.

### 5.2. Short-Circuiting with findFirst()/anyMatch()/limit()

```java
// WRONG: even after finding an item, the Stream still needs close().
String first = jdbc.queryForStream(
    "SELECT name FROM customer ORDER BY id",
    (rs, rowNum) -> rs.getString("name")
).findFirst().orElse("(none)");
```

Fix:

```java
try (Stream<String> names = jdbc.queryForStream(
        "SELECT name FROM customer ORDER BY id",
        (rs, rowNum) -> rs.getString("name"))) {
    String first = names.findFirst().orElse("(none)");
    // Use first within this scope or return a String value.
}
```

Operations needing only one row should prefer bounded SQL or `queryForObject` matching a 0/1 row expectation. `queryForObject` is not equivalent unless you are certain at most one row exists: it enforces different cardinality semantics and throws if the result count violates expectations.

### 5.3. Storing a Stream in a Singleton Field

```java
// WRONG: retaining a JDBC Stream across requests or threads.
private Stream<Customer> cachedRows;
```

A Stream is **single-use**, stateful during iteration, and resource-owning. Never reuse it as a cache. If caching is needed, materialize detached DTOs/values within the Stream scope and cache the JDBC-independent copy with proper invalidation and memory bounds.

### 5.4. Returning ResultSet/Stream to Another Layer Without a Close Contract

```java
// WRONG: who is responsible for closing? Is the transaction still alive?
public Stream<Customer> findAllOpen() {
    return jdbc.queryForStream(
        "SELECT id, name FROM customer",
        (rs, rowNum) -> new Customer(
            rs.getLong("id"), rs.getString("name")
        )
    );
}
```

This is an **anti-pattern illustrating risk**; it is not a recommended repository API. If returning a Stream is mandatory, the contract must explicitly state that the caller owns the resource and **must close it**, while ensuring the transaction remains valid during consumption; it is usually better to use a callback or return completed DTOs/Lists/responses so lifecycle stays in the repository/service.

### 5.5. Mistakenly Thinking Exhausting Rows "Naturally Closes" the Stream

`ResultSet.next()` returning `false` at the end of data does not mean `ResultSet.close()` ran. Reaching the end of elements is **iteration state**; closing is **resource release**. That is why the following still requires `try`:

```java
try (Stream<String> s = jdbc.queryForStream(
        "SELECT name FROM customer",
        (rs, rowNum) -> rs.getString("name"))) {
    s.forEach(System.out::println);
}
```

## 6. How Does queryForStream() Differ from query(..., RowMapper)?

With `query(sql, rowMapper)`, `JdbcTemplate` performs all reading and mapping within the call; by the time it returns `List<T>`, JDBC resources have normally been cleaned up.

With `queryForStream()`, `JdbcTemplate` **transfers close ownership** to the Stream recipient because data reading continues after the initiating call returns.

| API | Return type | When JDBC resources are cleaned up | Memory |
| --- | --- | --- | --- |
| `query(sql, RowMapper<T>)` | `List<T>` | When the call finishes or errors, managed by template. | Can hold entire result in a List. |
| `queryForStream(sql, RowMapper<T>)` | `Stream<T>` | When **caller calls close()**; template registers cleanup in onClose. | Can process element-by-element, though depends on driver and terminal op. |
| `query(sql, RowCallbackHandler)` | `void` | When callback finishes inside the call, managed by template. | Can keep memory small if handler does not accumulate. |
| `query(sql, ResultSetExtractor<R>)` | `R` | After extractor returns, managed by template. | Controlled by extractor; returns no live JDBC handle. |

### 6.1. RowCallbackHandler Is Simpler When Only Processing Row by Row

If the goal is iterating and processing rows **without returning a Stream**, you can use `RowCallbackHandler`:

```java
import java.util.concurrent.atomic.LongAdder;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowCallbackHandler;

public final class CustomerCounter {
    private final JdbcTemplate jdbc;

    public CustomerCounter(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public long countNames() {
        LongAdder total = new LongAdder();

        jdbc.query(
            "SELECT name FROM customer",
            (RowCallbackHandler) rs -> {
                if (rs.getString("name") != null) {
                    total.increment();
                }
            }
        );
        return total.sum();
    }
}
```

`RowCallbackHandler` receives each row positioned by `JdbcTemplate`, **without calling `rs.next()` itself**. Code does not close a Stream because no Stream is returned. Note that the driver may still buffer rows; "row-by-row processing" does not guarantee low memory across every DBMS.

### 6.2. ResultSetExtractor for Direct ResultSet Control

`ResultSetExtractor<R>` lets you iterate `ResultSet` yourself inside the callback and return a JDBC-detached result:

```java
Long total = jdbc.query(
    "SELECT amount FROM orders",
    rs -> {
        long count = 0;
        while (rs.next()) {
            if (rs.getBigDecimal("amount") != null) {
                count++;
            }
        }
        return count;
    }
);
```

This snippet is inside a method with `jdbc` and the `orders` table. With an extractor, the callback is permitted to call `rs.next()`; with `RowCallbackHandler` it is not. **Never return `rs` from the callback**, because `JdbcTemplate` closes resources when the call ends.

## 7. Spring Transactions: Streams Must Be Consumed Within Scope

In Spring's imperative JDBC model with `DataSourceTransactionManager` or `JdbcTransactionManager`, transaction resources are typically bound to the current thread. `JdbcTemplate` and `DataSourceUtils` reuse the bound connection when operating inside that transaction.

### 7.1. Right Pattern: Open, Consume, and Close the Stream Inside @Transactional

```java
import java.util.stream.Stream;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public final class CustomerReportService {
    private final JdbcTemplate jdbc;

    public CustomerReportService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(readOnly = true)
    public long countActive() {
        try (Stream<Long> ids = jdbc.queryForStream(
                "SELECT id FROM customer WHERE active = ?",
                (rs, rowNum) -> rs.getLong("id"),
                true)) {
            return ids.count();
        }
    }
}
```

This snippet requires importing `org.springframework.jdbc.core.JdbcTemplate`, matching DB tables/columns, and configured transaction management. The method must be invoked **through the Spring proxy** for `@Transactional` to take effect in proxy mode. The transaction-managed connection stays properly scoped; the Stream closes before the transaction completes.

With PostgreSQL JDBC, to actually stream via cursors when `fetchSize` is positive, a standard requirement is that the connection has auto-commit disabled inside an active transaction. `@Transactional(readOnly = true)` helps establish the transaction boundary, though you must still verify the driver, `ResultSet` type, and execution mode. `queryForStream()` by itself **does not guarantee PostgreSQL buffers only one batch**.

### 7.2. Risky Pattern: @Transactional Returning an Unread Stream

```java
// RISKY: the method's transaction may end before the caller iterates.
@Transactional(readOnly = true)
public Stream<Customer> openCustomers() {
    return jdbc.queryForStream(
        "SELECT id, name FROM customer",
        (rs, rowNum) -> new Customer(
            rs.getLong("id"), rs.getString("name")
        )
    );
}
```

In this case, the Spring transaction proxy normally ends the transaction immediately after the method returns **the Stream object**; the caller only begins reading elements afterward. If the DB/driver requires the connection/cursor to remain inside that transaction, errors, unexpected results, or overly long-lived resources can follow. Callers can also easily forget `close()`.

**Better design:** have the service perform both querying and processing within the same transactional method and return `List<DTO>`, `long`, an aggregated summary, or run a row-processing callback before exiting the transaction. If a truly lazy/streaming external API is required, design a dedicated resource and transaction contract instead of expecting `@Transactional` on a Stream-returning method to span the caller's usage.

### 7.3. Does Closing a Stream Inside a Transaction Return the Connection to the Pool Immediately?

Not necessarily. `Stream.close()` invokes `DataSourceUtils.releaseConnection(...)`, but if the connection **is bound to the active Spring transaction**, Spring retains it until commit/rollback. That is correct behavior so subsequent JDBC operations can share the transaction. Outside a transaction, the logical connection normally returns to the pool immediately when the Stream closes.

Do not measure "did the Stream close?" solely by watching Hikari's active connection count drop immediately inside an active transaction. Account for **both the Stream lifecycle and the transaction lifecycle**.

## 8. Do Not Pass JDBC Streams to Other Threads or Call parallel()

The code below is an **intentionally unsafe** example:

```java
Stream<Customer> rows = jdbc.queryForStream(
    "SELECT id, name FROM customer",
    (rs, rowNum) -> new Customer(rs.getLong("id"), rs.getString("name"))
);
executor.submit(() -> rows.forEach(System.out::println));
```

This illustrative snippet is not a standalone program. It lets the Stream/JDBC connection outlive the calling scope; the ThreadLocal transaction context on the creating thread does not automatically follow to the worker thread. Without clear ownership rules, it can be left unclosed or closed on another thread while still in use.

Likewise, **never use `rows.parallel()` to "speed up JDBC queries"**. One `ResultSet` and one JDBC `Connection` are not independent query pipelines per worker; drivers vary in concurrency rules and ordering/callbacks may be unsafe. For parallel computation, **materialize JDBC-detached DTOs**, close the Stream, and process the list in parallel—or split queries into independent DB tasks with separate transactions/connections sized appropriately for the pool.

Safer code:

```java
List<Customer> customers;
try (Stream<Customer> rows = jdbc.queryForStream(
        "SELECT id, name FROM customer",
        (rs, rowNum) -> new Customer(
            rs.getLong("id"), rs.getString("name")
        ))) {
    customers = rows.toList();
}
// JDBC resources are closed; only plain Java DTO processing follows.
customers.parallelStream().forEach(this::processCustomer);
```

This snippet also belongs in a class defining `processCustomer(Customer)`; use parallel streams only when CPU workload and item counts justify it. If `customers` is huge, materializing everything can strain memory; consider batching/cursors under an appropriate architecture.

## 9. Runnable Spring Boot Example: Closing Before the Next Query

The Java 17+ example below defines a complete Spring Boot application using H2 to create three rows, read the first two via `queryForStream()`, and continue querying after closing the Stream. The pool is capped at one connection to highlight why resources must not be held too long; the program **does not intentionally leak connections**.

### 9.1. Gradle

`build.gradle` in a minimal Spring Boot project:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
version = '1.0.0'

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
spring.main.web-application-type=none
spring.datasource.url=jdbc:h2:mem:stream_demo;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.datasource.hikari.maximum-pool-size=1
spring.datasource.hikari.connection-timeout=2000
```

`connection-timeout=2000` is **2,000 milliseconds** to wait when borrowing a connection from Hikari, not a query timeout. Setting pool size to one connection merely makes resource lifecycle behavior obvious in the demo; production pool sizing depends on instance count, concurrency, and DB limits. `DB_CLOSE_DELAY=-1` is an H2 option for in-memory demos.

### 9.2. Complete Java Application

File `src/main/java/example/StreamClosingApplication.java`:

```java
package example;

import java.util.List;
import java.util.stream.Stream;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootApplication
public class StreamClosingApplication {
    public static void main(String[] args) {
        SpringApplication.run(StreamClosingApplication.class, args);
    }

    public record Item(int id, String name) {}

    @Bean
    CommandLineRunner demo(JdbcTemplate jdbc) {
        return args -> {
            jdbc.execute("""
                CREATE TABLE items (
                    id INTEGER PRIMARY KEY,
                    name VARCHAR(50) NOT NULL
                )
                """);

            jdbc.update("INSERT INTO items(id, name) VALUES (?, ?)", 1, "Alpha");
            jdbc.update("INSERT INTO items(id, name) VALUES (?, ?)", 2, "Beta");
            jdbc.update("INSERT INTO items(id, name) VALUES (?, ?)", 3, "Gamma");

            List<String> firstTwo;
            try (Stream<Item> items = jdbc.queryForStream(
                    "SELECT id, name FROM items WHERE id >= ? ORDER BY id",
                    (rs, rowNum) -> new Item(
                        rs.getInt("id"), rs.getString("name")
                    ),
                    1)) {
                firstTwo = items
                    .limit(2)
                    .map(Item::name)
                    .toList();
            } // Stream closes even though limit stopped early.

            System.out.println("firstTwo=" + firstTwo);

            try (Stream<Item> items = jdbc.queryForStream(
                    "SELECT id, name FROM items",
                    (rs, rowNum) -> new Item(
                        rs.getInt("id"), rs.getString("name")
                    ))) {
                System.out.println("streamCount=" + items.count());
            }

            Integer tableCount = jdbc.queryForObject(
                "SELECT COUNT(*) FROM items", Integer.class
            );
            System.out.println("tableCount=" + tableCount);
        };
    }
}
```

Run with the Gradle wrapper from the project directory:

```bash
./gradlew bootRun
```

On Windows PowerShell, run `.\gradlew.bat bootRun`. With Java 17+, downloaded dependencies, and H2 running, **the lines produced by `System.out` in the program** are:

```text
firstTwo=[Alpha, Beta]
streamCount=3
tableCount=3
```

Spring Boot/Hikari may also print logs before and after those three lines. Elements are ordered by `ORDER BY id` in the first query, so `firstTwo` is deterministic; `count()` merely counts and does not depend on row order. A pool size of one connection still allows subsequent queries because each Stream closes before the next statement runs.

**What does this demo prove?** Proper usage of the Java Stream API with `try-with-resources` and continuing to use `JdbcTemplate` once processing finishes. It does **not** prove that the driver fetches batches incrementally from a server or that pool hold time is optimal; verifying those requires metrics/profiling on the real driver/DB.

## 10. How Can an Unclosed Stream Exhaust a Connection Pool?

Suppose a Hikari pool has at most 4 connections and a request executes:

```java
// WRONG: stream is never closed.
Stream<String> rows = jdbc.queryForStream(
    "SELECT name FROM items",
    (rs, rowNum) -> rs.getString("name")
);
rows.findFirst(); // terminal operation ends, resources stay open
```

If each request repeats this pattern without returning the connection to the pool promptly, the pool can accumulate 4 active connections, and subsequent requests block or time out waiting to borrow a connection. Exact behavior depends on the pool/driver and runtime lifecycle, but the risk is serious enough to always enforce closing.

```text
Request A --- queryForStream ---> Connection #1 held
Request B --- queryForStream ---> Connection #2 held
Request C --- queryForStream ---> Connection #3 held
Request D --- queryForStream ---> Connection #4 held
Request E --- getConnection() -> waits -> connectionTimeout
                            (if the 4 connections are not returned)
```

Typical symptoms: `HikariPool-... - Connection is not available, request timed out ...`; active count near maximum, low idle, rising pending/waiting threads, degraded latency. Never just increase `maximumPoolSize` as a "fix", because the resource lifetime bug remains.

### 10.1. How to Measure and Find Long-Held Resources

- **HikariCP:** monitor active, idle, pending, total connections, and acquisition timeouts.
- **Spring Boot Actuator/Micrometer:** use `hikaricp.*` metrics when enabled and configured.
- **Thread dumps / tracing:** inspect threads holding transactions, callback execution time, SQL, and where Streams are created.
- **Leak detection:** Hikari's `leakDetectionThreshold` can log stack traces when a connection is held past a threshold, though it is a **suspicion warning**—it neither closes the connection nor proves a leak definitively.
- **DB monitoring:** inspect session counts, long-running transactions, locks, cursors, and query durations.

Do not assume rising active counts always mean a leak: a legitimate long `@Transactional` or slow query also holds a connection. Correlate metrics against `close()`/commit/rollback boundaries and request paths. Inside a transaction, a closed Stream still may not reduce active counts until the transaction manager finishes the transaction.

## 11. Memory, fetchSize, and True Streaming

`queryForStream()` can avoid immediately allocating a `List`, yet **it does not automatically guarantee low memory usage**.

- JDBC drivers can buffer the entire `ResultSet`; server-side cursor mechanics vary by DBMS and connection settings.
- `Stream.toList()`, `sorted()`, or `collect(toList())` can still accumulate huge numbers of items; `sorted()` generally must hold data to sort.
- Java's `limit(n)` reduces items consumed in Java, while the DB may still process many rows; prefer `ORDER BY ... LIMIT n`/`FETCH FIRST n ROWS ONLY` when semantically valid and supported by the DB.
- `fetchSize` is only a **hint to the JDBC driver**. With PostgreSQL JDBC, positive fetch size usually requires a transaction/`autoCommit=false` and a forward-only result set to use cursor fetching; otherwise the driver may load everything.
- `JdbcTemplate.setMaxRows` caps rows returned via the JDBC ResultSet; it does not replace SQL pagination and does not guarantee the DB processes only that many rows.
- `JdbcTemplate.setQueryTimeout` sets a statement timeout, not an overall deadline for the entire Stream pipeline—especially slow callbacks or network I/O after the SQL runs.

If exporting millions of rows to a file or HTTP response, consider short batches, SQL/keyset pagination, driver-verified cursors, timeouts, and early cancellation; avoid holding a transaction/connection across a long HTTP connection that a client may drop abruptly without reliable cleanup.

### 11.1. Example Processing Row by Row Within Close Scope

```java
try (Stream<OrderRepository.OrderRow> rows = jdbc.queryForStream(
        "SELECT id, amount FROM orders ORDER BY id",
        (rs, rowNum) -> new OrderRepository.OrderRow(
            rs.getLong("id"), rs.getBigDecimal("amount")
        ))) {
    rows.forEach(row -> {
        // Process quickly; avoid holding the connection during slow network I/O.
        validateAmount(row);
    });
}
```

This snippet belongs in a class with `JdbcTemplate jdbc` and `validateAmount(...)`. If you need to call external network APIs, dispatch batches/messages after reading and closing the Stream, or design a job with separate transaction boundaries rather than holding a ResultSet and connection while waiting on external systems.

## 12. Exception Handling and Cancellation

Errors can occur at several points:

1. **When calling `queryForStream()`:** acquiring connection, preparing statement, or running SQL fails. `JdbcTemplate` translates JDBC errors per its mechanism; if no Stream was returned, the caller has no Stream to close.
2. **While consuming the Stream:** mapper reads a wrong column, driver fails on a later `ResultSet.next()`, or `filter()/map()/forEach()` throws. The caller needs `try-with-resources` to close on early exit.
3. **During close:** the driver may report an error when releasing resources. Under Java's `try-with-resources` semantics, the primary exception is preserved and close errors are attached as suppressed exceptions. `JdbcTemplate` has its own cleanup handling, so exact exception types depend on Spring internals and the driver.

Safe example:

```java
public List<String> loadNames() {
    try (Stream<String> names = jdbc.queryForStream(
            "SELECT name FROM customer",
            (rs, rowNum) -> rs.getString("name"))) {
        return names
            .filter(name -> name != null && !name.isBlank())
            .toList();
    }
}
```

If `filter()` throws or execution is interrupted during processing, `try` attempts to close the Stream. For `CompletableFuture` cancellation or aborted HTTP requests, **do not rely on Java Streams to self-clean** if the executing thread keeps running; the application must actively terminate the scope and run cleanup.

**Never auto-retry every operation after a JDBC error.** Simple read-only queries may be retried under an appropriate policy, whereas for operations with side effects, network/timeout errors do not prove the DB rolled back the transaction; evaluate idempotency and transaction state.

## 13. Why Not Return a Stream Directly from a Controller?

A common problematic design:

```java
// RISKY: Controller returns a JDBC-backed Stream to the serialization layer.
@GetMapping("/customers")
public Stream<CustomerDto> customers() {
    return repository.openCustomers();
}
```

Spring MVC may serialize after the controller method returns, via hooks/timings outside the transaction you assumed was still alive. Ownership of closing the Stream on completion, error, or client disconnect becomes unclear; it also leaks JDBC resources across architectural layers.

Normally, controllers should return **materialized DTOs or pages**:

```java
@GetMapping("/customers")
public List<CustomerDto> customers() {
    return service.listCustomers(100);
}
```

Here `service.listCustomers` opens, consumes, and closes the Stream in an appropriate scope before returning data. This controller snippet assumes service, DTO, annotations, and imports exist. If large HTTP streaming is genuinely required, design an explicit streaming pipeline with clear resource lifecycle, cancellation, and backpressure rather than returning a raw JDBC `Stream<T>`.

## 14. Common Mistakes and Fixes

| Wrong pattern or assumption | Consequence | Fix |
| --- | --- | --- |
| `jdbc.queryForStream(...).toList()` discarding the Stream | `toList()` does not auto-close; risks leaking ResultSet/Connection. | `try (Stream<T> s = jdbc.queryForStream(...)) { return s.toList(); }` |
| Calling `findFirst()` or `limit(10)` and assuming resources are freed | Short-circuiting only stops iteration. | Put the entire pipeline inside `try-with-resources`. |
| Returning a JDBC Stream from `@Transactional` and iterating in caller | Transaction ends before iteration; resources/cursors not guaranteed valid. | Consume and close inside the same transactional method, return DTOs. |
| Returning a JDBC Stream directly through Spring MVC JSON | Resource lifetime outlives controller scope; unclear cleanup. | Materialize page/DTO or design an explicit streaming lifecycle. |
| Storing a Stream in a singleton/cache | Single-use Stream gets shared; holds JDBC resources. | Cache materialized data, never Stream/ResultSet. |
| Passing a Stream to an executor/another thread | Thread-bound transaction does not follow; JDBC state used cross-thread. | Pass DTOs, close source first, open separate query in task if needed. |
| Calling `parallel()` on a JDBC Stream | Concurrency on ResultSet/connection is unsafe. | Iterate sequentially; if parallelizing, use separate queries/connections or DTOs after closing. |
| Omitting `close()` because all rows were read | Finishing iteration is not releasing resources. | Always close, even after `count()`/`forEach()`. |
| Increasing `maximumPoolSize` when pool exhausts | Underlying leak/long-hold bug remains. | Measure active/pending, fix unclosed Streams and long transactions. |
| Setting `fetchSize=100` and assuming low RAM | Driver may still buffer; `toList()` still collects all items. | Verify cursor/driver, pipeline, resources, and result structure. |

## 15. Self-Check Questions

**Question 1.** In `try (Stream<Row> rows = jdbc.queryForStream(...)) { rows.count(); }`, is closing still needed after `count()`?

**Answer:** Yes. `count()` is a terminal operation, but it does not call `close()`. Exiting the `try-with-resources` block guarantees close is invoked.

**Question 2.** Why can `jdbc.queryForStream(...).findFirst()` exhaust a connection pool even when reading only one row?

**Answer:** The Stream can still hold ResultSet/Statement/Connection after stopping early. Without closing, the borrowed pool connection is not returned promptly, especially across repeated requests.

**Question 3.** Does `queryForStream()` send SQL to the DB when called, or only when `toList()` runs?

**Answer:** In `JdbcTemplate`'s implementation, the JDBC statement is already executed before the Stream is returned. Row reading and mapping occur during consumption; the driver may prefetch/buffer earlier.

**Question 4.** Does closing a Stream inside `@Transactional` necessarily return the physical connection to the pool immediately?

**Answer:** No. `Stream.close` releases the ResultSet/Statement and calls Spring's `releaseConnection`; the connection may remain held by the transaction manager until commit/rollback.

**Question 5.** Should a repository return a JDBC-backed Stream through a controller for Spring MVC to serialize directly?

**Answer:** Generally no. Transaction/close boundaries become unclear; return materialized data or design a dedicated streaming pipeline with cleanup on completion/error/cancellation.

**Question 6.** How do `queryForStream()` and `query(..., RowMapper)` differ in resource management?

**Answer:** `query(..., RowMapper)` returns a fully read `List<T>` and the template cleans up JDBC resources before returning. `queryForStream()` returns a resource-holding Stream that the caller must close.

**Question 7.** Does `fetchSize=100` guarantee at most 100 records are held in RAM?

**Answer:** No. It is a hint; the driver may still buffer, and terminal operations may accumulate. Verify against the real DB driver and inspect how consumers process results.

## 16. Code Review Checklist

- [ ] Every `JdbcTemplate.queryForStream()` call has a clear owner responsible for calling `Stream.close()`.
- [ ] `try-with-resources` wraps **both Stream creation and Stream consumption**, even when pipelines short-circuit.
- [ ] Never assume a terminal operation closes the Stream automatically.
- [ ] Repositories/services never store live `Stream`, `Connection`, `Statement`, or `ResultSet` in singleton fields or caches.
- [ ] Never return JDBC-backed Streams across transaction, controller, async, or thread boundaries without a cleanup contract.
- [ ] When using `@Transactional`, the Stream is consumed and closed before the transaction ends.
- [ ] Use `PreparedStatement`/parameter binding whenever queries take dynamic inputs.
- [ ] For large datasets, analyze `fetchSize`, cursors, buffering, batching/pagination, transaction lifecycle, and operation duration.
- [ ] Monitor pool active/pending/timeout metrics and distinguish leaks from legitimate long-running transactions.
- [ ] Errors and cancellations still pass through resource cleanup; never rely on `System.gc()` or finalizers.

## 17. References

- [Spring Framework — JdbcTemplate API](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html): `queryForStream` returning a Stream that must be closed; overloads and `RowMapper`.
- [Spring Framework — JdbcTemplate source](https://github.com/spring-projects/spring-framework/blob/main/spring-jdbc/src/main/java/org/springframework/jdbc/core/JdbcTemplate.java): how `onClose` is registered to close ResultSet/Statement and call `DataSourceUtils.releaseConnection`.
- [Java SE 21 — Stream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Stream.html): resource-bearing Streams, terminal operations, and try-with-resources.
- [Spring Framework — DataSourceUtils](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/jdbc/datasource/DataSourceUtils.html): transaction-aware connection release.
- [pgJDBC — Query processing](https://jdbc.postgresql.org/documentation/query/): cursors/fetch size and driver requirements.

**Key takeaway:** `queryForStream()` hands you a JDBC reading pipeline **that still holds resources**. Ending the pipeline does not clean up resources. Open, process, and **close the Stream within the same explicit scope**; inside Spring transactions, finish the Stream before the transaction ends. Return only JDBC-detached values/DTOs outside that scope.
