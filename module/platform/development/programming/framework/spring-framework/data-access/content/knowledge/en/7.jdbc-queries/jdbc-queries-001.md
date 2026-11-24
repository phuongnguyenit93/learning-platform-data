# Querying a Single Value with queryForObject() in Spring JDBC

## 1. Lesson Objectives

When a Spring application needs to retrieve **exactly one row** from a relational database, `JdbcTemplate.queryForObject()` is a concise JDBC API with a **strict result-cardinality contract**. For calls returning a single simple value such as `Long`, `String`, or `BigDecimal`, the SQL query must also produce **exactly one column**. When you need an object from multiple columns, use the overload that accepts a `RowMapper<T>`.

This lesson helps you:
- Recognize when `queryForObject()` is a better fit than `query()`, `queryForList()`, or multi-row queries.
- Use the `Class<T>` and `RowMapper<T>` overloads properly, with safe parameter binding.
- Understand the difference between **0 rows**, **1 row with SQL NULL**, **1 row with a value**, **multiple rows**, **multiple columns**, and **database errors**.
- Handle `EmptyResultDataAccessException`, `IncorrectResultSizeDataAccessException`, and `IncorrectResultSetColumnCountException` without hiding bugs.
- Write runnable Java 17+/Spring Boot code, self-verify the output, and build tests for the query contract.
- Design repositories and services that clearly distinguish "must exist" lookups from "may not exist" lookups.

**Context:** Spring Framework 6.x, `spring-jdbc`, and `JdbcTemplate` with blocking JDBC programming. The Spring Boot examples use Java 17+ and do not require JPA. This lesson covers **querying a single value with `queryForObject()`**, not a general overview of all SQL query forms.

## 2. Two Levels of "A Single Value"

The name `queryForObject()` sometimes misleads developers into thinking any SQL query can fetch "one thing". In practice, you must ask two questions:

1. **How many rows does the SQL return?** The `queryForObject()` API expects **exactly one row**, whether for a scalar or an object.
2. **How many columns does the SQL return?** With the `Class<T> requiredType` overload, **one column** is required. With the `RowMapper<T>` overload, the mapper can read **multiple columns** from that row to construct an object.

Examples:

```sql
-- Exactly one row, one column: suitable for queryForObject(sql, Long.class)
SELECT COUNT(*) FROM customers;

-- At most one row, one column if id is PRIMARY KEY:
SELECT display_name FROM customers WHERE id = ?;

-- At most one row, multiple columns if id is PRIMARY KEY:
SELECT id, display_name, email FROM customers WHERE id = ?;

-- Potentially multiple rows: NOT compatible with queryForObject's contract unless guaranteed to be exactly one.
SELECT display_name FROM customers WHERE active = TRUE;
```

| SQL Result | `Class<T>` Overload | `RowMapper<T>` Overload |
|---|---|---|
| 0 rows | Throws `EmptyResultDataAccessException` | Throws `EmptyResultDataAccessException` |
| 1 row, 1 column, non-NULL value | Returns value converted to type T (if compatible) | Returns object created by mapper |
| 1 row, 1 column, SQL NULL | May return Java `null` | Decided by `RowMapper` |
| 1 row, multiple columns | Throws `IncorrectResultSetColumnCountException` | Valid: mapper reads the needed columns |
| More than 1 row | Throws `IncorrectResultSizeDataAccessException` | Throws `IncorrectResultSizeDataAccessException` |
| Invalid SQL, lost connection, conversion violation... | Data access exception | Data access exception or mapper exception |

`EmptyResultDataAccessException` is a subclass of `IncorrectResultSizeDataAccessException` for the case where **1 was expected but 0 were received**. Do not conflate "returning Java `null`" with "SQL returning no rows": they have different mechanisms and meanings.

## 3. How It Works Under the Hood

`JdbcTemplate` uses JDBC under the hood, while hiding boilerplate code:

```text
Repository / Service
       |
       | jdbcTemplate.queryForObject(sql, requiredType, args...)
       v
JdbcTemplate
       |
       +-- acquire Connection via DataSource according to transaction context
       +-- create PreparedStatement when binding arguments
       +-- bind '?' to values, execute SQL
       +-- read result set
       |     +-- 0 rows -> insufficient result size error
       |     +-- 1 row  -> map a single value/object
       |     +-- >1 row -> excessive result size error
       +-- clean up JDBC resources owned by the template
       |
       v
Return T / null, or throw DataAccessException
```

