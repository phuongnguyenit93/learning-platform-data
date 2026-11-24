# The Connection, Statement, and ResultSet Resource Chain in JDBC and Spring Framework

> **Goal:** Understand accurately how the three JDBC resources are created, dependent on one another, and released; trace the query flow from `DataSource`/`Connection` to `Statement` and `ResultSet`; write Java 17+ code without leaking connections or cursors; and know when Spring `JdbcTemplate` or a transaction manager owns the resource lifecycle on behalf of the application.

## 1. The Big Picture: Three Links, Three Responsibilities

A traditional JDBC operation typically follows this chain:

```text
DataSource / DriverManager
       |
       | getConnection(...)
       v
Connection                  <-- JDBC session with the database
       |
       | createStatement()
       | prepareStatement(sql)
       | prepareCall(sql)
       v
Statement                   <-- SQL statement and parameters/execution
  |- Statement
  |- PreparedStatement
  '- CallableStatement
       |
       | executeQuery(...)
       v
ResultSet                   <-- cursor for reading result rows
       |
       | next(), getString(), getLong(), ...
       v
Java data (record, DTO, domain object)
       |
       v
close ResultSet -> close Statement -> close Connection
```

**Connection** represents the JDBC session and associated state such as auto-commit, transaction, and isolation. **Statement** executes SQL using that connection. **ResultSet** is the result object bound to the statement that produced it; it typically holds a cursor, metadata, and driver/database-side resources. Java data already mapped into a record/DTO can generally outlive the closing of JDBC resources.

| Object | Creation Source | Role | Who Must Manage Closing in Raw JDBC? |
| --- | --- | --- | --- |
| `Connection` | `dataSource.getConnection()` or `DriverManager.getConnection(...)` | Communicate with the DB, hold transaction state, and create statements | Code that borrowed/created the connection; close when done, unless a container/framework owns it |
| `Statement` | `connection.createStatement()` | Execute static SQL, typically with no input data | Code that created the statement |
| `PreparedStatement` | `connection.prepareStatement(sql)` | SQL with `?` parameters; typically the default choice | Code that created the prepared statement |
| `CallableStatement` | `connection.prepareCall(sql)` | Call stored procedures when supported by the DB | Code that created the callable statement |
| `ResultSet` | `statement.executeQuery(...)`, `preparedStatement.executeQuery()`, or `getGeneratedKeys()` | Iterate over rows and read columns | Code that receives the result set, unless a higher-level API controls it |

`Connection`, `Statement`, and `ResultSet` all implement `AutoCloseable`. Therefore, **`try-with-resources` is the preferred mechanism for proper closing**, even when SQL execution or mapping throws an exception.

## 2. Lifecycle from Acquiring a Connection to Reading All Data

### Step 1 — Borrowing/Obtaining a Connection

A typical application injects a `javax.sql.DataSource` and calls:

```java
Connection connection = dataSource.getConnection();
```

`DataSource` is the provider of connections; in Spring Boot, it is typically a pooled datasource (such as HikariCP when the appropriate dependency is present). With a pool, a `getConnection()` call usually borrows a logical connection/handle, and **`close()` usually returns the handle to the pool**, rather than necessarily closing the physical TCP connection. Even so, the borrowing code must still close the handle immediately after use.

`Connection` has several characteristics to distinguish:

- `getAutoCommit()`: by the JDBC specification, a new connection defaults to auto-commit; a pool or transaction manager may reset this mode before handing it to application code.
- `setAutoCommit(false)`: SQL statements participate in a programmatically managed transaction; you must explicitly decide to `commit()` or `rollback()`.
- `setTransactionIsolation(...)`, `setReadOnly(...)`: configure transaction/driver behavior when supported; they do not replace transaction design on their own.
- `isClosed()` indicates whether the handle has been closed in terms of API state; it is **not** a reliable check of whether the connection can still communicate with the DB. Pools usually manage validation; JDBC provides `isValid(timeout)` when needed.

### Step 2 — Creating a Statement from a Connection

```java
Statement statement = connection.createStatement();

PreparedStatement prepared = connection.prepareStatement(
    "SELECT id, name FROM products WHERE id = ?"
);
```

`PreparedStatement` is a subtype of `Statement` that holds the SQL string at preparation time. Use `setLong(1, id)`, `setString(2, value)`, etc. to bind data with parameters starting at **index 1**. Parameter binding separates data values from SQL syntax, often supports statement reuse, and reduces the risk of SQL injection.

**Distinguishing the APIs:**

- With `Statement`: `executeQuery("SELECT ...")`, `executeUpdate("UPDATE ...")`.
- With `PreparedStatement`: call `set...(...)` and then invoke **`executeQuery()`** or **`executeUpdate()`** without passing the SQL string again.
- `executeQuery` is for statements that return a single `ResultSet`; `executeUpdate` is for DML/DDL that do not return query-style rows; `execute` is used when the result may be a result set, an update count, or multiple results.
- `CallableStatement` serves stored procedures; it may have output parameters and multiple results, requiring an understanding of how the driver returns them.

