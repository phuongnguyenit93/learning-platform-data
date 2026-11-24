# JdbcTemplate: query(), queryForObject(), update(), and execute()

## What Will You Learn?

`JdbcTemplate` is the core component of Spring JDBC, enabling applications to send SQL to a database without repeating boilerplate code for acquiring connections, creating statements, reading `ResultSet`s, closing resources, and translating most JDBC errors into the `DataAccessException` hierarchy.

When starting to write repositories with Spring JDBC, four method groups commonly cause confusion:

- **`query(...)`**: runs a query and maps **multiple rows** into a list or processes results via callbacks.
- **`queryForObject(...)`**: runs a query where the caller **expects exactly one row**, returning either an object from a `RowMapper` or a single scalar value.
- **`update(...)`**: executes data manipulation statements such as `INSERT`, `UPDATE`, `DELETE`; returns the **number of affected rows**.
- **`execute(...)`**: executes SQL or a general JDBC operation; the overload accepting a single SQL string is commonly used for DDL or tasks that do not need to read return data.

Goal after this lesson: choose the right method based on the SQL and expected cardinality; interpret results and exceptions accurately; bind parameters safely; place each command within an appropriate transaction boundary; and run a Java 17+ example with Spring Framework and H2.

> This article illustrates Spring Framework 6.2.x and Spring JDBC. This is not the JPA `EntityManager` API. Spring Boot can auto-configure the related beans, but it does not change the semantics of these methods.

## 1. Quick Decision Table

| Need | Commonly chosen method | Return value | If no matching rows exist |
| --- | --- | --- | --- |
| Fetch a list of books by criteria | `query(sql, rowMapper, args...)` | `List<Book>` | Empty list |
| Find a book by unique ID, required to exist | `queryForObject(sql, rowMapper, args...)` | One `Book` | Throws `EmptyResultDataAccessException` |
| Read a count, sum, name, or single value | `queryForObject(sql, Long.class, args...)` | A single value or `null` if the SQL value is NULL | No rows: exception; `COUNT(*)` without `GROUP BY` still returns one row containing 0 |
| Insert, update, or delete data | `update(sql, args...)` | `int` affected row count | Typically returns 0 for non-matching UPDATE/DELETE |
| Create tables in demos, run DDL | `execute(sql)` | `void` for the single-`String` overload | Depends on the DDL statement and database; typically no row set to map |
| Need low-level access via JDBC callbacks | `execute(ConnectionCallback<T>)` / `execute(PreparedStatementCreator, PreparedStatementCallback<T>)` overloads | `T` returned by callback | Depends on the callback |

**Rule—choose by data semantics, not SQL keyword:** `queryForObject` is only right when *exactly one row* is part of the use case contract. Adding `LIMIT 1` to mask multiple rows that might indicate dirty data is a separate decision and should not be done automatically.

## 2. General Mechanism of JdbcTemplate

A typical flow:

```text
Service / Use case
       |
       v
Repository: choose query/queryForObject/update/execute
       |
       v
JdbcTemplate: create Statement/PreparedStatement, bind parameters
       |
       v
DataSource -> JDBC Connection -> JDBC Driver -> Database
       |
       v
ResultSet / affected row count / SQL error
       |
       v
JdbcTemplate: map data, close resources, translate errors
       |
       v
Repository returns List<T> / T / int / void to Service
```

`JdbcTemplate` is created from a `DataSource`. When used properly inside a Spring-managed transaction, standard JDBC operations participate in the connection bound to the current transaction. Outside a surrounding Spring transaction, how each statement commits depends on the connection/JDBC configuration (typically auto-commit). **Choosing `query` or `update` does not automatically place an entire business workflow in a single transaction.**

There are many overloads for each method. This article favors modern signatures used with `RowMapper`, `Class<T>`, and `Object... args` parameters. For some overloads taking only static SQL, Spring may use a JDBC `Statement`; overloads with parameters typically create a `PreparedStatement` and bind data.

Since Spring Framework 5.3, many older overloads accepting `Object[]` **before** the mapper/type have been deprecated; prefer the newer order such as `queryForObject(sql, String.class, id)` or `queryForObject(sql, bookMapper, id)`.

## 3. query(): When You Want a List or Multiple Rows

### 3.1. Fetching `List<T>` with `RowMapper<T>`

Example SQL returning multiple books:

```sql
SELECT id, title, price, available
FROM books
WHERE price >= ?
ORDER BY id;
```

Calling Spring JDBC:

```java
RowMapper<Book> mapper = (rs, rowNum) ->
        new Book(
                rs.getLong("id"),
                rs.getString("title"),
                rs.getInt("price"),
                rs.getBoolean("available"));

List<Book> books = jdbc.query(
        """
        SELECT id, title, price, available
        FROM books
        WHERE price >= ?
        ORDER BY id
        """,
        mapper,
        150);
```

**This is an illustrative snippet**, assuming `Book` is a declared record and `jdbc` is a `JdbcTemplate` bean. Section 8 contains a complete, compilable/runnable program.

`RowMapper<Book>` receives a `ResultSet` positioned at the current row and the row index `rowNum` (0-based), then builds **one** `Book` object. `JdbcTemplate` loops over the rows itself, invokes the mapper for each row, and builds the list. Do not call `rs.next()` inside `RowMapper`; doing so can skip rows or corrupt the mapping flow.

Characteristics:

- **0 rows**: returns an empty list (`List.of()` semantically, without needing to assume a specific `List` implementation).
- **1 row**: a list with exactly one element.
- **N rows**: a list with N elements, in the order supplied by SQL.
- If order matters, `ORDER BY` must be specified. Databases do not guarantee stable ordering without an explicit ordering clause.
- If reading millions of rows into a `List<T>`, application memory can be overwhelmed. Consider pagination or callbacks/streams with proper resource lifecycle management.

### 3.2. RowMapper Is Not a Query Manager

`RowMapper` is responsible for turning **one row** into a Java object, not deciding how many times SQL runs or how many rows exist. For nullable columns, choose getters and handling carefully: for example, `rs.getInt(...)` returns 0 even when the actual value is SQL NULL; to distinguish, use `rs.wasNull()` or `rs.getObject(..., Integer.class)` when supported by the driver.

Example mapper returning a record:

```java
record Book(long id, String title, int price, boolean available) {}
```

This assumes `price` and `available` are both `NOT NULL` in the schema. If those two columns are nullable, the Java model and mapping logic must change.

### 3.3. `query()` Does Not Mean SQL Must Always Return More Than One Row

A query by ID that returns at most one row can still **use `query()`**:

```java
List<Book> result = jdbc.query(
        "SELECT id, title, price, available FROM books WHERE id = ?",
        mapper,
        42L);
```

This is useful when "not found" is a valid outcome. When `id` is known to be a primary key:

```java
Optional<Book> found = result.stream().findFirst();
```

This is a snippet; it requires `import java.util.Optional;` and `result` to be assigned. Do not apply `findFirst()` mechanically if the query can return multiple rows when the use case expects uniqueness: doing so ignores the risk of corrupted data. If an attribute must be unique, enforce a unique/primary key constraint in the database.

### 3.4. Other Query Overloads

Besides `RowMapper`, `query` also has callback overloads such as `ResultSetExtractor<T>` (processes the entire `ResultSet` as desired), `RowCallbackHandler` (processes each row without collecting into a list automatically), and overloads using `PreparedStatement`. Those tools fit when special aggregation is needed or when avoiding holding all results in memory. For standard CRUD, `query(sql, RowMapper, args...)` is the easiest to read and test.

## 4. queryForObject(): The Exactly-One-Row Contract

### 4.1. Reading a Single Value

To fetch a book title by primary key:

```java
String title = jdbc.queryForObject(
        "SELECT title FROM books WHERE id = ?",
        String.class,
        2L);
```

This `Class<T>` overload is for results with **one row, one column**. If the SQL returns two columns, Spring may throw `IncorrectResultSetColumnCountException`. If JDBC type conversion is incompatible, data conversion/reading errors can also occur.

Example row count:

```java
Long total = jdbc.queryForObject(
        "SELECT COUNT(*) FROM books",
        Long.class);
```

Because `COUNT(*)` without `GROUP BY` returns one aggregate row even when the table has no data, `total` is typically 0 rather than throwing `EmptyResultDataAccessException`. Do not confuse "`COUNT` equals 0" with "SQL returned no rows."

### 4.2. Mapping an Object with Multiple Columns

If the query returns one row with multiple columns, use the overload accepting `RowMapper`:

```java
Book book = jdbc.queryForObject(
        """
        SELECT id, title, price, available
        FROM books
        WHERE id = ?
        """,
        mapper,
        2L);
```

Here `mapper` decides how to build `Book` from one row, while `queryForObject` enforces the row count. `RowMapper` may itself return `null`; if the query genuinely returned one row, the resulting value can be `null` without being a "zero rows" error.

### 4.3. What Happens with 0, 1, or Multiple Rows?