In the `Class<T>` overload, Spring uses a **single-column** mapper to extract/convert the JDBC value to the appropriate Java type. In the `RowMapper<T>` overload, the mapper is invoked on each row to build the object; the final result must still contain exactly one row.

Overloads with `?` parameters typically use a prepared statement. Do not assume every overload uses a prepared statement: static SQL queries via no-argument overloads may use a JDBC `Statement` according to the API contract.

`JdbcTemplate` manages the lifecycle of JDBC resources in the normal path and translates `SQLException` instances into Spring's `DataAccessException` hierarchy. This does not mean it automatically turns missing results into `Optional.empty()`. When using `queryForObject()`, **cardinality is part of the contract**.

## 4. Using Class<T> to Retrieve a Single Value

This is the most readable form for scalar results.

### 4.1. Counting with COUNT(*)

```java
// In a class with a JdbcTemplate jdbc field:
Long count = jdbc.queryForObject(
    "SELECT COUNT(*) FROM customers",
    Long.class
);
```

Because `COUNT(*)` without `GROUP BY` returns **one row** even when the table is empty, `queryForObject()` fits well. The value when there are no data rows is **0**, not `null` or `EmptyResultDataAccessException`.

Choose `Long` for large counts to avoid assuming the value will always fit within `int` range. Driver mappings may support multiple numeric types, but if the database is large, `Long` is usually a safer choice than `Integer`.

### 4.2. Looking Up a Single Column by Unique Key

```java
String displayName = jdbc.queryForObject(
    "SELECT display_name FROM customers WHERE id = ?",
    String.class,
    customerId
);
```

- `?` is bound from `customerId`; do not concatenate input into SQL.
- If `id` is a primary key, at most one row matches.
- If no such ID exists: **throws `EmptyResultDataAccessException`**.
- If the column is nullable and a row exists: the Java value may be `null`.
- If the SQL returns two columns in the `String.class` overload, that is a column-count error, even if both columns are String.

A primary key guarantees **there is no more than one row**. It does not guarantee **there is exactly one row**. For user-supplied IDs, the 0-row case must still be handled.

### 4.3. Common Scalar Types

```java
// Illustrative methods in a repository with a JdbcTemplate jdbc field.
Long totalOrders = jdbc.queryForObject(
    "SELECT COUNT(*) FROM orders",
    Long.class
);

java.math.BigDecimal maxPrice = jdbc.queryForObject(
    "SELECT MAX(price) FROM products",
    java.math.BigDecimal.class
);

Boolean enabled = jdbc.queryForObject(
    "SELECT enabled FROM feature_flags WHERE flag_key = ?",
    Boolean.class,
    "new_checkout"
);
```

Note that `MAX(price)` on an empty set can return **one row with SQL NULL**. `maxPrice == null` in this example does not prove the SQL returned 0 rows. For monetary values, `BigDecimal` is commonly used to preserve decimal precision; avoid assuming the exact JDBC type without checking the schema/dialect.

If business rules state "when there are no products, the max price defaults to 0", you can write:

```sql
SELECT COALESCE(MAX(price), 0) FROM products;
```

Only use `COALESCE` when **0 is truly the business meaning**, not to erase the "no data" signal.

## 5. Using RowMapper<T> to Retrieve an Object from Multiple Columns

Consider querying a customer with `id`, `display_name`, `email`. If you call `queryForObject(sql, Customer.class)` without a suitable custom mapping mechanism, `Class<T>` is not an automatic command to "turn multiple columns into an entity". That overload is for **scalar one-column mapping**. Provide a `RowMapper<Customer>`:

```java
// Customer.java
package example.jdbc;

public record Customer(long id, String name, String email) {}
```

```java
// CustomerJdbcRepository.java
package example.jdbc;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;

@Repository
public class CustomerJdbcRepository {

    private static final RowMapper<Customer> CUSTOMER_MAPPER =
        (rs, rowNum) -> new Customer(
            rs.getLong("id"),
            rs.getString("display_name"),
            rs.getString("email")
        );

    private final JdbcTemplate jdbc;

    public CustomerJdbcRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public Customer requireById(long id) {
        return jdbc.queryForObject("""
                SELECT id, display_name, email
                FROM customers
                WHERE id = ?
                """, CUSTOMER_MAPPER, id);
    }
}
```

