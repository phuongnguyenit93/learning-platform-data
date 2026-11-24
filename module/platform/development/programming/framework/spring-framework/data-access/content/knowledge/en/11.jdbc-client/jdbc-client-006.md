# JdbcClient: single(), optional(), list(), and Result Cardinality Contracts

## Learning Objectives

A JDBC query can return **0 rows**, **1 row**, or **multiple rows**. Not every API treats those three situations the same way. When using Spring Framework's `JdbcClient`, you typically end a query chain with one of three methods:

- `list()`: returns a result set of **0..N rows** as `List<T>`.
- `optional()`: returns **0 or 1** mapped result as `Optional<T>`; **more than 1 row is an error**.
- `single()`: requires **exactly 1** **non-null** mapped result; missing rows, extra rows, or a null mapped value trigger corresponding exceptions in Spring Framework 6.2.

This is the **result cardinality contract**: the code declares up front what it considers valid, and Spring validates the actual query result against it.

After this lesson, you will be able to:

1. Write queries using `JdbcClient.sql(...).param(...).query(...).single()/optional()/list()`.
2. Pick the right API for a required record, an optionally absent record, or a collection of records.
3. Explain the exact behavior when SQL returns 0, 1, or 2+ rows, rather than mistakenly thinking `optional()` picks the first row or `single()` returns null when not found.
4. Distinguish **no rows** from **one row whose SQL column value is NULL**; understand the specific behavior in Spring Framework 6.2.
5. Use `RowMapper<T>` or `query(Class<T>)` appropriately, and handle `EmptyResultDataAccessException`, `IncorrectResultSizeDataAccessException`, and `TypeMismatchDataAccessException`.
6. Run the **Java 17+, Spring JDBC 6.2, and H2** example to verify each case with deterministic output.
7. Design repositories that express business intent clearly, protect uniqueness with data constraints, and avoid common performance/security mistakes.

**Scope:** Focuses on the trio `single()`, `optional()`, and `list()` of **Spring Framework `JdbcClient`**. Do not confuse them with `Optional`/`List` methods in Java Collections or Spring Data repository APIs.

## 1. Where Does JdbcClient Fit in Spring JDBC?

`JdbcClient` was introduced in **Spring Framework 6.1**. It provides a fluent API for common JDBC tasks, unifying calls with positional parameters (`?`) and named parameters (`:id`). Underneath, `JdbcClient` leverages `JdbcTemplate` and `NamedParameterJdbcTemplate`; it is **not an ORM** and does not replace JPA entity mapping or lazy loading.

A typical call chain:

```java
Customer customer = client.sql("""
        SELECT id, email, nickname
        FROM customers
        WHERE id = :id
        """)
    .param("id", 42L)
    .query(CUSTOMER_MAPPER)
    .single();
```

This is an **illustrative snippet**, assuming `client`, the `Customer` type, `CUSTOMER_MAPPER`, and the `customers` table exist. Section 8 provides a complete Java program.

Step-by-step explanation:

1. `sql(...)` defines the query structure.
2. `param("id", 42L)` binds the value 42 to the named parameter `:id`; data is never concatenated into the SQL string.
3. `query(CUSTOMER_MAPPER)` specifies how to map a `ResultSet` row into a `Customer`.
4. `single()` executes/resolves the query and enforces a single valid result per contract.

By itself, `query(RowMapper<T>)` returns a **`JdbcClient.MappedQuerySpec<T>`** so you can choose how to resolve it. Do not assume calling `query(mapper)` immediately returns a `List<Customer>` like `JdbcTemplate.query(...)`; ending with `list()`, `single()`, or `optional()` is what distinguishes the fluent API.

`JdbcClient.create(dataSource)` creates a client from a JDBC source; `JdbcClient.create(jdbcTemplate)` also exists to reuse an existing template's configuration. In a Spring application, `JdbcClient` can be declared as a bean and constructor-injected into repositories.

## 2. Decision Table: 0, 1, and Multiple Results

Assuming `query(RowMapper<T>)` maps each row into a **non-null** object:

| SQL row count | `list()` | `optional()` | `single()` |
| --- | --- | --- | --- |
| 0 | Empty `List<T>` | `Optional.empty()` | Throws `EmptyResultDataAccessException` |
| 1 | List with 1 element | `Optional.of(value)` | Returns one `T` |
| 2 or more | List with N elements | Throws `IncorrectResultSizeDataAccessException` | Throws `IncorrectResultSizeDataAccessException` |

Two points beginners must watch closely:

- **`optional()` does not mean "take one row if present, and pick arbitrarily if many".** It also requires **at most 1 row**. If the query actually returns two rows, `optional()` throws an exception.
- **`single()` does not mean "return object or null".** When there are no rows, it throws an exception. Specifically in Spring Framework **6.2**, a row mapped to **null** is also rejected by `single()`.

In this table, "SQL row count" more precisely means "number of elements produced by the query mapping"; with a standard `RowMapper`, each row yields one element. `list()` preserves the order returned by the DB, though **for deterministic ordering, the SQL must include `ORDER BY`**.