Use `PreparedStatement` for user-supplied input data. Do **not** concatenate input strings into SQL, even if "manually escaped". The `?` placeholder represents a **value**, and cannot substitute for table names or column names: dynamic SQL structural parts must be controlled via an allowlist.

### Step 3 — Executing and Receiving a ResultSet

```java
prepared.setLong(1, 42L);
try (ResultSet resultSet = prepared.executeQuery()) {
    while (resultSet.next()) {
        long id = resultSet.getLong("id");
        String name = resultSet.getString("name");
        // Map id/name into Java data while the cursor is still open.
    }
}
```

`ResultSet` is a **cursor**. Initially, the cursor is positioned *before the first row*; each successful `next()` call advances to a row and returns `true`. When no rows remain, `next()` returns `false`. Only call `getLong`/`getString` after `next()` has succeeded and while the result set is still open.

**Zero rows:** the `while (rs.next())` loop does not run; the `ResultSet` must still be closed. **Single row:** use `if (rs.next())`, and check `rs.next()` again if business logic strictly requires exactly one row. **Multiple rows:** map incrementally into a `List<DTO>`, or consume within bounded limits while the result set is alive.

### Step 4 — Closing in Reverse Dependency Order

```text
Create:    Connection  -> Statement          -> ResultSet
Use:                                            next/get...
Close:     Connection  <- Statement          <- ResultSet
           last           after ResultSet       first
```

When exiting a `try-with-resources` block with multiple resources, Java closes them **in the reverse order of their declaration**. For example, declaring connection, statement, and result set in one scope will close result set → statement → connection.

Per JDBC, **closing a `Statement` also closes the current `ResultSet` created by that statement**. Re-executing a statement typically also closes its current result set according to JDBC rules, except in cases where multiple results are handled with the appropriate API. Therefore, do not return a `ResultSet` out of a method and then close the statement; the cursor will no longer be usable. Even though cascading close exists, you should still manage the result set explicitly to make the release timing deterministic.

## 3. Complete and Correct try-with-resources Patterns

For a query that does not require binding parameters, all three resources can be declared in the same scope:

```java
// Illustrative code inside a method with "throws SQLException".
try (Connection con = dataSource.getConnection();
     Statement stmt = con.createStatement();
     ResultSet rs = stmt.executeQuery(
         "SELECT id, title FROM books ORDER BY id")) {

    while (rs.next()) {
        System.out.println(rs.getLong("id") + ":" + rs.getString("title"));
    }
}
// rs, stmt, and con are closed in the right order.
```

With `PreparedStatement`, parameters must be bound **before** calling `executeQuery()`, so the clearest approach is nested scopes:

```java
try (Connection con = dataSource.getConnection();
     PreparedStatement ps = con.prepareStatement(
         "SELECT id, title FROM books WHERE id = ?")) {

    ps.setLong(1, targetId);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getString("title"));
        }
    }  // Closes rs.
}      // Closes ps, then con.
```

This is an **illustrative snippet**, not standalone compilable code because it assumes `DataSource dataSource` and `long targetId` already exist. A complete runnable example is in section 5.

**Wrap allocations in `try` immediately upon acquisition:** if `prepareStatement` throws `SQLException`, the previously declared connection is still closed; if `executeQuery` throws an error, the statement and connection are still closed. Avoid opening a connection upfront and then passing through multiple `if` branches, `return` statements, or exceptions without `finally` or `try-with-resources` protection.

**Do not rely solely on GC:** the garbage collector manages Java memory, not the timely release of database cursors, sockets, or connections. Resource leaks commonly exhaust the pool and cause requests to wait or time out, even when the heap looks normal.

## 4. A Complete Program: Raw JDBC and Spring JdbcTemplate on the Same DB

The example uses **Java 17+, Maven, Spring Boot 3.5.16, Spring JDBC, and in-memory H2**. Spring Boot is used to quickly create `DataSource`/`JdbcTemplate`; the raw JDBC part still uses the three resources directly. All the following code belongs to one project, rather than independent runnable snippets. Spring Boot 3.5.16 is a released version; for real-world projects, choose a Spring Boot branch that is still under support.

**Structure:**

```text
jdbc-resource-chain/
├── pom.xml
└── src/main/
    ├── java/com/example/resources/ResourceChainApplication.java
    └── resources/
        ├── application.properties
        └── schema.sql
```

**`pom.xml`** — Spring Boot manages transitive dependency versions:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>jdbc-resource-chain</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

**`src/main/resources/schema.sql`** — creates a table on application startup:

```sql
CREATE TABLE books (
    id BIGINT PRIMARY KEY,
    title VARCHAR(120) NOT NULL
);
```

**`src/main/resources/application.properties`** — uses in-memory H2, disables the banner, and reduces logging to observe the demo output:

```properties
spring.main.web-application-type=none
spring.main.banner-mode=off
logging.level.root=ERROR
spring.datasource.url=jdbc:h2:mem:resourcechain;DB_CLOSE_DELAY=-1
spring.sql.init.mode=always
```

**`src/main/java/com/example/resources/ResourceChainApplication.java`**:

```java
package com.example.resources;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import javax.sql.DataSource;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootApplication
public class ResourceChainApplication {

    public static void main(String[] args) {
        SpringApplication.run(ResourceChainApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(DataSource dataSource, JdbcTemplate jdbc) {
        return args -> {
            // 1) Raw JDBC: Connection -> PreparedStatement.
            try (Connection con = dataSource.getConnection();
                 PreparedStatement ps = con.prepareStatement(
                         "INSERT INTO books (id, title) VALUES (?, ?)")) {

                ps.setLong(1, 1L);
                ps.setString(2, "JDBC");
                System.out.println("inserted=" + ps.executeUpdate());
            }

            // 2) Raw JDBC: Connection -> PreparedStatement -> ResultSet.
            try (Connection con = dataSource.getConnection();
                 PreparedStatement ps = con.prepareStatement(
                         "SELECT id, title FROM books WHERE id = ?")) {

                ps.setLong(1, 1L);

                try (ResultSet rs = ps.executeQuery()) {
                    while (rs.next()) {
                        System.out.println(
                                "raw=" + rs.getLong("id")
                                + ":" + rs.getString("title"));
                    }
                }
            }

            // 3) Spring JDBC automatically creates/closes resources during the query operation.
            String title = jdbc.queryForObject(
                    "SELECT title FROM books WHERE id = ?",
                    String.class, 1L);
            System.out.println("template=" + title);
        };
    }
}
```

**Run** from the `jdbc-resource-chain` directory, with JDK 17+ and Maven installed:

```bash
mvn spring-boot:run
```

**Three lines explicitly printed by the program** (excluding Maven/Spring output):

```text
inserted=1
raw=1:JDBC
template=JDBC
```

Explanation:

1. The first block **borrows a connection**, creates a prepared statement, binds `id/title`, and runs the INSERT; upon exiting the block, the statement and connection are closed/returned to the pool.
2. The second block opens a new connection/statement, `executeQuery()` produces a result set, and `next()` reads exactly one row; Java closes the result set before the statement and connection.
3. `JdbcTemplate.queryForObject` reads from the same database through the configured datasource; the code does not manually create or close the three low-level objects because Spring JDBC manages the resource scope of the call.
4. H2 keeps the in-memory database alive for the application lifecycle thanks to `DB_CLOSE_DELAY=-1`; the first statement completes with default auto-commit in the raw JDBC example. The three blocks in the demo **are not presented as a single transaction**.

If you forget to close the connection in a raw JDBC block on a datasource with a small pool, running it repeatedly for long enough can exhaust the pool's connections. If you hold onto `ResultSet` outside the second block, you will be accessing a closed cursor.

## 5. Commonly Confused Resource-Closing Rules

| Action | Primary Effect | Design Consequence |
| --- | --- | --- |
| `resultSet.close()` | Releases the result set/cursor and corresponding resources | **Does not automatically close the statement or connection** |
| `statement.close()` | Releases the statement; the active result set created by the statement is also closed | Do not continue reading the result set after the statement closes |
| `statement.executeQuery(...)` again | Under standard JDBC contract, the statement's current result set is closed on a new execution | Do not reuse the same statement before finishing reading the old cursor |
| `connection.close()` | Releases the JDBC connection handle; dependent objects are no longer usable | Always close statements/result sets proactively for clear timing; the pool can reclaim the handle |
| No more rows (`next()` returns false) | Cursor is positioned after the last row; does not mean all resources are released | Still close the result set and statement |
| Exception during execution/reading result set | Automatic closing is not guaranteed without cleanup | Wrap all allocations in `try-with-resources` |
| `executeUpdate()` returns update count | No standard `ResultSet` to iterate | Still must close `Statement` and `Connection` |
| `getGeneratedKeys()` | Returns a `ResultSet` for auto-generated keys when supported by the driver | Must consume and close this result set |

**Crucial point:** A ResultSet is tied to the statement that produced it, but closing a result set **does not** mean the statement is closed. Hence, a pattern like `return statement.executeQuery()` from a DAO while the DAO closes the statement/connection itself is a lifecycle bug.

### Incorrect example: returning a cursor that still depends on closed resources

