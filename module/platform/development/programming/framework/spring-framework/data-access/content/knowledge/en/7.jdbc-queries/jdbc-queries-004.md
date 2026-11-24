# Multiple Rows When Expecting One and IncorrectResultSizeDataAccessException

In Spring JDBC, a query can succeed at the database level yet **its result still violates the contract required by the application**. A classic case: code calls `JdbcTemplate.queryForObject(...)` to retrieve **exactly one row**, but the `WHERE` condition actually matches **two or more rows**. Spring then throws `IncorrectResultSizeDataAccessException`. This signals that **the returned row count does not match the expected row count**—it does not prove invalid SQL syntax or a dropped database connection.

This lesson focuses on cardinality (row count) mechanics, reading and handling the exception, real-world causes such as duplicate data or row-multiplying `JOIN`s, and choosing among `queryForObject`, `query`, optional lookups, and unique constraints. All examples use Spring JDBC; `@Transactional` appears only when explaining error-handling consequences inside transactions.

## 1. Contract of an "Exactly One Row" Query

Distinguish three common business requirements:

- **Exactly one:** Look up an account by a primary key known to exist; valid row count is **1**.
- **Zero or one:** Look up an optional profile by a unique identifier; valid row count is **0 or 1**.
- **Zero or many:** Fetch all orders of a customer; valid row count is **0, 1, 2, ...**.

`queryForObject` expresses **exactly one**, not "pick the first row if available". Review this table when querying with a standard `queryForObject` overload:

| Rows returned by SQL | Behavior of `queryForObject` | Meaning |
| --- | --- | --- |
| 0 | `EmptyResultDataAccessException` | Expected 1 but got 0; subclass of `IncorrectResultSizeDataAccessException`. |
| 1 | Returns the mapped object (may be `null` if row content maps to null) | Row count matches; data type and column count still depend on the overload used. |
| 2 | `IncorrectResultSizeDataAccessException` | Expected 1 but got 2. |
| 3 or more | `IncorrectResultSizeDataAccessException` | Expected 1 but got more than 1. |

The key point is **rows are counted before deciding to return an object**. Even if two rows contain identical names or values, they are still **two rows**. Even if `RowMapper` produces two objects equal by `equals()`, the "one row" condition still fails.

Example:

```sql
SELECT id, email
FROM customer
WHERE email = 'anna@example.test';
```

If two records share the same email, the SQL statement is still a valid query. `queryForObject` will not silently pick an arbitrary row; it raises a cardinality error so the caller addresses the expectation mismatch.

## 2. What Does the Exception Indicate?

Main class:

```java
org.springframework.dao.IncorrectResultSizeDataAccessException
```

This is an unchecked `DataAccessException` (under `RuntimeException`). Notable properties:

- `getExpectedSize()`: the number of results expected by the operation, typically `1`.
- `getActualSize()`: the actual number of results if known. In some construction paths it may be `-1` when the actual count is unknown; do not assume this value is always positive.
- Error message typically resembles `Incorrect result size: expected 1, actual 2`; exact formatting may vary by API/version.

Important subclass:

```java
org.springframework.dao.EmptyResultDataAccessException
```

`EmptyResultDataAccessException` **extends `IncorrectResultSizeDataAccessException`** and normally represents expecting at least one row but receiving **0**. Therefore, if you want to distinguish "not found" from "non-unique data", catch the specific exception **before** the parent exception:

```java
// Integration example: jdbc is a configured JdbcTemplate.
try {
    String status = jdbc.queryForObject(
        "SELECT status FROM customer WHERE id = ?",
        String.class,
        customerId
    );
    System.out.println(status);
} catch (EmptyResultDataAccessException noRow) {
    // Not found.
} catch (IncorrectResultSizeDataAccessException tooManyRows) {
    // Multiple rows when expecting only one.
}
```