### 2.1. Quick Selection Rules

| Business question | Usually right choice |
| --- | --- |
| Find customer by ID and customer **must** exist at this step | `single()` |
| Find customer by ID where "not found" is a normal state | `optional()` |
| Search all customers by keyword; nobody may match | `list()` |
| Find all orders for an account, 0..N orders | `list()` |
| Count orders via `SELECT COUNT(*)` without `GROUP BY` | `query(Long.class).single()` |
| Look up by unique email that might not be registered yet | `optional()`, paired with a DB UNIQUE constraint |
| Find by status OPEN (typically multiple records) | `list()`, do not use `single()` |
| Check whether a result page has a next row | `list()` with `LIMIT`/appropriate `size+1` fetching |
| Detect corrupted data because 2 records share a supposedly unique key | `single()/optional()` raises an error, though a **UNIQUE constraint** is needed to prevent corruption at the source |

Choose the method based on the **semantics and invariants** of the use case, not on guessing "the test data currently has 1 row".

## 3. single(): Requiring One Mandatory Result

### 3.1. Example: Finding a Customer by ID

```java
Customer found = client.sql("""
        SELECT id, email, nickname
        FROM customers
        WHERE id = :id
        """)
    .param("id", 2L)
    .query(CUSTOMER_MAPPER)
    .single();
```

In this snippet:

- `id` is the primary key, so the database guarantees **at most one row**.
- `single()` adds the expectation that **one row must exist**.
- If ID 2 exists and the mapper returns a `Customer` object, `found` holds that object.
- If the ID does not exist, `single()` throws `EmptyResultDataAccessException`.

The two constraints "at most one" and "at least one" come from different places: the **primary key** protects uniqueness, while **`single()`** enforces the repository's read contract.

### 3.2. Missing Row Case

```java
try {
    Customer required = client.sql(
            "SELECT id, email, nickname FROM customers WHERE id = :id")
        .param("id", 999L)
        .query(CUSTOMER_MAPPER)
        .single();
} catch (EmptyResultDataAccessException ex) {
    // ID 999 has no row in the result set.
    // Decide whether to translate to a domain error / HTTP 404 depending on context.
}
```

This snippet is not standalone; it needs `org.springframework.dao.EmptyResultDataAccessException` imported and the repository's variables. Note: `EmptyResultDataAccessException` is a subtype of `IncorrectResultSizeDataAccessException`; if catching both, catch the more specific subtype first.

A repository method like `requireById(id)` or `getRequired(id)` is the right place for `single()`. If a user supplies an arbitrary ID and the object may never have existed, `optional()` usually reflects the business semantics better.

### 3.3. Two-Row Case

Suppose the query:

```sql
SELECT id, email, nickname
FROM customers
WHERE nickname IS NOT NULL;
```

finds two customers with a non-null nickname. Calling `single()` throws `IncorrectResultSizeDataAccessException` because expected size = 1, actual size = 2. This is **not** a SQL syntax error; it is a valid SQL result that fails the cardinality contract.

**Do not "fix" this arbitrarily with `LIMIT 1`.** If the business logic requires uniqueness, `LIMIT 1` merely hides duplicate rows and can cause the application to pick a non-deterministic result. Inspect the filter/database constraints, or use `list()` if multiple customers are genuinely valid.

### 3.4. A Single Result Must Be Non-Null Since Spring Framework 6.2

An easily overlooked detail: `single()` on `JdbcClient.MappedQuerySpec<T>` in **Spring Framework 6.2** enforces a required **non-null** result rule. If the SQL query returns **exactly one row**, but the mapper returns `null` (for example, reading a `nickname` column that is SQL NULL via `query(String.class)`), `single()` throws **`TypeMismatchDataAccessException`**.

Illustrative example:

```java
String nickname = client.sql(
        "SELECT nickname FROM customers WHERE id = :id")
    .param("id", 2L)
    .query(String.class)
    .single();
```

If customer ID 2 exists but `nickname` is SQL NULL, the mapped `String` result is `null`; in Spring 6.2, `single()` **must not return null** and raises an exception. This **differs from** `JdbcTemplate.queryForObject(...)`, some overloads of which can return `null` for SQL NULL on a valid single row.

Do not assume this exact behavior for every older Spring version: Spring Framework 6.2 enforces the originally intended non-null contract more strictly. Review legacy code relying on `single()` returning null when upgrading.

### 3.5. When Is single() a Great Fit?

- Querying by primary key or unique key when business logic requires the record to exist.
- Scalar aggregate `SELECT COUNT(*) ...` without `GROUP BY`: always produces **one row**, even when the count is 0.
- A SQL expression designed to definitely return a **non-NULL** scalar value with a clear invariant.
- A business workflow that has already verified the ID and treats a missing record as an error to report.

Even when using `single()`, data can still be modified by another transaction between steps. If update consistency is required, apply transactions/locking or optimistic locking accordingly. `single()` is a query-result check, **not a transaction locking mechanism**.

## 4. optional(): Allowed to Be Absent, Never Allowed to Be Two