| Actual SQL row count | `queryForObject(sql, RowMapper, ...)` | `queryForObject(sql, Class<T>, ...)` |
| --- | --- | --- |
| 0 | Throws `EmptyResultDataAccessException` | Throws `EmptyResultDataAccessException` |
| 1 | Returns object created by mapper (can be `null`) | Returns scalar, can be `null` if SQL NULL; requires exactly one column |
| 2 or more | Throws `IncorrectResultSizeDataAccessException` | Throws `IncorrectResultSizeDataAccessException` |

`EmptyResultDataAccessException` is a subtype of `IncorrectResultSizeDataAccessException`; if catching separately, place the `EmptyResult` branch before the parent branch.

**Important:** `queryForObject` **does not simply grab the first element**. It enforces an exactly-one-row contract. For a query like `SELECT title FROM books WHERE available = TRUE` when multiple books match, calling `queryForObject` is the wrong choice even though the SQL is valid. Use `query`, or design the query/constraints so only one row actually exists.

### 4.4. Is "Not Found" an Error or a Valid State?

Suppose `findRequiredById(id)` in business logic assumes the ID must exist; `queryForObject` fits, and the service can translate `EmptyResultDataAccessException` into a domain exception.

If `findById(id)` can validly return "absent", there are two sensible options:

1. Use `query` filtering by PK and convert the 0/1-element list into `Optional<Book>`.
2. Call `queryForObject`, catch **specifically** `EmptyResultDataAccessException`, and return `Optional.empty()`.

Do not catch general `DataAccessException` and return empty data: that swallows connection failures, bad SQL, unique violations, and other incidents. Separating "does not exist" from "database failure" lets business logic react properly.

Another note: adding `LIMIT 1` only caps the query at one row; it **does not verify uniqueness** of the data. To prevent duplicates, use database constraints or a verification strategy that actually meets the requirement.

## 5. update(): INSERT, UPDATE, DELETE, and Affected Row Count

`JdbcTemplate.update(...)` is commonly used for data-modifying operations:

```java
int inserted = jdbc.update(
        "INSERT INTO books (id, title, price, available) VALUES (?, ?, ?, ?)",
        4L, "Data Access", 180, true);

int changed = jdbc.update(
        "UPDATE books SET price = ? WHERE id = ?",
        220, 4L);

int deleted = jdbc.update(
        "DELETE FROM books WHERE id = ?",
        4L);
```

The result variable is an `int` representing the **number of affected rows** reported by the JDBC driver (counting rules may differ slightly across statement types/databases). Do not equate that number with a boolean "business operation succeeded."

### 5.1. Meaning of Results 0, 1, N

- For a single-row `INSERT` that succeeds, it typically returns 1.
- For `UPDATE ... WHERE id = ?`, **0** usually indicates no matching row was found. No exception is thrown simply because nothing was updated.
- For `DELETE ... WHERE id = ?`, **0** usually means no row existed to delete or the condition did not match.
- For an overly broad `UPDATE` or `DELETE`, affected rows can be much larger than expected; this can be a severe bug, especially if `WHERE` is forgotten.

Example when business logic must update exactly one order:

```java
int affected = jdbc.update(
        "UPDATE orders SET status = ? WHERE id = ?",
        "PAID",
        orderId);

if (affected != 1) {
    throw new IllegalStateException(
            "Expected one order row, updated " + affected);
}
```

This is an **illustrative snippet**, assuming an `orders` table and `orderId` variable exist; not a standalone Java file. If 0 rows is a valid outcome (such as an idempotent delete), whether to raise an error must be decided by business requirements.

### 5.2. Using Row Count to Prevent Lost Updates

One way to implement optimistic locking is a conditional update using a version:

```sql
UPDATE accounts
SET balance = ?, version = version + 1
WHERE id = ? AND version = ?;
```

When calling `update`, a result of 1 means the condition was satisfied and the operation applied to one row; a result of 0 could mean the row does not exist or the version was already changed by another transaction. The service can return a conflict error so the client reloads the data. This only illustrates **the role of affected rows**, not a complete replacement for transaction/isolation design.

### 5.3. Can `update`'s Return Value Be Used to Get an Auto-Generated Key?

No. The `int` returned by `update` is the affected row count, **not an auto-generated ID**. If the DB generates IDs via identity/sequence, Spring JDBC supports overloads using `PreparedStatementCreator` and `KeyHolder`, or `SimpleJdbcInsert`, to retrieve generated keys. You must configure the driver, key column name, and statement creation to fit the DBMS. Do not assume `inserted == generatedId`.

### 5.4. `update` Does Not Automatically Enclose a Transaction