```java
// INCORRECT example, not a method you should use.
public ResultSet findBooks(DataSource source) throws SQLException {
    try (Connection con = source.getConnection();
         PreparedStatement ps = con.prepareStatement(
                 "SELECT id, title FROM books")) {
        return ps.executeQuery();
    } // ps/con are already closed before the caller uses the ResultSet.
}
```

**Fix:** read/map inside the block and then return an independent data type such as `List<Book>`, `Optional<Book>`, or a DTO. For very large datasets, a streaming API must clearly bind the open/close scope and have a contract guaranteeing that the consumer closes the stream.

```java
// Illustrative snippet placed in a method that already has DataSource and JDBC/List imports.
List<String> titles = new ArrayList<>();
try (Connection con = dataSource.getConnection();
     PreparedStatement ps = con.prepareStatement(
             "SELECT title FROM books ORDER BY id");
     ResultSet rs = ps.executeQuery()) {

    while (rs.next()) {
        titles.add(rs.getString("title"));
    }
}
return titles; // The List is used after all JDBC resources have been closed.
```

Requires `import java.util.ArrayList` and `import java.util.List`; this is an illustrative snippet, not a complete standalone program outside a project.

## 6. Reading ResultSet Correctly: Cursors, Data Types, and SQL NULL

By default, a `ResultSet` is typically `TYPE_FORWARD_ONLY` and `CONCUR_READ_ONLY` for statements created with basic configuration; drivers may support other scrollable/updatable types if requested and supported. Do not assume you can call `previous()` or `absolute(...)` on a forward-only cursor.

**Practical rules:**

- `next()` advances the cursor and reports whether a row remains; before calling `next()`, there is no current row.
- Column indices are **1-based**: `getString(1)` is the first column. Explicit column names/aliases like `getString("display_name")` help avoid depending on SELECT column order.
- SQL `NULL` has different semantics from 0/false/empty string. With primitive getters `getInt(...)` or `getLong(...)`, null is returned as 0; call `rs.wasNull()` immediately after the getter if you need to distinguish it.
- `rs.getObject("age", Integer.class)` can preserve `null` in the appropriate wrapper when the driver supports the conversion; for monetary amounts, dates/times, and JSON types, understand JDBC mapping and nullability.
- Retrieving `Blob`/`Clob` or binary streams requires separate lifecycle management; do not assume all large data is already buffered in memory or that the resource remains valid after closing the result set.

Example distinguishing `NULL`:

```java
int age = rs.getInt("age");
Integer nullableAge = rs.wasNull() ? null : age;
```

This is a snippet running **inside a `while (rs.next())` loop**, on a result set with an `age` column. Call `wasNull()` immediately after the getter being checked because a subsequent getter call can overwrite the `wasNull()` result.

### ResultSet is not an immutable collection

A `ResultSet` may load data incrementally and hold a server-side cursor or driver-side buffering depending on the database, fetch size, and configuration. It can be affected by transactions, closing the connection/statement, cursor holdability, and isolation. Do not treat a `ResultSet` like a `List` that can be passed freely across layers or stored long-term in a field.

If processing very large tables, consider:

- `setFetchSize(n)` / configuring the statement when appropriate; this is a **hint**, and driver implementations vary.
- Streaming with a clear scope and a connection kept open long enough; do not close the transaction before the iterator/stream finishes consuming.
- Limiting row counts (`setMaxRows`/SQL `LIMIT` when supported), pagination/keyset pagination, and avoiding unbounded loading into a `List`.
- Measuring timeouts, batch size, pool usage, and query plans; fetch size does not fix a SQL query missing an index.

## 7. Statement, PreparedStatement, and CallableStatement

The three types are related by inheritance, but their intended uses differ:

| Type | Created Via | Execution Call | Usage |
| --- | --- | --- | --- |
| `Statement` | `con.createStatement()` | `executeQuery(sql)`, `executeUpdate(sql)` | Simple static SQL; avoid concatenating input |
| `PreparedStatement` | `con.prepareStatement(sql)` | Bind `setXxx(index, value)`, then `executeQuery()`/`executeUpdate()` | Generally preferred for parameterized queries, updates, and batches |
| `CallableStatement` | `con.prepareCall(callSql)` | Bind input, register output, `execute()`; read results | Stored procedures when supported by the DB |

**A `Statement` must not be treated as a container holding an arbitrary number of independent result sets.** By default, JDBC allows one current result set per statement; executing a new statement can close the old result. For procedures or SQL producing multiple results, use `execute()`, `getResultSet()`, `getUpdateCount()`, and `getMoreResults()` according to the driver contract, closing each result set. Do not obtain multiple `ResultSet` objects from the same statement and assume they remain independently alive.