**Results:**
- Exactly one row → the mapper creates `Customer` and the method returns the object.
- No rows → `EmptyResultDataAccessException`.
- Multiple rows → `IncorrectResultSizeDataAccessException`.
- `email` column has SQL NULL → `rs.getString("email")` returns Java `null`, but **the row still exists**.

`RowMapper` should map to a DTO/record decoupled from `ResultSet`, never returning `ResultSet` outside the method. If a mapper itself returns Java `null` for a row, `queryForObject()` may return `null`; therefore **do not use `result == null` as a universal "not found" check**.

In Java 17, `record` is a good fit for immutable DTOs. If you need column-name mapping to a bean or record via a generic mapper, check `BeanPropertyRowMapper` or `DataClassRowMapper` depending on your Spring version, though for simple examples an explicit mapper makes aliases and nullability clearest.

## 6. The Exactly-One-Row Contract: 0, 1, More Than 1

### 6.1. No Rows Is an Exception, Not Null

```java
try {
    String name = jdbc.queryForObject(
        "SELECT display_name FROM customers WHERE id = ?",
        String.class,
        999L
    );
    System.out.println(name);
} catch (org.springframework.dao.EmptyResultDataAccessException ex) {
    System.out.println("Customer not found");
}
```

This is a snippet **inside a method that has a `jdbc` field**, not a standalone Java file. Only catch `EmptyResultDataAccessException` when **not found** is genuinely an expected scenario.

If the use case requires the customer to exist, you can translate it into a domain error. If the method is meant to check whether a customer may or may not exist, consider having the repository return `Optional<Customer>` (shown later). Do not catch all of `DataAccessException` to return "not found".

### 6.2. Multiple Rows Is a Cardinality Violation

```java
String name = jdbc.queryForObject(
    "SELECT display_name FROM customers WHERE active = ?",
    String.class,
    true
);
```

If there are multiple active customers, the method will throw `IncorrectResultSizeDataAccessException`. This matches the contract: you asked for **one customer**, but the SQL found **all active customers**.

The fix depends on business requirements:
- Want a **list of active customers** → use `jdbc.query(...)`/`queryForList(...)` returning 0..N rows.
- Want a **customer by unique key** → add the key condition and appropriate unique constraint.
- Want the **latest customer** → use `ORDER BY created_at DESC, id DESC LIMIT 1`, **accepting that zero rows may be returned**; the secondary key `id` makes ordering deterministic.
- Want to **verify uniqueness** → enforce `PRIMARY KEY`/`UNIQUE` in the database and treat duplicates as errors to handle, **do not mask them with `LIMIT 1`**.

### 6.3. One Row with Multiple Columns Is an Error for the Scalar Overload

```java
// WRONG: String.class requires one column, SQL returns two columns.
String invalid = jdbc.queryForObject(
    "SELECT display_name, email FROM customers WHERE id = ?",
    String.class,
    1L
);
```

When a query returns exactly one row but two columns, the `Class<T>` overload throws `IncorrectResultSetColumnCountException`. If you need both columns, use `RowMapper<Customer>` or a DTO projection; if you only need the name, select **only `display_name`**.

## 7. SQL NULL vs. 0 Rows: The Most Important Trap

Imagine this data:

| id | display_name | nickname |
|---:|---|---|
| 1 | An | NULL |
| 2 | Binh | Bi |

Query A:

```sql
SELECT nickname FROM customers WHERE id = 1;
```

Result: **one row, one column containing SQL NULL**. `queryForObject(..., String.class, 1L)` may return Java `null`.

Query B:

```sql
SELECT nickname FROM customers WHERE id = 999;
```

Result: **zero rows**. `queryForObject(...)` throws `EmptyResultDataAccessException`.

Query C:

```sql
SELECT COUNT(*) FROM customers WHERE id = 999;
```

Result: **one row**, value `0`.

Query D:

```sql
SELECT SUM(amount) FROM payments WHERE customer_id = 999;
```

If there are no matching payments, the SQL `SUM` aggregate (without `GROUP BY`) usually returns **one row with NULL**, unlike `COUNT(*)` which returns `0`.

**Comparison table:**