The snippet above is not a standalone runnable Java file; it requires imports, `jdbc`, `customerId`, and a database. If you catch the parent class first, the subsequent `EmptyResultDataAccessException` branch becomes unreachable (and catching a subclass after a superclass is invalid in Java).

### Is This a SQL/Driver Error?

Not necessarily. Often the database returns results **exactly matching the SQL**, and Spring detects that the result violates the API contract. For example, `WHERE department_id = 10` may be valid and intentionally return 20 employees; the bug is that the code called `queryForObject` instead of a list-reading API.

Conversely, if the domain asserts email must be unique yet the query returns two rows, the exception signals **a broken data invariant or faulty query**. Do not convert all such cases into "not found" or "take the first record".

## 3. How Does `queryForObject` Work in Spring JDBC?

Common overloads:

```java
// One row, one column, mapped to a simple type.
String name = jdbc.queryForObject(
    "SELECT name FROM customer WHERE id = ?",
    String.class,
    id
);

// One row, multiple columns, using RowMapper.
Customer customer = jdbc.queryForObject(
    "SELECT id, name FROM customer WHERE id = ?",
    (rs, rowNum) -> new Customer(
        rs.getLong("id"), rs.getString("name")
    ),
    id
);
```

These are integration snippets; `Customer` is an application type, while `jdbc` and `id` must be declared. A runnable model appears in the complete example below.

In `queryForObject(sql, Class<T>, args...)`, Spring maps **a single column value** to the requested type. In `queryForObject(sql, RowMapper<T>, args...)`, `RowMapper` builds an object from **one row that may have multiple columns**.

Both enforce the **one-row** expectation. `RowMapper` does not mean "automatically collapse multiple rows into one object"; it is invoked for rows returned by JDBC, and then Spring checks result size.

Additionally, `JdbcTemplate.queryForMap(...)` also enforces the **one-row** expectation, even though the returned object is a `Map<String, Object>` mapping that row's columns. Do not confuse "multiple columns" with "multiple rows".

If you want **multiple rows**, use `query(...)` with a `RowMapper`:

```java
List<Customer> customers = jdbc.query(
    "SELECT id, name FROM customer WHERE department_id = ? ORDER BY id",
    (rs, rowNum) -> new Customer(
        rs.getLong("id"), rs.getString("name")
    ),
    departmentId
);
```

`query` with `RowMapper` returns `List<Customer>` and accepts empty, single-row, or multi-row results. Collecting into a list carries memory cost proportional to row count; for large datasets use pagination or an appropriate sequential processing strategy.

## 4. Distinguishing **Row-Count** Errors, **Column-Count** Errors, and SQL NULL

These are three independent concerns.

### Wrong Row Count: `IncorrectResultSizeDataAccessException`

```sql
SELECT name
FROM customer
WHERE email = 'anna@example.test';
```

If 2 rows exist, `queryForObject` reports a **row-count** error even though only one column is selected.

### Exactly One Row, Multiple Columns Selected with `String.class`

```java
// Query returns 1 row with 2 columns; single-type overload needs 1 column.
String wrong = jdbc.queryForObject(
    "SELECT id, name FROM customer WHERE id = ?",
    String.class,
    1L
);
```

When there is one row with multiple columns, the single-value overload can throw `IncorrectResultSetColumnCountException`. To receive a multi-property object, use `RowMapper<Customer>` instead of `String.class`.

### One Row with SQL NULL

```sql
SELECT MAX(score)
FROM exam_result
WHERE student_id = -1;
```

With a `MAX` aggregate and no `GROUP BY`, the DB usually returns **one row** containing `NULL` when no data matches. `queryForObject(..., Integer.class)` may then return `null` **without throwing** `EmptyResultDataAccessException`: cardinality is **1**, value is **NULL**.

Similarly, a `RowMapper` can explicitly return null for a row. Thus a `null` result does not always mean "no row". When writing data-access code, specify clearly whether you are checking **row existence** or **column value**.

## 5. Why Does a Seemingly Unique Query Return Multiple Rows?