**Auto-generated keys:** use `con.prepareStatement(sql, Statement.RETURN_GENERATED_KEYS)`, run `executeUpdate()`, and then use `ps.getGeneratedKeys()` inside `try (ResultSet keys = ...)`; this is another result set that must also be closed. Check driver/database support and key generation order.

**Batching:** `addBatch`/`executeBatch` reduces round-trips when appropriate, but the statement and connection must still be closed; understand transactions, partial failures, and batch counts. Batching does not automatically mean "all-or-nothing atomic".

## 8. When Using Spring JdbcTemplate, Who Owns the Three Resources?

Spring Framework provides `JdbcTemplate` to standardize the JDBC pattern: acquiring a connection, creating a statement, binding, executing, iterating the result set, translating `SQLException` into the `DataAccessException` hierarchy, and cleanup. The application writes the SQL and mapping logic, and **does not manually close the resources managed by the template**.

```java
// Snippet in a DAO with JdbcTemplate jdbc injected.
List<BookRow> rows = jdbc.query(
    "SELECT id, title FROM books WHERE id >= ? ORDER BY id",
    (rs, rowNum) -> new BookRow(
        rs.getLong("id"), rs.getString("title")),
    1L
);
```

The snippet above requires a `record BookRow(long id, String title) {}`, `import java.util.List`, and the `JdbcTemplate jdbc` object. `RowMapper` receives an open `ResultSet` inside the callback, maps **one row**, and returns an independent object. `JdbcTemplate` retains responsibility for closing resources after the query finishes, even if the callback throws an error.

**Callback rules:** do not call `rs.close()`, `stmt.close()`, or `con.close()` on objects supplied by the template; do not cache `rs`/`con` for use after the callback ends. If you need to read rows in a custom way, use `ResultSetExtractor` or `RowCallbackHandler` per the API; cleanup responsibility still belongs to the template.

`JdbcTemplate` has common methods:

- `query(...)` for multiple rows / custom mappers.
- `queryForObject(...)` for exactly one row or value; an unexpected row count can throw a Spring exception, so do not use it arbitrarily when the result may be empty.
- `update(...)` for INSERT/UPDATE/DELETE, returning the update count.
- `batchUpdate(...)` for multiple updates.
- `execute(ConnectionCallback/StatementCallback/PreparedStatementCallback...)` to perform advanced JDBC work within a Spring-controlled scope.

Since Spring Framework 6.1, `JdbcClient` offers a fluent API for JDBC access, still built on the Spring JDBC infrastructure. Whether using `JdbcClient`, `NamedParameterJdbcTemplate`, or `JdbcTemplate`, learners still need to understand the three underlying resources to diagnose errors, tune performance, and handle transactions.

### Streaming through JdbcTemplate still carries closing responsibility

`JdbcTemplate.queryForStream(...)` returns a `Stream<T>` that depends on open JDBC resources. **The consumer must close the stream**:

```java
// Snippet with JdbcTemplate jdbc already injected.
try (Stream<String> titles = jdbc.queryForStream(
        "SELECT title FROM books ORDER BY id",
        (rs, rowNum) -> rs.getString("title"))) {

    titles.forEach(System.out::println);
}
```

Requires `import java.util.stream.Stream`. Do not return this stream out of a method and let the transaction/service method end before processing it. For reading millions of records, you also must inspect driver fetch/transaction behavior and backpressure; "stream" does not guarantee zero buffering.

## 9. With @Transactional: Connection Belongs to the Transaction Manager

**Important boundary:** `@Transactional` on a Spring service can open a transaction and hold **an appropriate connection** for the JDBC operations inside it. `JdbcTemplate` uses `DataSourceUtils`, so if a connection is bound to the current transaction, it participates instead of opening and committing a separate connection for every call.

```text
Caller -> Spring transactional proxy -> Service @Transactional
                                        |
                                   DataSourceTransactionManager
                                        |
                               Thread-bound Connection
                                   /          \
                                  v            v
                         JdbcTemplate A   JdbcTemplate B
                                  \            /
                                   \          /
                                  same DB transaction
                                        |
                                   commit / rollback
                                        |
                               release connection/pool
```

With imperative JDBC transactions managed by Spring:

- Use `JdbcTemplate` or `DataSourceUtils.getConnection(dataSource)` to obtain the connection aligned with the transaction.
- When obtaining via `DataSourceUtils`, **use `DataSourceUtils.releaseConnection(connection, dataSource)`**, and do not call `connection.close()` directly. Inside a transaction, the helper knows the connection must remain managed by the manager; outside a transaction, it can close/release the handle.
- If you still call `dataSource.getConnection()` directly on a standard datasource, you may accidentally obtain **a different connection** that does not participate in the active transaction. `TransactionAwareDataSourceProxy` is a compatibility mechanism for some code that only knows the DataSource API, but it is not a reason to manually close the transaction manager's connection.
- `@Transactional` does not automatically manage every connection from every datasource. You must configure the appropriate transaction manager, datasource, propagation, and thread context.
- Spring AOP uses proxies by default: self-invocation within the same object via `this.someMethod()` can bypass transaction advice. Do not assume an annotation on a private method automatically enables a transaction.