### 4.1. Lookup by Potentially Absent ID

```java
Optional<Customer> maybe = client.sql(
        "SELECT id, email, nickname FROM customers WHERE id = :id")
    .param("id", 999L)
    .query(CUSTOMER_MAPPER)
    .optional();

if (maybe.isPresent()) {
    System.out.println(maybe.get().email());
} else {
    System.out.println("Not found");
}
```

This is a snippet assuming `client`, `Customer`, `CUSTOMER_MAPPER`, and importing `java.util.Optional`.

With 0 rows: `Optional.empty()`. With 1 row and a mapper returning a non-null `Customer`: `Optional.of(customer)`. With multiple rows: still throws `IncorrectResultSizeDataAccessException`. There is no valid path where `optional()` silently takes the first row of a multi-row result.

In a repository, you can return `Optional<Customer> findById(long id)` to the service. The service decides whether `empty` means 404, a skipped action, a prompt to register, etc. Do not throw an error too early if absence is an allowed state.

### 4.2. optional() and SQL NULL: A Crucial Nuance

Compare two distinct situations:

- **A:** SQL returns no rows.
- **B:** SQL returns exactly one row whose **`nickname` column = NULL**, and the scalar mapper returns Java `null`.

With scalar mapping via `query(String.class).optional()`, both can yield **`Optional.empty()`**. Reason: Java's `Optional` cannot hold `null`; a null value is represented as absence of a value. Therefore, **`Optional.empty()` in a scalar query does not always prove that SQL returned zero rows**.

Example:

```java
Optional<String> nickname = client.sql(
        "SELECT nickname FROM customers WHERE id = :id")
    .param("id", 2L)
    .query(String.class)
    .optional();
```

If ID 2 exists but `nickname` is SQL NULL, `nickname.isEmpty()` returns true. The exact same behavior occurs when ID 2 does not exist.

**How to preserve the row-vs-column boundary:** Map the entire row into a **non-null** object, and allow properties inside that object to be nullable:

```java
record Customer(long id, String email, String nickname) {}

Optional<Customer> customer = client.sql(
        "SELECT id, email, nickname FROM customers WHERE id = :id")
    .param("id", 2L)
    .query((rs, rowNum) -> new Customer(
            rs.getLong("id"),
            rs.getString("email"),
            rs.getString("nickname")))
    .optional();
```

When the row exists, the mapper always constructs a `Customer` object, even if `nickname() == null`; hence `customer.isPresent()` is true. If there truly is no row, `Optional.empty()` is returned. This is the right pattern when business logic needs to distinguish **the entity exists** from **an attribute of the entity is missing**.

If a nullable scalar is an important case, you can define a wrapper record `NullableValue<T>` or an appropriate domain record to represent an existing row with a null value, instead of relying on `Optional<String>`.

### 4.3. Optional Does Not Catch All Errors

`optional()` does not swallow errors:

- 2+ rows → `IncorrectResultSizeDataAccessException`.
- Invalid SQL, missing permissions, constraint violations, driver/connection failures → the corresponding `DataAccessException` subtype.
- Mapper throws an exception due to missing column or incompatible data type → still fails.

Therefore, never wrap the entire call in `catch (DataAccessException ex) { return Optional.empty(); }`. That destroys the distinction between missing data and database failure and can mask security or concurrency issues.

### 4.4. Optional in a Service

The repository just needs to express the data contract:

```java
public Optional<Customer> findByEmail(String email) {
    return client.sql("""
            SELECT id, email, nickname
            FROM customers
            WHERE email = :email
            """)
        .param("email", email)
        .query(CUSTOMER_MAPPER)
        .optional();
}
```

This is a snippet from a repository that has `client` and `CUSTOMER_MAPPER`; it is not a standalone file. For the "0 or 1 row" contract to be meaningful, there should be a `UNIQUE` constraint on email along with clear normalization/collation rules. If the database permits duplicate emails and the query returns two rows, `optional()` raises an error—that is an inconsistency signal that must be fixed.

Do not mechanically use `Optional` as a nullable field inside an entity; consider service/API boundaries, serialization, and the project's domain model.

## 5. list(): Result Set of 0..N Rows

### 5.1. Fetching a List and Handling Empty Results

```java
List<Customer> customers = client.sql("""
        SELECT id, email, nickname
        FROM customers
        ORDER BY id
        """)
    .query(CUSTOMER_MAPPER)
    .list();
```

- 0 rows → an empty `List`, not a missing-row exception.
- 1 row → list with 1 element.
- N rows → list with N elements.
- `list()` does not deduplicate records if SQL returns two identical rows or the mapper creates two equal objects.
- The list preserves actual SQL result order; for predictable ordering, add `ORDER BY`.

For search screens, multi-record read APIs, or an account's detail items, `list()` is the standard choice. When there are no results, returning an empty list is usually simpler than throwing not-found for an entire search operation.

### 5.2. list() Does Not Enforce an "Exactly One" Contract

You could use `list()` to look up by ID:

```java
List<Customer> rows = client.sql(
        "SELECT id, email, nickname FROM customers WHERE id = :id")
    .param("id", 2L)
    .query(CUSTOMER_MAPPER)
    .list();
```

However, if you immediately write `rows.get(0)`, an empty result throws Java's `IndexOutOfBoundsException`, failing to express the data error properly. If you write `rows.stream().findFirst()`, you may silently ignore a multi-row case that business logic should treat as an error.

When a use case requires 0/1 or exactly 1, use `optional()` or `single()` so the contract is visible directly in code.

### 5.3. Queries Returning Many Rows Still Need Bounds When Appropriate

`list()` returns a **pre-resolved/detached list** and can consume significant memory. It does not paginate automatically. Example:

```java
List<Customer> page = client.sql("""
        SELECT id, email, nickname
        FROM customers
        ORDER BY id
        LIMIT :size OFFSET :offset
        """)
    .param("size", 20)
    .param("offset", 40L)
    .query(CUSTOMER_MAPPER)
    .list();
```

This snippet depends on a SQL dialect supporting `LIMIT/OFFSET`. Size/offset must be validated and computed safely, and SQL must have explicit sorting. For very large tables, consider keyset pagination or streaming with proper resource closing. `JdbcClient.MappedQuerySpec.stream()` provides a stream that must be closed after use; `list()` is not a lazy stream.

### 5.4. A RowMapper May Return Null: list Does Not Enforce Non-Null

`list()` returns whatever values the mapper produces. If a `RowMapper` intentionally returns null for certain rows (e.g., reading a nullable column), the list may contain null elements depending on the mapping API. That is very different from a list of non-null entities that have nullable fields.

Design your mapper so the return contract is clear:

- Querying **entities** → produce a non-null object for every row.
- Querying **nullable scalars** → consider a model representing SQL NULL, a wrapper record, or an appropriate API.
- Querying **non-null scalars** → ensure the SQL column/expression and mapping are non-null.

Do not assume `list().size()` equals the number of distinct business entities when a JOIN introduces duplicates; fix the SQL with `DISTINCT`/`EXISTS`/aggregation according to the use case.

## 6. How single(), optional(), list() Differ from Similarly Named APIs

### 6.1. Do Not Confuse JdbcClient with JdbcTemplate

| Purpose | Spring `JdbcClient` | Spring `JdbcTemplate` |
| --- | --- | --- |
| Query multiple rows | `.query(mapper).list()` | `.query(sql, mapper, args...)` |
| Query exactly one mapped object | `.query(mapper).single()` | `.queryForObject(sql, mapper, args...)` |
| Query 0/1 mapped object | `.query(mapper).optional()` | Can `query` 0/1 and wrap in `Optional`, or catch specific exceptions per contract |
| Single-column scalar | `.query(Long.class).single()` | `.queryForObject(sql, Long.class, args...)` |
| Write data | `.sql(sql).param(...).update()` | `.update(sql, args...)` |

`JdbcClient` is a facade for calling core JDBC APIs in a fluent chain. It **does not make SQL return different results**; the difference lies in the contract for resolving and representing row counts.

Important note on nullable scalars: `JdbcTemplate.queryForObject(...)` can return Java null when the SQL column is NULL, whereas `JdbcClient.query(Class<T>).single()` in Spring Framework 6.2 requires a **non-null result**. Read the exact API contract rather than inferring solely from the word "single".

### 6.2. Do Not Confuse with Spring Data Repositories

`CrudRepository.findById(id)` and `Optional` in Spring Data JDBC/JPA are different repository APIs with different mapping and persistence lifecycles. This lesson covers **Spring Framework `org.springframework.jdbc.core.simple.JdbcClient`**, not derived methods on `JpaRepository`/`CrudRepository`.

Sharing the word "optional" does not guarantee identical generated SQL, null mapping, or transaction management.

### 6.3. Other JdbcClient Options

Beyond the trio covered here, `MappedQuerySpec` also provides `set()` (an ordered set per contract) and `stream()` (a lazily resolved stream requiring resource closing). For mapper-less `query()`, `ResultQuerySpec` provides methods like `listOfRows()`, `singleRow()`, `singleColumn()`, `singleValue()`, or `optionalValue()` (names/capabilities may vary by version). These are not interchangeable with `MappedQuerySpec<T>.list()/single()/optional()` and have different return types.

When reading standard entities or scalars, `query(RowMapper<T>)` or `query(Class<T>)` followed by the trio above is the most direct path to learn.

## 7. Important Edge Cases

### 7.1. COUNT(*) Returns One Row Even When Nothing Matches

```java
Long count = client.sql("""
        SELECT COUNT(*)
        FROM customers
        WHERE id > :id
        """)
    .param("id", 999L)
    .query(Long.class)
    .single();
```

With no customer having id greater than 999 → `COUNT(*)` (without `GROUP BY`) returns **one row** with value 0, so `single()` returns 0. It does not throw `EmptyResultDataAccessException`.

By contrast, `SELECT email WHERE id = 999` returns **0 rows**, so `single()` throws and `optional()` returns empty.