### 5.1. Search Condition Is Not a Unique Key

If `customer.email` has no unique constraint, two records can share an email:

| id | email | plan |
| ---: | --- | --- |
| 1 | anna@example.test | gold |
| 2 | anna@example.test | silver |
| 3 | bob@example.test | bronze |

`WHERE id = ?` on a primary key returns at most one row. `WHERE email = ?` without a unique constraint can return multiple rows. Check the **schema**, not just the code author's intent.

Likewise, searching by `first_name`, `status`, `department_id`, date ranges, `LIKE`, or non-unique fields is normally a **set-returning** operation.

### 5.2. `JOIN` Multiplies Rows (Join Fan-Out)

Even when the parent table has a single unique record, joining a child table with multiple records multiplies **result rows**:

```sql
-- customer.id is PRIMARY KEY; customer_note may have multiple notes per customer.
SELECT c.id, c.name
FROM customer c
JOIN customer_note n ON n.customer_id = c.id
WHERE c.id = 3;
```

If customer 3 has two notes, the SQL above returns **two rows with the same c.id and c.name**. That does not necessarily mean two duplicate customers exist in the parent table; each result row corresponds to a joined pair.

If the goal is only to check whether the customer has any notes, use `EXISTS` instead of a row-multiplying join:

```sql
SELECT c.id, c.name
FROM customer c
WHERE c.id = 3
  AND EXISTS (
      SELECT 1
      FROM customer_note n
      WHERE n.customer_id = c.id
  );
```

If you need all notes, use a list-returning API and map the relationship explicitly. If you need the note count, use `COUNT`/`GROUP BY` or a subquery per business semantics. Do not blindly add `DISTINCT` to "suppress the error", because deduplicating the projection can hide true relationships.

### 5.3. Missing or Incorrect Filter Conditions

A query assumed to be unique might omit `tenant_id`, `version`, `locale`, `deleted_at IS NULL`, or part of a composite key. For instance, `external_id` may only be unique **per tenant**, so `WHERE external_id = ?` is insufficient; you need `WHERE tenant_id = ? AND external_id = ?` backed by the right unique constraint.

You must also consider data normalization: email case sensitivity, whitespace, collation, and soft-delete handling. A condition like `LOWER(email) = LOWER(?)` does not prove the DB has a unique constraint on that same expression.

### 5.4. `GROUP BY` Queries Return Multiple Groups

```sql
SELECT department_id, COUNT(*)
FROM employee
GROUP BY department_id;
```

The SQL above returns one row **per department**, not one grand-total row. If you truly want a single overall total, write `SELECT COUNT(*) FROM employee` (without `GROUP BY`). Conversely, if you need per-group statistics, use `query` to retrieve a list.

## 6. Why Is `LIMIT 1` Usually the Wrong Fix?

A common knee-jerk reaction:

```sql
SELECT id, email, plan
FROM customer
WHERE email = ?
LIMIT 1;
```

This forces the result to at most one row, yet if email ought to be unique, it **hides corrupted data**. Without `ORDER BY`, there is no stable guarantee of which row is "first"; the chosen row can change with indexes, execution plans, DB versions, or data mutations.

Even adding `ORDER BY id ASC LIMIT 1` merely turns "smallest-id record" into the selection rule—it **does not enforce the uniqueness invariant**.

`LIMIT 1` (or `FETCH FIRST 1 ROW ONLY` depending on dialect) is valid when the business requirement is genuinely to **pick one record**: for example, a customer's latest order, newest message, or most recent session. In that case, express deterministic ordering with a unique tie-breaker:

```sql
SELECT id, created_at, status
FROM orders
WHERE customer_id = ?
ORDER BY created_at DESC, id DESC
LIMIT 1;
```

This is a **zero or one after limiting** query—it does not guarantee an order exists. If none exists, `queryForObject` still throws `EmptyResultDataAccessException`. If the ordering lacks a unique tie-breaker, two records with identical timestamps can be chosen non-deterministically.

