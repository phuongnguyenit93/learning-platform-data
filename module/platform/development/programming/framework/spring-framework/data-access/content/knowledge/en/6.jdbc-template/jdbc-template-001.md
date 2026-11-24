# JdbcTemplate and JdbcOperations in Data Access Architecture

> **Key takeaway:** In Spring JDBC, `JdbcOperations` is the **interface defining the JDBC operations contract**; `JdbcTemplate` is the **class implementing that contract**. Both belong to `org.springframework.jdbc.core`. The repository layer can depend on `JdbcOperations` to declare the operations it needs, while Spring provides `JdbcTemplate` to execute them using a `DataSource`, managing connections/resources and translating SQL errors. This is an application of programming to an interface right in the data access layer.

This article clarifies the interface/implementation relationship, their place in the Spring Framework architecture, complete JDBC code, result handling, transactions, testability, and limitations to distinguish.

## 1. Two Types, One Operations Contract

Basic imports:

```java
import org.springframework.jdbc.core.JdbcOperations;
import org.springframework.jdbc.core.JdbcTemplate;
```

At the type-relationship level:

```java
public interface JdbcOperations {
    // Only illustrates the meaning of the interface; not the full API signature.
}

public class JdbcTemplate implements JdbcOperations {
    // Spring provides the actual implementation.
}
```

**The snippet above is a simplified diagram, not for creating two identically named types in an application.** In real projects, always import `JdbcOperations` and `JdbcTemplate` from Spring; do not redefine them yourself.

- **`JdbcOperations`:** defines a set of high-level JDBC methods, such as `query(...)`, `queryForObject(...)`, `update(...)`, `batchUpdate(...)`, and `execute(...)`. It only describes the operations a caller can request, without deciding the details of how JDBC resources are created and closed.
- **`JdbcTemplate`:** the central implementation of Spring JDBC. It coordinates the execution steps: acquiring a connection, preparing a statement, binding parameters, running SQL, iterating over the `ResultSet`, invoking callbacks/`RowMapper`, closing resources, and translating `SQLException` into the `DataAccessException` hierarchy.
- **`DataSource`:** the source that supplies `java.sql.Connection` instances to `JdbcTemplate`. It is typically configured as an independent bean and may use a connection pool.
- **`Connection`:** the actual JDBC object that Spring obtains from the `DataSource` when it needs to interact with the database.

Dependency diagram:

```text
Service layer (business logic, @Transactional)
                 |
                 v
BookRepository (Book access contract)
                 ^
                 |
JdbcBookRepository (JDBC implementation)
                 |
                 v
JdbcOperations (JDBC operations interface)
                 ^
                 | implements
                 |
JdbcTemplate (Spring implementation)
                 |
                 v
DataSource ---> Connection ---> SQL ---> Database
```

The diagram shows **two interfaces at two different levels**:

1. `BookRepository` is the **business contract for Book data**, named and designed by the application itself: `findById`, `save`, `findAll`.
2. `JdbcOperations` is the **general-purpose SQL/JDBC operations contract**, provided by Spring: `query`, `update`, `execute`.

Do not call `JdbcOperations` a business repository interface: it still exposes SQL and JDBC callbacks. It helps decouple a DAO from the **concrete `JdbcTemplate` implementation**, but it does not make the DAO completely independent of Spring JDBC.

## 2. Why Does JdbcTemplate Need the JdbcOperations Interface?

A DAO can depend on the concrete class:

```java
import org.springframework.jdbc.core.JdbcTemplate;

public final class SimpleBookDao {
    private final JdbcTemplate jdbc;

    public SimpleBookDao(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }
}
```

It can also depend on the interface:

```java
import org.springframework.jdbc.core.JdbcOperations;

public final class SimpleBookDao {
    private final JdbcOperations jdbc;

    public SimpleBookDao(JdbcOperations jdbc) {
        this.jdbc = jdbc;
    }
}
```

**The two blocks above are two alternative choices for the same class**; do not place both in the same package when compiling. In the second approach, the code only needs the methods published by `JdbcOperations`. Spring can inject a `JdbcTemplate` bean because that class implements the interface.

Practical benefits of depending on `JdbcOperations`:

- **Reduced coupling to a concrete implementation:** the DAO declares its need to use the JDBC execution API without needing to know which bean fulfills it.
- **Easier mocking/stubbing in unit tests:** you can create a mock `JdbcOperations` to verify coordination in the DAO without having to mock `Connection`, `PreparedStatement`, and `ResultSet`.
- **API scope control:** a variable of type `JdbcOperations` only allows calling methods of the contract; `JdbcTemplate`-specific configuration such as configuration setters does not appear at this boundary.
- **Consistency with dependency injection:** the class can receive the interface via its constructor, while Spring decides the actual instance when creating beans.

