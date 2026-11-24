# Missing Rows and EmptyResultDataAccessException

> **Important rule:** In Spring JDBC, `JdbcTemplate.queryForObject(...)` is used when the application **expects the query to return exactly one row**. If the actual result is **0 rows**, Spring throws `org.springframework.dao.EmptyResultDataAccessException`. This is a **failure to satisfy the result-cardinality contract**, not an indication that the SQL is invalid or the database is broken. If "not found" is a normal business scenario, choose an API or conversion pattern that explicitly represents absence.

This lesson focuses on the meaning of `EmptyResultDataAccessException`, when it occurs, how to distinguish it from SQL `NULL` or multiple rows, and how to write Spring JDBC repositories/services with clear contracts.

## 1. When Does This Error Occur?

Consider a customers table:

```sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    name VARCHAR(80) NOT NULL,
    nickname VARCHAR(80)
);

INSERT INTO customers (id, name, nickname) VALUES (1, 'Lan', NULL);
INSERT INTO customers (id, name, nickname) VALUES (2, 'Minh', 'M');
```

This SQL query has no matching row:

```sql
SELECT id, name, nickname
FROM customers
WHERE id = 99;
```

If executed via `JdbcTemplate.query(...)`, the application receives an empty `List`. However, if you use `queryForObject(...)` with a `RowMapper`, Spring requires exactly one row and throws `EmptyResultDataAccessException` when the result has 0 rows:

```java
Customer customer = jdbc.queryForObject(
    "SELECT id, name, nickname FROM customers WHERE id = ?",
    (rs, rowNum) -> new Customer(
        rs.getLong("id"),
        rs.getString("name"),
        rs.getString("nickname")
    ),
    99L
);
```

Here `jdbc` is a preconfigured `JdbcTemplate` or `JdbcOperations` variable; `Customer` is an application-defined data type. This code snippet is a call inside a method, not a standalone runnable Java program. Because no `id = 99` exists, no `Customer` object is created and the exception is thrown.

### Specific Conditions

A call that "expects one result" has three main outcomes:

| Actual row count | `queryForObject(...)` | Meaning |
| --- | --- | --- |
| **0** | Throws `EmptyResultDataAccessException` | No row matches the condition, yet the API requires one row |
| **1** | Maps the row and returns the object (may return `null` in some cases) | Row-cardinality contract is satisfied |
| **2 or more** | Throws `IncorrectResultSizeDataAccessException` | More than one row returned when the API requires exactly one |

`EmptyResultDataAccessException` is a subclass of `IncorrectResultSizeDataAccessException`. Therefore `catch (IncorrectResultSizeDataAccessException ex)` also catches the 0-row error, so if business logic distinguishes *not found* from *unexpected duplicate data*, catch the more specific subclass or use a more expressive API.

**Not every query returning 0 rows throws this error.** The error type depends on which Spring method is called and its expectations, not merely on database state.

## 2. Origin and Meaning of the Exception in Spring

Fully qualified name:

```java
import org.springframework.dao.EmptyResultDataAccessException;
```

Relevant inheritance chain in Spring Framework:

```text
RuntimeException
  └─ DataAccessException
       └─ NonTransientDataAccessException
            └─ DataRetrievalFailureException
                 └─ IncorrectResultSizeDataAccessException
                      └─ EmptyResultDataAccessException
```

This error is an unchecked exception: no `throws` declaration is required on Java method signatures. It belongs to Spring's data-access exception hierarchy, so the service layer can receive it without handling raw `SQLException`.

**"Non-transient" does not mean a record can never appear later.** It reflects that this error category is unsuitable for automatic recovery simply by retrying the same operation under the same assumptions. A record might be created later; whether to retry is a business decision, not a default reaction to `EmptyResultDataAccessException`.

The exception carries expected and actual result-set size info inherited from `IncorrectResultSizeDataAccessException`:

```java
try {
    // Call a queryForObject query that may return 0 rows.
} catch (EmptyResultDataAccessException ex) {
    System.out.println(ex.getExpectedSize());
    System.out.println(ex.getActualSize());
}
```

When expected is 1 and actual is 0, those two values are typically `1` and `0`. This is an **illustrative fragment inside a method**, not complete code with a concrete `jdbc` variable. Do not rely on `ex.getMessage()` text for business decisions: exception messages may change across Spring versions.

### How Does JdbcTemplate Handle It?

Conceptually:

1. Spring acquires an appropriate `Connection` from `DataSource`.
2. Prepares/executes the SQL, iterates over `ResultSet`, and invokes `RowMapper` when rows exist.
3. Validates the result against `queryForObject`'s **one-row** contract.
4. If there are no rows, throws `EmptyResultDataAccessException`; if more than one row, throws `IncorrectResultSizeDataAccessException`.
5. Closes JDBC resources and releases the connection per Spring policy, even when an exception occurs.

Because there are no rows, the `RowMapper` callback is **never invoked**. Fixing row-mapping logic will not turn a 0-row query into a valid `queryForObject` result. If "not found" is allowed, change the query contract or handling rules in the repository layer.

## 3. Distinguishing 0 Rows, SQL NULL, and Zero Value

This is the most common source of confusion.

### Case A: No Rows

```sql
SELECT nickname FROM customers WHERE id = 99;
```

`id = 99` is not found. With:

```java
String nickname = jdbc.queryForObject(
    "SELECT nickname FROM customers WHERE id = ?",
    String.class,
    99L
);
```

Spring throws `EmptyResultDataAccessException`; it **does not return `null`** just because the SQL has no rows.

### Case B: One Row Exists, but the Column Is SQL NULL

```sql
SELECT nickname FROM customers WHERE id = 1;
```

The table has customer `id = 1`, and the `nickname` column is `NULL`. With:

```java
String nickname = jdbc.queryForObject(
    "SELECT nickname FROM customers WHERE id = ?",
    String.class,
    1L
);
```

The result can be Java `null` because **there was exactly one row, and the single column's value was SQL `NULL`**. No `EmptyResultDataAccessException` is thrown. Likewise, the `queryForObject(sql, RowMapper<T>, args...)` overload can return `null` if the `RowMapper` intentionally returns `null` for an existing row.

If you need to distinguish "no row" from "row exists with a NULL column", **do not store only a nullable scalar in a Java variable**. Map the row into an object/record containing the ID (and nullable properties) and express "whether the record exists" with `Optional<Customer>`. Then `Optional.empty()` represents a missing record, while `Optional.of(customer)` can have `customer.nickname() == null`.

### Case C: One Row with COUNT Value Equal to 0

```sql
SELECT COUNT(*) FROM customers WHERE id = 99;
```

With a `COUNT(*)` query **without `GROUP BY`** like this, the DB returns exactly **one row**, with count value `0`. Thus:

```java
Long count = jdbc.queryForObject(
    "SELECT COUNT(*) FROM customers WHERE id = ?",
    Long.class,
    99L
);
```

`count` is `0L` and no `EmptyResultDataAccessException` is thrown. This is the difference between "no business data rows" and "the result of a row-counting aggregation". If you add `GROUP BY` or `HAVING`, the aggregate query may produce zero groups, in which case the aggregate query itself can return 0 rows; do not apply the "COUNT always returns one row" rule mechanically.

### Comparison Table

| SQL or scenario | Rows returned | `queryForObject` |
| --- | ---: | --- |
| `SELECT name ... WHERE id = 99` | 0 | `EmptyResultDataAccessException` |
| `SELECT nickname ... WHERE id = 1`, SQL NULL value | 1 | Java `null` (`String.class` variant) |
| `SELECT COUNT(*) ... WHERE id = 99` | 1 | Value `0` |
| `SELECT name ... WHERE id = 2` | 1 | `"Minh"` |
| `SELECT id FROM customers` with two customers | 2 | `IncorrectResultSizeDataAccessException` |
| `UPDATE customers SET ... WHERE id = 99` via `jdbc.update` | SELECT row count not applicable | `update` returns `0`, does not throw missing-result error |

## 4. Not Every Spring JDBC API Expects Exactly One Row

| API | Result when 0 rows | When to use |
| --- | --- | --- |
| `queryForObject(sql, rowMapper, args...)` | Throws `EmptyResultDataAccessException` | Contract requires exactly one object/row |
| `queryForObject(sql, requiredType, args...)` | Throws `EmptyResultDataAccessException` | Contract requires exactly one row, **one column** of a specific type |
| `queryForMap(sql, args...)` | Throws `EmptyResultDataAccessException` | Expects exactly one row as a `Map` |
| `query(sql, rowMapper, args...)` | Returns empty `List<T>` | Query allows 0..N rows |
| `queryForList(...)` | Returns empty list | Reading a list of rows/values |
| `update(sql, args...)` | Returns `0` if no rows were updated/deleted | Writing data and checking affected row count |
| `JdbcClient` `.query(...).optional()` (Spring 6.1+) | `Optional.empty()` | Fluent API when 0 or 1 row is valid |
| `JdbcClient` `.query(...).single()` (Spring 6.1+) | Throws incorrect result size error | Fluent API when exactly one row is mandatory |