With `COUNT(*) ... GROUP BY status`, there can be **0 or many groups**; do not apply the "always one row" rule to every aggregate query. Choose `list()` when reading multiple groups.

### 7.2. LEFT JOIN Can Multiply Row Counts

Suppose a customer has three orders:

```sql
SELECT c.id, c.email
FROM customers c
LEFT JOIN orders o ON o.customer_id = c.id
WHERE c.id = :id;
```

Even though `c.id` is a primary key, a 1-to-N JOIN can return **three rows** for the same customer. If you call `single()`/`optional()`, Spring throws a result-size error. Do not blindly fix this by taking the first row; consider removing the JOIN if order data isn't needed, using `EXISTS`, separate queries, or appropriate `DISTINCT`/aggregation.

This illustrates that **SQL result cardinality** differs from uniqueness of the root entity. Design the query so that one row corresponds to one intended business result.

### 7.3. Do Not Use LIMIT 1 to Hide Duplicate Data

```sql
SELECT id, email, nickname
FROM customers
WHERE email = :email
LIMIT 1;
```

The query above may cap results at one row, but if emails are duplicated, the underlying bug still exists. If business rules require only one customer per email, add a `UNIQUE` constraint/index aligned with email normalization rules and test the data.

If the requirement is "get the latest record", `ORDER BY created_at DESC, id DESC LIMIT 1` can be a **valid** contract because the use case genuinely asks for one record. When the dataset may be empty, `optional()` expresses it better; when it must exist, `single()` fits. The key is **intentional `LIMIT 1`**, not masking accidental duplicates.

### 7.4. Distinguishing Missing, SQL NULL, and Database Errors

There are three very different state groups:

1. **No row**: `optional()` → empty; `single()` → `EmptyResultDataAccessException`.
2. **Row exists, nullable column is NULL**: mapper returns an object with a null field → row still exists; scalar mapper returns null → `optional()` may be empty, Spring 6.2 `single()` throws `TypeMismatchDataAccessException`.
3. **SQL cannot execute**: syntax error, connection failure, missing permission, column mapping error... → corresponding `DataAccessException` subtype or exception; must never be silently converted into "no row".

This is why repository APIs should pick return types matching the nature of the data, and code should never catch all `DataAccessException`s to return `Optional.empty()`.

## 8. Runnable Example: Java 17, Spring JdbcClient 6.2, and H2

The program below uses an H2 database with **three customers**, one of whom has a SQL NULL nickname. It tests:

- `list()` with 0 or 3 rows;
- `single()` with 1, 0, >1 rows;
- `optional()` with 1, 0, >1 rows;
- `query(String.class).optional()` when a column is SQL NULL;
- `query(String.class).single()` when a column is SQL NULL in Spring 6.2;
- `COUNT(*)` returning 0 while still producing one result row.

The program runs standalone with **Java 17+**, Spring Framework **6.2.12**, H2 **2.3.232**, and Gradle. No Spring Boot or external database server is needed.

### 8.1. Project Structure

```text
jdbc-client-cardinality/
├── build.gradle
└── src/main/java/example/JdbcClientCardinalityDemo.java
```

### 8.2. Contents of build.gradle

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-jdbc:6.2.12'
    runtimeOnly 'com.h2database:h2:2.3.232'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'example.JdbcClientCardinalityDemo'
}
```

`spring-jdbc` includes `JdbcClient`, `JdbcTemplate`, and `DriverManagerDataSource`; Gradle pulls the required transitive dependencies automatically. H2 runs in memory and is loaded via the JDBC driver at runtime.

### 8.3. Complete Java Source

Create `src/main/java/example/JdbcClientCardinalityDemo.java`:

```java
package example;

import java.util.List;
import java.util.Optional;

import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.dao.IncorrectResultSizeDataAccessException;
import org.springframework.dao.TypeMismatchDataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

public class JdbcClientCardinalityDemo {

    record Customer(long id, String email, String nickname) {}

    private static final String BASE_SELECT =
            "SELECT id, email, nickname FROM customers";

    private static final RowMapper<Customer> CUSTOMER_MAPPER =
            (rs, rowNum) -> new Customer(
                    rs.getLong("id"),
                    rs.getString("email"),
                    rs.getString("nickname"));