However, **not every DAO is required to declare `JdbcOperations`**. Using `JdbcTemplate` directly is valid and supported by Spring, especially when the class needs implementation-specific configuration methods or characteristics. Do not add a project-defined interface just to copy the entire `JdbcOperations` API without introducing a new business boundary.

### Distinguishing Polymorphism from Changing Database Technology

The following is valid in terms of Java types:

```java
JdbcOperations operations = new JdbcTemplate(dataSource);
```

`dataSource` in this example is a pre-configured `javax.sql.DataSource` variable; the snippet is a statement inside a method/constructor, not a standalone program.

Because `JdbcTemplate implements JdbcOperations`, an interface variable can point to a concrete instance. However, **switching from JDBC to JPA or R2DBC cannot be done merely by swapping the implementation of `JdbcOperations`**: this interface carries a synchronous JDBC contract, whereas JPA/R2DBC have different access models. To decouple business logic from persistence technology, place a domain-oriented repository interface at a higher layer, such as `BookRepository`.

## 3. What Does JdbcTemplate Do Instead of Plain JDBC?

When using plain JDBC to fetch records, a developer typically has to:

1. Obtain a `Connection` via `DataSource.getConnection()`.
2. Create a `PreparedStatement`.
3. Bind each parameter to the `?` placeholders.
4. Call `executeQuery()`.
5. Loop through the `ResultSet` and read each column by type.
6. Close the `ResultSet` and `Statement`, and release the `Connection` even when an error occurs.
7. Handle `SQLException`, distinguish database errors, and decide how errors propagate to upper layers.

`JdbcTemplate` handles most of that repetitive mechanism and lets application code provide the SQL, parameters, and data mapping logic. For example:

```java
List<String> titles = jdbc.query(
    "SELECT title FROM books WHERE price >= ? ORDER BY id",
    (rs, rowNum) -> rs.getString("title"),
    100
);
```

`jdbc` is an injected `JdbcOperations` or `JdbcTemplate` variable; `titles` receives the list in the order requested by SQL. This is a **code snippet inside a method** assuming a `books` table, not a standalone Java file.

Spring uses `RowMapper<String>` (expressed as a lambda) to convert each row into a `String`. There is no need to manually write a `while (resultSet.next())` loop, close the statement, or return the connection. When SQL needs parameters, use `?` and bind values to avoid concatenating user input directly into the SQL string.

### Responsibility Split Table

| Task | Handled by `JdbcTemplate`/Spring | Handled by application code |
| --- | --- | --- |
| Connections | Obtains/releases a JDBC connection via a transaction-aware source | Chooses/configures the `DataSource` |
| SQL | Prepares and executes the statement | Writes business-correct SQL |
| Parameters | Binds values via JDBC | Supplies values and appropriate data types |
| Results | Iterates over `ResultSet` and invokes callbacks | Maps rows to records/DTOs |
| Resources | Closes `ResultSet`, statement, and releases connection | Does not retain JDBC resource references outside callbacks |
| Errors | Translates many `SQLException`s into `DataAccessException` | Decides error handling with business meaning |
| Transactions | Integrates with Spring's connection-bound mechanism | Defines `@Transactional` boundaries and an appropriate transaction manager |

**Limitations:** `JdbcTemplate` does not automatically know business SQL, does not guarantee queries are always efficient, does not automatically prevent N+1 queries, and does not replace schema, index, or transaction design.

## 4. Complete Spring Boot Application Example: Repository Depending on JdbcOperations

This example uses **Java 17+**, Spring Boot 3.3+, Spring JDBC, and in-memory H2. Create a standard Spring Boot Gradle project with the Spring Boot plugin and dependency management, then add the dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
}
```

This is the `dependencies` section added to an **existing Spring Boot build script**, not the entire `build.gradle` file. For Maven, use the equivalent dependencies. Spring Boot can auto-configure `JdbcTemplate` only when conditions such as a valid data source and required classes on the classpath are met.

**`src/main/resources/application.yml`:**

```yaml
spring:
  datasource:
    url: "jdbc:h2:mem:jdbc_ops_demo;DB_CLOSE_DELAY=-1"
    driver-class-name: org.h2.Driver
    username: sa
    password: ""