Note on `queryForObject(sql, Class<T>, ...)`: one row with **multiple columns** violates the single-column requirement and may throw `IncorrectResultSetColumnCountException`; use `RowMapper<T>` to map a multi-column record. One row with `SQL NULL` in the mapped column can return Java `null`, so even an "exactly one row" API does not inherently promise a non-null object.

### Why Not Fix It with LIMIT 1?

```sql
SELECT id, name FROM customers WHERE name = 'Lan' LIMIT 1;
```

`LIMIT 1` can prevent a query from returning more than one row, yet **it does not create a row when the actual result is 0**. It also masks duplicate data when names are not unique and fails to define which record is "first" without an appropriate `ORDER BY`.

If business rules require uniqueness, define constraints (such as PRIMARY KEY or an appropriate UNIQUE), query by the key, and handle missing records. If business rules ask for "any/latest single row", specify the sort criteria and fallback rules explicitly.

## 5. Three Strategies for Handling "Not Found"

### Strategy 1: Not Found Is a Valid Outcome — Return Optional

Example `findById` API allowing absence:

```java
public Optional<Customer> findById(long id) {
    List<Customer> rows = jdbc.query(
        "SELECT id, name, nickname FROM customers WHERE id = ?",
        CUSTOMER_MAPPER,
        id
    );
    return DataAccessUtils.optionalResult(rows);
}
```

This is a **method inside a repository**, with `jdbc` of type `JdbcOperations`, `CUSTOMER_MAPPER` of type `RowMapper<Customer>`, and imports `java.util.List`, `java.util.Optional`, `org.springframework.dao.support.DataAccessUtils`. A full runnable version is in section 6.

`DataAccessUtils.optionalResult(Collection<T>)` has been available since Spring Framework **6.1**. Its behavior:

- 0 elements: `Optional.empty()`.
- 1 element: `Optional` containing the element if non-`null`.
- More than 1 element: `IncorrectResultSizeDataAccessException`.

The advantage over `rows.stream().findFirst()` is that it still detects anomalous data if a query was supposed to return at most one row. In this primary-key `id` lookup, the DB already enforces uniqueness; using `optionalResult` makes the contract clear in Java as well. On older Spring versions without `optionalResult`, check the size of `rows` and convert manually while keeping multiple rows as an error.

**Important:** If `RowMapper` returns `null` for a real row, `Optional.empty()` can still occur. When you need to distinguish an existing record from a SQL NULL attribute, have the mapper build a non-null object and keep nullable attributes inside the object.

### Strategy 2: Existence Is Mandatory — Use queryForObject

When the contract is `getRequiredById`, a missing record can be an error at the data-access layer:

```java
public Customer getRequiredById(long id) {
    return jdbc.queryForObject(
        "SELECT id, name, nickname FROM customers WHERE id = ?",
        CUSTOMER_MAPPER,
        id
    );
}
```

If the method is strictly internal, you can let `EmptyResultDataAccessException` propagate. If the business/service layer needs a domain-specific signal, catch this exception specifically and translate it into a domain exception like `CustomerNotFoundException`. Do not translate every `DataAccessException` into "does not exist", because other errors such as SQL syntax errors, database disconnects, or too many results do not mean the same thing.

### Strategy 3: Catch the Specific Exception and Return Optional

When a codebase already uses `queryForObject` and cannot yet change the query:

```java
public Optional<Customer> findById(long id) {
    try {
        Customer result = jdbc.queryForObject(
            "SELECT id, name, nickname FROM customers WHERE id = ?",
            CUSTOMER_MAPPER,
            id
        );
        return Optional.ofNullable(result);
    } catch (EmptyResultDataAccessException ex) {
        return Optional.empty();
    }
}
```

This is a valid approach when **only 0 rows** is considered a normal outcome. It preserves multi-row errors, schema errors, and other DB errors. However, on a query path where missing data is frequent, creating and catching exceptions is unnecessary when `query(...)` returning a list works cleanly. For APIs designed to allow missing records from the start, prefer `Optional` or a list directly in the repository.

### How to Choose?