**Example using DataSourceUtils for low-level JDBC in a DAO** (illustrative code needing imports, placed inside a class that already has `DataSource dataSource`):

```java
public List<String> findTitles() throws SQLException {
    Connection con = DataSourceUtils.getConnection(dataSource);
    try {
        List<String> titles = new ArrayList<>();
        try (PreparedStatement ps = con.prepareStatement(
                 "SELECT title FROM books ORDER BY id");
             ResultSet rs = ps.executeQuery()) {

            while (rs.next()) {
                titles.add(rs.getString("title"));
            }
        }
        return titles;
    } finally {
        DataSourceUtils.releaseConnection(con, dataSource);
    }
}
```

Here, `PreparedStatement` and `ResultSet` are created by the DAO, so the DAO closes them using try-with-resources. **The connection provided by `DataSourceUtils`** is returned via the helper so that the Spring transaction manager decides whether to close it physically or return it to the pool yet. Imports: `java.sql.*`, `java.util.*`, `org.springframework.jdbc.datasource.DataSourceUtils`. This snippet illustrates how to proceed when low-level JDBC APIs are genuinely needed; most CRUD should prefer `JdbcTemplate` to reduce boilerplate.

## 10. Closing a Connection Does Not Guarantee Proper Commit or Rollback

In raw JDBC, a new connection is typically in `autoCommit=true` mode. Each SQL statement is committed according to JDBC rules upon completion. If a business operation has multiple statements that must succeed or fail together, an explicit transaction boundary must be set:

```java
// Raw JDBC pattern inside a method "throws SQLException".
// Assumes valid DataSource source, SQL statements, and parameters.
try (Connection con = source.getConnection()) {
    con.setAutoCommit(false);
    try {
        try (PreparedStatement debit = con.prepareStatement(
                 "UPDATE accounts SET balance = balance - ? WHERE id = ?")) {
            debit.setLong(1, amount);
            debit.setLong(2, fromId);
            debit.executeUpdate();
        }
        try (PreparedStatement credit = con.prepareStatement(
                 "UPDATE accounts SET balance = balance + ? WHERE id = ?")) {
            credit.setLong(1, amount);
            credit.setLong(2, toId);
            credit.executeUpdate();
        }
        con.commit();
    } catch (SQLException | RuntimeException ex) {
        try {
            con.rollback();
        } catch (SQLException rollbackFailure) {
            ex.addSuppressed(rollbackFailure);
        }
        throw ex;
    }
}
```

**The snippet above only illustrates closing and transaction decisions**, not a production money transfer design: it does not check balances, updated row counts, concurrency, idempotency, or invariants. Variables `source`, `amount`, `fromId`, and `toId` are undeclared in the snippet. The takeaway is that the transaction is committed or rolled back **before closing the connection**.

Calling JDBC `Connection.close()` while a transaction is still active has implementation/driver-dependent results; **closing must not be relied upon as a guaranteed rollback operation**. Toggling `setAutoCommit(false)` back to `true` while a transaction is still open can even trigger a commit; do not arbitrarily reset state before rolling back. The pool or transaction framework is responsible for resetting state on a connection returned to the pool; manually managed code must verify the specific contract.

With a Spring service using `@Transactional`, do **not** manually call `setAutoCommit(false)`, `commit()`, `rollback()`, or `close()` on a connection belonging to the transaction manager. Place the transaction boundary on the service, use JDBC through templates/helpers, and let the manager complete the commit/rollback. Mixing manual management and declarative transactions on the same connection easily causes premature commits or breaks rollback.

## 11. Exceptions and Cleanup

Operations like `getConnection`, `prepareStatement`, `executeQuery`, `rs.next`, `rs.getXxx`, and `close` can all throw `SQLException`. When using `try-with-resources`:

1. If the code in the block succeeds, Java closes the resources in reverse order and reports any close errors.
2. If the code throws an error, Java still closes every resource that was successfully created.
3. If both the main code and `close()` throw exceptions, the exception from `close()` is recorded as a **suppressed exception** (see `Throwable.getSuppressed()`), preventing the original error from being lost.

Example of inspecting JDBC errors when diagnostics are needed:

```java
try (Connection con = dataSource.getConnection();
     PreparedStatement ps = con.prepareStatement(
         "SELECT id FROM books WHERE id = ?")) {
    ps.setLong(1, 1L);
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getLong(1));
        }
    }
} catch (SQLException e) {
    System.err.println("SQLState=" + e.getSQLState());
    System.err.println("VendorError=" + e.getErrorCode());
    for (Throwable suppressed : e.getSuppressed()) {
        System.err.println("Close failure: " + suppressed);
    }
    throw e; // Let the caller make business/transaction decisions.
}
```

