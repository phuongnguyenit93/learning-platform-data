# JdbcTemplate Manages Resource Creation and Release by Contract

## 1. Learning Objectives and Scope

In Spring Framework, `JdbcTemplate` is the central class for using JDBC without writing repetitive boilerplate to obtain a `Connection`, create a `Statement`, iterate a `ResultSet`, catch `SQLException`, and clean up resources after every operation. However, "Spring closes everything automatically" is **too broad** of an understanding: `JdbcTemplate` only manages resources according to the **API contract** it owns. Resources created by callbacks themselves, a `Stream` returned for the caller to consume, and connection lifecycles within transactions must be handled with the right responsibility.

This article explains in detail:
- When `Connection`, `Statement`/`PreparedStatement`, and `ResultSet` are created and released.
- The path of `JdbcTemplate` through `DataSource`, `DataSourceUtils`, and Spring transactions.
- Distinguishing **closing a logical connection**, **returning a connection to the pool**, and **closing a physical connection**.
- Who closes resources for `RowMapper`, `ResultSetExtractor`, `RowCallbackHandler`, `PreparedStatementCallback`, and `ConnectionCallback`.
- The special case of `queryForStream`: **the caller must close the `Stream`**.
- Resource cleanup when SQL or callbacks fail, exception translation, and common leak pitfalls.
- How to write repositories, services, and tests to verify resource contracts and avoid holding connections for too long.

**Scope:** Blocking JDBC in Spring Framework 6.x, Spring Boot 3.x, and Java 17+. When referring to `DataSourceTransactionManager`/`JdbcTransactionManager`, it is assumed the transaction manager and `JdbcTemplate` use the same `DataSource`. JPA/Hibernate and R2DBC have their own resource mechanisms and are not the focus of this article.

## 2. The Three JDBC Resource Types and Their Lifecycles

In raw JDBC, the typical flow is:

```text
DataSource
    │ getConnection()
    ▼
Connection
    │ prepareStatement(sql)
    ▼
PreparedStatement / Statement
    │ executeQuery()
    ▼
ResultSet
    │ next(), getXxx()
    ▼
Application objects/DTOs
```

**`Connection`** represents a JDBC session to the DB (usually a handle/proxy from a pool). It holds state such as auto-commit, isolation, SQL warnings, and may be participating in a transaction.

**`Statement`/`PreparedStatement`** is the SQL execution resource; `PreparedStatement` typically holds bound parameters, timeout, fetch size, and can produce one or more `ResultSet`s depending on the API.

**`ResultSet`** represents a result row set bound to an active statement/connection. An open `ResultSet` is not an immutable DTO; it has a lifecycle and usually requires JDBC driver/server resources.

If writing raw JDBC, the application must close opened resources (typically in reverse order: `ResultSet` → `Statement` → `Connection`), even when mapping throws an error. Java `try-with-resources` handles this for `AutoCloseable`.

**With `JdbcTemplate`, responsibilities are separated:** the application supplies SQL, parameters, and mapping/logic; the template performs most JDBC management. Still, you need to understand who creates which resource, who owns it, and when a caller receives a "live" result like a `Stream`.

## 3. Ownership Contract Table: Who Creates and Who Releases?

| Resource or API | Party That Typically Creates/Acquires | Who Must Release? | Notes |
|---|---|---|---|
| `Connection` of a standard `JdbcTemplate.query/update` operation | `JdbcTemplate` acquires via `DataSourceUtils` | `JdbcTemplate` invokes release logic; transaction/pool decides whether to actually close right then | Do not call `connection.close()` from `RowMapper` |
| `PreparedStatement` of a standard `JdbcTemplate.query/update` operation | Template based on SQL and standard callbacks | Template | Do not manually close the statement passed by the template to a callback |
| `ResultSet` created by a standard `query(...)`, passed to `RowMapper`/`ResultSetExtractor` | Template executing the statement | Template | Read/map inside the callback; do not return raw `ResultSet` outward |
| `Statement` supplied by the template to `StatementCallback` | Template | Template | Callback must not close the provided statement |
| `PreparedStatement` supplied by the template to `PreparedStatementCallback` | Template | Template | Callback must close any **self-opened `ResultSet`** via `executeQuery()` if applicable |
| `PreparedStatement` created manually inside `ConnectionCallback` | Callback | **Callback** | Use `try-with-resources` |
| `ResultSet` created manually inside `ConnectionCallback` | Callback | **Callback** | Close within scope before the callback finishes |
| `Connection` passed into `ConnectionCallback` | Template | Template/transaction manager | Callback must not close this connection |
| `Stream<T>` from `JdbcTemplate.queryForStream` | Template returns it to caller | **Caller closes the stream** | Use `try (Stream<T> rows = ...)` |
| `Connection` acquired manually from `DataSourceUtils.getConnection` | Low-level application code | Application calls `DataSourceUtils.releaseConnection` | Must use the **same `DataSource`**; do not close a transactional connection directly |

Among standard callbacks, the Spring documentation emphasizes the case of a **ResultSet opened by the callback itself**: the template generally closes statements it creates, but you must not infer that doing so will always release a ResultSet opened separately by the callback, especially when statement/connection pooling mechanisms are in play. Close that ResultSet inside the callback using `try-with-resources`.

**Simple rule: for resources handed to you by an API just to use, follow the API's contract; for resources you create yourself, you are responsible for closing them, unless the contract transfers ownership to another party.**

## 4. Basic Execution Cycle of JdbcTemplate

For a typical `JdbcTemplate.query(sql, rowMapper, args)`, the logical diagram is as follows:

```text
Repository calls JdbcTemplate.query(...)
  1. DataSourceUtils.getConnection(dataSource)
         │
         ├─ If an appropriate Spring JDBC transaction is active:
         │    get the connection bound to the current transaction
         └─ Otherwise: get a connection from DataSource/pool
  2. Create PreparedStatement
  3. Bind parameters and execute SQL
  4. Receive ResultSet, iterate each row
  5. Invoke RowMapper on each row to create Java object
  6. Close ResultSet and PreparedStatement managed by the template
  7. DataSourceUtils.releaseConnection(connection, dataSource)
         │
         ├─ Connection belongs to an active transaction:
         │    keep it managed by transaction manager until transaction ends
         └─ Connection does not belong to a transaction:
         │    close/release handle per DataSource/pool
  8. Return List/DTO or throw appropriate exception
```

This is a **logical model**. The exact order and number of low-level calls can vary by overload, driver, Spring version, and execution technique; the essential point to remember is that the template arranges cleanup according to contract, even when intermediate work throws an error.

### It is not "every SQL statement creates a new physical connection"

A production `DataSource` in server applications typically uses a connection pool, such as HikariCP. When the application requests a connection, the pool can hand out a **logical handle** to an already existing physical connection. When code calls `close()` on the handle outside a transaction, the pool typically returns the connection to the available pool list, **without** establishing or tearing down a physical TCP/DB connection on every request. A pool may close a physical connection when it is evicted, reaches max lifetime, or on shutdown.

Therefore:
- "`JdbcTemplate` releases the connection" is **correct lifecycle releasing**.
- "Every query creates and closes a TCP session" is **false in the case of a pooled DataSource**.
- "Since there is a pool, there is no need to release connections" is also **false**: forgetting to release exhausts pool handles, forcing other requests to wait and eventually time out.

## 5. A Sample Problem Implementable in Spring Boot

Suppose we have orders and audit log tables, with PostgreSQL:

```sql
CREATE TABLE orders (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_code VARCHAR(64) NOT NULL UNIQUE,
    status VARCHAR(16) NOT NULL,
    amount_cents BIGINT NOT NULL CHECK (amount_cents >= 0)
);

CREATE TABLE order_audit (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES orders(id),
    event VARCHAR(32) NOT NULL
);
```

Typical Gradle dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'org.postgresql:postgresql'
}
```

`application.properties` uses environment variables instead of hardcoding passwords:

```properties
spring.datasource.url=jdbc:postgresql://localhost:5432/orders_db
spring.datasource.username=orders_app
spring.datasource.password=your-local-secret
```

The configuration above is only a **local example**; it requires a matching DB, user, migrations, and secrets provided securely in the runtime environment. Spring Boot typically configures `DataSource`, the connection pool, `JdbcTemplate`, and the corresponding transaction manager when dependencies and auto-configuration conditions match. There is no need to manually `new JdbcTemplate()` per request.

Immutable DTO:

```java
// OrderRow.java
package example.jdbc;

public record OrderRow(
    long id,
    String code,
    String status,
    long amountCents
) {}
```

Repository:

```java
// OrderJdbcRepository.java
package example.jdbc;

import java.util.List;
import java.util.Optional;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;

@Repository
public class OrderJdbcRepository {

    private static final RowMapper<OrderRow> ORDER_MAPPER = (rs, rowNum) ->
        new OrderRow(
            rs.getLong("id"),
            rs.getString("order_code"),
            rs.getString("status"),
            rs.getLong("amount_cents")
        );

    private final JdbcTemplate jdbc;

    public OrderJdbcRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<OrderRow> findByStatus(String status) {
        return jdbc.query("""
                SELECT id, order_code, status, amount_cents
                FROM orders
                WHERE status = ?
                ORDER BY id
                """, ORDER_MAPPER, status);
    }

    public Optional<OrderRow> findByCode(String code) {
        List<OrderRow> matches = jdbc.query("""
                SELECT id, order_code, status, amount_cents
                FROM orders
                WHERE order_code = ?
                """, ORDER_MAPPER, code);

        if (matches.size() > 1) {
            throw new IllegalStateException(
                "Order code must be unique");
        }
        return matches.stream().findFirst();
    }

    public int markPaid(long id) {
        return jdbc.update("""
                UPDATE orders
                SET status = 'PAID'
                WHERE id = ? AND status = 'NEW'
                """, id);
    }