- `findById`: typically returns `Optional<Customer>`, depending on the application contract.
- `getRequiredById`: returns `Customer` or throws when missing.
- `searchByName`: returns `List<Customer>`; 0 rows is normally an empty list.
- `countByStatus`: returns a count; `0` is a valid result.
- `updateById` / `deleteById`: inspect affected row count (`0`/`1`), then decide if a missing record is a business error.

Method naming should help readers predict the contract: `find` usually allows absence, `require/getRequired` demands existence, `list/search` can return 0..N rows. This is an **application design convention**, not a naming rule imposed by Spring on `JdbcTemplate`.

## 6. Runnable Spring Boot Example: Observing 0 Rows, SQL NULL, and 0 Updates

The example below uses **Java 17+, Spring Boot 3.3+, Spring JDBC, and in-memory H2**. It intentionally creates a row with `nickname = NULL` to prove SQL NULL differs from no row, and intentionally looks up `id = 99` to observe the exception.

Create a standard Gradle Spring Boot project with the Spring Boot plugin and dependency management. In the `dependencies` block of `build.gradle`, add:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
}
```

This is a **dependency block inside an already-configured Spring Boot project**, not a standalone runnable `build.gradle`.

**`src/main/resources/application.yml`:**

```yaml
spring:
  datasource:
    url: "jdbc:h2:mem:empty_result_demo;DB_CLOSE_DELAY=-1"
    driver-class-name: org.h2.Driver
    username: sa
    password: ""
```

**`src/main/java/example/Customer.java`:**

```java
package example;

public record Customer(long id, String name, String nickname) {}
```

`Customer` is a Java 17 record; the `nickname` field is allowed to be `null` to represent SQL NULL in its corresponding column.

**`src/main/java/example/CustomerRepository.java`:**

```java
package example;

import java.util.List;
import java.util.Objects;
import java.util.Optional;

import org.springframework.dao.support.DataAccessUtils;
import org.springframework.jdbc.core.JdbcOperations;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;

@Repository
public final class CustomerRepository {
    private static final RowMapper<Customer> CUSTOMER_MAPPER =
        (rs, rowNum) -> new Customer(
            rs.getLong("id"),
            rs.getString("name"),
            rs.getString("nickname")
        );

    private final JdbcOperations jdbc;

    public CustomerRepository(JdbcOperations jdbc) {
        this.jdbc = jdbc;
    }

    // Contract: requires exactly one row.
    public Customer getRequiredById(long id) {
        return jdbc.queryForObject(
            "SELECT id, name, nickname FROM customers WHERE id = ?",
            CUSTOMER_MAPPER,
            id
        );
    }

    // Contract: may have 0 or 1 customer.
    public Optional<Customer> findById(long id) {
        List<Customer> rows = jdbc.query(
            "SELECT id, name, nickname FROM customers WHERE id = ?",
            CUSTOMER_MAPPER,
            id
        );
        return DataAccessUtils.optionalResult(rows);
    }

    // Row exists with SQL NULL nickname -> Java null.
    public String nicknameFor(long id) {
        return jdbc.queryForObject(
            "SELECT nickname FROM customers WHERE id = ?",
            String.class,
            id
        );
    }

    // COUNT(*) without GROUP BY returns one row even when count is 0.
    public long countById(long id) {
        Long count = jdbc.queryForObject(
            "SELECT COUNT(*) FROM customers WHERE id = ?",
            Long.class,
            id
        );
        return Objects.requireNonNull(count);
    }

    // UPDATE affecting 0 rows returns 0, not EmptyResultDataAccessException.
    public int rename(long id, String newName) {
        return jdbc.update(
            "UPDATE customers SET name = ? WHERE id = ?",
            newName,
            id
        );
    }
}
```

Here `JdbcOperations` is the Spring interface implemented by `JdbcTemplate`. Spring Boot auto-configures a `JdbcTemplate` bean when auto-configuration conditions match; the repository receives it via constructor injection. `RowMapper<Customer>` constructs a non-null record when a row is received, so `Optional<Customer>` accurately reflects row existence.

**`src/main/java/example/EmptyResultDemoApplication.java`:**

```java
package example;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.jdbc.core.JdbcOperations;