This snippet is placed in a method `throws SQLException` with `dataSource` already present; it is not a standalone program. `SQLException` also has a `getNextException()` chain provided by the driver in some cases. Do not log SQL containing sensitive data or credentials. With `JdbcTemplate`, Spring translates common errors into `DataAccessException` (unchecked); you still need to recognize specific exceptions like constraint violations or connection failures to apply appropriate retries or messaging.

**Do not catch and ignore exceptions** just to "keep running": if inside a transaction, the whole transaction may need to roll back. Multi-layered manual cleanup code easily leaves execution paths missing `close()`; `try-with-resources` places cleanup right alongside resource ownership.

## 12. Common Mistakes and How to Fix Them

### Mistake A — Only Closing Connection, Forgetting Statement/ResultSet

```java
// WRONG: if an exception occurs before con.close(), even the connection can leak.
Connection con = dataSource.getConnection();
Statement stmt = con.createStatement();
ResultSet rs = stmt.executeQuery("SELECT * FROM books");
// multi-step processing, may throw an exception...
con.close();
```

**Fix:** use `try-with-resources` for all three, closing in reverse order. Although `Statement.close()` closes the active result set, explicit cleanup avoids holding resources until the end of the request and avoids relying on indirect behavior.

### Mistake B — Using ResultSet Outside the Statement's Scope

```java
// WRONG: ResultSet has lost its statement/connection.
ResultSet rs;
try (Connection con = dataSource.getConnection();
     Statement stmt = con.createStatement()) {
    rs = stmt.executeQuery("SELECT title FROM books");
}
rs.next(); // SQLException on closed cursor.
```

**Fix:** map data within the open scope, or design a stream/callback with clear ownership.

### Mistake C — Executing a Statement a Second Time While Still Iterating the First ResultSet

```java
// WRONG lifecycle: the second executeQuery typically closes the first cursor.
ResultSet first = stmt.executeQuery("SELECT id FROM books");
ResultSet second = stmt.executeQuery("SELECT title FROM books");
first.next();  // Unusable because the statement now has a new result.
```

**Fix:** finish reading and close the first result set, or use a second statement on the connection when two concurrent cursors are genuinely needed and supported by the driver.

### Mistake D — Confusing the Return Values of executeQuery and executeUpdate

`executeQuery()` returns a `ResultSet` for queries. `executeUpdate()` returns the affected row count, or a JDBC-defined value for statements not returning a result set. For procedures/SQL producing multiple results, use `execute()` together with `getResultSet()`/`getUpdateCount()`. Choose the API according to the SQL type.

### Mistake E — Concatenating Input into SQL Strings

```java
// WRONG: the condition can be altered by malicious input.
String sql = "SELECT * FROM users WHERE email = '" + email + "'";

// CORRECT: bind values via PreparedStatement.
PreparedStatement ps = con.prepareStatement(
        "SELECT * FROM users WHERE email = ?");
ps.setString(1, email);
```

The correct snippet is illustrative; `ps` must be inside `try-with-resources` in real code. Binding does not work for dynamic identifiers; allowlist table/column names that need to vary.

### Mistake F — Using a Directly Acquired Connection Inside an Active Spring Transaction

Inside `@Transactional`, manually calling `dataSource.getConnection()` and then `close()` can create a separate connection that commits independently and is not part of the service's transaction. **Fix:** use `JdbcTemplate` or `DataSourceUtils.getConnection/releaseConnection`. Do not pass a connection across threads or store it in a singleton field.

### Mistake G — Holding Cursors/Connections Too Long

Querying millions of rows and then performing network calls, file uploads, or waiting on user input **while holding the connection** will starve the pool of resources. **Fix:** paginate or consume early in a short scope; if streaming is truly needed, set timeouts and limits, tune fetch/batch sizes per DB, and ensure the stream is processed and released reliably.

## 13. Connecting to the Spring Framework Data Layer

When organizing a Spring application into controller → service → repository/DAO:

- **DAO writing raw JDBC:** closing `Statement`/`ResultSet` is the DAO's responsibility; the connection is acquired using a mechanism aligned with the transaction manager if present.
- **DAO using JdbcTemplate:** Spring handles the boilerplate of creating/closing resources; the DAO returns DTOs/records/Lists instead of JDBC cursors.
- **Service with `@Transactional`:** Spring manages the transaction boundary and the participating connection; the repository does not manually commit/close a connection owned by the manager.
- **Connection pool:** the datasource hands out logical handles for multiple calls; do not "fix" leaks by increasing the pool size indefinitely. Monitor active/idle/pending counts, query durations, and controlled leak detection.
- **ORM independence:** `Connection`/`Statement`/`ResultSet` are the JDBC model. Hibernate/JPA may also execute over JDBC underneath, but entities/`EntityManager` have different lifecycles and abstractions; do not conflate those objects with JDBC cursors.