    public static void main(String[] args) {
        DriverManagerDataSource ds = new DriverManagerDataSource();
        ds.setDriverClassName("org.h2.Driver");
        ds.setUrl("jdbc:h2:mem:cardinality_demo;DB_CLOSE_DELAY=-1");
        ds.setUsername("sa");
        ds.setPassword("");

        JdbcTemplate setup = new JdbcTemplate(ds);
        JdbcClient client = JdbcClient.create(ds);

        setup.execute("""
                CREATE TABLE customers (
                    id BIGINT PRIMARY KEY,
                    email VARCHAR(100) NOT NULL UNIQUE,
                    nickname VARCHAR(100)
                )
                """);

        // Static SQL creating fixtures: not SQL concatenated from user input.
        setup.execute("""
                INSERT INTO customers (id, email, nickname) VALUES
                    (1, 'ana@example.test', 'Ann'),
                    (2, 'bao@example.test', NULL),
                    (3, 'chi@example.test', 'Chi')
                """);

        // list(): query returning three rows.
        List<Customer> all = client.sql(BASE_SELECT + " ORDER BY id")
                .query(CUSTOMER_MAPPER)
                .list();
        System.out.println("listSize=" + all.size());
        System.out.println(
                "listIds=" + all.stream().map(Customer::id).toList());

        // list(): zero rows still returns an empty list.
        List<Customer> noRows = client.sql(
                BASE_SELECT + " WHERE id > :id ORDER BY id")
                .param("id", 99L)
                .query(CUSTOMER_MAPPER)
                .list();
        System.out.println("listEmpty=" + noRows.isEmpty());

        // single(): exactly one row, mapper constructs a non-null object.
        Customer required = client.sql(
                BASE_SELECT + " WHERE id = :id")
                .param("id", 2L)
                .query(CUSTOMER_MAPPER)
                .single();
        System.out.println("single=" + required);

        // optional(): 0 rows vs. 1 row.
        Optional<Customer> present = client.sql(
                BASE_SELECT + " WHERE id = :id")
                .param("id", 1L)
                .query(CUSTOMER_MAPPER)
                .optional();
        System.out.println(
                "optionalPresent=" +
                present.map(Customer::email).orElse("<none>"));

        Optional<Customer> missing = client.sql(
                BASE_SELECT + " WHERE id = :id")
                .param("id", 99L)
                .query(CUSTOMER_MAPPER)
                .optional();
        System.out.println("optionalMissing=" + missing.isEmpty());

        // single(): zero rows is a cardinality error.
        try {
            client.sql(BASE_SELECT + " WHERE id = :id")
                    .param("id", 99L)
                    .query(CUSTOMER_MAPPER)
                    .single();
        } catch (EmptyResultDataAccessException ex) {
            System.out.println(
                    "singleMissing=EmptyResultDataAccessException");
        }

        // Both optional() and single() reject 2+ row results.
        try {
            client.sql(BASE_SELECT + " WHERE id >= :id ORDER BY id")
                    .param("id", 2L)
                    .query(CUSTOMER_MAPPER)
                    .optional();
        } catch (IncorrectResultSizeDataAccessException ex) {
            System.out.println(
                    "optionalMultiple=IncorrectResultSizeDataAccessException");
        }

        try {
            client.sql(BASE_SELECT + " WHERE id >= :id ORDER BY id")
                    .param("id", 2L)
                    .query(CUSTOMER_MAPPER)
                    .single();
        } catch (IncorrectResultSizeDataAccessException ex) {
            System.out.println(
                    "singleMultiple=IncorrectResultSizeDataAccessException");
        }

        // One row with SQL NULL nickname: scalar optional is empty.
        Optional<String> nullableNickname = client.sql(
                "SELECT nickname FROM customers WHERE id = :id")
                .param("id", 2L)
                .query(String.class)
                .optional();
        System.out.println(
                "nullScalarOptionalEmpty=" + nullableNickname.isEmpty());

        // In Spring 6.2, scalar single() rejects null.
        try {
            client.sql(
                    "SELECT nickname FROM customers WHERE id = :id")
                    .param("id", 2L)
                    .query(String.class)
                    .single();
        } catch (TypeMismatchDataAccessException ex) {
            System.out.println(
                    "nullScalarSingle=TypeMismatchDataAccessException");
        }

        // COUNT(*) without GROUP BY still returns one row containing 0.
        Long countZero = client.sql("""
                SELECT COUNT(*) FROM customers WHERE id > :id
                """)
                .param("id", 99L)
                .query(Long.class)
                .single();
        System.out.println("countZero=" + countZero);
    }
}
```

The program intentionally uses `JdbcTemplate` for DDL/fixtures and then `JdbcClient` to demonstrate query results; both connect to the same H2 `DataSource`.

`Customer` is a Java record; `nickname` can be null while `Customer` **remains a non-null object**. `CUSTOMER_MAPPER` creates one `Customer` for each `ResultSet` row. Do not call `rs.next()` inside the mapper, because Spring already positions the cursor at the current row before invoking `RowMapper`.

`DriverManagerDataSource` is convenient for demos, not a production connection pool. `DB_CLOSE_DELAY=-1` keeps the H2 in-memory database alive across multiple connections in the same JVM; data does not persist after the process exits.

### 8.4. Run Command and Output

From the directory containing `build.gradle`, run:

```bash
gradle run
```

If using Gradle Wrapper, run `./gradlew run` (Linux/macOS) or `gradlew.bat run` (Windows). Gradle may print extra build logs; the lines produced by the program's **`System.out.println`**, in order, are:

```text
listSize=3
listIds=[1, 2, 3]
listEmpty=true
single=Customer[id=2, email=bao@example.test, nickname=null]
optionalPresent=ana@example.test
optionalMissing=true
singleMissing=EmptyResultDataAccessException
optionalMultiple=IncorrectResultSizeDataAccessException
singleMultiple=IncorrectResultSizeDataAccessException
nullScalarOptionalEmpty=true
nullScalarSingle=TypeMismatchDataAccessException
countZero=0
```

Step-by-step interpretation:

1. Three inserted rows have IDs 1, 2, 3. `ORDER BY id` guarantees `listIds=[1, 2, 3]`.
2. `WHERE id > 99` matches nothing; `list()` still returns an empty list.
3. `single()` with `id=2` returns a `Customer` object containing a null nickname. The **non-null mapped object** contract is still satisfied.
4. `optional()` with `id=1` contains the object with Ana's email; with `id=99` it returns empty.
5. `single()` with `id=99` throws `EmptyResultDataAccessException`.
6. `WHERE id >= 2` matches two rows 2 and 3; both `optional()` and `single()` reject it, throwing `IncorrectResultSizeDataAccessException`.
7. `query(String.class)` reads the **single nickname column** of ID 2, which is SQL NULL. `optional()` returns empty so `nullScalarOptionalEmpty=true`.
8. With the same scalar NULL, `single()` in Spring 6.2 throws `TypeMismatchDataAccessException`.
9. `COUNT(*)` with no match returns one row with 0, so `single()` receives `Long 0` normally.

**Important verification:** Do not interpret `nullScalarOptionalEmpty=true` as "customer ID 2 does not exist". ID 2 exists; only their nickname attribute is NULL.

### 8.5. Exercises Modifying the Program

- Change `id=99` in the `optional()` call to `id=3`; predict the returned email.
- Change `WHERE id >= 2` to `WHERE id > 2`; then only row ID 3 matches, so both `single()` and `optional()` succeed.
- Change the scalar query from `nickname` to `email` for ID 2; `single()` will return `bao@example.test` because the email column is `NOT NULL`.
- Insert another customer with a NULL nickname, then call `.query(CUSTOMER_MAPPER).list()`; the list gains a non-null object with a nullable field.
- Write a `GROUP BY nickname` query and observe whether 0, 1, or multiple groups are returned; choose `list()` if you want to read all groups.

No `@Bean` configuration changes are needed since this demo creates the client manually. In a production Spring application, declare `JdbcClient` via configuration to inject it into repositories.

## 9. Designing Repositories with Clear Contracts

### 9.1. APIs Should State Clearly "Is Existence Required?"

A clean repository:

```java
public final class CustomerRepository {
    private final JdbcClient jdbc;