@SpringBootApplication
public class EmptyResultDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(EmptyResultDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner runDemo(
            JdbcOperations jdbc, CustomerRepository customers) {
        return args -> {
            jdbc.execute("""
                CREATE TABLE customers (
                    id BIGINT PRIMARY KEY,
                    name VARCHAR(80) NOT NULL,
                    nickname VARCHAR(80)
                )
                """);

            jdbc.update(
                "INSERT INTO customers (id, name) VALUES (?, ?)",
                1L, "Lan"
            );
            jdbc.update(
                "INSERT INTO customers (id, name, nickname) VALUES (?, ?, ?)",
                2L, "Minh", "M"
            );

            System.out.println(
                "required=" + customers.getRequiredById(1L)
            );

            try {
                customers.getRequiredById(99L);
            } catch (EmptyResultDataAccessException ex) {
                System.out.println("missing=EmptyResultDataAccessException");
            }

            System.out.println(
                "optionalFound=" + customers.findById(2L)
            );
            System.out.println(
                "optionalMissing=" + customers.findById(99L)
            );
            System.out.println(
                "nicknameSqlNull=" + (customers.nicknameFor(1L) == null)
            );
            System.out.println(
                "countMissing=" + customers.countById(99L)
            );
            System.out.println(
                "updateMissing=" + customers.rename(99L, "Nobody")
            );
        };
    }
}
```

Run from the root directory of the Spring Boot project:

```bash
./gradlew bootRun
```

On Windows, you can use `gradlew.bat bootRun`. With the freshly created in-memory H2 database and no other initialization scripts, the lines **printed by the program itself** are:

```text
required=Customer[id=1, name=Lan, nickname=null]
missing=EmptyResultDataAccessException
optionalFound=Optional[Customer[id=2, name=Minh, nickname=M]]
optionalMissing=Optional.empty
nicknameSqlNull=true
countMissing=0
updateMissing=0
```

Why is this right?

1. `getRequiredById(1)` finds one row and `RowMapper` builds a `Customer`. The `nickname` field is `null`, yet the `Customer` object **still exists**.
2. `getRequiredById(99)` has no row, triggering `EmptyResultDataAccessException`. The `catch` block prints only the observed scenario label without depending on the exception message.
3. `findById(2)` uses `query` and `DataAccessUtils.optionalResult` and returns a populated `Optional`. `findById(99)` returns `Optional.empty()`.
4. `nicknameFor(1)` receives exactly one row and a SQL NULL column, so the `String` value is Java `null`.
5. `COUNT(*)` returns one row with count `0`, and `UPDATE` affects no rows so `jdbc.update(...)` returns `0`.

These three Java files form a complete demonstration when placed in a **Spring Boot project with the dependencies and configuration above**. They cannot be compiled with bare `javac` without the Spring libraries; use the project's Gradle/Maven build to compile and run. If switching from H2 to PostgreSQL, you need the driver, DB config, and to account for dialect/schema-initialization differences.

## 7. Translating Technical Errors into Business Contracts

A repository sometimes exposes a mandatory-existence API, while the service wants to express a domain-meaningful error:

```java
public Customer requireCustomer(long id) {
    try {
        return customers.getRequiredById(id);
    } catch (EmptyResultDataAccessException ex) {
        throw new CustomerNotFoundException(id, ex);
    }
}
```

This is a **service method fragment** with a `customers` variable of type `CustomerRepository` and `EmptyResultDataAccessException` imported. An example domain exception you can use:

```java
public final class CustomerNotFoundException extends RuntimeException {
    public CustomerNotFoundException(long id, Throwable cause) {
        super("Customer " + id + " does not exist", cause);
    }
}
```

This class should live in `CustomerNotFoundException.java` if it is a public top-level class and can be placed in your application package. Translating errors so the service/controller knows *not found* does not force the repository layer to know about HTTP.

In a REST API, a controller or `@RestControllerAdvice` can map `CustomerNotFoundException` to HTTP **404 Not Found** for a single-resource-by-ID endpoint. However, you should not return 404 for every query returning an empty list: search endpoints usually return **200 OK** with `[]`; that distinction depends on the API contract.

### Do Not Mask Database Errors

The following snippet is problematic:

```java
try {
    return customers.getRequiredById(id);
} catch (org.springframework.dao.DataAccessException ex) {
    return null;
}
```

This is an example of **bad code** inside a method returning `Customer`: catching `DataAccessException` too broadly and converting every error into `null`. It can hide lost database connections, broken SQL, permission denied, or duplicate data. To express a missing record, handle only `EmptyResultDataAccessException` or design the query to return `Optional` from the beginning.

Likewise, do not turn every `IncorrectResultSizeDataAccessException` into `Optional.empty()`: a multiple-row error signals a violation of the uniqueness expectation and could be a SQL/schema bug or data issue needing investigation.

### Do Not Use Exceptions for Routine Control Flow

If a lookup feature frequently finds no data, a `findById` version returning `Optional` makes the contract easier to read and avoids generating stack traces for normal result branches. Conversely, if missing data violates an important precondition, throwing a clear error is appropriate.

The design decision lies in **the meaning of "not found"**, not in trying to eliminate all exceptions.

## 8. Less Obvious Edge Cases

### 8.1. `queryForObject` Returns `null` Even with Exactly One Row

This can happen when the SQL column value is `NULL` (with the `requiredType` form) or when a developer-provided `RowMapper` returns `null`. Do not equate "no exception thrown" with "value is always non-null". In Java, if data must definitely be non-null, enforce `NOT NULL` in the schema, validate data, and state clear method contracts.

### 8.2. Zero Rows Due to Filters, Joins, or Access Controls

A wrong `WHERE` condition, inner join dropping rows, tenant filter, soft-delete filter, or authorization filter can all cause a query to return 0 rows. Before concluding "the database has no record", inspect **the actual SQL sent**, bound parameters, tenant/security context, and which database/schema is connected.

Never log passwords, access tokens, or sensitive personal data just to debug a zero-row query.

### 8.3. Multiple Calls and Concurrent Data Changes

Between "checking whether a record exists" and "reading/updating the record", another transaction can delete or modify the data. A prior existence check does not guarantee a subsequent query still finds the row. For writes, generally rely on **affected row count** and DB constraints; when special consistency guarantees are needed, design appropriate isolation, locking, or versioning.

### 8.4. `UPDATE` Finding Zero Rows Does Not Throw EmptyResultDataAccessException

```java
int affected = jdbc.update(
    "UPDATE customers SET name = ? WHERE id = ?",
    "New name",
    99L
);
```

`affected` is `0` if no rows were modified. If business rules require updating exactly one row, **the application checks it explicitly**:

```java
if (affected == 0) {
    throw new CustomerNotFoundException(99L, null);
}
if (affected != 1) {
    throw new IllegalStateException(
        "Expected one updated customer, got " + affected
    );
}
```

These two fragments belong inside a method with `jdbc` and the exception class defined above. Normally, `UPDATE ... WHERE id = ?` with `id` as primary key affects at most one row. If `WHERE` filters on a non-unique attribute, consider the case where multiple rows get updated. `0` could mean non-existence or an extra condition like a mismatched version; depending on business logic, that may be a "conflict" rather than "not found".

### 8.5. Only a Unique Key Guarantees at Most One Row

If `WHERE name = ?` uses a non-unique criterion, `queryForObject` can fail on the **multiple rows** branch, even if initial tests only had unique names. To guarantee at most one row, define an appropriate UNIQUE/PRIMARY KEY constraint or clarify that the operation only needs "the latest record" and sort/limit accordingly.

Do not use `LIMIT 1` to hide a uniqueness bug that the business needs to detect.

### 8.6. Row-Count Errors Differ from Column-Count Errors

`queryForObject(sql, String.class, ...)` requires one row **and one column**. `SELECT id, name ...` has two columns and thus violates that overload, even if the query returns only one row. For multi-column results, use `RowMapper<Customer>` to map, or select only one column in SQL.

## 9. Writing Tests to Distinguish Each Branch

Meaningful tests should verify **0 rows**, **1 row with a NULL value**, **1 normal row**, **multiple rows**, and **UPDATE affecting 0 rows**.

In a Spring Boot project with `spring-boot-starter-test` and H2, you can write a JDBC slice test. This example reuses `CustomerRepository` and `Customer` from section 6.

**Add test dependency** in your configured Gradle build:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

**`src/test/java/example/CustomerRepositoryTest.java`:**

```java
package example;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.context.annotation.Import;
import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.dao.IncorrectResultSizeDataAccessException;
import org.springframework.jdbc.core.JdbcOperations;