| Scenario | Row count | Single-column content | Result from `queryForObject(..., Class<T>)` |
|---|---:|---|---|
| No record matches key | 0 | None | `EmptyResultDataAccessException` |
| Record exists, nullable column is NULL | 1 | SQL NULL | Java `null` may be returned |
| Count on empty set | 1 | 0 | Number 0 |
| Aggregate SUM/MAX on empty set | 1 | SQL NULL | Java `null` |
| Invalid SQL/connection error | Not reliably known | Undefined | Appropriate `DataAccessException` |

If the contract genuinely needs to distinguish "no row" from "row exists with NULL", return an object containing a **non-NULL key** alongside the nullable field, or define an explicit result type. `Optional.ofNullable(scalarValue)` alone cannot preserve this distinction.

### Null and Java Primitives

`Long.class` returns a nullable `Long`. If you write:

```java
long count = jdbc.queryForObject(
    "SELECT SUM(amount_cents) FROM orders",
    Long.class
);
```

When the query returns SQL NULL, auto-unboxing can cause a `NullPointerException`. If you want to handle an absent aggregate:

```java
Long sum = jdbc.queryForObject(
    "SELECT SUM(amount_cents) FROM orders",
    Long.class
);
long total = (sum == null) ? 0L : sum;
```

Only apply a default of 0 after deciding the business meaning. For monetary amounts with decimal places, prefer `BigDecimal` instead of converting to `double`.

## 8. "May Not Exist" Lookups with Optional

`queryForObject()` favors the **exactly one row** contract. When a repository needs to advertise 0..1, there are several valid approaches:

### 8.1. Catch EmptyResultDataAccessException Specifically

```java
// Illustrative method in a repository with a JdbcTemplate jdbc field,
// and RowMapper<Customer> CUSTOMER_MAPPER always creates a non-null Customer.
public java.util.Optional<Customer> findById(long id) {
    try {
        Customer customer = jdbc.queryForObject(
            "SELECT id, display_name, email FROM customers WHERE id = ?",
            CUSTOMER_MAPPER,
            id
        );
        return java.util.Optional.of(customer);
    } catch (org.springframework.dao.EmptyResultDataAccessException ex) {
        return java.util.Optional.empty();
    }
}
```

This makes it explicit that **not found** is a normal outcome. SQL, connection, or duplicate-row errors are still propagated and handled separately.

`Optional.of(customer)` is appropriate here because this specific mapper always builds an object; if your mapper is allowed to return null, define the contract clearly and do not casually use `Optional.ofNullable(...)` to conflate no-row with null-row.

### 8.2. Use query() and Enforce Cardinality

```java
// Illustrative method in a repository with CUSTOMER_MAPPER.
public java.util.Optional<Customer> findByIdViaList(long id) {
    java.util.List<Customer> rows = jdbc.query(
        "SELECT id, display_name, email FROM customers WHERE id = ?",
        CUSTOMER_MAPPER,
        id
    );
    if (rows.isEmpty()) {
        return java.util.Optional.empty();
    }
    if (rows.size() != 1) {
        throw new org.springframework.dao.IncorrectResultSizeDataAccessException(
            1, rows.size());
    }
    return java.util.Optional.of(rows.get(0));
}
```

This makes the cardinality check explicit, though it requires extra code and is unsuitable if the SQL could return millions of rows: you must limit or revise the query. With a unique key, the database guarantees at most one row, so the application will not load a large result set.

### 8.3. JdbcClient When Using Spring Framework 6.1+

`JdbcClient` provides a fluent syntax on top of JDBC:

```java
// Illustrative method; JdbcClient is injected.
public java.util.Optional<Customer> findByIdViaClient(long id) {
    return jdbcClient.sql("""
            SELECT id, display_name, email FROM customers WHERE id = :id
            """)
        .param("id", id)
        .query(CUSTOMER_MAPPER)
        .optional();
}
```

`optional()` expresses 0..1, `single()` expresses exactly one, and `list()` expresses 0..N. These methods belong to `JdbcClient`, **not overloads of `JdbcTemplate.queryForObject()`**. Choose the API based on your contract and Spring version; there is no need to switch to `JdbcClient` solely to "avoid exceptions" if the existing code is already clear.

## 9. PreparedStatement and Parameter Binding

Never concatenate input into SQL:

```java
// WRONG: SQL injection risk, broken escaping, hard to reuse query plans.
String sql = "SELECT email FROM customers WHERE display_name = '"
    + userInput + "'";
String email = jdbc.queryForObject(sql, String.class);
```

Correct:

```java
String email = jdbc.queryForObject(
    "SELECT email FROM customers WHERE display_name = ?",
    String.class,
    userInput
);
```

`?` is a bind placeholder; the JDBC driver handles the corresponding value, and user data is not interpreted as SQL syntax. When there are multiple parameters, the argument order must match `?`:

```java
Long count = jdbc.queryForObject("""
        SELECT COUNT(*)
        FROM customers
        WHERE active = ? AND display_name LIKE ?
        """,
    Long.class,
    true,
    prefix + "%"
);
```

`LIKE` and wildcard characters `%`/`_` have special search semantics. If `prefix` is user text and you want literal matching (without user-supplied wildcards), escape wildcards according to your SQL dialect/`ESCAPE` clause; parameter binding prevents SQL injection, **it does not alter `LIKE` semantics**.

Table/column names and `ORDER BY` expressions cannot be bound as scalar data; if users need to choose a sort order, map the chosen value against an allowlist of column names instead of interpolating input directly.

### Using NamedParameterJdbcTemplate

When many parameters make positional order error-prone, `NamedParameterJdbcTemplate` provides equivalent overloads:

```java
// Method in a class with a NamedParameterJdbcTemplate namedJdbc field.
public String requireEmail(long id) {
    return namedJdbc.queryForObject(
        "SELECT email FROM customers WHERE id = :id",
        java.util.Map.of("id", id),
        String.class
    );
}
```

It still follows "exactly one row, one column" and may return null if `email` in the DB is NULL. Named parameters do not make a query automatically "optional" and do not prevent multiple rows if the SQL lacks a uniqueness condition.

## 10. Runnable Spring Boot Demo with H2

This section provides **a complete Spring Boot application** to observe the exact states: a single count value, an object, 0 rows, multiple rows, and SQL NULL. Embedded H2 is chosen for quick local learning; in real deployments, test again with your production DB/driver.

### 10.1. Structure

```text
query-for-object-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/example/jdbc/QueryForObjectDemoApplication.java
    └── resources/
        ├── application.properties
        ├── schema.sql
        └── data.sql
```

`settings.gradle`:

```groovy
rootProject.name = 'query-for-object-demo'
```

`build.gradle` (Spring Boot 3.3.5, Java 17 example):

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

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

`src/main/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:querydemo;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
```

`src/main/resources/schema.sql`:

```sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    display_name VARCHAR(100) NOT NULL,
    nickname VARCHAR(100),
    active BOOLEAN NOT NULL
);
```

`src/main/resources/data.sql`:

```sql
INSERT INTO customers (id, display_name, nickname, active)
VALUES (1, 'An', NULL, TRUE);

INSERT INTO customers (id, display_name, nickname, active)
VALUES (2, 'Binh', 'Bi', TRUE);

INSERT INTO customers (id, display_name, nickname, active)
VALUES (3, 'Chi', NULL, FALSE);
```

`src/main/java/example/jdbc/QueryForObjectDemoApplication.java`:

```java
package example.jdbc;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.dao.IncorrectResultSizeDataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;

@SpringBootApplication
public class QueryForObjectDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(QueryForObjectDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner demonstrate(JdbcTemplate jdbc) {
        return args -> {
            Long count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM customers",
                Long.class);
            System.out.println("count=" + count);

            RowMapper<Customer> mapper = (rs, rowNum) ->
                new Customer(
                    rs.getLong("id"),
                    rs.getString("display_name"));

            Customer customer = jdbc.queryForObject(
                "SELECT id, display_name FROM customers WHERE id = ?",
                mapper,
                1L);
            System.out.println("found=" + customer.name());

            try {
                jdbc.queryForObject(
                    "SELECT id, display_name FROM customers WHERE id = ?",
                    mapper,
                    999L);
            } catch (EmptyResultDataAccessException ex) {
                System.out.println("notFound=true");
            }

            try {
                jdbc.queryForObject(
                    "SELECT id, display_name FROM customers WHERE active = ?",
                    mapper,
                    true);
            } catch (IncorrectResultSizeDataAccessException ex) {
                System.out.println("notUnique=true");
            }

            String nickname = jdbc.queryForObject(
                "SELECT nickname FROM customers WHERE id = ?",
                String.class,
                1L);
            System.out.println("nicknameIsNull=" + (nickname == null));
        };
    }
}

record Customer(long id, String name) {}
```