When investigating duplicate data without loading millions of rows into Java, you can query at most **two rows** to detect "more than one":

```sql
SELECT id
FROM customer
WHERE email = ?
ORDER BY id
LIMIT 2;
```

If `queryForObject` runs on this result and reports `actualSize=2`, you know for sure **there are at least two rows**, though not the true original total. This check does not replace a unique constraint.

## 7. Complete Java 17+ Example: Three Result Sizes and a JOIN Bug

This example uses Spring JDBC and in-memory H2, **without Spring Boot or a server**. Using `JdbcTemplate`, it creates sample tables and verifies:

1. One row → `queryForObject` returns the result.
2. Zero rows → `EmptyResultDataAccessException`.
3. Two rows → `IncorrectResultSizeDataAccessException`.
4. Valid multiple rows → `query` returns a list.
5. `COUNT(*)` without `GROUP BY` still returns one row with count 0.
6. One-to-many `JOIN` causes a lookup by customer primary key to return two rows.
7. Query by parent primary key without joining returns exactly one object.

### Create the Maven Project

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>learning</groupId>
    <artifactId>jdbc-one-row-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.1.14</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.2.224</version>
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
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/OneRowDemo.java`:

```java
import java.util.List;

import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.dao.IncorrectResultSizeDataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

public class OneRowDemo {
    private record Customer(long id, String email, String plan) {}

    public static void main(String[] args) {
        DriverManagerDataSource source = new DriverManagerDataSource(
                "jdbc:h2:mem:one_row_demo;DB_CLOSE_DELAY=-1", "sa", "");
        JdbcTemplate jdbc = new JdbcTemplate(source);

        jdbc.execute(
            "CREATE TABLE customer (" +
            "id BIGINT PRIMARY KEY, " +
            "email VARCHAR(100) NOT NULL, " +
            "plan VARCHAR(20) NOT NULL)");
        jdbc.execute(
            "CREATE TABLE customer_note (" +
            "note_id INT PRIMARY KEY, " +
            "customer_id BIGINT NOT NULL, " +
            "body VARCHAR(100) NOT NULL)");

        jdbc.update(
            "INSERT INTO customer (id, email, plan) VALUES (?, ?, ?)",
            1L, "anna@example.test", "gold");
        jdbc.update(
            "INSERT INTO customer (id, email, plan) VALUES (?, ?, ?)",
            2L, "anna@example.test", "silver");
        jdbc.update(
            "INSERT INTO customer (id, email, plan) VALUES (?, ?, ?)",
            3L, "bob@example.test", "bronze");

        jdbc.update(
            "INSERT INTO customer_note (note_id, customer_id, body) " +
            "VALUES (?, ?, ?)", 10, 3L, "note A");
        jdbc.update(
            "INSERT INTO customer_note (note_id, customer_id, body) " +
            "VALUES (?, ?, ?)", 11, 3L, "note B");

        String one = jdbc.queryForObject(
            "SELECT plan FROM customer WHERE email = ?",
            String.class, "bob@example.test");
        System.out.println("One row: " + one);

        try {
            jdbc.queryForObject(
                "SELECT plan FROM customer WHERE email = ?",
                String.class, "missing@example.test");
        } catch (EmptyResultDataAccessException e) {
            System.out.println("No row: actual=" + e.getActualSize());
        }

        try {
            jdbc.queryForObject(
                "SELECT plan FROM customer WHERE email = ?",
                String.class, "anna@example.test");
        } catch (IncorrectResultSizeDataAccessException e) {
            System.out.println(
                "Multiple rows: expected=" + e.getExpectedSize() +
                ", actual=" + e.getActualSize());
        }

        List<String> matches = jdbc.query(
            "SELECT id, plan FROM customer " +
            "WHERE email = ? ORDER BY id",
            (rs, rowNum) ->
                rs.getLong("id") + ":" + rs.getString("plan"),
            "anna@example.test");
        System.out.println("All matching: " + matches);

        Long count = jdbc.queryForObject(
            "SELECT COUNT(*) FROM customer WHERE email = ?",
            Long.class, "missing@example.test");
        System.out.println("Count missing: " + count);

        try {
            jdbc.queryForObject(
                "SELECT c.plan FROM customer c " +
                "JOIN customer_note n ON n.customer_id = c.id " +
                "WHERE c.id = ?",
                String.class, 3L);
        } catch (IncorrectResultSizeDataAccessException e) {
            System.out.println(
                "Join produced: " + e.getActualSize() + " rows");
        }

        RowMapper<Customer> mapper = (rs, rowNum) ->
            new Customer(
                rs.getLong("id"),
                rs.getString("email"),
                rs.getString("plan"));

        Customer byId = jdbc.queryForObject(
            "SELECT id, email, plan FROM customer WHERE id = ?",
            mapper, 3L);
        System.out.println(
            "By primary key: " + byId.id() + "/" + byId.plan());
    }
}
```

Run in the directory containing `pom.xml` with JDK 17+ and Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=OneRowDemo
```

