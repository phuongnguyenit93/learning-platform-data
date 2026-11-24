# What Spring Handles Instead of Manual JDBC Code

## 1. The Problem: What Does Plain JDBC Force Developers to Do?

JDBC (Java Database Connectivity) is the standard API for Java to interact with relational databases. JDBC provides `Connection`, `PreparedStatement`, `ResultSet`, and `SQLException`. It offers direct control, yet even a very simple operation such as "find a user by ID" requires repeating a lot of technical boilerplate:

1. Obtain a `DataSource` or connection details; acquire a `Connection`.
2. Create a `PreparedStatement` for the SQL and bind parameters in the exact order and type.
3. Execute `executeQuery()` / `executeUpdate()` and read the results.
4. Iterate through `ResultSet`, extract the right columns, and map them to Java objects.
5. Close `ResultSet`, `Statement`, and `Connection` along both success and error paths.
6. Handle `SQLException` and decide which exceptions to propagate to the business layer.
7. If multiple statements require consistency, manually control transactions (`autoCommit`, `commit`, `rollback`) and avoid running statements on different connections.

The plain JDBC snippet below shows that *reading a single record* already takes many lines. `try-with-resources` helps close resources safely, but it does not eliminate the boilerplate:

```java
// Illustrative snippet inside a class that already has a DataSource and record Person(long id, String name).
Person findByIdRaw(DataSource dataSource, long id) throws SQLException {
    String sql = "SELECT id, name FROM people WHERE id = ?";
    try (Connection connection = dataSource.getConnection();
         PreparedStatement statement = connection.prepareStatement(sql)) {
        statement.setLong(1, id);
        try (ResultSet rs = statement.executeQuery()) {
            if (!rs.next()) {
                return null;
            }
            return new Person(rs.getLong("id"), rs.getString("name"));
        }
    }
}
```

Opening/closing resources, translating errors, and repeating query boilerplate are *infrastructure concerns*. The actual application-specific logic is just the SQL, the `id` value, the result-mapping rules, and the behavior when no record is found.

## 2. Which Tasks Does Spring JDBC Take Over?

The flagship component is `JdbcTemplate` in the `spring-jdbc` module. The application supplies a `DataSource` and simply expresses the SQL, parameters, and mapping; Spring orchestrates the sequence of JDBC steps.

| Task | Manual JDBC | Spring JDBC |
| --- | --- | --- |
| Acquire and release connections | Call `getConnection()` then `close()`; manually coordinate if a transaction exists | `JdbcTemplate` uses Spring's connection acquisition/release mechanism, coordinating with the active transaction when configured properly |
| Create statement, set parameters | `prepareStatement`, positional `setXxx` | `query` / `update` take SQL and parameters; callbacks available for special cases |
| Execute and close resources | Call execute and close `ResultSet`, `Statement`, connection | Template executes and cleans up resources on both success and failure paths |
| Iterate results | `while (rs.next())`, construct objects manually | `RowMapper`, `ResultSetExtractor`, `RowCallbackHandler` |
| SQL errors | Catch/handle checked `SQLException` | Translates into unchecked `DataAccessException` hierarchy, with specific exception types when recognized |
| Multiple writes in one transaction | Keep the same connection, disable auto-commit, commit/rollback manually | `PlatformTransactionManager` and `@Transactional` manage transaction boundaries when enabled and used properly |
| Queries with named parameters | Positional JDBC `?` | `NamedParameterJdbcTemplate` with `:name`, converted to JDBC parameters |
| Batch operations | Assemble batch/flush manually | `batchUpdate` supports batch execution |
| Auto-generated keys | `RETURN_GENERATED_KEYS` then read results | `KeyHolder` / `GeneratedKeyHolder` helps retrieve DB-generated keys |

**Responsibility boundary:** Spring *does not write correct SQL for you*, *does not fix your schema*, *does not prevent every performance issue*, and *does not create a transaction just because you instantiate `JdbcTemplate`*. Developers remain responsible for query design, indexing, business correctness, input security, and transaction configuration.

### 2.1. How a Query Is Processed

```text
Repository / DAO
    │  SQL + parameters + RowMapper
    ▼
JdbcTemplate
    ├─ acquires Connection from DataSource via Spring's mechanism
    ├─ prepares PreparedStatement and binds parameters
    ├─ executes query/update
    ├─ reads ResultSet via callback/RowMapper
    ├─ translates SQLException to DataAccessException
    └─ closes ResultSet/Statement, releases Connection appropriately for the transaction
    ▼
Java result or translated exception
```