import static org.junit.jupiter.api.Assertions.*;

@JdbcTest
@Import(CustomerRepository.class)
class CustomerRepositoryTest {
    @Autowired
    JdbcOperations jdbc;

    @Autowired
    CustomerRepository customers;

    @BeforeEach
    void setUp() {
        jdbc.execute("""
            CREATE TABLE IF NOT EXISTS customers (
                id BIGINT PRIMARY KEY,
                name VARCHAR(80) NOT NULL,
                nickname VARCHAR(80)
            )
            """);
        jdbc.update("DELETE FROM customers");
        jdbc.update(
            "INSERT INTO customers (id, name) VALUES (?, ?)",
            1L, "Lan"
        );
        jdbc.update(
            "INSERT INTO customers (id, name, nickname) VALUES (?, ?, ?)",
            2L, "Minh", "M"
        );
    }

    @Test
    void requiredLookupThrowsWhenZeroRows() {
        assertThrows(
            EmptyResultDataAccessException.class,
            () -> customers.getRequiredById(99L)
        );
    }

    @Test
    void optionalLookupReturnsEmptyWhenZeroRows() {
        assertTrue(customers.findById(99L).isEmpty());
        assertEquals("Minh", customers.findById(2L).orElseThrow().name());
    }

    @Test
    void existingRowWithNullColumnIsNotMissing() {
        assertNull(customers.nicknameFor(1L));
        assertTrue(customers.findById(1L).isPresent());
    }