Lines produced by `System.out.println`:

```text
One row: bronze
No row: actual=0
Multiple rows: expected=1, actual=2
All matching: [1:gold, 2:silver]
Count missing: 0
Join produced: 2 rows
By primary key: 3/bronze
```

**Explanation using the demo data:**

- `bob@example.test` appears once → `queryForObject` returns `bronze`.
- `missing@example.test` has no rows → subclass `EmptyResultDataAccessException` with `getActualSize() = 0`.
- `anna@example.test` appears twice → superclass `IncorrectResultSizeDataAccessException` with `expectedSize = 1`, `actualSize = 2`.
- `query` for Anna's email keeps both rows ordered by `ORDER BY id` → `[1:gold, 2:silver]`.
- `SELECT COUNT(*)` without `GROUP BY` returns one row containing 0 → not confused with "0 rows".
- Customer id 3 has only one row, yet has two `customer_note` rows → the `JOIN` yields two result rows and `queryForObject` reports a cardinality mismatch.
- Querying customer by primary key without joining returns exactly one row, and `RowMapper` constructs `Customer`.

`DriverManagerDataSource` in this example creates a new connection on demand and is **not a pool**; do not use it as a production performance template. The goal of the demo is JDBC query behavior and result contracts.

## 8. When Should You Use `queryForObject`, `query`, or `Optional`?

Choose the API **after determining the business-permitted row count**.

| Business expectation | API/usage | If 0 received | If >1 received |
| --- | --- | --- | --- |
| Exactly one row | `queryForObject(sql, RowMapper, args...)` | `EmptyResultDataAccessException` | `IncorrectResultSizeDataAccessException` |
| Exactly one row, one column | `queryForObject(sql, Class<T>, args...)` | `EmptyResultDataAccessException` | `IncorrectResultSizeDataAccessException` |
| May not exist, but must be unique if present | Catch `EmptyResultDataAccessException` **specifically** and return `Optional.empty()`, preserving >1 errors | `Optional.empty()` | Non-unique data error is preserved |
| May not exist or may have many | `query(sql, RowMapper, args...)` / `queryForList(...)` | Empty list | Multi-element list |
| Want total row count | `SELECT COUNT(*)` without `GROUP BY` + `queryForObject(..., Long.class)` | Number 0 | Query still returns one total row |
| Want latest record | `ORDER BY ... DESC` + limit 1, also handle absence | Absent → needs handling policy | Result picked by rule, unlike uniqueness requirement |

### Example Returning `Optional` When 0 Rows Is Valid