Typically `JdbcTemplate` uses `DataSourceUtils` to obtain the connection bound to the current thread's transaction if one exists; while a transaction is active, "releasing" does not mean physically closing the connection before the transaction ends. With a connection pool, `close()` normally returns the connection to the pool rather than tearing down the socket to the DB every time.

`JdbcTemplate` is designed to be reused across components as a configured object. You can create one instance per `DataSource` (or configure additional specialized instances); do not create a new template per record.

## 3. Runnable Example: Same Data, Two Query Styles

This example uses **Java 17+**, Maven, **Spring JDBC 6.2.12**, and an in-memory H2 database. No DB server installation is needed.

Structure:

```text
jdbc-work-demo/
├── pom.xml
└── src/main/java/example/JdbcWorkDemo.java
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>jdbc-work-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
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

`src/main/java/example/JdbcWorkDemo.java`:

```java
package example;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Map;
import javax.sql.DataSource;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

public class JdbcWorkDemo {
    record Person(long id, String name) {}

    public static void main(String[] args) throws SQLException {
        JdbcDataSource dataSource = new JdbcDataSource();
        dataSource.setURL("jdbc:h2:mem:demo;DB_CLOSE_DELAY=-1");
        dataSource.setUser("sa");
        dataSource.setPassword("");

        JdbcTemplate jdbc = new JdbcTemplate(dataSource);
        jdbc.execute("CREATE TABLE people (id BIGINT PRIMARY KEY, name VARCHAR(100) NOT NULL)");
        jdbc.update("INSERT INTO people (id, name) VALUES (?, ?)", 1L, "Lan");
        jdbc.update("INSERT INTO people (id, name) VALUES (?, ?)", 2L, "Minh");

        Person raw = findByIdRaw(dataSource, 1L);
        System.out.println("Raw JDBC: " + raw);

        RowMapper<Person> mapper =
                (rs, rowNum) -> new Person(rs.getLong("id"), rs.getString("name"));

        Person fromTemplate = jdbc.queryForObject(
                "SELECT id, name FROM people WHERE id = ?", mapper, 2L);
        System.out.println("JdbcTemplate: " + fromTemplate);

        NamedParameterJdbcTemplate named = new NamedParameterJdbcTemplate(dataSource);
        Person fromNamed = named.queryForObject(
                "SELECT id, name FROM people WHERE id = :personId",
                Map.of("personId", 1L),
                mapper);
        System.out.println("NamedParameter: " + fromNamed);
    }

    static Person findByIdRaw(DataSource dataSource, long id) throws SQLException {
        String sql = "SELECT id, name FROM people WHERE id = ?";
        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, id);
            try (ResultSet rs = statement.executeQuery()) {
                if (!rs.next()) {
                    return null;
                }
                return new Person(rs.getLong("id"), rs.getString("name"));
            }
        }
    }
}
```

In the directory containing `pom.xml`, run:

```bash
mvn -q compile exec:java -Dexec.mainClass=example.JdbcWorkDemo
```

Output printed by the program (Maven may emit additional messages depending on the environment):

```text
Raw JDBC: Person[id=1, name=Lan]
JdbcTemplate: Person[id=2, name=Minh]
NamedParameter: Person[id=1, name=Lan]
```

**Explanation:** All three approaches return the same `Person` type. The plain JDBC method manually manages `Connection`, `PreparedStatement`, and `ResultSet`. The two Spring queries only specify SQL, parameters, and a `RowMapper`; closing resources and translating `SQLException` into data access exceptions are handled by the template. `jdbc.update(...)` returns the number of affected rows (here each insert returns 1), which is useful when validating expectations.

## 4. Mapping Results and Record Cardinality

`JdbcTemplate` does not guess every DTO structure in your application. You still choose how data is read:

- `RowMapper<T>` maps **one row** of a `ResultSet` into a `T`. Use `query(sql, mapper, args...)` to fetch a list; the template runs the loop.
- `queryForObject(sql, mapper, args...)` is suitable when expecting **exactly one row**; zero rows typically raises `EmptyResultDataAccessException`, and more than one row raises `IncorrectResultSizeDataAccessException`. It does **not** return `null` as the raw JDBC example branch did.
- `ResultSetExtractor<T>` processes the **entire** `ResultSet` in a custom way, such as aggregating multiple rows into one aggregate object.
- `RowCallbackHandler` processes rows sequentially via a callback when you do not need to build a result list. However, the `ResultSet` is only valid inside the callback; do not retain it for use after the template method finishes.

Example of fetching multiple rows and handling the zero-row case:

```java
// Snippet used inside a DAO that already has JdbcTemplate jdbc and RowMapper<Person> mapper.
List<Person> people = jdbc.query(
        "SELECT id, name FROM people ORDER BY id", mapper);