Two sequential `update` calls do not commit/roll back as a single business unit by default. A service that must ensure all operations succeed together usually uses `@Transactional` with an appropriate transaction manager, invoked through a Spring-managed proxy. Details are explained in Section 10.

## 6. execute(): Running SQL or General JDBC Callbacks

### 6.1. Overload Accepting a SQL String

```java
jdbc.execute("""
        CREATE TABLE books (
            id BIGINT PRIMARY KEY,
            title VARCHAR(120) NOT NULL,
            price INT NOT NULL,
            available BOOLEAN NOT NULL
        )
        """);
```

`execute(String sql)` does not map a `ResultSet` to a `List` or scalar, and this overload returns `void`. Thus it is convenient for creating tables/schemas in demos or running SQL commands that do not need return data. It **should not be the default choice** for `SELECT` merely because the name "execute" sounds general: for `SELECT`, use `query`/`queryForObject` when you need results. For DML needing affected row counts, use `update`.

Distinguish **Spring's `JdbcTemplate.execute(String)`** from the low-level **JDBC `Statement.execute(String)`** method; they do not have the same return type. JDBC `Statement.execute` returns a boolean indicating the form of the first result, whereas Spring's `execute(String)` overload returns `void`.

**Do not overuse DDL in production applications.** Real schemas are normally managed by migration tools/operations teams (Flyway, Liquibase, or similar workflows), avoiding ad-hoc table creation/alteration while handling HTTP requests. Transactional effects of DDL also vary across DBMSs.

### 6.2. `execute` Overloads Taking Callbacks Serve a Different Purpose

`JdbcTemplate` also provides overloads taking `ConnectionCallback<T>`, `StatementCallback<T>`, or `PreparedStatementCreator` + `PreparedStatementCallback<T>`. They allow working at a lower JDBC level while still benefiting from Spring's resource management and exception translation.

Snippet using a connection callback to read JDBC driver metadata:

```java
String product = jdbc.execute(
        (ConnectionCallback<String>) connection ->
                connection.getMetaData().getDatabaseProductName());
```

This is **not a standalone program**; it requires a `JdbcTemplate` variable `jdbc` and `import org.springframework.jdbc.core.ConnectionCallback`. Callback overloads can return `String`/`T` provided by the callback, unlike `void execute(String sql)`.

Use callbacks when you genuinely have special JDBC needs, not to manually rewrite `ResultSet` loops for routine CRUD. If a callback receives a transactional connection, do not close the Spring-managed connection yourself; let the framework manage resource lifecycles per the callback contract.

### 6.3. `execute` Does Not "Bypass" the Database

Even though it returns `void`, the command is still sent to the database. Invalid SQL, missing permissions, or structural errors can still throw `DataAccessException`. With callbacks, commands can read or write depending on callback logic, so always inspect the code and understand its effects before using it in real systems.

## 7. Parameter Binding and Data Type Conversion

### 7.1. Use Placeholders for User-Supplied Values

```java
List<Book> books = jdbc.query(
        "SELECT id, title, price, available FROM books WHERE title = ?",
        mapper,
        userTitle);
```

This snippet assumes valid `mapper` and `userTitle`. The `?` placeholder separates user data from the SQL statement. This applies to `query`, `queryForObject`, and `update` when using parameter-accepting overloads. Never concatenate `" ... WHERE title = '" + userTitle + "'"` due to SQL injection risk and broken quote escaping.

Placeholders **do not replace table names, column names, `ASC`/`DESC` directions, or entire SQL clauses**. When dynamic sorting by column name is required, choose from an allowlist of permitted columns/directions before constructing the SQL structure.

### 7.2. Watch JDBC Data Types

`JdbcTemplate` normally lets the JDBC driver infer SQL types from Java values when binding `Object... args`. For `null`, special types, or timestamps, you sometimes need to specify an explicit `SQLType` via `SqlParameterValue`, `PreparedStatementSetter`, or appropriate configuration. On `ResultSet`, primitive getters can hide SQL NULL; use wrapper types or check `wasNull()` when needed.

Reading `TIMESTAMP`/`TIMESTAMP WITH TIME ZONE` requires aligning timezones, Java types (`Instant`, `LocalDateTime`, `OffsetDateTime`, etc.), and JDBC driver behavior. The demo example uses integers/booleans to stay focused on the semantics of the four methods.

### 7.3. Database Errors Do Not Disappear

Spring translates many `SQLException`s into the `DataAccessException` hierarchy (unchecked). Examples: duplicate primary key, invalid SQL, connection failure, or other constraint violations. Never catch broadly and return an empty list or 0; only translate errors that the business layer can meaningfully handle. Log enough context for diagnosis without leaking secrets or sensitive data.