```

Here, the H2 database is created in memory when the application runs and requires no separate DB server.

### 4.1. Return Data Type

**`src/main/java/example/Book.java`:**

```java
package example;

public record Book(long id, String title, int price) {}
```

`record` has been available since Java 16, suitable for Java 17+. It automatically provides a constructor, `id()`/`title()`/`price()` accessors, and a predictable `toString()`.

### 4.2. Business Repository Contract

**`src/main/java/example/BookRepository.java`:**

```java
package example;

import java.util.List;
import java.util.Optional;

public interface BookRepository {
    int insert(Book book);
    List<Book> findAll();
    Optional<Book> findById(long id);
}
```

Services use `BookRepository` instead of writing SQL directly. The methods describe the module's data needs: insert, find all, find by identifier.

### 4.3. JDBC Repository Using JdbcOperations

**`src/main/java/example/JdbcBookRepository.java`:**

```java
package example;

import java.util.List;
import java.util.Optional;

import org.springframework.jdbc.core.JdbcOperations;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;

@Repository
public final class JdbcBookRepository implements BookRepository {
    private static final RowMapper<Book> BOOK_MAPPER =
        (rs, rowNum) -> new Book(
            rs.getLong("id"),
            rs.getString("title"),
            rs.getInt("price")
        );

    private final JdbcOperations jdbc;