    public CustomerRepository(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    public Customer requireById(long id) {
        return jdbc.sql("""
                SELECT id, email, nickname
                FROM customers
                WHERE id = :id
                """)
            .param("id", id)
            .query(CUSTOMER_MAPPER)
            .single();
    }

    public Optional<Customer> findById(long id) {
        return jdbc.sql("""
                SELECT id, email, nickname
                FROM customers
                WHERE id = :id
                """)
            .param("id", id)
            .query(CUSTOMER_MAPPER)
            .optional();
    }

    public List<Customer> findByEmailPrefix(String prefix) {
        return jdbc.sql("""
                SELECT id, email, nickname
                FROM customers
                WHERE email LIKE :pattern
                ORDER BY id
                """)
            .param("pattern", prefix + "%")
            .query(CUSTOMER_MAPPER)
            .list();
    }
}
```

This is a **design-oriented snippet**, not a standalone compilable Java file since `Customer`/`CUSTOMER_MAPPER` and imports are defined elsewhere. With `LIKE`, binding prevents SQL injection at the value position but does not automatically escape wildcard characters `%` and `_` inside `prefix`; if searching for a **literal** prefix, escape the pattern according to your DBMS/`ESCAPE` clause.

Here:

- `requireById` clearly states that a missing record is an error.
- `findById` clearly states that a missing record is a normal state.
- `findByEmailPrefix` clearly states that multiple records may be returned; add `ORDER BY` and pagination for large datasets.

Note that `Optional<Customer>` does not prevent data corruption—database uniqueness constraints are the foundational safeguard.

### 9.2. Exception Policies Belong in the Business Layer

The service layer can translate `EmptyResultDataAccessException` into `CustomerNotFound` or HTTP 404 depending on context. If `CustomerRepository.findById` returns `Optional.empty()`, the service can call `orElseThrow(...)` when a specific use case requires existence.

Do not lump every behavior into one method and make controllers guess status from `null`. Use intentional method names, return types, and exceptions without losing DB error signals.

### 9.3. Correct Cardinality Still Requires Proper Authorization

Example with multiple tenants:

```java
Optional<Customer> candidate = jdbc.sql("""
        SELECT id, email, nickname
        FROM customers
        WHERE tenant_id = :tenantId AND id = :id
        """)
    .param("tenantId", verifiedTenantId)
    .param("id", customerId)
    .query(CUSTOMER_MAPPER)
    .optional();
```

This snippet assumes `verifiedTenantId` was established by the authorization layer and the table has a `tenant_id` column. The system must verify the caller is permitted to access that tenant; `optional()` only checks **the row count after filtering**, not authorization. Never let `COUNT(*)` or error logs leak information about another tenant.

## 10. Common Mistakes and How to Fix Them

| Symptom | Possible cause/meaning | Resolution |
| --- | --- | --- |
| `single()` finds no row | 0 results, throws `EmptyResultDataAccessException` | Translate to domain not-found or switch to `optional()` if absence is valid |
| `optional()` throws even though "optional" | SQL returns 2 or more rows | Check WHERE/JOIN/UNIQUE; never take the first row unconditionally |
| `single()` throws `IncorrectResultSizeDataAccessException` | SQL returns 2+ rows | Fix query/invariant, or choose `list()` when multiple are valid |
| `single()` throws `TypeMismatchDataAccessException` on scalar | One row returned SQL NULL in Spring Framework 6.2 | Use a wrapper row object or revise the nullable contract |
| Scalar `optional()` is empty even though row exists | Single-column nullable mapper returned null | Use a non-null row wrapper to separate row vs. field |
| `list()` returns empty | No SQL row matched the criteria | Return empty collection or handle in UI |
| `list()` returns too many rows | Query lacks LIMIT or sufficiently narrow filter | Paginate/stream; avoid loading everything into memory |
| `COUNT(*)` is 0 yet `single()` does not fail | Aggregate without GROUP BY still returns one row | This is expected behavior |
| `single()` fails with JOIN despite unique PK | 1-to-N JOIN multiplies rows | Design query to return one entity; use EXISTS/separate queries if needed |
| Concatenating user input into SQL instead of binding | SQL injection or escaping bugs | Use `:name`/`?` and `param(...)` |
| Query lacks ORDER BY and list order shifts | DB guarantees no order without ORDER BY | Add explicit sort, with a unique tiebreaker when paginating |
| Catching all `DataAccessException` and returning empty | Hides DB/driver/query/permission errors | Only handle business-meaningful error cases |
| Equating JdbcClient with JPA repositories | Two frameworks at different abstraction layers | Read the exact API contract and source code |
| H2 tests pass while production SQL fails | Different SQL dialect/driver/schema | Run integration tests on the production DBMS |

## 11. Testing a Cardinality Contract

For repositories returning `single()` or `optional()`, write tests covering at least three data setups:

1. **0 rows**: `single()` must throw the missing exception; `optional()` returns empty; `list()` is empty.
2. **1 row**: all three return the corresponding result, given a non-null mapper.
3. **2 rows**: `single()`/`optional()` must error; `list()` returns two elements.

Then add **SQL NULL** tests:

- A record with a null nullable field mapped to a **non-null** entity/record; `optional()` must still be present.
- A nullable scalar query returning one `null`; `optional()` is empty, `single()` (Spring 6.2) fails on null result.
- A `COUNT(*)` query without `GROUP BY` matching 0 records; `single()` equals 0.

Also check **JOINs** and **unique constraints** for critical endpoints: if a query can multiply rows, fix it in SQL or adjust the DTO design right away.

Tests should not depend on concrete driver-specific `SQLException` subclass names across all JDBC drivers; assert the semantically appropriate Spring exception types and test with the exact library versions used in your project.

## 12. Self-Check Questions

1. A query returns 0 rows. What do `list()`, `optional()`, and `single()` return respectively?
2. With exactly one row mapped to a `Customer` object, what types do the three methods return?
3. Does `optional()` "take the first row" when SQL returns two rows?
4. Why does `single()` fit `requireById` while `optional()` fits `findById`?
5. How can a `LEFT JOIN` from customers to orders cause `single()` to fail even though `customers.id` is the PK?
6. When is `LIMIT 1` a valid contract and when does it hide duplicate bugs?
7. Why does `SELECT COUNT(*)` without `GROUP BY` and with no matching rows not cause `single()` to report empty?
8. In Spring 6.2, if SQL returns one row but `RowMapper` returns null, what does `single()` do?
9. If the `nickname` column is NULL while the `Customer` record is still constructed, is `Optional<Customer>` present?
10. Why does an empty `query(String.class).optional()` **not prove** the query returned zero rows?
11. Does `list()` automatically paginate, deduplicate, or guarantee ordering?
12. Why should you not catch all `DataAccessException`s to return `Optional.empty()`?

**Takeaway:** With `JdbcClient`, **`list()` = 0..N**, **`optional()` = 0..1**, and **`single()` = exactly 1 non-null result** in Spring Framework 6.2. Cardinality is a use-case contract; SQL data, mappers, and return types must all uphold that contract. In particular, always distinguish **no row** from **a row with a SQL NULL column**.

### Official Documentation

- Spring Framework 6.2 — [JDBC Core: Unified JdbcClient Operations](https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/core.html).
- Spring Framework 6.2 — [JdbcClient API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/simple/JdbcClient.html).
- Spring Framework 6.2 — [JdbcClient.MappedQuerySpec API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/simple/JdbcClient.MappedQuerySpec.html).
- Spring Framework 6.2 — [DataAccessUtils API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/dao/support/DataAccessUtils.html).
- Java SE 17 — [Optional API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Optional.html).