```java
import java.util.Optional;
import org.springframework.dao.EmptyResultDataAccessException;

// Illustrative snippet in a repository with JdbcTemplate jdbc.
public Optional<Customer> findOptionalById(long id) {
    try {
        return Optional.ofNullable(jdbc.queryForObject(
            "SELECT id, email, plan FROM customer WHERE id = ?",
            (rs, rowNum) -> new Customer(
                rs.getLong("id"),
                rs.getString("email"),
                rs.getString("plan")),
            id));
    } catch (EmptyResultDataAccessException notFound) {
        return Optional.empty();
    }
}
```

This is an integration method requiring field `jdbc` and type `Customer`, not a standalone Java file. It **does not swallow** `IncorrectResultSizeDataAccessException` when multiple rows exist. With a primary key, multiple rows should not happen if the schema is sound; if it happens in a complex query, look for SQL bugs or join relationships.

`Optional.ofNullable` can return `Optional.empty()` if a `RowMapper` returns null even though the SQL had one row. Therefore, if you must distinguish "no row" from "one row with null values", define a mapper that returns a non-null object representing the row, or use a result type that carries explicit presence info.

### `DataAccessUtils` for Already-Queried Lists

Spring provides cardinality helpers, for example:

```java
// Illustration: customers is a List<Customer> obtained from jdbc.query(...).
Customer required = DataAccessUtils.requiredSingleResult(customers);
Customer maybe = DataAccessUtils.singleResult(customers);
Optional<Customer> optional = DataAccessUtils.optionalResult(customers);
```

Requires importing `org.springframework.dao.support.DataAccessUtils` and `java.util.Optional`. This is an integration snippet; `customers` does not exist in a standalone file.

For a valid list:

- `requiredSingleResult`: requires exactly one element; empty or multiple both error.
- `singleResult`: empty returns null; more than one throws `IncorrectResultSizeDataAccessException`.
- `optionalResult`: empty returns `Optional.empty()`; more than one throws an exception; use when a presence/absence interface is desired.

Use these helpers **only when you deliberately fetched a list**; they do not fix an earlier query returning too many rows and can add overhead if the dataset is unbounded. For mappers that can return null, consider the meaning of `null` under the helper and domain contracts.

## 9. Handling Duplicate Data: Fix the Query or Fix the Schema?

When receiving multiple rows where only one was expected, distinguish **three scenarios**.

### A. The Query Is Actually a List Query

For example: all invoices for a customer, multiple shipping addresses, multiple roles for an account. This is valid one-to-many data. Change the repository to `query` and let the service decide how to use the list.

```java
List<Long> orderIds = jdbc.queryForList(
    "SELECT id FROM orders WHERE customer_id = ? ORDER BY id",
    Long.class,
    customerId
);
```

This is an integration snippet in a JDBC repository, requiring the `orders` table and corresponding variables. `queryForList(sql, Class<T>, args...)` returns one value from **each row** and still requires each row to have one compatible column; if you need multiple columns, use `query` with `RowMapper`.

### B. The Query Accidentally Multiplies Rows via JOIN

Rewrite the SQL according to intent: use `EXISTS` when you only need an existence condition on the child table; use grouping/aggregates when summarizing; or map one-to-many into a collection when preserving the full relationship. `SELECT DISTINCT` is appropriate only when deduplicating rows in the **projection** is genuinely the business requirement; it can discard information and does not fix underlying data.

### C. The Domain Truly Requires Uniqueness

For example: login username, invoice number within a tenant, external key per provider. In that case:

1. Verify the complete business key, including tenant, active/soft-delete status, and normalization.
2. Find duplicate records and decide how to handle historical data; do not arbitrarily delete one of them.
3. Place a `UNIQUE` constraint/index in the database on the exact column combination or expression if supported by the DBMS.
4. Keep write-conflict error handling. Do not rely solely on a `SELECT` check before `INSERT` to enforce uniqueness, because two transactions can both pass the check and both write.

Illustrative schema when email must be globally unique across the table:

```sql
CREATE TABLE account (
    id BIGINT PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    CONSTRAINT uq_account_email UNIQUE (email)
);
```