**Run:** use Gradle 8.x compatible with the sample Spring Boot version, then at the project root:

```bash
gradle bootRun
```

Or use the project's Gradle Wrapper if configured: `./gradlew bootRun` on Unix/macOS, `gradlew.bat bootRun` on Windows.

Five lines **printed by the program**, in exact order (Spring Boot/Gradle may print additional startup/build logs):

```text
count=3
found=An
notFound=true
notUnique=true
nicknameIsNull=true
```

Explanation:
1. `COUNT(*)` produces exactly one row, count column = 3.
2. Query by id=1 has one row with two columns; `RowMapper` creates the record `Customer(1, "An")`.
3. id=999 has no rows, so `EmptyResultDataAccessException` is caught and prints `notFound=true`.
4. `active=TRUE` matches An and Binh (two rows), so `queryForObject` reports excess results.
5. id=1 exists but `nickname` is SQL NULL; the scalar query returns Java null without throwing `EmptyResultDataAccessException`.

The demo uses fixed data and H2 for ease of running. It does **not** prove the behavior of all PostgreSQL/MySQL drivers or all real schemas. When switching DBs, test data types, SQL dialect, indexes, and exception translation in a production-like environment.

## 11. Repository and Service Design: Who Decides "Not Found"?

Separate the data layer from business logic. A repository can name a method `requireById` to express "exactly one row", or `findById` returning `Optional` if absence is allowed. The service decides whether absence is acceptable in a given use case.

Example of a service that requires finding the customer:

```java
// CustomerNotFoundException.java
package example.jdbc;

public final class CustomerNotFoundException extends RuntimeException {
    public CustomerNotFoundException(long id) {
        super("Customer not found: " + id);
    }
}
```

```java
// CustomerLookupService.java
package example.jdbc;

import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.stereotype.Service;

@Service
public class CustomerLookupService {
    private final CustomerJdbcRepository repository;

    public CustomerLookupService(CustomerJdbcRepository repository) {
        this.repository = repository;
    }

    public Customer getRequired(long id) {
        try {
            return repository.requireById(id);
        } catch (EmptyResultDataAccessException ex) {
            throw new CustomerNotFoundException(id);
        }
    }
}
```

If `CustomerJdbcRepository.requireById` queries by primary key, you can specifically translate the 0-row error into a domain error. Do **not** catch the general `IncorrectResultSizeDataAccessException` and turn all cases into "customer not found", because the >1 row case signals a broken query or missing constraint. If you need to catch both in one block, remember `EmptyResultDataAccessException` extends `IncorrectResultSizeDataAccessException`, so place the more specific catch branch first.

The HTTP layer can later translate `CustomerNotFoundException` into 404 (per API policy). Do not force the repository to return `ResponseEntity`, because a JDBC repository may be called from batch jobs, message consumers, or other non-HTTP services.

## 12. Error Handling That Preserves Meaning

| Scenario | Typical Behavior | Recommended Resolution |
|---|---|---|
| No row, query requires exactly one | `EmptyResultDataAccessException` | Decide absence at the use case level, optionally map to domain NotFound |
| More than one row | `IncorrectResultSizeDataAccessException` | Fix query or unique constraint, do not arbitrarily pick the first row |
| One row, multiple columns with `Class<T>` | `IncorrectResultSetColumnCountException` | SELECT only one column or use RowMapper |
| One row with SQL NULL | Java `null` in scalar overload | Define nullability, use COALESCE if meaningful |
| Invalid SQL syntax or missing column | Grammar-related `DataAccessException` | Fix SQL/migration/mapping, do not convert to not-found |
| DB connection lost/pool timeout | Resource/data access error group | Log/monitor, 5xx response per policy, do not return empty |
| Duplicate key on INSERT | Constraint exception | Handle business conflict, unrelated to 0 rows on SELECT |
| Mapper reads wrong type or missing column | Mapping/conversion/runtime error | Fix mapper, alias, schema; run integration tests |

**Anti-pattern:**

```java
// WRONG: every error is reported as customer does not exist.
try {
    return jdbc.queryForObject(sql, CUSTOMER_MAPPER, id);
} catch (Exception ex) {
    return null;
}
```

This is an illustrative snippet inside a class that already has `sql`, `jdbc`, and `CUSTOMER_MAPPER`; it is not standalone code. It hides broken SQL, mapping bugs, DB outages, and duplicate data behind Java null, making the system hard to operate.