## 8. Runnable Example: Java 17, Spring JdbcTemplate, and H2

The example below demonstrates **all four method groups** with deterministic data and output. It uses **Java 17+**, Spring Framework **6.2.12**, Gradle, and in-memory H2. No Spring Boot, Docker, or external database installation is required.

### 8.1. Directory Structure

```text
jdbc-operations-demo/
├── build.gradle
└── src/main/java/example/JdbcTemplateOperationsDemo.java
```

### 8.2. `build.gradle` Configuration

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.12'
    implementation 'org.springframework:spring-jdbc:6.2.12'
    runtimeOnly 'com.h2database:h2:2.3.232'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'example.JdbcTemplateOperationsDemo'
}
```

`spring-jdbc` provides `JdbcTemplate` and related callbacks/exceptions. `spring-context` provides the Spring container and `@Configuration`, `@Bean` annotations. H2 is the JDBC driver and runtime database, so placing it in `runtimeOnly` fits this example.

### 8.3. Complete Java File

Create `src/main/java/example/JdbcTemplateOperationsDemo.java`:

```java
package example;

import java.util.List;
import javax.sql.DataSource;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.dao.IncorrectResultSizeDataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

@Configuration
public class JdbcTemplateOperationsDemo {

    @Bean
    DataSource dataSource() {
        DriverManagerDataSource ds = new DriverManagerDataSource();
        ds.setDriverClassName("org.h2.Driver");
        ds.setUrl("jdbc:h2:mem:jdbc_operations;DB_CLOSE_DELAY=-1");
        ds.setUsername("sa");
        ds.setPassword("");
        return ds;
    }

    @Bean
    JdbcTemplate jdbcTemplate(DataSource dataSource) {
        return new JdbcTemplate(dataSource);
    }

    record Book(long id, String title, int price, boolean available) {}