If existing data already has two rows with the same email, adding the constraint may **fail** until duplicates are resolved. If the rule is uniqueness only within a tenant, the constraint usually belongs on `(tenant_id, email)` rather than `email` alone. Case comparison, whitespace, and soft-delete semantics depend on domain design and DB dialect.

Once data is protected by an appropriate unique constraint in the DB, `SELECT ... WHERE unique_key = ?` can be designed to return at most one row. Then `queryForObject` is a reasonable choice if the record is required to exist.

## 10. Exceptions and Spring Transactions

`IncorrectResultSizeDataAccessException` is an unchecked exception extending `DataAccessException`. If it escapes an actually Spring-intercepted `@Transactional` method with an active transaction, Spring's default rollback rule for `RuntimeException` normally triggers transaction rollback.

```java
// Integration service illustration; repository has findExactlyOne.
@Transactional
public void registerPurchase(long customerId) {
    jdbc.update(
        "INSERT INTO purchase_audit (customer_id) VALUES (?)",
        customerId
    );

    Customer customer = repository.findExactlyOne(customerId);
    // If the method above throws IncorrectResultSizeDataAccessException,
    // the transaction may roll back the prior INSERT as well.
}
```

This snippet is not standalone because it omits concrete classes/fields and schema. If the error is **caught and swallowed** inside the transaction and the method finishes normally, Spring may commit earlier writes unless the transaction was already marked rollback-only for another reason.

Do not convert a "multiple rows when expecting one" error into a default value and continue a critical workflow. If business allows an absent record, catch only `EmptyResultDataAccessException`; if multiple records violate an invariant, let a meaningful error be recorded or translate it into an explicit domain exception while preserving transaction policy.

Note on API error responses: a non-unique data exception may be a server-side data/configuration bug or a controlled domain conflict; do not automatically assume every `IncorrectResultSizeDataAccessException` maps to HTTP 404/409/500. The mapping depends on the API contract and where the discrepancy arose.

## 11. Diagnosing in a Real System

When you see `IncorrectResultSizeDataAccessException: expected 1, actual 2`, a useful investigation sequence is:

1. **Identify the exact call site:** which `queryForObject` or `queryForMap` overload? Is the query intended to be exactly one?
2. **Reproduce the SQL and parameters in a safe test environment:** do parameters filter by tenant, status, and time range properly? Never leak personal data/secrets in logs.
3. **Run the SELECT as a multi-row query:** inspect the actual rows, primary keys, and business keys. Do not look only at the first row in a database client UI.
4. **Check JOINs:** group results by the root key and count child rows. One root customer can produce multiple joined rows.
5. **Compare against schema:** is there a `PRIMARY KEY`/`UNIQUE` on the exact column combination? Is there uncleaned legacy data? Could uniqueness be bypassed by NULLs or partial index conditions?
6. **Decide the new repository contract:** exactly one, zero-or-one, or many? Update SQL, API, or constraints accordingly.
7. **Add tests for 0/1/2+ rows and concurrency if relevant:** verify exception types and transaction rollback when needed.

A query to investigate duplicate records by email:

```sql
SELECT email, COUNT(*) AS occurrences
FROM customer
GROUP BY email
HAVING COUNT(*) > 1
ORDER BY occurrences DESC, email;
```

This summary reveals emails appearing on multiple rows, yet does **not** automatically distinguish invalid duplicates from valid multiple versions. Inspect the business key and actual schema.

A query to investigate row multiplication from a `JOIN`:

```sql
SELECT c.id, COUNT(*) AS joined_rows
FROM customer c
JOIN customer_note n ON n.customer_id = c.id
GROUP BY c.id
HAVING COUNT(*) > 1
ORDER BY c.id;
```

Each row here shows a customer with more than one joined row from notes; it does not prove the `customer` table contains duplicates.

## 12. Common Anti-Patterns