    public void addAudit(long orderId, String event) {
        jdbc.update("""
                INSERT INTO order_audit (order_id, event)
                VALUES (?, ?)
                """, orderId, event);
    }
}
```

**Point to observe:** the repository only manages data and the result contract; **`Connection`, `PreparedStatement`, and `ResultSet` do not appear in the calling code**. `ORDER_MAPPER` is invoked by the template while the ResultSet is still valid. After `query()` returns, `List<OrderRow>` contains Java records detached from JDBC resources; the caller can use it without holding a cursor or connection.

`Optional` is a 0..1 choice; the SQL schema has a unique constraint so one order code must not return multiple rows. Handling `matches.size()>1` in the example clarifies the invariant; in real applications, Spring Framework 6.1+'s `JdbcClient.optional()` API can also express 0..1 directly, though the unique constraint in the database is still necessary. `query()` uses blocking JDBC; it has nothing to do with async/reactive.

### Where is the Connection obtained?

The `findByStatus()` call executes the entire query under the orchestration of `JdbcTemplate`. When the query finishes, the statement/resultset are cleaned up and the connection is released according to context. The application **does not need `finally { conn.close(); }`** around `jdbc.query()`.

Creating one shared `JdbcTemplate` with a stably configured `DataSource` is normal. Once configured, the template is designed to be used concurrently by multiple repositories/callers; avoid mutating mutable settings on the same template while multiple threads are using it.

## 6. Without @Transactional: Resources per Operation

Suppose a service invokes two commands, but **does not** declare a surrounding Spring transaction:

```java
public void payWithoutTransaction(long id) {
    int updated = repository.markPaid(id);
    if (updated != 1) {
        throw new IllegalStateException("Order not NEW");
    }
    repository.addAudit(id, "PAID");
}
```

This is an **illustrative method in a service with a `repository` field**, not a standalone program.

Common scenario:
1. `markPaid()` acquires a connection, runs `UPDATE`, cleans up the statement, and releases the connection; if the connection is configured for auto-commit, the statement has already committed.
2. `addAudit()` acquires a connection handle for `INSERT`, processes it, and releases it.
3. If inserting the audit fails, the prior update may already be committed: **proper resource cleanup does not mean statements are committed atomically**.

The two commands might happen to receive the same physical connection reissued by the pool, but **they do not form a transaction merely by sharing a pool or `JdbcTemplate`**. A transaction is a separate policy coordinated by the transaction manager and business boundaries.

## 7. With @Transactional: Why Isn't the Connection Released Immediately After Each SQL Statement?

When a Spring transaction is activated via a proxy, with `DataSourceTransactionManager` or `JdbcTransactionManager` pointing to the right `DataSource`, the transaction manager acquires/binds one JDBC connection for the current transaction. `JdbcTemplate` uses `DataSourceUtils`, so calls within the same transaction normally use that exact connection.

```text
Service.payOrder()       @Transactional starts
  |
  | Spring transaction manager
  |   └── acquires/binds Connection C to the current thread
  |
  ├── repository.markPaid(id)
  |      JdbcTemplate → DataSourceUtils → Connection C
  |      creates Statement A → UPDATE → closes Statement A
  |      release(C) → recognizes C belongs to transaction, not yet returned to pool
  |
  ├── repository.addAudit(id, "PAID")
  |      JdbcTemplate → DataSourceUtils → Connection C
  |      creates Statement B → INSERT → closes Statement B
  |      release(C) → C still belongs to transaction
  |
  └── service returns normally / throws exception
         |
         ├── commit (if valid)
         └── rollback (per rollback policy)
                |
                └── unbinds/cleans up C, returns connection to DataSource/pool