A way to remember responsibilities:

```text
Raw JDBC:
  Caller / DAO owns Connection -> Statement -> ResultSet
  Caller / DAO closes in reverse order.

Spring JdbcTemplate:
  Framework owns Connection/Statement/ResultSet scope.
  Callback owns only data mapping; return Java data.

Spring @Transactional:
  Transaction manager owns transactional Connection lifetime.
  JdbcTemplate/DataSourceUtils participate correctly.
  Service owns business transaction boundary.
```

## 14. Checklist Before Completing a DAO or Query

- [ ] I know **who creates** the connection/statement/result set and **who must close** them.
- [ ] Every resource I own is placed in `try-with-resources` or an equivalent `finally` block.
- [ ] `ResultSet` is read **before** the statement/connection closes; no raw cursor is returned outward.
- [ ] I use `PreparedStatement` and bind parameters for user-supplied values.
- [ ] I check `next()`, SQL `NULL`, columns read, and exact data types.
- [ ] I choose the right `executeQuery`/`executeUpdate`/`execute`.
- [ ] Transactions are explicitly committed/rolled back when I manage them myself; never left up to `close()`.
- [ ] If Spring manages the transaction, I use `JdbcTemplate`/`DataSourceUtils` instead of a separate connection.
- [ ] `JdbcTemplate` callbacks only map data; I close returned streams when the API requires it.
- [ ] Large queries have a fetch/limit/stream strategy with appropriate scope and timeouts.
- [ ] Exception paths still clean up resources cleanly and do not swallow the root cause of errors.
- [ ] Tested zero rows, multiple rows, SQL errors, mapping errors, and pool usage in tests.

## 15. Self-Check

**1.** Does `Statement.close()` close the current `ResultSet`?  
**Answer:** yes, per the JDBC contract for the result set created by that statement. However, you should still use explicit `try-with-resources` for the result set to release it early and safely.

**2.** Does `ResultSet.close()` close the `Connection`?  
**Answer:** no. Closing only the result set does not release the connection; the owner of the connection must release it according to its contract.

**3.** A DAO returns a `ResultSet` from inside `try (Connection...; Statement...)`; the caller iterates it afterward. True or false?  
**Answer:** false, because the statement/connection have already been closed when the method returns. Return mapped Java data or design a scoped streaming approach instead.

**4.** A `PreparedStatement` has `?` parameters; calling `executeQuery("SELECT...")` like a `Statement`. True or false?  
**Answer:** wrong API usage; bind with `setXxx` and then call `executeQuery()` with no arguments.

**5.** Inside a `@Transactional` service, each repository calls `dataSource.getConnection()` on its own. Are the queries guaranteed to share one transaction?  
**Answer:** no. For JDBC in Spring, use `JdbcTemplate`/`DataSourceUtils` along with the same datasource/transaction manager.

**6.** With HikariCP pooling enabled, `Connection.close()` may return to the pool rather than closing the TCP socket. Do we still need to call `close()`?  
**Answer:** yes, still required! Without returning the logical handle, the pool runs out of connections for other requests.

**7.** In raw JDBC with `setAutoCommit(false)`, calling only `close()` without `commit()/rollback()`. Is rollback guaranteed?  
**Answer:** no; the outcome when closing a connection with an active transaction is implementation-dependent. You must finish the transaction explicitly.

## Official References

- Java SE 17 JDBC `Connection`: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Connection.html
- Java SE 17 JDBC `Statement`: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Statement.html
- Java SE 17 JDBC `PreparedStatement`: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/PreparedStatement.html
- Java SE 17 JDBC `ResultSet`: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/ResultSet.html
- Java SE 17 `try-with-resources`: https://docs.oracle.com/javase/tutorial/essential/exceptions/tryResourceClose.html
- Spring Framework — JDBC core/`JdbcTemplate`: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring Framework — Connection management/`DataSourceUtils`: https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html
- Spring Framework — Transaction management: https://docs.spring.io/spring-framework/reference/data-access/transaction.html
- Spring Boot 3.5.16 release: https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/

**Final Takeaway:** `Connection` creates `Statement`, and `Statement` creates `ResultSet`. When doing raw JDBC, **close in reverse order using try-with-resources**. When using `JdbcTemplate`, **Spring owns callback cleanup**. When using `@Transactional`, **the transaction manager owns the participating connection**. Knowing clearly *who owns the resource* prevents most connection leaks, prematurely closed cursors, and broken transactions.