    @Test
    void countAndUpdateUseZeroValueInsteadOfEmptyResultError() {
        assertEquals(0L, customers.countById(99L));
        assertEquals(0, customers.rename(99L, "Nobody"));
    }

    @Test
    void queryForObjectRejectsMultipleRows() {
        assertThrows(
            IncorrectResultSizeDataAccessException.class,
            () -> jdbc.queryForObject(
                "SELECT id FROM customers",
                Long.class
            )
        );
    }
}
```

Run:

```bash
./gradlew test
```

On Windows, use `gradlew.bat test`. Spring Boot 3.3 with `@JdbcTest`, H2, and the imported repository will run the checks against the embedded database. The test code does not need to boot the full application via `main`; `@JdbcTest` initializes only the relevant JDBC components.

Expected outcome: **5 tests pass**. This assumes no conflicting `customers` schema exists, H2 test dependencies/config are valid, and JUnit/Spring Boot versions are compatible. Because `@JdbcTest` normally starts a transaction and rolls back after each test, methods are isolated per Spring testing rules; still avoid relying on test execution order.

**Do not write tests asserting exact exception message text.** Assert the *error type*, result type, row count, and data. If you want to distinguish missing rows from multiple rows, write separate tests for the two branches instead of using overly broad `assertThrows(DataAccessException.class, ...)`.

## 10. Choosing Interfaces at Each Layer

```text
GET /customers/99
      |
      v
Controller
      |
      v
Service: requireCustomer(99)
      |
      v
Repository: getRequiredById(99)
      |
      v
JdbcTemplate.queryForObject(...)
      |
      +-- 1 row   -> Customer
      |
      +-- 0 rows  -> EmptyResultDataAccessException
      |                 |
      |                 v
      |          Service translates to NotFound
      |                 |
      |                 v
      |          Controller returns 404 per API contract
      |
      +-- >1 row  -> IncorrectResultSizeDataAccessException
                        (expectation violation to investigate)