| Anti-pattern | Why it is harmful | Alternative |
| --- | --- | --- |
| Using `queryForObject` for a one-to-many field | Valid multiple records trigger exceptions. | Use `query`/`queryForList`, map data according to relationship. |
| Catching broad `IncorrectResultSizeDataAccessException` and returning `null` | Swallows both >1 and 0 errors, hiding broken invariants. | Catch `EmptyResultDataAccessException` specifically if 0 is allowed; >1 needs an explicit policy. |
| Adding `LIMIT 1` without `ORDER BY` | Picks a row depending on execution plan; hides duplicates. | Pick top 1 only if business requires it, with ordering/tie-breaker. |
| Adding `DISTINCT` to every buggy JOIN query | Can discard true relationship info, does not fix source data. | Use `EXISTS`, aggregates, fix the join, or map a collection as intended. |
| Assuming `COUNT(*) = 0` means no SQL rows | Ungrouped aggregate still returns one row containing 0. | Distinguish result-set cardinality from the count value inside a row. |
| Using `String.class` when SELECTing multiple columns | One row but violates the column-count contract. | Use `RowMapper` for multi-property objects. |
| Seeing two equal objects and treating them as one row | Cardinality counts SQL rows, not distinct post-mapping values. | Verify constraints or design a proper aggregate. |
| Checking uniqueness only with SELECT before INSERT | Two concurrent transactions can pass the check simultaneously. | Use DB unique constraints and handle race/write conflicts. |
| Using `@Transactional` while catching/swallowing all result errors | Risks committing prior writes after bad data was detected. | Preserve error signals and appropriate rollback policies. |
| Logging all sensitive query parameters | Can expose emails, personal identifiers, or protected data. | Log query name, error code, row count, safe IDs, or masked/redacted params. |

## 13. Checklist for Choosing the Right Result Model

Before writing `queryForObject`, answer:

1. **What guarantees at most one row?** Primary key/unique constraint, or just an assumption unprotected by the DB?
2. **Is zero rows valid?** If yes, the repository should expose an explicit `Optional`/nullable contract instead of unexpectedly failing.
3. **If two rows appear, what should the system do?** Report a data error, switch to a list, or pick a record by a specified business ordering?
4. **Does the SQL have JOIN or GROUP BY?** Post-join/aggregate cardinality differs from the base table's cardinality.
5. **Are you reading one column or a multi-column entity?** The `Class<T>` and `RowMapper<T>` overloads have different column-count contracts.
6. **Could there be NULL or aggregates?** A row containing NULL is completely different from having no rows.
7. **Do unique constraints cover tenant, soft-delete, normalization, and concurrency?**
8. **Are exceptions caught at the right layer?** Especially when the query sits inside a transaction with preceding writes.

### Key Takeaways

- **`queryForObject` requires exactly one SQL row**; it is not an API for "grabbing the first record".
- **0 rows** normally throws `EmptyResultDataAccessException`, a subclass of `IncorrectResultSizeDataAccessException`; **more than 1 row** throws `IncorrectResultSizeDataAccessException`.
- `getExpectedSize()`/`getActualSize()` aid diagnosis, but do not replace inspecting SQL, parameters, and schema.
- A `JOIN` can multiply rows even when the parent table has a unique primary key. Duplicate column values also do not prove parent-table duplicates.
- Use `query` for lists; use `queryForObject` for exactly one; use `Optional` intentionally for zero-or-one while preserving >1 errors.
- **`LIMIT 1` is valid only when business rules call for an ordered selection**, not as a hack for data that ought to be unique.
- If true uniqueness is required, enforce **unique constraints in the database**, do not rely solely on Java checks.

### References

- Spring Framework — `JdbcTemplate`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html
- Spring — `IncorrectResultSizeDataAccessException`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/dao/IncorrectResultSizeDataAccessException.html
- Spring — `EmptyResultDataAccessException`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/dao/EmptyResultDataAccessException.html
- Spring — `DataAccessUtils`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/dao/support/DataAccessUtils.html
- Spring — JDBC querying: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