List<Person> matches = jdbc.query(
        "SELECT id, name FROM people WHERE id = ?", mapper, 999L);
Person optional = matches.isEmpty() ? null : matches.get(0);
```

This example is a **snippet**, not a standalone Java file; it requires importing `java.util.List` and having `jdbc` and `mapper`. For queries that return at most one row, using `query(...)` and checking the list clearly expresses "may not exist."

Automatic mappers like `BeanPropertyRowMapper` can reduce boilerplate for compatible JavaBeans, but explicit mapping with `RowMapper` usually offers better control over column names, types, `NULL` values, and immutable objects.

## 5. Parameter Binding: Convenient and Safe

`JdbcTemplate` preserves JDBC's `PreparedStatement` model: data values are bound separately from the SQL structure.

```java
// Correct: the id value is passed as a parameter.
jdbc.query("SELECT id, name FROM people WHERE id = ?", mapper, userId);

// Avoid: concatenating user input directly into SQL.
String unsafe = "SELECT id, name FROM people WHERE name = '" + inputName + "'";
```

When a query has multiple conditions, `NamedParameterJdbcTemplate` allows meaningful parameter names:

```java
String sql = """
        SELECT id, name FROM people
        WHERE id >= :minId AND name = :name
        ORDER BY id
        """;
Map<String, ?> params = Map.of("minId", 1L, "name", "Lan");
List<Person> result = named.query(sql, params, mapper);
```

Spring parses `:minId` and `:name`, converts them into JDBC placeholders, and binds the corresponding values; the database itself does not need to support `:name` syntax. When binding a list for `IN (:ids)`, watch out for empty lists and per-DB parameter limits; check beforehand rather than assuming every case is handled identically.

**Important limitation:** placeholders are only for *values* (such as id, name, timestamp), not for substituting table names, column names, or `ORDER BY` directions. Dynamic SQL structural elements must come from an application-side allowlist.

Since Spring Framework 6.1, `JdbcClient` has been added as a fluent API combining positional and named parameters on top of familiar JDBC mechanics. It is an alternative style and does not remove the need to understand `DataSource`, binding, mapping, or transactions.

## 6. Exception Translation: From SQLException to DataAccessException

JDBC uses `SQLException` (checked), which forces business layers to declare `throws SQLException` or `catch` and wrap errors manually. `JdbcTemplate` catches JDBC errors and uses a `SQLExceptionTranslator` to map them to the `org.springframework.dao.DataAccessException` hierarchy (unchecked).

Common exception types when recognized by the database and translator:

| Situation | Possible Spring Exception |
| --- | --- |
| Unique/primary key violation | `DuplicateKeyException` |
| Invalid SQL | `BadSqlGrammarException` |
| No row when `queryForObject` expects 1 | `EmptyResultDataAccessException` |
| Unexpected row count | `IncorrectResultSizeDataAccessException` |
| Unclassified specific JDBC error | `UncategorizedSQLException` |

Translation relies on exception subclasses, SQLState, error codes, and translator configuration; it is **not guaranteed** that every driver/DB produces the exact same specific type in all situations. The original exception can still be preserved as the cause for diagnostics.

Example of deliberately handling a duplicate key error:

```java
try {
    jdbc.update("INSERT INTO people (id, name) VALUES (?, ?)", 1L, "Khac");
} catch (DuplicateKeyException ex) {
    // Can return a business message such as "id already exists";
    // do not merely log it and silently report the operation succeeded.
}
```

This is a DAO/service snippet. `@Repository` is useful for marking the persistence layer and enabling exception translation for applicable persistence APIs, but it is **not a prerequisite** for `JdbcTemplate` to translate `SQLException`: the template itself already performs that translation.

## 7. Transactions: How Does Spring Coordinate Connections Automatically?

You can read or write a single standalone statement without a Spring-managed transaction. However, a business operation spanning multiple statements usually requires **all-or-nothing** behavior, such as a money transfer that debits a source account and credits a destination account.

With plain JDBC, developers must retain the same `Connection`, disable `autoCommit`, manually `commit` or `rollback` on failure, and finally restore the connection state appropriately before returning it to the pool. Missing a single error branch can leave partial updates in the database or leave the connection in an unexpected state.

In Spring, boundaries are typically placed at the **service layer**:

```java
// Illustrative snippet in a Spring application configured with a transaction manager for the DataSource.
@Service
public class TransferService {
    private final JdbcTemplate jdbc;