**Correct handling pattern:** catch only the errors allowed to map to a business outcome, and let other exceptions propagate. Detailed technical error info should be recorded in internal logs/traces without exposing database URLs, SQL containing sensitive data, credentials, or stack traces in API responses.

### Does Retrying Fix Missing Rows or Duplicate Rows?

Usually **no**:
- 0 rows by ID will not magically become 1 row on retry; only retry when there is an eventual-consistency reason and a clear policy.
- Multiple rows due to a missing unique constraint should not be retried indefinitely; fix the data invariant.
- Connection loss/deadlocks may be transient, but retries require bounds, backoff, timeouts, and idempotency checks. Do not retry every `DataAccessException`.
- For writes, a timeout may occur after the DB already applied the change; retrying is not a default part of `queryForObject()`.

## 13. When Not to Use queryForObject()

### 13.1. 0..N Results

To query a list, use `jdbc.query(sql, rowMapper, args...)`:

```java
// Illustrative method in a repository with CUSTOMER_MAPPER.
public java.util.List<Customer> findActive() {
    return jdbc.query("""
            SELECT id, display_name, email
            FROM customers
            WHERE active = ?
            ORDER BY id
            """, CUSTOMER_MAPPER, true);
}
```

0 rows → empty list. N rows → list of N records. For large tables, use pagination/`LIMIT`, deterministic ordering, and DTO projection to avoid loading the entire result into the heap.

### 13.2. Only Checking Whether a Record Exists

`COUNT(*)` can be used with `queryForObject`, but if you only need a boolean existence check, a `SELECT EXISTS(...)` query (dialect-dependent) can express intent better:

```java
Boolean exists = jdbc.queryForObject("""
        SELECT EXISTS (
            SELECT 1 FROM customers WHERE id = ?
        )
        """, Boolean.class, customerId);
```

In supporting databases, an `EXISTS` query returns **one row/one boolean column**, regardless of whether the customer exists. Do not treat `false` as a missing row.

### 13.3. Fetching the "First Row" of a Result Set

`queryForObject()` checks for exactly one row. `ORDER BY` by itself does **not** limit the row count, so if you need only the single latest record, apply `LIMIT 1` (or the DB-equivalent mechanism) with deterministic ordering:

```sql
SELECT id, display_name
FROM customers
WHERE active = TRUE
ORDER BY id DESC
LIMIT 1;
```

This query can return 0 or 1 row; if 0 is valid, you still must use an optional API or handle `EmptyResultDataAccessException` explicitly. Do not add `LIMIT 1` to "fix" a query on a key that ought to be unique: doing so can hide data corruption.

### 13.4. Mapping Multiple Columns into a Map

If you need multiple columns without a DTO, `queryForMap` is an API with a one-row contract that maps column names to values; however, a DTO/RowMapper usually provides better type safety and a clearer contract. `queryForObject(sql, Class<T>)` does **not** automatically map multiple columns into a `Map` or entity.

### 13.5. Asynchronous/Reactive Queries

`JdbcTemplate` is a blocking JDBC API. Wrapping it in `CompletableFuture` or `Mono.fromCallable` does not make the driver non-blocking. If the application actually uses R2DBC, `DatabaseClient.one()` is a different API with its own semantics. Do not use reactive wrappers to bypass JDBC cardinality concerns.

## 14. Testing This Topic Meaningfully

A good test suite covers **both row count and column count**:

| Fixture/query | Expected |
|---|---|
| `SELECT COUNT(*)` on empty table | Long `0`, no exception |
| `SELECT name WHERE id = 1` with one row | Customer name |
| `SELECT name WHERE id = 999` | `EmptyResultDataAccessException` |
| `SELECT name WHERE active = TRUE` with two rows | `IncorrectResultSizeDataAccessException` |
| `SELECT name, email WHERE id = 1` with `String.class` | `IncorrectResultSetColumnCountException` |
| `SELECT nickname WHERE id = 1` with SQL NULL | Java null value |
| `SELECT id, name WHERE id = 1` with `RowMapper<Customer>` | A `Customer` with populated properties |
| SQL with invalid column name or disconnected DB | Technical error, not converted to Optional.empty() |
| Parameter containing quotes or SQL-like text | Bound as data; does not alter SQL structure |
| `findById()` method with non-existent ID | `Optional.empty()`, if 0..1 contract is advertised |

### JUnit Test in a Spring Project