    public JdbcBookRepository(JdbcOperations jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public int insert(Book book) {
        return jdbc.update(
            "INSERT INTO books (id, title, price) VALUES (?, ?, ?)",
            book.id(), book.title(), book.price()
        );
    }

    @Override
    public List<Book> findAll() {
        return jdbc.query(
            "SELECT id, title, price FROM books ORDER BY id",
            BOOK_MAPPER
        );
    }

    @Override
    public Optional<Book> findById(long id) {
        List<Book> found = jdbc.query(
            "SELECT id, title, price FROM books WHERE id = ?",
            BOOK_MAPPER,
            id
        );
        return found.stream().findFirst();
    }
}
```

Point-by-point explanation:

- `@Repository` allows Spring to detect the class during component scanning and create a bean, while also clarifying its role in the data access layer.
- The constructor requires **`JdbcOperations`**, while the actual bean is typically **`JdbcTemplate`** created by Spring Boot. This is dependency inversion via an interface.
- `BOOK_MAPPER` is a `RowMapper<Book>` that receives each result row and turns it into a record. The callback does not retain `ResultSet` after the method finishes.
- `insert` calls `update` and returns the number of affected rows; for a successful insert, this is typically 1.
- `findAll` uses `ORDER BY id` so the output order is deterministic. JDBC/Spring does not guarantee order if the SQL does not request it.
- `findById` uses `query`, so a query with zero rows returns an empty list and `Optional.empty()`. Since `id` is a PRIMARY KEY, there is at most one row; there is no need to catch the "zero rows" exception from `queryForObject`.
- The `?` placeholder separates `id`/`title`/`price` values from the SQL text. If a client supplies column names or dynamic SQL structure, a whitelist must be used; placeholders cannot be used for table or column names.

### 4.4. Running the Application and Observing Results

**`src/main/java/example/JdbcOperationsDemoApplication.java`:**

```java
package example;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcOperations;

@SpringBootApplication
public class JdbcOperationsDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(JdbcOperationsDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(JdbcOperations jdbc, BookRepository books) {
        return args -> {
            jdbc.execute("""
                CREATE TABLE books (
                    id BIGINT PRIMARY KEY,
                    title VARCHAR(100) NOT NULL,
                    price INT NOT NULL
                )
                """);

            System.out.println("insert1=" +
                books.insert(new Book(1L, "Java", 120)));
            System.out.println("insert2=" +
                books.insert(new Book(2L, "Spring", 200)));

            System.out.println("all=" + books.findAll());
            System.out.println("found=" + books.findById(2L));
            System.out.println("missing=" + books.findById(99L));
        };
    }
}
```

From the project root directory, run:

```bash
./gradlew bootRun
```

On Windows, use `gradlew.bat bootRun`. In a fresh H2 database with no additional schema or data scripts, the lines **printed by the program** (aside from Spring logs) are:

```text
insert1=1
insert2=1
all=[Book[id=1, title=Java, price=120], Book[id=2, title=Spring, price=200]]
found=Optional[Book[id=2, title=Spring, price=200]]
missing=Optional.empty
```

Why do we get this output?

1. Spring Boot creates a `DataSource` from H2 and provides a `JdbcTemplate`; that concrete bean can be injected via the `JdbcOperations` type.
2. `CommandLineRunner` creates the table using `execute`, then calls the repository API.
3. Both `INSERT`s are valid, so `update` returns 1 for each call.
4. `findAll` returns the list mapped via `BOOK_MAPPER` in ascending ID order.
5. `findById(2L)` finds one record; ID 99 has no rows so it returns `Optional.empty()`.
6. With JDBC/`JdbcTemplate`, these statements are executed directly at this layer without needing to create JPA entities or an `EntityManager`.

**Limitations of the example:** The Java files above form a complete Spring Boot program **when placed in a project with the corresponding build/dependency configuration**. They cannot be compiled with plain JDK `javac` alone because Spring libraries are required on the classpath. If run multiple times against the same database file or with another schema creation mechanism, insertion results may differ; that is why the example uses a fresh in-memory H2 database.

## 5. Key Operation Groups in JdbcOperations

`JdbcOperations` has many overloads; understanding the meaning of each method group is more important than memorizing every signature.

| API | Use when | Behavior |
| --- | --- | --- |
| `execute(String sql)` | DDL or SQL that needs no return data from a callback | Executes the SQL statement; other `execute` overloads accept callbacks |
| `update(String sql, Object... args)` | `INSERT`, `UPDATE`, `DELETE` | Returns `int` for affected row count; can be 0 |
| `query(String sql, RowMapper<T>, Object... args)` | Querying 0..N rows | Returns `List<T>`; 0 rows yields an empty list |
| `queryForObject(String sql, Class<T>, Object... args)` | Single row, single column such as `COUNT(*)` | Requires exactly 1 row and 1 column, mapped to the desired type |
| `queryForObject(String sql, RowMapper<T>, Object... args)` | Exactly 1 row to map into an object | Requires exactly 1 row; does not automatically turn 0 rows into `Optional.empty()` |
| `batchUpdate(...)` | Multiple update operations grouped in a batch | Returns affected row count info per batch item, depending on JDBC driver support |
| `queryForList(...)` | Simple result lists | Has overloads returning `List<Map<String,Object>>` or a single-column list of a specified type |
| `execute(..., callback)`, `query(..., callback)` | Need to customize statement creation or result extraction | Allows JDBC callbacks with lifecycle managed by the template |

### 5.1. `query(...)` vs. `queryForObject(...)`

When looking up an optional record, `query(...)` is often more expressive:

```java
List<Book> books = jdbc.query(
    "SELECT id, title, price FROM books WHERE id = ?",
    BOOK_MAPPER,
    42L
);
Optional<Book> one = books.stream().findFirst();
```

Here `BOOK_MAPPER` is the `RowMapper<Book>` declared in the repository, `jdbc` is the injected `JdbcOperations`, and the code resides inside a method.

By contrast:

```java
Book book = jdbc.queryForObject(
    "SELECT id, title, price FROM books WHERE id = ?",
    BOOK_MAPPER,
    42L
);
```

`queryForObject` expects exactly one row; if there are no rows it throws `EmptyResultDataAccessException`, and if there are multiple rows it throws a result-size error (`IncorrectResultSizeDataAccessException` or an appropriate subclass). When `id` has a unique constraint, multiple rows will not occur if data is valid, but **the not-found case must still be handled according to the business contract**.

For counts:

```java
Integer count = jdbc.queryForObject(
    "SELECT COUNT(*) FROM books WHERE price >= ?",
    Integer.class,
    100
);
```

`COUNT(*)` always returns one row in this simple aggregate query, so `queryForObject` fits well; the value can exceed the `Integer` range in very large systems, in which case consider `Long.class`.

### 5.2. ResultSet Processing Callback Types

`JdbcOperations` provides several callback types:

- **`RowMapper<T>`:** converts each row into an object; `query` collects them into a `List<T>`. This is the common choice when mapping records/DTOs.
- **`ResultSetExtractor<T>`:** processes the entire `ResultSet` and decides the return data structure itself; useful when multiple rows need to be grouped into a nested structure.
- **`RowCallbackHandler`:** processes one row at a time, typically to update an accumulator or stream data to an application-managed sink, without automatically building a `List<T>` like `RowMapper`.

Example using `ResultSetExtractor<Integer>` solely to illustrate a callback over the full result set:

```java
Integer count = jdbc.query(
    "SELECT id FROM books",
    rs -> {
        int seen = 0;
        while (rs.next()) {
            seen++;
        }
        return seen;
    }
);
```

In this query, counting in Java works, but **in a real application you should use `SELECT COUNT(*)`** so the DB performs the work more efficiently. A `ResultSetExtractor` callback receives a `ResultSet` not yet positioned on the first row; the code must call `next()` itself. Conversely, in `RowMapper`, Spring has already advanced the cursor to the corresponding row before invoking the callback.

Do not store or return the `ResultSet`/`Connection` itself outside a callback: the template closes resources when the call completes.

### 5.3. Batch Update

When there are many rows to write, you can use `JdbcOperations.batchUpdate(...)` instead of calling `update(...)` in a loop for each row. Example inside a method that has `jdbc`:

```java
int[] counts = jdbc.batchUpdate(
    "UPDATE books SET price = ? WHERE id = ?",
    java.util.List.of(
        new Object[] {150, 1L},
        new Object[] {250, 2L}
    )
);
```

This is a batch overload for a list of parameter arrays in modern Spring JDBC; the driver may return affected row counts or JDBC values like `Statement.SUCCESS_NO_INFO` in some cases. **Batching does not automatically mean an atomic transaction**: an explicit transaction is required if the updates must commit or rollback together. Likewise, batching does not guarantee the database executes logically less SQL; the benefit usually lies in fewer round-trips and driver optimizations.

## 6. Place in a Multi-Layered Architecture

A separation of responsibilities with lasting value:

```text
HTTP Controller / Message Consumer
             |
             v
Service (business rules, transaction boundary)
             |
             v
Domain Repository interface (BookRepository)
             |
             v
Infrastructure implementation (JdbcBookRepository)
             |
             v
JdbcOperations -> JdbcTemplate -> DataSource -> Database
```

**Controllers** do not need to know about `JdbcTemplate` or SQL when services/repositories encapsulate data operations. **Services** handle business rules, call repositories, and decide transactions. **JDBC repositories** write SQL, bind parameters, map result sets, and return appropriate objects. **Spring JDBC** takes care of resource lifecycles and standardizing data access errors.

### Why Should Services Depend on BookRepository?

If a service depends directly on `JdbcOperations` and contains SQL, business logic becomes mixed with persistence, making it harder to change schemas/queries, test business logic independently, and reuse data access functionality.

This does not mean **every small application needs many separate classes/interfaces**. Small applications or simple SQL scripts can inject `JdbcOperations` straight into a service. However, when business logic has multiple use cases or needs storage details isolated, a `BookRepository` expressing domain intent is usually easier to maintain.

### When to Choose a JdbcTemplate-Typed Field?

If a DAO needs an API only present on `JdbcTemplate`, or needs specific configuration at initialization time, using the concrete type can make sense. If the DAO only needs `query`/`update`, a field of type `JdbcOperations` is a clear choice. **Do not mutate the configuration of a shared `JdbcTemplate` while multiple requests are running**; the object is safe to share once configuration is complete.

## 7. Transactions: Do JdbcTemplate and JdbcOperations Create Transactions Automatically?

**No.** `JdbcOperations` is a JDBC operations interface; `JdbcTemplate` typically uses `DataSourceUtils` to look up the appropriate connection and participate in a Spring-managed transaction when one exists. Transaction boundaries are determined by the Spring transaction manager and `@Transactional` configuration, not by the name of the `jdbc` variable.

Service example integrating with `BookRepository` above:

**`BookBatchService.java`:**

```java
package example;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BookBatchService {
    private final BookRepository books;

    public BookBatchService(BookRepository books) {
        this.books = books;
    }

    @Transactional
    public void addPair(Book first, Book second) {
        books.insert(first);
        books.insert(second);
    }
}
```

This class is used in a **Spring context with a transaction manager for the matching `DataSource`**, and the method is called from another bean through a Spring proxy. If the second insert causes a `DuplicateKeyException` (an unchecked `DataAccessException`), default rollback rules typically roll back the first insert as well.

Key distinctions:

- Calling individual `jdbc.update(...)` **outside** a declared transaction depends on the connection's and environment's `autoCommit` mode; do not assume two calls form an atomic unit.
- Within a Spring JDBC transaction, operations via `JdbcTemplate`/`JdbcOperations` using the same data source can share the connection bound by the transaction manager.
- Transactions are managed by `DataSourceTransactionManager` or `JdbcTransactionManager` and must point to the matching `DataSource` bean. Multiple data sources do not automatically participate in a distributed transaction just because `@Transactional` is present.
- If obtaining a raw JDBC connection manually inside a Spring transaction, use `DataSourceUtils.getConnection(dataSource)` and `releaseConnection(connection, dataSource)` or use `JdbcTemplate`; calling `dataSource.getConnection()` directly on a typical pool is **not guaranteed** to participate in the currently bound transaction.
- `@Transactional` via Spring AOP proxies typically does not apply to self-invocations `this.someMethod()` within the same bean; new threads spawned by `@Async`/`CompletableFuture` also do not automatically inherit thread-bound transactions.

Therefore, when repository code declares a `JdbcOperations` field instead of `JdbcTemplate`, **transaction rules do not change**. At runtime, the actual implementation and connection management are still used.

## 8. Translating SQL Errors into DataAccessException

A major value of `JdbcTemplate` is providing a unified Spring error hierarchy rather than `SQLException`, which varies by DBMS and driver. Operations on `JdbcOperations` typically throw unchecked `DataAccessException` (or a subclass) when data access errors occur.

Typical examples:

| Case | Spring type you may encounter | Meaning |
| --- | --- | --- |
| Unique key violation | `DuplicateKeyException` | Insert/update hits a unique or PK constraint |
| Invalid query syntax | `BadSqlGrammarException` | SQL is invalid for the dialect/schema |
| `queryForObject` finds no rows | `EmptyResultDataAccessException` | Expected exactly 1 row but received 0 |
| `queryForObject` receives multiple rows | `IncorrectResultSizeDataAccessException` | Result count does not match expectation |
| DB resource issue | `DataAccessException` subclass depending on cause | Timeout, unreachable DB, or driver error |

**There is no guarantee that every DBMS maps every SQL error code to the same specific subclass.** Spring uses an error translator depending on JDBC/DBMS/configuration. Business code should catch only the specific error types it can handle; unrecoverable errors are usually allowed to propagate to the exception/transaction policy layer.

Do not rely on `catch (SQLException)` around a `jdbc.query(...)` call as in plain JDBC: the `JdbcTemplate` contract translates errors into unchecked exceptions. Conversely, custom JDBC callbacks may be permitted to declare `SQLException` so the template translates it at the callback boundary.

### Handling "Not Found"

`queryForObject` has an **exactly-one-result** contract. If a use case allows "absent", appropriate approaches include:

- `query(...)` returning `List<T>`, then producing `Optional.empty()` as in the example repository.
- Using `queryForObject(...)` and specifically catching `EmptyResultDataAccessException` when that is an intentional part of the contract.

Do not catch `DataAccessException` and turn all failures into `Optional.empty()`: doing so hides syntax errors, lost DB connections, and database failures as "data not found".

## 9. JdbcOperations, NamedParameterJdbcOperations, and JdbcClient

These three APIs are related, but they are **not three interchangeable names for one interface**:

| API | Parameter syntax | Relationship |
| --- | --- | --- |
| `JdbcOperations` | Positional `?` placeholders in classic JDBC methods | Interface implemented by `JdbcTemplate` |
| `JdbcTemplate` | Supports traditional JDBC execution API with `?` and callbacks | Class implementing `JdbcOperations` |
| `NamedParameterJdbcOperations` | Named placeholders such as `:id`, `:title` | Separate interface implemented by `NamedParameterJdbcTemplate` |
| `JdbcClient` (Spring 6.1+) | Fluent API supporting positional or named parameters | Facade using `JdbcOperations`/`NamedParameterJdbcOperations` underneath for execution |

**`NamedParameterJdbcOperations` does not extend `JdbcOperations`.** When you need to pass many named values or want explicit parameter names, you can inject the `NamedParameterJdbcOperations` interface and use `NamedParameterJdbcTemplate` as the implementation.

Example inside a method with `NamedParameterJdbcOperations namedJdbc`:

```java
Integer count = namedJdbc.queryForObject(
    "SELECT COUNT(*) FROM books WHERE price >= :minPrice",
    java.util.Map.of("minPrice", 100),
    Integer.class
);
```

This uses Spring's separate interface:

```java
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcOperations;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
```

Named parameters are translated/bound by Spring into the appropriate JDBC statement. Named parameters are a way to express intent more clearly when a long query has many parameters; they **do not convert SQL into a different query language**.

Since Spring Framework 6.1, `JdbcClient` provides a unified fluent API for common queries/updates and delegates execution to the underlying operations classes. It does not make `JdbcOperations` obsolete or valueless; advanced callback cases can still use `JdbcTemplate`/`JdbcOperations`.

## 10. Thread Safety, Connection Pools, and Resources

`JdbcTemplate` is designed to be **thread-safe once configured**. A single bean can be injected into multiple repositories and serve concurrent requests; each operation does not use a single global `Connection`. Connections come from the `DataSource`/pool and are managed per operation or transaction.

Practical rules:

1. **Register `DataSource` and `JdbcTemplate` as shared beans** in normal configuration instead of creating a new template on every request. Calling `new JdbcTemplate(dataSource)` manually can still work, but container beans help keep configuration consistent.
2. **Do not store `Connection`, `Statement`, or `ResultSet` in fields of a singleton repository.** They have short lifecycles and carry per-execution state.
3. **Do not retain resources beyond a callback.** For example, `RowMapper` must read data and build a DTO/record; returning a `ResultSet` directly causes the resource to be closed before the caller uses it.
4. **Do not use `HashSet`/`HashMap` when code requires list ordering that those structures do not guarantee.** To get ordered results from the DB, use an appropriate `ORDER BY` in SQL, even when using `JdbcTemplate`.
5. **Be careful with streaming queries.** When using overloads that return `Stream<T>`, the caller must close the stream per the API; do not assume a long-lived stream automatically returns its connection immediately after creation.
6. **Avoid overly long queries inside transactions.** A held connection reduces the pool handles available for other requests; measure connection hold time, active/idle/pending pool counts, and concurrency before increasing pool size.
7. **Configure SQL statement/transaction timeouts appropriately.** Pool acquisition timeout, JDBC query timeout, and transaction timeout are distinct concerns.
8. **Parameter safety:** bind values with `?` or named parameters; never concatenate raw user input into SQL. Components that cannot be bound, such as column names for sorting, must be validated against a whitelist.

With multiple `JdbcTemplate`/`JdbcOperations` beans or multiple `DataSource`s, Spring may not know which bean to inject. Disambiguate explicitly using `@Qualifier`, `@Primary`, or bean configuration, and ensure the transaction manager matches the data source. Do not just look at the field name `jdbc` and assume connections go to the right DB.

## 11. Testing at the Right Level of Abstraction

Two complementary kinds of testing apply:

**Repository unit tests with a mock `JdbcOperations`:** verify that the repository invokes the right operation, binds the right parameters, and converts data into business results according to the contract. Because the interface can be mocked, the test does not need to spin up a real `DataSource`. However, if mocking `query(...)` to return a canned `Book`, the test **does not prove** that the SQL runs on a DB or that `RowMapper` maps columns accurately.

**Integration tests with a real database or H2:** execute the schema and test data, invoke the repository through a Spring context/`JdbcTemplate`, and verify:
- `INSERT` and `SELECT` read the right data/columns.
- Queries with `ORDER BY` actually return the requested order.
- Not-found cases properly return `Optional.empty()`.
- Constraints such as unique keys or foreign keys fail properly at the data layer.
- A `@Transactional` service rolls back multiple updates against the same data source when an unchecked exception occurs.
- With multiple `DataSource`s, repositories use the right data source and transaction manager.

Spring Boot provides the `@JdbcTest` slice test to focus on testing JDBC components; it can be combined with `@Import(JdbcBookRepository.class)` and an appropriate embedded test database. In systems using PostgreSQL-specific syntax or behavior, testing only with H2 can miss differences; in that case, test against real PostgreSQL (for example, via Testcontainers).

A test running repeatedly "without errors" also does not prove the repository manages resources cleanly: if leaks are suspected, observe active pool connections after a sufficient number of operations under test conditions.

### Decision Questions When Designing Classes

- Does the DAO only need general `query`/`update` methods? You can declare the field as `JdbcOperations`.
- Does the DAO need configuration APIs or specifics of `JdbcTemplate`? Consider injecting the concrete type, configured once at startup.
- Should the business API avoid seeing SQL? Define a repository interface like `BookRepository`.
- Does a query have too many `?` parameters? You can use `NamedParameterJdbcOperations` with `:paramName`.
- Want a fluent syntax on Spring 6.1+? Consider `JdbcClient`.
- Need to guarantee atomicity across multiple operations? Define `@Transactional`/transaction manager; do not expect `JdbcOperations` to group statements automatically.

## 12. Common Misconceptions to Avoid

| Misconception | Reality |
| --- | --- |
| "`JdbcOperations` is a class just like `JdbcTemplate`." | `JdbcOperations` is an **interface**; `JdbcTemplate` is an **implementation**. |
| "Simply declaring a `JdbcOperations` field makes Spring create the bean automatically." | An actual bean such as `JdbcTemplate` is still required, configured manually or via appropriate auto-configuration. |
| "Since the DAO uses an interface, it doesn't need SQL." | `JdbcOperations` is still a general JDBC API; the repository implementation must write SQL. |
| "`JdbcTemplate` always opens a new connection for every query." | The `DataSource` can be a pool, and Spring can reuse a connection bound to a transaction. |
| "Calling `queryForObject` with 0 rows returns `null`." | No; under its exactly-one-row contract, 0 rows causes `EmptyResultDataAccessException`. |
| "`query(...)` automatically guarantees a list ordered by ID." | No; database ordering requires an appropriate `ORDER BY`. |
| "`batchUpdate` automatically creates an atomic transaction." | No; an appropriate transaction boundary is needed to commit/rollback the whole batch. |
| "When using JdbcTemplate, the DAO must close the Connection itself." | Normally the template manages resources; do not manually close its connection inside callbacks. |
| "Spring JDBC automatically detects and optimizes all slow SQL." | No; DBAs/applications still need indexes, proper SQL, query plan analysis, and timeouts. |
| "`JdbcOperations`, `NamedParameterJdbcOperations`, and `JdbcClient` are the same interface." | These are distinct APIs; they can work together within the same Spring JDBC stack. |

## 13. Self-Check Questions

**Question 1.** Why can we write `JdbcOperations jdbc` yet pass a `JdbcTemplate` instance into the constructor?

**Answer:** Because `JdbcTemplate implements JdbcOperations`. Java allows an interface-typed variable to accept a matching implementation; the DAO code only depends on methods published by the interface.

**Question 2.** Do `BookRepository` and `JdbcOperations` in the example have overlapping responsibilities?

**Answer:** No. `BookRepository` describes business operations on books; `JdbcOperations` describes general SQL operations. `JdbcBookRepository` bridges the two contracts.

**Question 3.** When a query might return no rows, why is `query(...)` usually easier to turn into an `Optional` than `queryForObject(...)`?

**Answer:** `query` returns an empty list when there are 0 rows; `queryForObject` requires exactly one row and throws an exception if none is found.

**Question 4.** In a `@Transactional` service, does changing a repository field from `JdbcTemplate` to `JdbcOperations` break the transaction?

**Answer:** No, provided Spring injects the same implementation/`DataSource` and operations still go through transaction integration. Transactions are governed by the transaction manager and calling through the Spring proxy.

**Question 5.** Does successfully mocking `JdbcOperations` prove that the SQL query is compatible with PostgreSQL?

**Answer:** No. Mocks only verify Java interactions against simulated behavior; integration tests running the SQL and schema on a suitable database are required.

**Question 6.** When should you write `JdbcOperations`, and when should you write `NamedParameterJdbcOperations`?

**Answer:** `JdbcOperations` for SQL using positional `?` placeholders; `NamedParameterJdbcOperations` for SQL using named `:name` placeholders. Choose based on repository clarity needs, without assuming the two interfaces extend one another.

## References

- [Spring Framework — `JdbcOperations` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/jdbc/core/JdbcOperations.html): JDBC contract, method groups, and the rationale for using an interface to improve testability.
- [Spring Framework — `JdbcTemplate` Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html): implementation, JDBC callbacks, resource management, exception translation.
- [Spring Framework — JDBC Core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): how to execute SQL, `JdbcTemplate`, `NamedParameterJdbcTemplate`, `JdbcClient`.
- [Spring Framework — Data Access with JDBC](https://docs.spring.io/spring-framework/reference/data-access/jdbc.html): responsibility split table between the framework and application.
- [Spring Framework — Controlling Database Connections](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html): `DataSource`, `DataSourceUtils`, and JDBC transactions.
- [Spring Framework — `NamedParameterJdbcOperations` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.0/javadoc-api/org/springframework/jdbc/core/namedparam/NamedParameterJdbcOperations.html): named parameters contract.

**Remember:** `JdbcOperations` specifies **what the repository can do with JDBC**; `JdbcTemplate` decides **how to execute that operation using JDBC and Spring**. The application layer should provide clear SQL, mapping, and business boundaries, letting Spring manage connections, statements, result sets, and context-aware error translation. To stay independent of storage technology at the business level, create a domain-oriented repository interface rather than letting services depend directly on SQL APIs.