```

Complete service example in a Spring project context:

```java
// OrderPaymentService.java
package example.jdbc;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderPaymentService {
    private final OrderJdbcRepository repository;

    public OrderPaymentService(OrderJdbcRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void pay(long orderId) {
        int updated = repository.markPaid(orderId);
        if (updated != 1) {
            throw new IllegalStateException("Order not NEW");
        }
        repository.addAudit(orderId, "PAID");
    }
}
```

Here:
- If both the update and the audit insert succeed, the transaction is committed.
- If the audit insert causes a `DataAccessException` (unchecked), Spring rolls back the transaction by default.
- If the application throws `IllegalStateException` as in the example, it also rolls back by default.
- If using a **checked exception**, rollback configuration must be decided explicitly (e.g., `@Transactional(rollbackFor = SomeCheckedException.class)` when required).
- `@Transactional` on a method generally only takes effect when the call goes through a Spring proxy; **self-invocation** within the same object does not trigger a new proxy transaction by default.
- Imperative transaction logic relies on context bound to the executing thread; transactions do not propagate automatically across `@Async`/other threads.

A transaction waiting on a network API, message broker, or long-running processing can **hold a connection for a long time**, even though `JdbcTemplate` closed each statement. That can cause pool exhaustion; keep transactions short and do not use a transaction as a "wrapper" around all slow work.

### Connection cleanup is not the same as commit/rollback

`JdbcTemplate` is responsible for the JDBC statement/resultset lifecycle and calling connection release according to rules. **The transaction manager** is responsible for commit/rollback boundaries and releasing the connection when the transaction ends. Do not call `con.commit()`, `con.rollback()`, or `con.close()` directly inside a `RowMapper`/callback participating in a Spring transaction: doing so breaks ownership and consistency.

## 8. Standard Callbacks: Template and Application Responsibilities

`JdbcTemplate` accepts callbacks for SQL/mapping, yet not all callbacks share the same ownership. Let's examine several common cases.

### 8.1. RowMapper<T>

`RowMapper` is called for each row of the ResultSet created by `JdbcTemplate`. Inputs include the current `ResultSet` and the row number. The callback:
- Reads the required columns and creates a Java object/record.
- Must not `close()` the `ResultSet`, `Statement`, or indirectly received `Connection`.
- Must not retain a reference to `ResultSet` for processing after `query()` returns.
- If mapping fails, lets the error propagate; the template still performs the necessary cleanup.

**Good example:** `ORDER_MAPPER` in section 5 returns an immutable `OrderRow`. **Bad example:** returning an object holding a `ResultSet` field and waiting for the HTTP layer to read the data; by then the ResultSet's lifecycle has ended.

### 8.2. ResultSetExtractor<T>

`ResultSetExtractor` receives the entire `ResultSet` of a query to map complex structures; for instance, grouping multiple rows into an aggregate. The template manages this ResultSet, and the callback must not close it. Process all needed data **while the callback is running**.

```java
// Illustrative method in OrderJdbcRepository.
public long sumPaidAmounts() {
    return jdbc.query("""
            SELECT amount_cents
            FROM orders
            WHERE status = ?
            """, rs -> {
                long total = 0;
                while (rs.next()) {
                    total = Math.addExact(
                        total, rs.getLong("amount_cents"));
                }
                return total;
            }, "PAID");
}
```

This maps the entire result set into one value; `Math.addExact` throws an error on `long` overflow. For large datasets, SQL `SUM` in the DB may be more efficient; the example only shows that the callback **is allowed to iterate** the ResultSet and the template **owns** the ResultSet. Never write `return rs;`.

### 8.3. RowCallbackHandler

`RowCallbackHandler` is also invoked by the template during iteration, useful for consuming each row, such as computing a checksum or feeding a controlled processor. Do not call `rs.next()` inside this callback: the template already controls cursor movement to the current row per the `RowCallbackHandler` contract.

```java
// Illustrative method in repository, with JdbcTemplate jdbc.
public void visitOrderCodes(
        java.util.function.Consumer<String> visitor) {
    jdbc.query("""
            SELECT order_code
            FROM orders
            ORDER BY id
            """, (org.springframework.jdbc.core.RowCallbackHandler) rs ->
                visitor.accept(rs.getString("order_code")));
}
```

`visitor` must process data synchronously inside the callback and must not retain `ResultSet`. Limit queries when tables are very large, or consider batching/streaming with measurement and control mechanisms. `RowCallbackHandler` avoids building a `List` holding every row, yet **does not make JDBC non-blocking**.

### 8.4. PreparedStatementCreator / PreparedStatementSetter

`PreparedStatementCreator` receives a connection and **returns a `PreparedStatement` it created** for `JdbcTemplate` to execute. For a statement returned per contract, the template takes responsibility for closing it after use. `PreparedStatementSetter` only binds parameters into a statement supplied by the template; the callback **must not** close that statement. If a callback creates additional streams, files, or auxiliary resultsets/statements outside the main API, the callback must clean up the resources it owns.

There is no need for low-level callbacks when `jdbc.query(sql, mapper, args)` or `jdbc.update(sql, args)` is clear enough. Using simpler APIs usually reduces the chance of violating resource contracts.

## 9. ConnectionCallback: Given a Connection, Manage Statements You Create

With `ConnectionCallback<T>`, `JdbcTemplate.execute(...)` passes the connection to the callback to run custom JDBC work. **`JdbcTemplate` still owns the connection**, while statements/resultsets opened by the callback itself must be closed by the callback.

Example:

```java
// JdbcLowLevelCounter.java
package example.jdbc;

import java.sql.PreparedStatement;
import java.sql.ResultSet;
import org.springframework.jdbc.core.ConnectionCallback;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class JdbcLowLevelCounter {
    private final JdbcTemplate jdbc;

    public JdbcLowLevelCounter(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public long count(String status) {
        return jdbc.execute((ConnectionCallback<Long>) connection -> {
            try (PreparedStatement statement =
                     connection.prepareStatement("""
                         SELECT COUNT(*) FROM orders WHERE status = ?
                         """)) {
                statement.setString(1, status);
                try (ResultSet rows = statement.executeQuery()) {
                    rows.next(); // COUNT(*) without GROUP BY returns one row
                    return rows.getLong(1);
                }
            }
        });
    }
}
```

Ownership analysis:
- **Do not** write `try (Connection con = connection)`, and **do not** call `connection.close()` in the callback. The connection is supplied by the template and held by the transaction manager if inside a transaction.
- `PreparedStatement` is created by the callback **calling** `connection.prepareStatement(...)` itself, so the callback closes it via try-with-resources.
- `ResultSet` is opened by the callback **calling** `statement.executeQuery()` itself, so the callback closes it before exiting the callback.
- If SQL throws `SQLException`, try-with-resources still cleans up the opened statement/resultset; `JdbcTemplate` catches the SQLException and translates it to Spring's exception hierarchy.
- If `rows.getLong(1)` or mapping throws a `RuntimeException`, cleanup still occurs and the application exception propagates without automatically turning into a `DataAccessException` just because it is inside the template.

Do not arbitrarily call `connection.setAutoCommit(false)`, `commit`, or `rollback` inside a callback running under a Spring transaction. When a transaction is genuinely needed, place `@Transactional` on the service or use `TransactionTemplate`/an appropriate transaction manager.

### 9.1. PreparedStatementCallback also has the ResultSet ownership exception

You can let `JdbcTemplate` create the statement and have the callback execute it directly. In that case:
- The template **closes the `PreparedStatement` it supplied**.
- The callback must close the `ResultSet` opened by its own `executeQuery()`.

```java
// Illustrative method in a repository with field JdbcTemplate jdbc.
public long countWithPreparedStatementCallback(String status) {
    return jdbc.execute("""
            SELECT COUNT(*) FROM orders WHERE status = ?
            """, (org.springframework.jdbc.core.PreparedStatementCallback<Long>) ps -> {
        ps.setString(1, status);
        try (java.sql.ResultSet rs = ps.executeQuery()) {
            rs.next();
            return rs.getLong(1);
        }
    });
}
```

This is why the statement "`JdbcTemplate` automatically closes all ResultSets opened by callbacks" is inaccurate. Spring's callback documentation explicitly notes that a ResultSet opened by a callback **should be closed within the callback itself**, because closing the statement may simply return the statement to a statement pool rather than cleaning up ResultSet resources as expected.

## 10. queryForStream: The Caller Receives an Unfinished Resource Lifecycle

`JdbcTemplate.queryForStream(...)` (Spring Framework 5.3+) differs from `query(...)` returning a `List`:
- It returns a `java.util.stream.Stream<T>`.
- The stream may read rows while the statement, resultset, and connection still need to stay open.
- **The caller must close the Stream**, ideally via `try-with-resources`.
- "Having called `forEach` or `toList`" **does not mean the Stream closes automatically**; a terminal operation is no substitute for `close()`.

```java
// OrderStreamReader.java
package example.jdbc;

import java.util.stream.Stream;
import java.util.function.Consumer;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;

@Repository
public class OrderStreamReader {
    private static final RowMapper<OrderRow> MAPPER =
        (rs, rowNum) -> new OrderRow(
            rs.getLong("id"),
            rs.getString("order_code"),
            rs.getString("status"),
            rs.getLong("amount_cents"));

    private final JdbcTemplate jdbc;

    public OrderStreamReader(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void visitRecentOrders(
            String status, int maxRows,
            Consumer<OrderRow> consumer) {
        if (maxRows < 1 || maxRows > 5000) {
            throw new IllegalArgumentException("maxRows out of range");
        }

        try (Stream<OrderRow> rows = jdbc.queryForStream("""
                SELECT id, order_code, status, amount_cents
                FROM orders
                WHERE status = ?
                ORDER BY id
                LIMIT ?
                """, MAPPER, status, maxRows)) {
            rows.forEach(consumer);
        }
    }
}
```

Upon exiting `try`, `rows.close()` is invoked even if `consumer.accept(...)` throws an error. `queryForStream` guarantees the resource closing mechanism when **the stream is closed**. Do not write:

```java
// WRONG: returning a Stream from a DAO without establishing clear closing responsibility.
public java.util.stream.Stream<OrderRow> leakProne() {
    return jdbc.queryForStream(
        "SELECT id, order_code, status, amount_cents FROM orders",
        MAPPER);
}
```

The bad snippet is an **illustrative method in a class with fields `jdbc` and `MAPPER`**, not standalone code. Returning a stream can be valid if the API explicitly transfers ownership and the caller definitely closes it, yet the easiest mistake to overlook is "passing a Stream across layers until nobody closes it".

**Also do not open a stream in a `@Transactional` method and return the stream outward** expecting the transaction to stay alive: when the method returns, the transaction proxy may end, causing subsequent stream consumption to fail or violate boundaries. Consume the stream *inside* the transaction scope or use another data-processing API/mechanism.

### Streaming does not automatically guarantee low memory across all databases

The actual degree of streaming depends on the JDBC driver, fetch size, autocommit, SQL statement, and database. For example, PostgreSQL JDBC often requires a positive fetch size and an appropriate transaction to read via a cursor instead of loading all data immediately. `queryForStream` neither replaces `LIMIT`/pagination nor creates a reactive `Flux`. Always measure heap usage, connection hold time, and server cursors in a real environment.

## 11. If Truly Using Raw JDBC: try-with-resources and DataSourceUtils

Sometimes a library requires a raw `Connection`. There are two cases that **must not be confused**.

### 11.1. Raw JDBC when you genuinely own the Connection

```java
// Raw JDBC method; caller supplies DataSource and handles SQLException.
public long countRaw(
        javax.sql.DataSource dataSource, String status)
        throws java.sql.SQLException {

    try (java.sql.Connection con = dataSource.getConnection();
         java.sql.PreparedStatement ps = con.prepareStatement(
             "SELECT COUNT(*) FROM orders WHERE status = ?")) {
        ps.setString(1, status);
        try (java.sql.ResultSet rs = ps.executeQuery()) {
            rs.next();
            return rs.getLong(1);
        }
    }
}
```

Here, the code **acquires the connection itself**, so it must close it. However, calling `dataSource.getConnection()` directly on a standard DataSource **does not necessarily participate in a Spring thread-bound transaction**. Do not copy this method into a `@Transactional` service and assume it uses the same connection as `JdbcTemplate`.

### 11.2. Low-level JDBC aware of Spring transactions

If `JdbcTemplate` cannot be used due to a special API, `DataSourceUtils` is the low-level path:

```java
// Illustrative method; assumes field javax.sql.DataSource dataSource.
public long countSpringAware(String status)
        throws java.sql.SQLException {

    java.sql.Connection con =
        org.springframework.jdbc.datasource.DataSourceUtils
            .getConnection(dataSource);
    try {
        try (java.sql.PreparedStatement ps = con.prepareStatement(
                "SELECT COUNT(*) FROM orders WHERE status = ?")) {
            ps.setString(1, status);
            try (java.sql.ResultSet rs = ps.executeQuery()) {
                rs.next();
                return rs.getLong(1);
            }
        }
    } finally {
        org.springframework.jdbc.datasource.DataSourceUtils
            .releaseConnection(con, dataSource);
    }
}
```

You must use the same `DataSource` instance when getting and releasing. `DataSourceUtils.releaseConnection` **does not immediately close a connection bound to the thread by the transaction manager**, while releasing the handle outside a transaction per datasource policy. The code above still manages statements/resultsets manually and decides how to translate `SQLException`; therefore only use it when there is a real reason. For regular SQL work, `JdbcTemplate` is cleaner and less risky.

Spring provides `TransactionAwareDataSourceProxy` for integrating legacy code that only knows how to call standard `DataSource` `getConnection()/close()`. This is a compatibility integration option, not needed for new repositories written with `JdbcTemplate`.

## 12. When Errors Occur, JdbcTemplate Still Cleans Up

Suppose a `RowMapper` fails on row 13 because a column format is not as expected. If the template did not clean up resources on the exception branch, then:
1. `ResultSet` remains open.
2. `Statement` remains open/held by the pool.
3. `Connection` is not returned on time.
4. After many failing requests, the pool is exhausted even though all preceding successful queries released properly.

`JdbcTemplate` structures its cleanup branches to handle both **success and failure**. It also uses `SQLExceptionTranslator` to translate JDBC `SQLException` into Spring's `DataAccessException` hierarchy: e.g., SQL syntax errors, constraint violations, and resource access failures. The exact subtype depends on the driver/translator; an identical subtype across all databases is not guaranteed.

```text
Run query
   |
   ├─ success ───────────────► map rows ──► cleanup ──► return
   |
   ├─ SQLException ──────────► cleanup ──► DataAccessException
   |
   └─ RuntimeException from app ► cleanup ──► propagate exception
```

**Note:** A `RuntimeException` thrown by an application callback does not automatically become a SQL error; it is typically propagated to the caller. If the method is inside `@Transactional`, rollback also depends on the exception type and rollback policy configuration, not on whether the statement was closed.

### Why not swallow errors to "return the connection early"?

The following snippet is an anti-pattern:

```java
// WRONG: swallowing all errors and returning an empty list.
try {
    return jdbc.query(sql, mapper);
} catch (RuntimeException ex) {
    return java.util.List.of();
}
```

This is a **non-standalone** snippet with `jdbc`/`sql`/`mapper` in the current scope. `JdbcTemplate` already performs cleanup on the error branch; swallowing exceptions does not make cleanup any better. It only tricks clients into thinking there is no data and hides SQL/connection failures.

Only catch specific errors when the business contract requires it, use `DataAccessException`/appropriate subtypes, and let exception translation work; log at controlled boundaries and avoid duplicate logging at every layer.

## 13. Transaction Principles and "Holding Connections Too Long"

A `@Transactional` request sometimes spends only 5 ms on queries, yet the transaction holds the connection for 3 seconds because it subsequently calls an external API. The database and connection pool must still reserve resources for this transaction. With many concurrent requests like this, the pool waits and times out.

Example of poor design:

```java
@Transactional
public void process(long id) {
    repository.markPaid(id);
    slowRemoteGateway.notifyPayment(id); // Network I/O can be very slow
    repository.addAudit(id, "PAID");
}
```

This is a **service sketch** with injected dependencies, not a standalone Java file. Even though `JdbcTemplate` closes each statement, the transaction remains open and the connection can be held while waiting on the network.

A sound design typically looks like this:
- Complete DB modifications inside a short transaction.
- Avoid calling slow network APIs inside a transaction whenever possible.
- If events must be delivered after commit without losing them, consider a **transactional outbox** and a separate consumer.
- Avoid using `REQUIRES_NEW` indiscriminately when the pool has few connections; nested propagation can require additional connections and cause pool exhaustion.
- Configure timeouts for transactions and queries, but do not treat timeouts as an automatic substitute for cleanup, concurrency limits, or pool tuning.

**Early statement cleanup and returning the connection to the pool are two different milestones.** Understanding them helps pinpoint the true cause of connection pool starvation.

## 14. A Pure Java 17 Example of Resource Cleanup on Failure

The snippet below does not use Spring or JDBC. It simulates the **ownership principle and try-with-resources ordering** for learners to run immediately without a database dependency. It is **not a test of the JdbcTemplate implementation**.

File name: `CloseOrderDemo.java`.

```java
public class CloseOrderDemo {

    static final class Tracked implements AutoCloseable {
        private final String name;

        Tracked(String name) {
            this.name = name;
        }

        @Override
        public void close() {
            System.out.println("close " + name);
        }
    }

    public static void main(String[] args) {
        try (Tracked connection = new Tracked("Connection");
             Tracked statement = new Tracked("Statement");
             Tracked rows = new Tracked("ResultSet")) {

            System.out.println("read rows");
            throw new IllegalStateException("mapping failed");

        } catch (IllegalStateException ex) {
            System.out.println("caught " + ex.getMessage());
        }
    }
}
```

Run:

```bash
javac CloseOrderDemo.java
java CloseOrderDemo
```

Exact stdout:

```text
read rows
close ResultSet
close Statement
close Connection
caught mapping failed
```

Key takeaway: `AutoCloseable` resources opened before an error are still closed in reverse order. `JdbcTemplate` uses appropriate cleanup mechanisms and transaction/pool boundaries, while `queryForStream` shifts part of the closing responsibility to the caller. Do not mechanically apply the demo's "close Connection" line inside a template callback.

## 15. Reasons a Pool Can Exhaust Despite Using JdbcTemplate

`JdbcTemplate` reduces the risk of JDBC resource leaks, **but does not solve every pool capacity issue**.

| Symptom | Possible Cause | What to Check |
|---|---|---|
| Active connections climb and stay high | Long transactions, slow queries, lock waits | Transaction duration, slow SQL, lock metrics |
| Pool pending threads rise | Concurrency exceeds pool or DB is bottlenecked | Pool size, concurrency, p95/p99, DB capacity |
| Pool exhausts after many stream operations | `queryForStream` is not being closed | Wrap every stream in try-with-resources |
| Only happens when a low-level callback fails | Callback creates its own `ResultSet`/`Statement` and forgets to close | Ownership per callback API; test failure paths |
| Errors appear when calling a network service | Holding a transaction while waiting on network | Separate DB transactions from external side effects |
| Timeouts after multiple batches | Oversized batches or large ResultSet/materialization | Fetch size, chunk size, SQL plan, batch strategy |
| Two DataSources in the same service | Transaction manager does not manage the DataSource used by the template | Bean/qualifier wiring and transaction manager |
| "Dirty" connection after DB error | App manually alters autoCommit/isolation without reset; driver/pool bug | Avoid manual state changes under transactions; pool health |
| Many physical DB connections observed | Pool configured/scaled across many instances, not a default template "leak" | Active/idle/max per instance, total instances |

Distinguish clearly:
- **Leaked resource:** caller fails to close a resource it owns, causing handles to be held indefinitely.
- **Long-held connection:** valid transaction/query that simply runs very long; not necessarily a leak.
- **Pool exhaustion:** demand exceeds supply for some period; can stem from slow queries, locks, undersized pool, or leaks.
- **Physical connection churn:** DB/TCP sessions continuously created and destroyed, usually tied to pool config, network, or DB behavior—do not deduce this solely from the number of `JdbcTemplate.query` calls.

## 16. Configuring and Observing Resources in Spring Boot

The Spring Boot JDBC starter typically integrates a pool like HikariCP when on the classpath with matching auto-configuration. Minimal example configuration adjustable after measurement:

```properties
spring.datasource.hikari.maximum-pool-size=10
spring.datasource.hikari.connection-timeout=30000
```

`maximum-pool-size` caps the number of connections managed by the pool; `connection-timeout` is how long to wait for a connection from the pool (in milliseconds in HikariCP config). These numbers are illustrative only, **not default recommendations for every production system**. Raising pool size blindly can shift the bottleneck to the DB, increase concurrent transactions/locks, and reduce throughput.

Observe:
- Pool active/idle/pending counts and connection acquisition wait times.
- Transaction duration and query latency p50/p95/p99.
- Concurrent requests, timeout rates, and `CannotGetJdbcConnectionException`/connection failure errors.
- DB sessions, slow queries, lock waits, CPU/I/O.
- Code paths using `queryForStream` or `ConnectionCallback`, plus rare error paths.

With Spring Boot Actuator/Micrometer properly configured, pool metrics can be collected; exact names/values depend on the registry, version, and instrumented beans. HikariCP's leak detection feature can assist investigation, though legitimately long-held connections can produce false positives; use it purposefully rather than treating it as absolute proof of a leak.

**Do not look only at the Java heap:** a JDBC connection/statement/resultset can retain driver, socket, server cursor, and DB resources; low heap usage does not mean every connection has been returned to the pool.

## 17. Testing to Prove Contract Compliance

### 17.1. Testing repository behavior

With real PostgreSQL via Testcontainers or an equivalent integration database, prepare fixtures and verify:
1. `findByStatus("NEW")` returns the right DTOs.
2. `findByStatus("MISSING")` returns an empty list, not `null`.
3. `markPaid(id)` returns the expected updated row count.
4. When SQL or mapping fails, the application receives the proper exception instead of silently returning empty.
5. With the same data, repeated calls do not accumulate active connections unexpectedly.

JUnit 5 example with Spring Boot JDBC test slice (requires schema/fixtures prepared, e.g., via `schema.sql` or migrations):

```java
// OrderJdbcRepositoryTest.java
package example.jdbc;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;

@JdbcTest
@Import(OrderJdbcRepository.class)
class OrderJdbcRepositoryTest {

    @Autowired JdbcTemplate jdbc;
    @Autowired OrderJdbcRepository repository;

    @Test
    void queryReturnsMappedRows() {
        jdbc.update("""
            INSERT INTO orders (order_code, status, amount_cents)
            VALUES (?, ?, ?)
            """, "TEST-1", "NEW", 1500L);

        var rows = repository.findByStatus("NEW");
        assertThat(rows)
            .anySatisfy(row -> {
                assertThat(row.code()).isEqualTo("TEST-1");
                assertThat(row.amountCents()).isEqualTo(1500L);
            });
    }
}
```

This test **only compiles/runs in a Spring Boot project with JUnit 5, AssertJ, Spring Boot test starter, and a created schema**; it cannot be run with standalone `javac`. The Spring JDBC test slice typically opens a transaction and rolls it back per test; therefore, do not use this test alone to claim "the connection returned to the pool right after the query". To measure release outside a transaction, design dedicated test instrumentation and avoid letting test proxies/transactions mask the result.

### 17.2. Testing transactions and rollback

In an integration test, prepare a valid ID and call `pay(id)`; verify both `orders.status` and `order_audit` after commit. Then inject a controlled failure on the audit insert and verify:
- The order update rolls back along with the audit.
- The exception still propagates per contract.
- After the transaction finishes, the connection is not held indefinitely.
- There is no manual `commit/close` behavior from callbacks.

Do not rely solely on mocked repositories to claim rollback works: mocks do not create real JDBC transactions. Use an actual DB to verify.

### 17.3. Testing error branches and streams

- Deliberately trigger a `SQLException` (querying a wrong column in a test environment) and then execute another valid query on a small pool: the failing operation must not leave resources held permanently.
- Create a `RowMapper` that throws `IllegalStateException` on a row, verify the exception propagates, and confirm the pool does not accumulate handles.
- Use `queryForStream` inside try-with-resources and have the consumer throw mid-way: after the block exits, the stream is still closed.
- For a `PreparedStatementCallback` opening a ResultSet manually, use tests/instrumentation to confirm the ResultSet is closed on both success and failure paths.
- To count `Connection.close()` accurately, a controlled spying/proxy DataSource can be used, **but it must be interpreted within the transaction/pool context**: a logical close does not prove a physical socket was closed.

### 17.4. Testing under load

Run realistic queries with the same dataset/driver/pool:
- Ramp concurrency near the limit.
- Measure active/pending/idle counts, handle return rate, timeouts, and DB utilization.
- Compare `query(...)` returning a list, a properly closed `queryForStream(...)`, and an intentionally unclosed stream test case in an isolated test environment.
- Inspect query latency, long transactions, and lock waits; **do not conclude a pool leak merely because active connections are high at a point in time**.

## 18. Common Mistakes and How to Fix Them

**Mistake 1 — Manually closing Connection inside a template callback**

```java
// WRONG: the Connection supplied by JdbcTemplate is not the callback's to close.
jdbc.execute((org.springframework.jdbc.core.ConnectionCallback<Void>) con -> {
    con.close();
    return null;
});
```

This can break transactions or cause other operations in the same transaction to fail. **Correct:** use the connection supplied by the template inside the callback; only close statements/resultsets the callback **created itself**.

**Mistake 2 — Using raw DataSource.getConnection() and forgetting to close**

```java
// WRONG: connection stays held permanently without finally/try-with-resources.
java.sql.Connection con = dataSource.getConnection();
java.sql.PreparedStatement ps = con.prepareStatement("SELECT 1");
// ...
```

This is an illustrative snippet, not a complete method. **Correct:** prefer `JdbcTemplate`. If acquiring a JDBC connection manually, use try-with-resources; if it must participate in a Spring JDBC transaction, acquire/release via `DataSourceUtils` or use `JdbcTemplate.execute(ConnectionCallback)`.

**Mistake 3 — Assuming queryForStream auto-closes after a terminal operation**

```java
// WRONG: missing close for Stream even after consuming it.
var results = jdbc.queryForStream(
    "SELECT id, order_code, status, amount_cents FROM orders",
    MAPPER);
results.forEach(System.out::println);
```

This snippet is inside a class with `jdbc`/`MAPPER`. **Correct:** `try (var results = jdbc.queryForStream(...)) { ... }`.

**Mistake 4 — Closing the ResultSet managed by the template inside RowMapper**

`RowMapper` does not own the ResultSet and must not close it. **Correct:** only construct the DTO and return it. Conversely, for a ResultSet opened manually in `PreparedStatementCallback` via `executeQuery()`, the callback **must close it** because it owns it.

**Mistake 5 — Opening additional connections in every RowMapper invocation**

Querying 500 rows where each callback queries the DB again can create 500 round-trips (N+1) and add pool pressure. **Correct:** use SQL JOIN/projection/batching when appropriate, or design separate batch lookups.

**Mistake 6 — Thinking @Transactional works on every call**

Self-invocation, missing proxies, a transaction manager pointing to a different DataSource, or thread switching can prevent the expected transaction scope. **Correct:** place transaction boundaries on public Spring-managed service methods, test against a real DB, and verify transaction manager/DataSource wiring.

**Mistake 7 — Using @Transactional to fix a Stream leak**

A transaction does not waive the responsibility to close a Stream, nor does it extend automatically if the method returns the Stream. **Correct:** finish consuming within the transaction and keep try-with-resources in the same scope.

**Mistake 8 — Swallowing every SQLException/RuntimeException**

Swallowing errors frees no additional resources and only hides operational failures. **Correct:** preserve error signals, classify them at necessary boundaries, and record appropriate metrics/logs.

## 19. Self-Check Questions

1. When `JdbcTemplate.query(...)` returns a `List<OrderRow>`, do the Java records still depend on `ResultSet`? **No**: they are already-mapped objects; the template has finished the ResultSet lifecycle of the standard query.
2. If a `PreparedStatementCallback` calls `ps.executeQuery()`, who closes the received ResultSet? **The callback** should use try-with-resources, even though the statement was supplied by the template.
3. When `JdbcTemplate` is participating in `@Transactional`, does calling `releaseConnection` after a query return the connection to the pool immediately? **Not necessarily**: a connection bound to a transaction is held by the transaction manager until the transaction completes.
4. Does `Connection.close()` on a Hikari pooled connection always close the physical DB socket? **No**: it usually just returns the logical connection to the pool.
5. Why does `Stream.toList()` not replace `Stream.close()`? A **terminal operation** consumes elements but does not guarantee calling close on the stream; you must use try-with-resources.
6. If a `RowMapper` throws a RuntimeException, does `JdbcTemplate` clean up resources? **Yes, per its cleanup contract**, though the mapper's exception can still propagate; JDBC cleanup and business error handling are separate responsibilities.
7. Why do long transactions exhaust a pool even when there is no leak? Because a connection can remain validly held for the entire transaction, even after individual statements have closed.
8. Should you call `dataSource.getConnection()` directly inside a `@Transactional` service? Only if you explicitly understand and handle transaction awareness; prefer the template or `DataSourceUtils` for low-level code.

## 20. Code Review Checklist

- [ ] Repository uses an injected/configured `JdbcTemplate` with the right `DataSource`.
- [ ] Standard queries/updates only supply SQL, parameters, and mapping; they do not manually open or close connections.
- [ ] Callbacks do not close JDBC resources supplied by the template.
- [ ] Every `PreparedStatement`/`ResultSet` **opened by a callback itself** has proper try-with-resources/finally.
- [ ] Every `queryForStream` is closed via `try-with-resources`, or caller ownership is explicitly documented and tested.
- [ ] No `ResultSet`, `PreparedStatement`, or raw `Connection` is returned outside its lifecycle scope.
- [ ] Transaction manager and template use the right `DataSource`; transactional methods are invoked through Spring proxies.
- [ ] Transactions are short enough; connections are not held while waiting on external system calls.
- [ ] `DataAccessException` is not swallowed, nor are SQL errors mapped to empty lists.
- [ ] Pool, queries, and transactions are measured; long-held connections are distinguished from resource leaks.
- [ ] Integration tests cover success, SQL exceptions, mapping exceptions, rollback, and stream cleanup.
- [ ] Closing a logical handle is not confused with closing a physical connection.

## 21. Conclusion

**`JdbcTemplate` executes and cleans up JDBC resources according to its API contract.** It acquires connections using a Spring-transaction-compatible mechanism, creates statements, iterates/maps the ResultSet, and releases template-owned resources even across failure paths. **The transaction manager** decides when a connection participating in a transaction is actually returned to the pool; **the pool** decides when a logical close translates to closing a physical connection.

Application code still has clear responsibilities: close statements/resultsets created inside callbacks, close streams returned from `queryForStream`, keep transactions short, and never violate ownership of connections supplied by the template. Only by understanding all three layers of responsibility—**template, transaction, and pool**—can you prevent leaks, avoid pool starvation, and design a reliable JDBC layer.

## Official Documentation for Further Reference

- Spring Framework — Data Access with JDBC (what Spring manages vs. what the application is responsible for): https://docs.spring.io/spring-framework/reference/data-access/jdbc.html
- Spring Framework — JDBC Core, JdbcTemplate, callbacks, and SQLExceptionTranslator: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring Framework — Controlling Database Connections, DataSourceUtils: https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html
- Spring Framework — Synchronizing Resources with Transactions: https://docs.spring.io/spring-framework/reference/data-access/transaction/tx-resource-synchronization.html
- Spring Framework — Annotation-driven Transaction Management: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring API — JdbcTemplate queryForStream and Stream closing requirements: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html