    private static final RowMapper<Book> BOOK_MAPPER = (rs, rowNum) ->
            new Book(
                    rs.getLong("id"),
                    rs.getString("title"),
                    rs.getInt("price"),
                    rs.getBoolean("available"));

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(
                             JdbcTemplateOperationsDemo.class)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);

            // execute(String): schema DDL, no result data needed.
            jdbc.execute("""
                    CREATE TABLE books (
                        id BIGINT PRIMARY KEY,
                        title VARCHAR(120) NOT NULL,
                        price INT NOT NULL,
                        available BOOLEAN NOT NULL
                    )
                    """);

            // update(String, Object...): INSERT, receives affected row count.
            int a = jdbc.update(
                    "INSERT INTO books (id, title, price, available) VALUES (?, ?, ?, ?)",
                    1L, "Java Basics", 100, true);

            int b = jdbc.update(
                    "INSERT INTO books (id, title, price, available) VALUES (?, ?, ?, ?)",
                    2L, "Spring JDBC", 200, true);

            int c = jdbc.update(
                    "INSERT INTO books (id, title, price, available) VALUES (?, ?, ?, ?)",
                    3L, "SQL Patterns", 150, false);

            System.out.println("inserted=" + (a + b + c));

            // query: multiple rows, RowMapper converts each row into a Book.
            List<Book> list = jdbc.query(
                    """
                    SELECT id, title, price, available
                    FROM books
                    WHERE price >= ?
                    ORDER BY id
                    """,
                    BOOK_MAPPER,
                    150);

            System.out.println("query=" + list);

            // queryForObject with RowMapper: exactly 1 row, multiple columns.
            Book one = jdbc.queryForObject(
                    "SELECT id, title, price, available FROM books WHERE id = ?",
                    BOOK_MAPPER,
                    2L);
            System.out.println("one=" + one);

            // queryForObject with Class<T>: exactly 1 row, 1 column.
            String title = jdbc.queryForObject(
                    "SELECT title FROM books WHERE id = ?",
                    String.class,
                    1L);
            System.out.println("title=" + title);

            Long count = jdbc.queryForObject(
                    "SELECT COUNT(*) FROM books",
                    Long.class);
            System.out.println("count=" + count);

            // update with UPDATE, including the case where no row matches.
            int updated = jdbc.update(
                    "UPDATE books SET price = ? WHERE id = ?",
                    225,
                    2L);

            int missingUpdated = jdbc.update(
                    "UPDATE books SET price = ? WHERE id = ?",
                    999,
                    42L);

            System.out.println(
                    "updated=" + updated + ",missingUpdated=" + missingUpdated);

            // update with DELETE.
            int deleted = jdbc.update(
                    "DELETE FROM books WHERE id = ?",
                    3L);
            System.out.println("deleted=" + deleted);

            // query with no rows: empty List, not an exception.
            List<Book> empty = jdbc.query(
                    """
                    SELECT id, title, price, available
                    FROM books
                    WHERE price > ?
                    ORDER BY id
                    """,
                    BOOK_MAPPER,
                    1000);
            System.out.println("emptyQuery=" + empty.size());

            // queryForObject with no rows: exception.
            try {
                jdbc.queryForObject(
                        "SELECT title FROM books WHERE id = ?",
                        String.class,
                        999L);
            } catch (EmptyResultDataAccessException ex) {
                System.out.println(
                        "missingOne=EmptyResultDataAccessException");
            }

            // queryForObject with > 1 row: exception.
            // At this point, 2 books remain (ID 1 and 2).
            try {
                jdbc.queryForObject(
                        "SELECT title FROM books",
                        String.class);
            } catch (IncorrectResultSizeDataAccessException ex) {
                System.out.println(
                        "multiple=IncorrectResultSizeDataAccessException");
            }

            System.out.println(
                    "finalCount=" + jdbc.queryForObject(
                            "SELECT COUNT(*) FROM books",
                            Long.class));
        }
    }
}
```

In this program, `@Bean` declares one H2 `DataSource` and one `JdbcTemplate`. Since there is only one `DataSource` bean, the `DataSource dataSource` parameter is resolved uniquely by Spring. `@Qualifier` is not needed; the `Qualifier` import in this example is unused and can be removed when copying code into a real project.

`BOOK_MAPPER` maps columns from `ResultSet` to a Java record. The `books` table defines `price` and `available` as `NOT NULL`, so mapping to `int` and `boolean` loses no NULL information. `JdbcTemplate` manages the JDBC lifecycle via `DataSource` without needing `Connection.close()` in each query.

**Demo limitations:** `DriverManagerDataSource` opens a new connection per request, which is not an optimal connection pool for production. `DB_CLOSE_DELAY=-1` keeps the in-memory H2 database alive across connection closes within the same JVM; data disappears when the process exits.

### 8.4. Running the Program and Checking stdout

In the project directory containing `build.gradle`, run:

```bash
gradle run
```

If the project includes the Gradle Wrapper, use `./gradlew run` on Linux/macOS or `gradlew.bat run` on Windows. Gradle may print its own build logs; **the lines emitted by Java's `System.out.println`** in order are:

```text
inserted=3
query=[Book[id=2, title=Spring JDBC, price=200, available=true], Book[id=3, title=SQL Patterns, price=150, available=false]]
one=Book[id=2, title=Spring JDBC, price=200, available=true]
title=Java Basics
count=3
updated=1,missingUpdated=0
deleted=1
emptyQuery=0
missingOne=EmptyResultDataAccessException
multiple=IncorrectResultSizeDataAccessException
finalCount=2
```

**Matching step by step against the SQL:**

1. `execute(...)` creates the table. Three `update(INSERT)` calls insert books 1, 2, and 3; total affected rows = 3.
2. `query(...)` with `price >= 150` fetches book ID 2 (200) and ID 3 (150). `ORDER BY id` guarantees output order ID 2 then ID 3.
3. `queryForObject(..., BOOK_MAPPER, 2L)` returns one `Book`; the `String.class` overload returns the title of ID 1. `COUNT(*)` equals 3.
4. `update(UPDATE)` updates book 2's price to 225 and returns 1; updating non-existent ID 42 returns 0.
5. `update(DELETE)` deletes book 3 and returns 1. Querying `price > 1000` finds no books, so `query` returns an empty list.
6. `queryForObject` for ID 999 throws an empty-result exception. `queryForObject` without `WHERE` looks up titles from the **two** remaining rows, throwing a result-size exception.
7. The final `COUNT(*)` equals 2.

Here `queryForObject` throws an exception for the wrong **row count**, unlike `update` returning 0 when an UPDATE matches no rows. That is a crucial distinction when writing services.

### 8.5. A Quick Way to Test a Common Mistake

Try changing `jdbc.query(...)` in the program to `jdbc.queryForObject(...)` for `price >= 150`. Since two books initially match the condition, calling a method expecting one row throws `IncorrectResultSizeDataAccessException`. Switch back to `query`. Conversely, if defining an API like `findRequiredById`, use `queryForObject` with a unique ID and handle the exception intentionally.

## 9. Writing Repositories: Putting Method Selection in the Right Place

In real applications, controllers should not know SQL or how to construct `RowMapper`s. A Spring JDBC repository can define clear read/write use cases:

```java
@Repository
public class BookRepository {
    private final JdbcTemplate jdbc;