```

In a **list** retrieval flow, the repository uses `query(...)` returning `List<Customer>` and the controller can return `200 OK` with `[]`. In a **specific resource** retrieval flow, the service can return a not-found error or map to 404. In a **job requiring reference data**, "0 rows" may be a critical configuration error; do not ignore it casually.

With HTTP, consider not leaking the existence of resources the caller is unauthorized to view. Response rules also depend on the authorization model and API contract, and cannot be derived solely from `EmptyResultDataAccessException`.

### Transactions and Rollback

`EmptyResultDataAccessException` is a runtime exception. If it escapes a Spring-managed `@Transactional` method, the default rollback policy typically marks the transaction for rollback. If you catch the error and return `Optional.empty()` inside the transaction, the exception no longer escapes; therefore do not treat "catching the exception" and "letting the exception propagate" as equivalent in transactional impact. You may need business rules or explicit rollback configuration when appropriate.

However, "not found" does not always mean rollback is required: for instance, an optional lookup inside a transaction may be valid with zero rows. Design transactions around **the semantics of the entire unit of work**, not a blanket desire to handle all 0-row errors uniformly.

## 11. Common Mistakes

1. **"queryForObject returns null if there are no rows."** Wrong: with 0 rows, it throws `EmptyResultDataAccessException`. `null` can only come from a row mapped to a null value.
2. **"Not finding a row means the SQL failed."** Wrong: the SQL can be completely valid and return 0 rows. The error comes from the Spring API's "exactly one row" contract.
3. **"Just catch DataAccessException and return Optional.empty."** Wrong: hides other DB/SQL errors. Handle only the expected absence case.
4. **"COUNT(*) equal to 0 throws EmptyResultDataAccessException."** Wrong for ungrouped count queries: it returns one row with value 0.
5. **"UPDATE finding nothing throws EmptyResultDataAccessException."** Wrong: `jdbc.update` normally returns an affected row count of 0.
6. **"With a RowMapper, I can handle zero rows inside the callback."** Wrong: the callback is never invoked when there are no rows to map.
7. **"Adding LIMIT 1 solves everything."** Wrong: does not handle 0 rows and can hide duplicate data; ordering must also be considered.
8. **"If a query returns multiple rows, just grab the first element."** Inappropriate when business requires uniqueness; `findFirst` can mask data bugs.
9. **"SQL NULL and a missing record are the same."** Wrong: you must distinguish row existence from column value.
10. **"EmptyResultDataAccessException is a checked SQLException."** Wrong: it is an unchecked exception in Spring's `DataAccessException` hierarchy.
11. **"Catching the error and substituting any dummy object is safe."** Be careful: fallbacks must be business-approved results, not replacements for required data validation.
12. **"Every single-result API in every library behaves the same."** Wrong: read the exact contracts of `JdbcTemplate`, `NamedParameterJdbcTemplate`, `JdbcClient`, JPA, or Spring Data repositories.

## 12. Self-Check

**Question 1.** The query `SELECT name FROM customers WHERE id = 99` has no rows. What does `jdbc.queryForObject(sql, String.class, ...)` return?

**Answer:** Throws `EmptyResultDataAccessException`, does not return `null`.

**Question 2.** Customer `id = 1`'s `nickname` column is SQL `NULL`. What does a `queryForObject` call reading only this column return?

**Answer:** Java `null` because there is exactly one row and the column value is SQL NULL; no missing-row error occurs.

**Question 3.** When searching for a list of customers by name where nobody may match, which API should you choose?

**Answer:** `query(...)` returning `List<Customer>`, where 0 rows is an empty list. Do not catch exceptions from a single-row API to simulate list searches.

**Question 4.** If `queryForObject` receives two rows, is that `EmptyResultDataAccessException`?

**Answer:** No. Multiple rows violate the exactly-one requirement via `IncorrectResultSizeDataAccessException`. `EmptyResultDataAccessException` is for 0 rows.

**Question 5.** How do you represent "customer exists with NULL nickname" differently from "customer does not exist"?

**Answer:** Map a single row to a non-null `Customer` and return `Optional<Customer>`. `Optional.empty()` means no row; `Optional.of(customer)` can hold `nickname == null`.

**Question 6.** If `jdbc.update("DELETE ... WHERE id = ?", 99L)` returns 0, should the application catch `EmptyResultDataAccessException`?

**Answer:** No. That return value is the affected row count. If business rules require deleting one row, check `affected == 0` explicitly and map to an appropriate domain result/error.

**Question 7.** Why prefer `DataAccessUtils.optionalResult` over `stream().findFirst()` when expecting 0 or 1 row?

**Answer:** `optionalResult` preserves the "more than one is an error" rule. `findFirst` silently discards extra rows, masking uniqueness violations.

## References

- [Spring Framework — EmptyResultDataAccessException](https://docs.spring.io/spring-framework/docs/6.1.12/javadoc-api/org/springframework/dao/EmptyResultDataAccessException.html): meaning of the missing-row error and relationship with `IncorrectResultSizeDataAccessException`.
- [Spring Framework — JdbcOperations, 6.2](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/jdbc/core/JdbcOperations.html): contracts for `queryForObject`, `query`, `queryForMap`, `update`, and overloads.
- [Spring Framework — DataAccessUtils](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/dao/support/DataAccessUtils.html): `optionalResult`, `singleResult`, and result-size handling rules.
- [Spring Framework — JDBC Core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): how `JdbcTemplate` queries, maps rows, and manages resources and errors.
- [Spring Framework — JdbcClient](https://docs.spring.io/spring-framework/docs/6.1.0-M4/javadoc-api/org/springframework/jdbc/core/simple/JdbcClient.html): fluent `single()`/`optional()` API introduced in Spring 6.1.
- [Spring Boot — SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html): `DataSource` and Spring JDBC configuration.

**Key takeaway:** `EmptyResultDataAccessException` occurs when an API **requires a row** yet the query returns **0 rows**. Missing data may be normal or a business error; the decision belongs to the repository/service contract. Use `Optional` or `List` for results allowed to be absent, use `queryForObject` when exactly one row is genuinely required, and always distinguish 0 rows from one row containing SQL NULL or a `COUNT(*)` returning 0.