A short example with JUnit 5, Spring Boot, and the created database fixture:

```java
// Test snippet in a class with JdbcTemplate jdbc and appropriate schema/fixture.
@Test
void missingRowThrowsEmptyResult() {
    assertThatThrownBy(() ->
        jdbc.queryForObject(
            "SELECT display_name FROM customers WHERE id = ?",
            String.class,
            999L))
        .isInstanceOf(EmptyResultDataAccessException.class);
}
```

You need to import `org.junit.jupiter.api.Test`, `org.assertj.core.api.Assertions.assertThatThrownBy`, `EmptyResultDataAccessException`, and initialize/inject `jdbc` in the test. This is an **illustrative test method**, not a standalone runnable file.

In Spring Boot, `@JdbcTest` helps test the JDBC slice and manages per-test transactions, but for SQL/driver-specific behavior (especially PostgreSQL, MySQL), run integration tests against the real DB type, e.g., with Testcontainers. H2 only demonstrates the simple flow in section 10's demo.

### Common Mistakes Spotted During Code Review

1. **Writing `queryForObject()` to fetch "any one record"** even though the SQL may return 0 or many rows. Fix with an explicit 0..1/1/0..N contract.
2. **Using `String.class` for a two-column SQL query** and expecting Spring to pick the first column automatically. Fix the SQL or use a RowMapper.
3. **Assuming missing data returns `null`**; in reality, 0 rows throws EmptyResult, while SQL NULL may return null.
4. **Writing `Optional.ofNullable(queryForObject(...))` and believing 0 rows returns empty**; in reality, 0 rows throws an exception before Optional is ever constructed.
5. **Using `LIMIT 1` to hide duplicates** instead of adding a unique constraint or writing a context-appropriate query.
6. **Concatenating user input directly into SQL** instead of binding `?`.
7. **Catching `Exception` and returning a default value**, causing broken SQL to be treated as "not found".
8. **Unboxing a nullable `Long` into `long`** when SQL may return NULL from `SUM`/`MAX`.
9. **Ignoring JDBC getter types and NULL behavior** in RowMapper: `rs.getLong(...)` returns `0` for SQL NULL; to distinguish, check `rs.wasNull()` or use `rs.getObject(..., Long.class)`.
10. **Failing to verify unique constraints** and assuming a `WHERE external_code = ?` condition always matches at most one row.

## 15. Checklist Before Choosing queryForObject

- [ ] SQL is designed for **exactly one row**; if querying by ID/natural key, the database has an appropriate constraint.
- [ ] If calling the `Class<T>` overload, SQL returns **only one column**, and the Java type is compatible with the JDBC type.
- [ ] If SQL has multiple columns, `RowMapper<T>` is used and column nullability is well understood.
- [ ] Distinguish **0 rows**, **SQL NULL**, **COUNT(*) = 0**, and **multiple rows**.
- [ ] If 0 rows is valid, the method returns Optional or handles EmptyResult explicitly.
- [ ] If >1 row is an error, do not mask it with LIMIT 1 and protect it with tests/constraints.
- [ ] Input values are bound with `?` or named parameters; no raw input concatenation into SQL.
- [ ] Tests cover one row, zero rows, multiple rows, wrong column count, SQL NULL, and database errors.
- [ ] Do not swallow `DataAccessException` or turn infrastructure errors into "no data".
- [ ] Repository contract is reflected in method names/return types; service decides NotFound per use case.

## 16. Key Takeaways

**`JdbcTemplate.queryForObject()` is a query operation that requires exactly one row.** Use `Class<T>` for **single-column** results (COUNT, name, amount, status), and use `RowMapper<T>` when a single row has **multiple columns** to map into an object. **0 rows** is an insufficient-cardinality error; **more than 1 row** is an excessive-cardinality error; a single row containing **SQL NULL** may return Java null without a "not found" error. Choose the API matching the actual allowed result count, keep parameters bound, and let technical errors propagate properly to the handling layer.

## Official Documentation

- Spring Framework — Using JDBC Core Classes, Querying (SELECT) section: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring Framework — `JdbcOperations` Javadoc (`queryForObject` contract): https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/jdbc/core/JdbcOperations.html
- Spring Framework — `JdbcTemplate` API: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html
- Spring Framework — `JdbcClient` API: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring Framework — JDBC Exceptions and SQLExceptionTranslator: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