    public BookRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<Book> findAffordable(int maxPrice) {
        return jdbc.query(
                """
                SELECT id, title, price, available
                FROM books
                WHERE price <= ?
                ORDER BY id
                """,
                BOOK_MAPPER,
                maxPrice);
    }

    public Book requireById(long id) {
        return jdbc.queryForObject(
                "SELECT id, title, price, available FROM books WHERE id = ?",
                BOOK_MAPPER,
                id);
    }

    public int changePrice(long id, int newPrice) {
        return jdbc.update(
                "UPDATE books SET price = ? WHERE id = ?",
                newPrice, id);
    }
}
```

This is an **illustrative snippet, not a standalone Java file**: it assumes `Book`, `BOOK_MAPPER`, imports for `Repository`/`JdbcTemplate`/`List`, and the `books` table already exist. When organizing real code, keep shared `RowMapper`s in the repository or a dedicated class, and place record types where repositories can reference them.

With the repository:

- `findAffordable` returns a list, even when empty.
- `requireById` clearly expresses the "must have one book" contract.
- `changePrice` returns affected rows so the service can decide if 0 rows is an error.
- DDL is managed during startup/schema migrations, not inside request-handling methods.

If looking up a book by ID **may legitimately find nothing**, change the API to `Optional<Book> findById(long id)` and use a 0/1-row `query` as explained, or catch `EmptyResultDataAccessException` specifically.

## 10. Transactions: Which Methods Are Inside a Transaction?

The four `JdbcTemplate` methods only dictate how a single operation executes. When business logic spans multiple steps that must commit or roll back together, the transaction boundary normally belongs to the service layer:

```java
@Service
public class OrderService {
    private final OrderRepository orders;
    private final InventoryRepository inventory;

    public OrderService(
            OrderRepository orders,
            InventoryRepository inventory) {
        this.orders = orders;
        this.inventory = inventory;
    }