    public TransferService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void transfer(long fromId, long toId, long amount) {
        if (amount <= 0 || fromId == toId) {
            throw new IllegalArgumentException("Invalid transfer");
        }
        int debit = jdbc.update(
                "UPDATE accounts SET balance = balance - ? " +
                "WHERE id = ? AND balance >= ?",
                amount, fromId, amount);
        if (debit != 1) {
            throw new IllegalStateException("Source missing or insufficient funds");
        }
        int credit = jdbc.update(
                "UPDATE accounts SET balance = balance + ? WHERE id = ?",
                amount, toId);
        if (credit != 1) {
            throw new IllegalStateException("Destination missing");
        }
    }
}
```

Illustrative imports: `org.springframework.stereotype.Service`, `org.springframework.transaction.annotation.Transactional`, and `org.springframework.jdbc.core.JdbcTemplate`. Running this in practice requires an `accounts` table, a `JdbcTemplate` bean, a suitable transaction manager, and transaction management enabled. This is a **service example**, not a standalone program; business rules for balances, locking, currency types, and concurrency must be designed further for the target database.

When a call to `transfer(...)` passes through a Spring transaction proxy, the transaction manager starts or joins a transaction; `JdbcTemplate` acquires the corresponding connection from the same `DataSource`; if both statements succeed the transaction is committed, while the `RuntimeException` in the example triggers rollback by default.

Typical plain Spring Framework configuration:

```java
@Configuration
@EnableTransactionManagement
class JdbcConfig {
    @Bean
    PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new JdbcTransactionManager(dataSource);
    }
}
```

This illustrative configuration requires importing `org.springframework.context.annotation.*`, `org.springframework.transaction.PlatformTransactionManager`, `org.springframework.jdbc.support.JdbcTransactionManager`, `javax.sql.DataSource`, and a concrete `DataSource` bean. With Spring Boot and `spring-boot-starter-jdbc`, the framework typically auto-configures `DataSource`, `JdbcTemplate`, and the transaction manager when matching conditions and dependencies are present; you still need to configure the URL/driver/credentials and verify against the real environment.

Common misconceptions:

- `@Transactional` is only metadata without an active transaction infrastructure; `new TransferService(...)` outside the container receives no proxy.
- In default proxy mode, **self-invocation** (`this.transfer(...)` called from within the same bean) does not trigger the advice of the called method; call through an appropriate bean/proxy or redesign service boundaries.
- By default, `@Transactional` rolls back on `RuntimeException` and `Error`, and does not roll back on checked exceptions without extra configuration (such as `rollbackFor`). Catching and swallowing an exception can also cause Spring to commit because the method returns normally.
- `readOnly = true` is primarily an optimization/setup hint for drivers or ORMs, **not an absolute write-prevention mechanism**.
- `JdbcTemplate` only participates in a transaction automatically when it uses a `DataSource` matching the transaction manager. Manually opening a connection via `dataSource.getConnection()` inside a transactional block can obtain a different connection and break atomicity; prefer templates or `DataSourceUtils` for low-level JDBC integration.
- Database transactions do not protect external side effects such as sending emails or making HTTP calls; those do not roll back alongside a JDBC transaction.

## 8. Other JDBC Utilities Provided by Spring

Beyond single queries, Spring JDBC offers APIs that reduce boilerplate where needed:

- **`batchUpdate`:** submits multiple parameter sets in a batch, typically reducing driver/database round-trip overhead. Actual gains depend on the driver, batch size, transactions, and SQL type; errors and update counts still require handling.
- **`KeyHolder` / `GeneratedKeyHolder`:** retrieves primary keys generated by the DB during an INSERT; key retrieval support depends on the driver and SQL.
- **`SimpleJdbcInsert`:** a convenience API for INSERTs that can use DB metadata to build part of the statement; it is not an ORM.
- **`JdbcClient` (Spring 6.1+):** a fluent style for queries and updates; uses Spring JDBC mechanics underneath.
- **`SimpleJdbcCall`:** assists with calling stored procedures and functions, still subject to metadata differences across DBs and drivers.
- **`JdbcTestUtils`, `@JdbcTest` in the Spring testing ecosystem:** help set up DB access tests; they do not replace testing against the production dialect/DB when SQL is vendor-dependent.

Standalone batch example independent of transaction configuration:

```java
List<Object[]> args = List.of(
        new Object[] { 3L, "An" },
        new Object[] { 4L, "Binh" }
);
int[] updateCounts = jdbc.batchUpdate(
        "INSERT INTO people (id, name) VALUES (?, ?)", args);