    @Transactional
    public void placeOrder(long productId, int quantity) {
        inventory.decreaseStock(productId, quantity);
        orders.insertOrder(productId, quantity);
    }
}
```

This is an **illustrative design pattern**; `OrderRepository` and `InventoryRepository` are not defined here, so it cannot compile as a standalone file. It requires a Spring-managed service, transaction management enabled, an appropriate transaction manager, and repositories whose resources participate in the same transaction.

Technical points:

- For single-datasource Spring JDBC, `DataSourceTransactionManager` or `JdbcTransactionManager` manages transactions bound to the matching `DataSource`.
- `JdbcTemplate` leverages Spring transaction synchronization to reuse the connection bound to the current thread/transaction. Opening `dataSource.getConnection()` manually in the wrong way can put queries outside the transaction.
- `@Transactional` in default proxy mode requires calls to go through the Spring bean proxy; self-invocation within the same object normally does not trigger transaction advice.
- By default, declarative transactions roll back on `RuntimeException` and `Error`, not automatically on all checked exceptions; configure `rollbackFor` when genuinely needed.
- A local transaction on one `DataSource` does not guarantee atomic commit across two different databases. With multiple sources, select the right manager and design cross-system consistency explicitly.
- `@Transactional(readOnly = true)` is a read-optimization hint/setting, not a substitute for database permissions or a guarantee that `update` statements will always be blocked.

## 11. Errors to Distinguish Before Handling

| Situation | Symptom | Reasonable decision |
| --- | --- | --- |
| `query` returns 0 rows | Empty list | Show "no results" / return empty collection |
| `queryForObject` returns 0 rows | `EmptyResultDataAccessException` | Report not found if required; otherwise convert to `Optional` |
| `queryForObject` returns >1 row | `IncorrectResultSizeDataAccessException` | Check SQL, unique constraints, and data; do not arbitrarily pick the first row |
| `queryForObject(sql, Class<T>)` returns >1 column | `IncorrectResultSetColumnCountException` | Select a single column or switch to `RowMapper` |
| `queryForObject` gets one row with SQL NULL value | May return `null` | Distinguish from zero rows; design nullability explicitly |
| `update` matches no rows | Returns 0 | Depending on use case: no-op, not found, or conflict |
| `update` affects more rows than expected | Returns N > expected | Check `WHERE`, locking, transactions, and data |
| SQL, unique/FK, connection, or permission error | A `DataAccessException` subtype | Handle per error category; do not turn into "not found" |
| `execute` runs invalid DDL | May throw an exception | Fix schema/DDL/migration; do not treat as an empty-result query error |

Remember that a Spring exception **does not automatically mean** it is always safe to retry. Unique constraint violations should not be retried infinitely; transient connection errors may be retried if the operation is designed to be idempotent with bounded retry policies.

## 12. Performance and Safety in Real Applications

**Select only what you need.** Prefer explicit column names over `SELECT *` for stable mapping. Add appropriate filters and `ORDER BY`, and use pagination for large tables instead of loading everything into a `List`.

**Beware queries inside loops.** Running `queryForObject` by ID across 1,000 items creates 1,000 database round trips. Consider set-based queries, batch queries, or appropriate joins/projections.

**Actively guard against huge result sets.** `query(...)` with `RowMapper` collects results into a list; for very large datasets, use pagination or callbacks/streams with proper resource management rather than building a massive list.

**Observe SQL at the right layer.** Spring JDBC can log SQL at DEBUG level (typically under the `org.springframework.jdbc.core.JdbcTemplate` category), but do not diagnose database latency from logs alone. Inspect query plans, indexes, connection pools, query counts, network latency, and locking when endpoints slow down. Avoid logging PII, passwords, tokens, or sensitive data.

**Do not equate `execute` with `update`.** `execute` does not automatically return affected row counts; when business logic needs to verify exactly one row changed, `update` is better suited. Do not run ad-hoc DDL in production.

**Verify against a real database.** H2 helps with learning the API, but it differs from other DBMSs in SQL dialect, data types, transactions, and generated keys. For applications targeting PostgreSQL/MySQL, run integration tests against the matching engine, for instance using Testcontainers.

## 13. Common Thinking Mistakes

| Misconception | Correct understanding |
| --- | --- |
| "`query` always returns at least one row." | No; if there are no rows, it returns an empty list. |
| "`queryForObject` grabs the first row." | No; it requires exactly one row; 0 or >1 throws an exception. |
| "`queryForObject(sql, Long.class)` works for any SELECT." | Only fits a single-row, single-column result convertible to `Long`. |
| "`COUNT(*) = 0` throws `EmptyResultDataAccessException`." | Without `GROUP BY`, COUNT returns one row containing 0. |
| "`update` returns the generated ID." | It returns affected rows; getting generated IDs requires `KeyHolder` or an equivalent mechanism. |
| "`update` returning 0 means a SQL error." | The SQL can be valid and simply match no rows. |
| "`execute` is the best way to run all SQL." | For normal data reads/writes, pick `query`/`queryForObject`/`update` per contract. |
| "`RowMapper` must call `rs.next()`." | `JdbcTemplate` advances each row before invoking the mapper. |
| "The four methods automatically form one business transaction." | Transaction boundaries must be configured/coordinated separately. |
| "Catching `DataAccessException` and returning empty is safe." | That hides database errors and corrupts business semantics. |

## 14. Self-Check Questions

1. A search screen might have no results or hundreds of books. Should you choose `query` or `queryForObject`? Why?
2. How should an API that "fetches a required order by primary key" handle 0, 1, and multiple rows?
3. Why does `SELECT COUNT(*)` without `GROUP BY` usually differ from `SELECT title WHERE id = ?` when there is no matching data?
4. With `UPDATE books SET price=? WHERE id=?`, does `int affected=0` mean the SQL syntax is invalid?
5. When a primary key is auto-generated, why cannot `update` returning 1 be used as the ID?
6. When is `execute(String)` more appropriate than `update(String, Object...)`?
7. Why should a mapper not call `rs.next()` itself?
8. When updating inventory and then creating an order, how do you ensure both operations roll back on failure?
9. If a query returns one row with a SQL NULL column, what can the result of a scalar overload be?
10. Can you catch `EmptyResultDataAccessException` to return `Optional.empty()`? Why should you not catch all `DataAccessException`s to do that?

**Remember:** `query` represents a **0..N-row** result set; `queryForObject` expresses **exactly one row**; `update` expresses **writing data and counting affected rows**; `execute` is the low-level SQL/callback path for remaining needs. Pick the method based on the data contract, then handle cardinality, errors, parameters, and transactions explicitly.

### Official Documentation for Reference

- Spring Framework — [JDBC Core: Querying, Updating, JdbcTemplate](https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/core.html).
- Spring Framework — [JdbcTemplate Javadoc 6.2](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html).
- Spring Framework — [JdbcOperations Javadoc 6.2](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/JdbcOperations.html).
- Spring Framework — [Transaction Management](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction.html).