```

This is a snippet requiring `java.util.List` and an initialized `jdbc`. Do not infer the number of network round trips solely from the array length; drivers handle batching differently.

## 9. Which Developer Decisions Does Spring Not Replace?

Understanding this boundary prevents unrealistic expectations of abstractions:

1. **SQL and schema:** Spring does not choose indexes, prevent N+1 queries, fix SQL missing a `WHERE` clause, adjust pagination, or decide the right isolation level.
2. **Data security:** you must still validate inputs, restrict dynamic queries, enforce authentication/authorization, and handle concurrent updates. Parameter binding does not automatically protect dynamically concatenated column or table names.
3. **"Not found" semantics:** you decide whether to return `Optional`, an empty list, a 404 error, or a business exception; `queryForObject` typically throws an exception when no row is found.
4. **Atomicity:** you must properly configure the transaction manager, proxy call boundaries, `DataSource`, and rollback handling. A template alone does not wrap an entire service in a transaction.
5. **Resources and performance:** you still need to configure the connection pool, timeouts, appropriate fetch sizes/batches, and monitor slow SQL and connection counts. The template cleans up resources it opens itself, not arbitrary resources you open outside it.
6. **ORM:** `JdbcTemplate` does not provide a persistence context, dirty checking, lazy loading, or JPA/Hibernate-style entity relationship mapping. Spring Data JDBC also has its own model and is not synonymous with `JdbcTemplate`.

## 10. Common Mistakes and Remedies

| Mistake | Consequence | Remedy |
| --- | --- | --- |
| Concatenating user values directly into SQL | SQL injection and quoting bugs | Use `?` / `:name` placeholders and bind parameters |
| Using `queryForObject` for queries that may return 0 or many rows | Unexpected exceptions | Use `query` or enforce a unique constraint and handle 0 rows explicitly |
| Creating `JdbcTemplate` and assuming all statements run in 1 transaction | Partial writes when a later statement fails | Configure a transaction manager, place `@Transactional` on the service, and verify rollback |
| Catching `Exception` and only logging inside a transactional service | May commit even though the business operation failed | Let appropriate exceptions propagate or explicitly mark rollback per design |
| Calling `@Transactional` via `this.method()` | Bypasses the default proxy | Design calls through Spring beans and test actual transaction behavior |
| Opening a separate connection inside business logic using `JdbcTemplate` | Outside the transaction; leaks or partial updates | Use the template or an API participating in Spring-managed transactions |
| Retaining `ResultSet` for use after a callback | `ResultSet` is already closed when the template returns | Convert results into DTOs/collections immediately inside the callback |
| Treating Spring as a substitute for all DB tuning | Queries stay slow; contention and deadlocks | Use EXPLAIN, indexes, latency measurements, and tune pool and transaction duration |

## 11. Applying This in a Real Project

A small, verifiable approach:

1. **Configure a `DataSource`** pointing to a real DB with an appropriate connection pool; store credentials via secrets management, never hardcoded in source code.
2. **Create or inject `JdbcTemplate`/`NamedParameterJdbcTemplate`**. Repositories own SQL, parameters, and DTO mapping; services orchestrate use cases.
3. **Choose a clear contract for each method**: exactly one required row, zero or one row, many rows, or updated row count. Explicitly check `updateCount` when a business rule requires exactly one row.
4. **Place transactions at the service layer** for multi-statement operations that must commit or roll back together. Test both the success path and the failure path right after the first statement.
5. **Test realistically**: seed deterministic data; test duplicate keys, missing rows, rollbacks, concurrent updates, and dialect limits; monitor SQL, pool usage, and locks during execution.
6. **Drop down to low-level JDBC only when needed** for driver-specific features; even then, integrate with Spring-managed connections and transactions.

### Self-Check Questions

- Why does `try-with-resources` in plain JDBC still fail to eliminate all boilerplate?
- What does `RowMapper` do, and who is responsible for closing the `ResultSet`?
- Why is binding `:name` safer than concatenating values, yet unable to bind arbitrary column names?
- If the debit statement succeeds but the credit statement fails, what conditions are required for the first statement to roll back?
- How does `queryForObject` differ from a raw query returning `null` when no data is found?

**Key point to remember:** Spring JDBC removes most of the repetitive infrastructure code of plain JDBC: acquiring/releasing resources, preparing and executing statements, iterating/mapping results, translating exceptions, and integrating connections with transactions. SQL design, business contracts, security, transaction boundaries, and performance remain the application developer's responsibility.

### Official References

- Spring Framework — JDBC core: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring Framework — Using `@Transactional`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework — JDBC transaction management: https://docs.spring.io/spring-framework/reference/data-access/transaction.html
