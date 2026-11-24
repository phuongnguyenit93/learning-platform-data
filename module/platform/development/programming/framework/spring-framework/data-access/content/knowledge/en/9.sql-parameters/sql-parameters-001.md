# PreparedStatement and the Mechanism for Separating SQL from Values

## Lesson Objectives

In a Spring application using JDBC, an SQL statement typically consists of two parts with completely different roles:

1. **Statement structure**: SQL keywords, tables, columns, operators, and query logic determined by the program.
2. **Data values**: emails, product codes, customer IDs, dates, search keywords... which may come from an HTTP request, file, message queue, or another database.

`PreparedStatement` passes **values** into SQL parameter positions **without turning the content of those values into SQL syntax**. This is the foundational technique for querying data accurately and preventing SQL injection at bindable positions.

After this lesson, you will be able to:

- Distinguish between building SQL by string concatenation and preparing an SQL statement then binding parameters.
- Understand the `?` marker, parameter indices starting at **1**, and methods like `setString`, `setInt`, `setLong`, `setNull`, `setObject`.
- Use `PreparedStatement` for `SELECT`, `INSERT`, `UPDATE`; manage `Connection`, `ResultSet`, and `PreparedStatement` with try-with-resources in plain JDBC.
- Recognize the limits of bind parameters: they cannot replace table names, column names, `ASC/DESC`, or an entire SQL fragment.
- Connect how Spring `JdbcTemplate` and `NamedParameterJdbcTemplate` use parameters instead of writing low-level JDBC code for every query.
- Run a **Java 17+**, Spring JDBC + H2 program to verify that values containing single quotes and SQL-shaped strings are still treated as data.
- Avoid common mistakes with `NULL`, `IN (...)`, `LIKE`, parameter ordering, statement reuse, and false assumptions about performance.

**Scope:** This lesson covers **SQL parameters and PreparedStatement in JDBC/Spring data access**. It does not replace courses on database authorization, ORM, transaction isolation, or execution plan optimization.

## 1. What Can Happen When Concatenating Values into SQL?

Suppose an application wants to retrieve an account by a user-provided email:

```sql
SELECT id, email, balance
FROM accounts
WHERE email = 'alice@example.test';
```

The following Java code is **unsafe** when `email` comes from an external source:

```java
// DO NOT use with untrusted input data.
String sql = "SELECT id, email, balance FROM accounts WHERE email = '"
        + email + "'";
```

If the value contains a single quote, such as `O'Reilly@example.test`, the concatenated SQL may no longer be valid. More seriously, if the data contains characters with special meaning such as quotes, SQL operators, or comment symbols, it can **alter the statement structure** instead of being compared as an email string.

Example of an input value deliberately shaped like SQL syntax:

```text
' OR 1=1 --
```

If inserted verbatim between two quotes added by the developer, the email condition can be transformed into an always-true expression and the remainder commented out; that is a form of **SQL injection**. This is an example to explain the risk, **not a way to execute queries for testing on unauthorized systems**.

You should not try to fix this by manually adding `'`, manually replacing `'` with `''`, or filtering a few keywords like `OR`, `SELECT`, `DROP`. Quoting/escaping depends on the SQL dialect and configuration; blocklists are easy to bypass and corrupt valid data.

**The right approach:** keep the SQL with parameter markers intact, and bind values through the JDBC API.

## 2. The Standard Mindset: Fixed Structure, Separate Values

Instead of concatenating SQL:

```java
String sql = "SELECT id, email, balance FROM accounts WHERE email = ?";
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, email);
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Process each row returned by the DB.
        }
    }
}
```

This is a **code snippet**, assuming `connection` is an open `java.sql.Connection`, `email` is already defined, and `java.sql.PreparedStatement`/`ResultSet` are imported. A complete program is provided in section 9.

Conceptual flow:

```text
SQL decided by the application:
  SELECT id, email FROM accounts WHERE email = ?
                                      |
                                      v
PreparedStatement: parameter #1 has string type
  setString(1, "O'Reilly@example.test")
                                      |
                                      v
JDBC driver / database:
  the SQL part is the statement; the parameter part is data
                                      |
                                      v
Database compares the email column against the exact bound string
```

When the user enters `' OR 1=1 --`, JDBC still passes it as the **string value of parameter number 1**. That content is not promoted to an `OR` operator or an SQL comment in the query; as a result, the database searches for an email matching that exact strange string, usually returning no rows.

At the implementation level, depending on the JDBC driver, DBMS, and configuration, the driver may send the SQL and parameters over a dedicated protocol, compile server-side, cache statements, or use another mechanism. **You do not need to assume every driver sends two separate network packets** to understand the safety guarantee: the important contract is that parameter values remain treated as **data**, not new SQL syntax.

### 2.1. Question Marks Are Not Manual String Replacement

In the statement:

```sql
SELECT *
FROM accounts
WHERE id = ? AND email = ?;
```

there are **two parameter markers**. They are not strings to be searched and replaced using `String.replace("?", ...)`. The caller uses `PreparedStatement` setters; the JDBC driver/DBMS is responsible for representing the value according to the corresponding SQL type.

`setLong(1, id)` binds to the first marker, and `setString(2, email)` binds to the second marker. Indices start at **1**, not 0 like Java array indices.

### 2.2. Valid Input Still Must Be Bound

Validating email format, title length, or user permissions is necessary, but it does not make string concatenation safe. Even for an already validated email, **still bind it**:

```java
PreparedStatement ps = connection.prepareStatement(
        "SELECT id FROM accounts WHERE email = ?");
ps.setString(1, validatedEmail);
```

The snippet above only illustrates the mechanism; in real code, use try-with-resources and an appropriate connection acquisition mechanism.

Conversely, parameter binding **does not automatically provide authorization**. If a user may only see data for tenant 7, the SQL still needs the corresponding tenant filter and the backend must verify tenant access rights:

```sql
SELECT id, email
FROM accounts
WHERE tenant_id = ? AND email = ?;
```

Both values are bound, but **the rule governing which tenant a user may access** still belongs to application security design.

## 3. Most Important JDBC PreparedStatement APIs

`PreparedStatement` belongs to the `java.sql` package and is created from a `Connection`:

```java
PreparedStatement ps = connection.prepareStatement(
        "SELECT id FROM accounts WHERE email = ?");
```

`PreparedStatement` extends `Statement` and has many methods. In typical data access, remember these groups:

| Method | Purpose |
| --- | --- |
| `connection.prepareStatement(sql)` | Prepares a JDBC object for SQL containing `?` markers |
| `ps.setString(index, value)` | Binds a string value |
| `ps.setInt(index, value)`, `setLong(...)` | Binds an appropriate integer value |
| `ps.setBoolean(index, value)` | Binds a boolean |
| `ps.setBigDecimal(index, value)` | Binds an exact decimal number, e.g., money with an explicit scale policy |
| `ps.setObject(index, value)` | Binds an object-typed value; must consider the driver's SQL type inference capability |
| `ps.setNull(index, java.sql.Types.VARCHAR)` | Binds SQL NULL with an explicit SQL type |
| `ps.executeQuery()` | Runs a query returning a `ResultSet` (typically `SELECT`) |
| `ps.executeUpdate()` | Runs DML or an appropriate command and returns the affected row count |
| `ps.execute()` | General-purpose mechanism, returning a boolean indicating the form of the first result |
| `ps.addBatch()`, `ps.executeBatch()` | Groups compatible executions for batch processing |
| `ps.clearParameters()` | Clears currently bound values on the statement |
| `ps.close()` | Releases statement resources; prefer try-with-resources |

When `executeQuery()` returns a `ResultSet`, JDBC places the cursor before the first row. You call `rs.next()` to advance to each row; getters like `getLong("id")` read columns at the current row.

`executeUpdate()` returns the **number of affected rows** per the JDBC/driver contract, not the auto-generated ID. When a generated key is needed, use the statement creation overload requesting generated keys and `getGeneratedKeys()`, or Spring helper utilities.

**JDBC `PreparedStatement`'s `execute()`** is not the same as Spring's `void JdbcTemplate.execute(String sql)`: they are methods at different abstraction layers. For standard CRUD, prefer the explicit `executeQuery` or `executeUpdate`.

### 3.1. Binding Order and Data Types Must Match

SQL:

```sql
UPDATE accounts
SET balance = ?
WHERE id = ?;
```

Java:

```java
try (PreparedStatement ps = connection.prepareStatement(
        "UPDATE accounts SET balance = ? WHERE id = ?")) {
    ps.setInt(1, newBalance);
    ps.setLong(2, accountId);
    int affected = ps.executeUpdate();
}
```

This is a snippet, assuming `connection`, `newBalance`, and `accountId` exist. Swapping the order of the two setters can cause a data type error or, more dangerously, a valid SQL statement that updates the wrong row.

Tip: when there are many markers, place them on clearly readable SQL lines and check sequentially from left to right; avoid statements with many same-typed parameters without clear naming.

### 3.2. Re-executing the Same PreparedStatement with New Values

A `PreparedStatement` can be executed multiple times with different parameters. Bound values **are retained** until you replace them with a setter or call `clearParameters()`; they are not automatically cleared by default after `executeQuery()`.

```java
try (PreparedStatement ps = connection.prepareStatement(
        "SELECT id FROM accounts WHERE email = ?")) {
    ps.setString(1, "alice@example.test");
    try (ResultSet rs = ps.executeQuery()) {
        // Process alice's result.
    }

    ps.setString(1, "bob@example.test");
    try (ResultSet rs = ps.executeQuery()) {
        // Process bob's result.
    }
}
```

This is only an illustrative snippet; each `ResultSet` is closed before the next execution. For an SQL statement with three markers, you must assign all three properly for each use (or know exactly which parameters are intentionally kept). Stale request data accidentally remaining on a statement is a very hard bug to detect.

Do not put a single `PreparedStatement` into a singleton bean to be shared across multiple requests/threads. JDBC connections and statements have their own lifecycle/concurrency semantics and generally **should not be shared** that way. In Spring, sharing a properly configured `JdbcTemplate` bean is a different model: it coordinates JDBC operations through a datasource, not by having requests share an arbitrary prepared statement.

## 4. How Does Separating SQL and Values Prevent SQL Injection?

### 4.1. Comparing Two Ways of Building Queries

**Unsafe:**

```java
String sql = "SELECT id FROM accounts WHERE email = '" + userInput + "'";
// User input becomes part of the final SQL syntax.
```

**Safe for value positions:**

```java
String sql = "SELECT id FROM accounts WHERE email = ?";
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, userInput);
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Process rows whose email equals userInput.
        }
    }
}
```

`userInput` may contain single quotes, comment markers, or strings that look like SQL; at the bind position, they are data. This is the **core principle** of prepared statements in preventing SQL injection.

However, do not claim that "using `PreparedStatement` makes every kind of injection disappear." If part of the SQL structure is still concatenated from external input, that part still carries risk.

### 4.2. Identifiers and Keywords Are Not Bind Parameters

You cannot use question marks in place of table names, column names, keyword lists, or sort directions:

```sql
-- Does NOT mean sorting by the column specified by the client:
SELECT id, title FROM tasks ORDER BY ?;

-- Do NOT use a placeholder as an identifier:
SELECT * FROM ? WHERE id = ?;

-- Does NOT turn the value "DESC" into an SQL keyword:
SELECT id FROM tasks ORDER BY created_at ?;
```

`?` represents **a single value** in an SQL expression, not a syntactic component such as a table name, `ASC`, or `DESC`.

If the client selects a sort option, map the input to one of a set of **fixed SQL structures owned by the application**:

```java
static String safeOrderBy(String requested) {
    return switch (requested) {
        case "newest" -> "created_at DESC, id DESC";
        case "oldest" -> "created_at ASC, id ASC";
        case "title"  -> "title ASC, id ASC";
        default -> throw new IllegalArgumentException("Unsupported sort");
    };
}
```

When calling it, concatenate only the **value returned from the allowlist** into the fixed SQL; still bind all other values with `?`. Never pass `request.getSort()` directly into SQL. For dynamic table names per tenant, use a controlled schema/routing design rather than substituting arbitrary identifiers with parameters.

### 4.3. Dynamic WHERE and Conditional Structures

If filters are toggled based on the request, you can build the SQL structure branch by branch **as defined by the application itself**, then bind the corresponding values:

```java
String sql = "SELECT id, title FROM tasks WHERE tenant_id = ?";
if (status != null) {
    sql += " AND status = ?";
}
// If adding a marker for status, a corresponding bind value must be added.
// Do not concatenate status directly into the SQL statement.
```

This is an illustrative snippet without the JDBC invocation, meant to distinguish **structure** chosen by code and **values** from the request. When filters get complex, use a controlled builder or `NamedParameterJdbcTemplate` to reduce the risk of parameter order mismatch.

### 4.4. IN (...) and Lists of Values

A statement like:

```sql
SELECT id, title FROM tasks WHERE id IN (?);
```

with a single `?` **does not mean** the driver automatically expands a `List<Long>` into 4 markers. That is still **one parameter**; passing a collection into one marker may fail or carry DB-specific semantics (such as an SQL array) different from what you expect.

With JDBC positional parameters, generate the exact number of markers for a validated list, then bind each ID:

```sql
SELECT id, title FROM tasks WHERE id IN (?, ?, ?);
```

With Spring, `NamedParameterJdbcTemplate` is often simpler because it can expand a collection parameter for `IN (:ids)` within the limits of JDBC/DBMS. However, an **empty list** must be handled intentionally: return an empty result or choose an appropriate SQL, rather than assuming `IN ()` is accepted by every DBMS. You should also bound the list size to avoid overly long SQL or too many bind parameters.

### 4.5. LIKE: Safe Binding, Yet Still Has Wildcards

Example:

```sql
SELECT id FROM tasks WHERE title LIKE ?;
```

If you bind `"%_"`, it is still an **SQL LIKE pattern value**; the database may interpret `%` as multiple characters and `_` as a single character, rather than two literal characters to match. `PreparedStatement` prevents that content from breaking the SQL structure, but **does not automatically escape LIKE wildcards**.

When the business requirement is to search for the exact substring typed by the user, you must define how `%`, `_`, and the escape character are escaped for the SQL dialect, then use an appropriate `ESCAPE` clause or choose full-text/another search mechanism. Do not confuse "not vulnerable to SQL injection" with "character-exact search results."

## 5. Pay Attention to NULL and Parameter SQL Types

### 5.1. Bind NULL with an Explicit Type

In plain JDBC, when a parameter is SQL NULL:

```java
ps.setNull(1, java.sql.Types.VARCHAR);
```

or you can use `setObject(...)` with appropriate SQL type information. The `NULL` type can matter when the driver/database cannot infer the type from an expression or overload. In Spring JDBC, `SqlParameterValue`, `PreparedStatementSetter`, and overloads accepting SQL types help specify the type explicitly when needed.

`ps.setObject(1, null)` does not always behave identically across every JDBC driver/SQL dialect. For code deployed across multiple DBs, do not rely on type guessing when the query is likely ambiguous.

### 5.2. NULL in SQL Follows Three-Valued Logic

Binding `null` to `WHERE nickname = ?` **does not cause** SQL to turn into `IS NULL`. In standard SQL, `col = NULL`/`col = ?` with a NULL parameter evaluates to UNKNOWN, so it will not match rows where `nickname` is NULL in `WHERE`.

If the requirement is to filter for IS NULL, write the corresponding SQL structure:

```sql
SELECT id FROM accounts WHERE nickname IS NULL;
```

Or use a null-safe expression supported by the DBMS when designing for both NULL and non-NULL (such as `IS NOT DISTINCT FROM` in PostgreSQL). Choose the structure according to business semantics; do not expect JDBC to rewrite SQL logic automatically.

### 5.3. Dates/Times, UUID, Money, and Decimals

- For money, prefer `BigDecimal` and SQL `DECIMAL/NUMERIC` with defined precision/scale over arithmetic with `double` when decimal precision is needed.
- For dates/times, explicitly decide on the timezone and appropriate Java/JDBC type: `LocalDate`, `LocalDateTime`, `Instant`, `OffsetDateTime`, `java.sql.Timestamp`, etc. must be mapped according to JDBC driver/DB support.
- UUID may be stored using a DB-specific type or string/binary; bind with a type supported by the driver.
- With `setObject` and less common Java types, test against a real DBMS. Do not assume every driver supports all JDBC 4.2 types identically.
- With `ResultSet.getInt(...)` on a nullable column, a result of 0 can represent SQL NULL; use `wasNull()` or `getObject(..., Integer.class)` appropriately when distinction is needed.

The exercise examples only use `VARCHAR`, `BIGINT`, and `INT` to keep binding clear; beginners do not need to solve timezone or decimal conversion right away.

## 6. PreparedStatement and Transactions, Resources, Performance

### 6.1. Always Close JDBC Resources in Proper Order

In plain JDBC, the safe pattern is:

```java
try (Connection connection = dataSource.getConnection();
     PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, email);
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Process row.
        }
    }
}
```

Resources are closed in reverse order of declaration in try-with-resources; `ResultSet` is closed before the statement/connection. Do not retain a `ResultSet` for use after closing the statement/connection.

In Spring `JdbcTemplate`, the framework handles most acquisition and release of resources, so repositories typically only provide SQL, parameters, and a `RowMapper`. **Do not manually close a connection whose transaction is managed by Spring** when writing custom JDBC callbacks; follow the callback/Spring contract.

### 6.2. PreparedStatement Does Not Determine Transactions by Itself

`PreparedStatement` **is not a transaction**. If you want multiple SQL statements to commit or roll back together, you need an appropriate transaction boundary:

- Plain JDBC: `connection.setAutoCommit(false)`, execute the statements on **the same connection**, `commit()` on success, `rollback()` on failure, and restore configuration/close resources properly.
- Spring: use `@Transactional` on a Spring-managed service with the right transaction manager; `JdbcTemplate` operations using the matching datasource participate in the transaction-managed connection.
- If there are two different databases, a single local JDBC transaction does not span both; that is a separate distributed transaction/consistency problem.

Do not confuse using a prepared statement with queries being immune to blocking, deadlocks, or bypassing constraints. Locking/transaction/validation rules are still enforced by the database.

### 6.3. Is PreparedStatement Always Faster Than Statement?

**There is no guarantee it is always faster.** Depending on the driver, DBMS, reuse count, server-side prepare, statement cache, execution plan, and data volume, a statement may be parsed/planned once or multiple times. Some drivers have a threshold before enabling server-side preparation or may partially emulate it client-side.

The benefit **guaranteed at the API level** is how data is bound and how SQL syntax is separated from values at parameter positions; performance depends on the specific environment. If optimization is needed, measure benchmarks/query plans in your target DBMS; do not treat `PreparedStatement` as something that automatically eliminates full scans or gives every query an index.

### 6.4. Batching Multiple Values for the Same SQL Structure

When inserting many rows with the same template:

```java
try (PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO audit_events (id, message) VALUES (?, ?)")) {
    for (AuditEvent event : events) {
        ps.setLong(1, event.id());
        ps.setString(2, event.message());
        ps.addBatch();
    }
    int[] affectedCounts = ps.executeBatch();
}
```

This is an illustrative snippet assuming `connection`, `AuditEvent`, `events`, and the schema exist. Batching can reduce round-trips depending on the driver/config, but it does not guarantee all statements form a single transaction. If all must succeed or roll back together, configure a transaction. The batch result array may contain special values such as `Statement.SUCCESS_NO_INFO`; not every element is necessarily a specific row count.

Spring JDBC offers `JdbcTemplate.batchUpdate(...)` and overloads taking `BatchPreparedStatementSetter` to reduce boilerplate code while preserving the principle of setting values via setters.

## 7. How Does Spring JdbcTemplate Use PreparedStatement?

In Spring Framework data access applications, repositories typically use `JdbcTemplate` instead of directly obtaining a `Connection`. When calling an overload with bind parameters, `JdbcTemplate` creates an appropriate prepared statement/setter and releases resources according to Spring JDBC's lifecycle.

Example:

```java
List<Account> accounts = jdbc.query(
        """
        SELECT id, email, balance
        FROM accounts
        WHERE balance >= ? AND email <> ?
        ORDER BY id
        """,
        (rs, rowNum) -> new Account(
                rs.getLong("id"),
                rs.getString("email"),
                rs.getInt("balance")),
        minimumBalance, excludedEmail);
```

This is only a snippet, with `jdbc`, `Account`, `minimumBalance`, and `excludedEmail` defined elsewhere. `JdbcTemplate.query(String, RowMapper<T>, Object... args)` maps values in marker order. You do not need to write `ps.setInt(1, ...)`/`ps.setString(2, ...)` when the values are automatically bound with sufficiently clear types.

Corresponding operations:

```java
Long count = jdbc.queryForObject(
        "SELECT COUNT(*) FROM accounts WHERE balance >= ?",
        Long.class,
        minimumBalance);

int affected = jdbc.update(
        "UPDATE accounts SET balance = balance + ? WHERE id = ?",
        delta, accountId);
```

`queryForObject` is used when a query is expected to return exactly one row; `COUNT(*)` without `GROUP BY` returns one row containing 0 when there are no records. `update` returns the affected row count, typically 0 when `WHERE` matches nothing. **Do not concatenate values into SQL before calling `JdbcTemplate`**, because doing so breaks the SQL/value separation right at the Java layer.

### 7.1. JDBC API vs. JdbcTemplate: What Is Similar?

| Plain JDBC | With JdbcTemplate | Responsibility Retained by the Application |
| --- | --- | --- |
| `connection.prepareStatement(sql)` | `jdbc.query(sql, mapper, args...)` | Write correct SQL and choose data to return |
| `ps.setString(...)` / `setLong(...)` | `Object... args` parameters or `PreparedStatementSetter` | Bind in the right order/types |
| `ps.executeQuery()`, `rs.next()` | `query(...)` invokes `RowMapper` per row | Map each row accurately |
| `ps.executeUpdate()` | `jdbc.update(sql, args...)` | Check affected rows per business rules |
| try-with-resources closing statement/result set | Spring manages resources via template | Do not keep result set/connection beyond lifecycle |
| `SQLException` | Unchecked `DataAccessException` hierarchy | Classify and handle errors meaningfully |

**Important distinction:** not *every overload* of `JdbcTemplate` is guaranteed to use `PreparedStatement`. Some overloads accepting SQL without bindings may use JDBC `Statement`. When callers supply values, choose an overload accepting bind arguments or a setter to ensure proper parameter handling.

### 7.2. PreparedStatementSetter When Fine-Grained Control Is Needed

When you want to manually set a value with a specific SQL type or configure the statement, Spring provides `PreparedStatementSetter`:

```java
int updated = jdbc.update(
        "UPDATE accounts SET nickname = ? WHERE id = ?",
        ps -> {
            ps.setNull(1, java.sql.Types.VARCHAR);
            ps.setLong(2, accountId);
        });
```

This is a snippet, assuming `jdbc` and `accountId` exist. The overload taking `PreparedStatementSetter` is chosen because the lambda has one parameter of type `PreparedStatement`. `setNull` carries an explicit SQL type, avoiding ambiguity when updating a nullable column.

Inside the callback method, **do not call `ps.executeUpdate()`** if the contract only asks to bind parameters: `JdbcTemplate` itself executes the statement and collects the result; calling execute twice can cause duplicate writes.

For NULL values or special types, another option is `SqlParameterValue`:

```java
int affected = jdbc.update(
        "UPDATE accounts SET nickname = ? WHERE id = ?",
        new SqlParameterValue(java.sql.Types.VARCHAR, null),
        accountId);
```

This snippet requires importing `org.springframework.jdbc.core.SqlParameterValue`. It specifies the SQL type of the NULL value explicitly, fitting well when you want to use the `Object... args` overload without writing a setter callback.

### 7.3. NamedParameterJdbcTemplate: Naming Instead of Remembering Positions

For SQL statements with many parameters, Spring supports `NamedParameterJdbcTemplate`:

```java
var named = new NamedParameterJdbcTemplate(dataSource);

var params = new MapSqlParameterSource()
        .addValue("minBalance", 200)
        .addValue("email", "bob@example.test");

List<Long> ids = named.query(
        """
        SELECT id FROM accounts
        WHERE balance >= :minBalance AND email <> :email
        ORDER BY id
        """,
        params,
        (rs, rowNum) -> rs.getLong("id"));
```

This is a snippet, not a standalone program; it requires importing `NamedParameterJdbcTemplate`, `MapSqlParameterSource`, and having a `dataSource`. `:minBalance`/`:email` **are not standard SQL engine parameter syntax**; Spring translates the names into JDBC placeholders and binds the corresponding values before execution. Having the same name appear multiple times in an SQL statement helps avoid repeating and tracking parameter positions.

`NamedParameterJdbcTemplate` can expand collection parameters for `IN (:ids)`, though empty lists and reasonable element count limits must still be handled. Using named parameters improves readability; **it does not make concatenating identifiers from user input safe**.

### 7.4. Repositories Should Bind Where SQL Is Owned

In a well-structured design, the repository owns both the structural SQL and parameter binding; the service passes validated values and enforces access permissions. Controllers should not assemble SQL strings from requests. The method example below is only a code snippet inside a repository that already has a `JdbcTemplate` bean:

```java
public Optional<Account> findByEmail(String email) {
    List<Account> found = jdbc.query(
            """
            SELECT id, email, balance
            FROM accounts
            WHERE email = ?
            """,
            ACCOUNT_MAPPER,
            email);
    return found.stream().findFirst();
}
```

This pattern assumes the `email` column has a UNIQUE constraint (or the query is guaranteed to return at most one row); otherwise, `findFirst()` can mask duplicate data bugs. When "exactly one row must exist," `queryForObject` and handling `EmptyResultDataAccessException` carry different semantics. Parameter binding solves **SQL syntax safety**, not automatically **cardinality**.

## 8. Common Mistakes with PreparedStatement

| Misconception | Correct Understanding / Resolution |
| --- | --- |
| "`?` can replace anything in SQL." | Only replaces **values** at parameter positions; identifiers, keywords, and sort directions must come from controlled structures. |
| "Parameter indices start at 0." | JDBC `setXxx(index,...)` starts at **1**. |
| "`setString(1, "123")` and `setLong(1, 123)` are always equivalent." | Data types and DB/driver conversion plans may differ; bind the proper SQL type. |
| "PreparedStatement also auto-escapes LIKE wildcards." | Data is still a LIKE pattern; `%` and `_` still act as wildcards. |
| "`IN (?)` accepts a Java List and expands automatically." | Not in standard JDBC positional markers; expand markers or use named parameters that support collections. |
| "Binding NULL is equivalent to an IS NULL condition." | `WHERE col = NULL` does not match NULL under SQL three-valued logic; use an appropriate `IS NULL` structure. |
| "Just validate input, then concatenating SQL is safe." | Validation and parameter binding address different goals; still bind data. |
| "PreparedStatement is always faster than Statement." | Depends on driver, caching, DB, and query plan; the true benefit is separating structure and values. |
| "Using JdbcTemplate blocks all SQL injection." | Concatenating user input into SQL before calling the template is still dangerous; use parameterized overloads and allowlists for dynamic structure. |
| "Re-running PreparedStatement auto-clears old parameters." | Bound values are usually retained until replaced/cleared; update all parameters completely for each new run. |
| "PreparedStatement auto-commits/rolls back multiple SQL statements." | Transactions must be configured separately on the connection or Spring service. |
| "Sharing one PreparedStatement across all requests is good." | Do not arbitrarily share statements/connections across threads; let the connection pool and JdbcTemplate manage lifecycles properly. |

## 9. Complete Hands-on Practice: Java 17 + Spring JDBC + H2

This example shows **the same database** being queried via plain JDBC `PreparedStatement` and `JdbcTemplate`; values containing single quotes and SQL-shaped strings are treated as data. It uses H2 in-memory to run standalone without needing an external database server.

**Requirements:** JDK 17+, a Java 17-compatible Gradle (or matching Gradle Wrapper), and access to download dependencies from Maven Central on first run.

### 9.1. Directory Structure

```text
prepared-statement-demo/
├── build.gradle
└── src/main/java/example/PreparedStatementDemo.java
```

### 9.2. build.gradle

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
    mainClass = 'example.PreparedStatementDemo'
}
```

There is no need to create a Spring `ApplicationContext` because the example builds `JdbcTemplate` directly from the datasource to illustrate SQL/binding. In a real application, the datasource is typically managed by the Spring container and repositories receive `JdbcTemplate` via DI.

### 9.3. Complete Java File

Create `src/main/java/example/PreparedStatementDemo.java`:

```java
package example;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

public class PreparedStatementDemo {
    public static void main(String[] args) throws Exception {
        DriverManagerDataSource ds = new DriverManagerDataSource();
        ds.setDriverClassName("org.h2.Driver");
        ds.setUrl("jdbc:h2:mem:prepared_demo;DB_CLOSE_DELAY=-1");
        ds.setUsername("sa");
        ds.setPassword("");

        JdbcTemplate jdbc = new JdbcTemplate(ds);

        // DDL demo: table has an email containing a single quote.
        jdbc.execute("""
                CREATE TABLE accounts (
                    id BIGINT PRIMARY KEY,
                    email VARCHAR(120) NOT NULL UNIQUE,
                    balance INT NOT NULL
                )
                """);

        // Spring JdbcTemplate binds four values with placeholders.
        jdbc.update(
                "INSERT INTO accounts (id, email, balance) VALUES (?, ?, ?)",
                1L, "alice@example.test", 100);
        jdbc.update(
                "INSERT INTO accounts (id, email, balance) VALUES (?, ?, ?)",
                2L, "bob@example.test", 200);
        jdbc.update(
                "INSERT INTO accounts (id, email, balance) VALUES (?, ?, ?)",
                3L, "O'Reilly@example.test", 300);

        String sql = """
                SELECT id, balance
                FROM accounts
                WHERE email = ?
                """;

        // Plain JDBC: we manage the PreparedStatement ourselves.
        try (Connection connection = ds.getConnection();
             PreparedStatement ps = connection.prepareStatement(sql)) {

            // Value containing ' is compared accurately.
            ps.setString(1, "O'Reilly@example.test");
            try (ResultSet rs = ps.executeQuery()) {
                if (rs.next()) {
                    System.out.println(
                            "found=" + rs.getLong("id")
                            + ":" + rs.getInt("balance"));
                }
            }

            // Do not change SQL, only change the value of marker #1.
            ps.setString(1, "' OR 1=1 --");
            try (ResultSet rs = ps.executeQuery()) {
                System.out.println("strangeInputFound=" + rs.next());
            }

            // The statement can still be reused with a new value.
            ps.setString(1, "bob@example.test");
            try (ResultSet rs = ps.executeQuery()) {
                if (rs.next()) {
                    System.out.println(
                            "reusedId=" + rs.getLong("id"));
                }
            }
        }

        // Spring queryForObject: a single row/scalar value.
        Long count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM accounts WHERE balance >= ?",
                Long.class,
                200);
        System.out.println("countAtLeast200=" + count);

        // Spring query: list and RowMapper.
        List<String> emails = jdbc.query(
                """
                SELECT email
                FROM accounts
                WHERE balance >= ?
                ORDER BY id
                """,
                (rs, rowNum) -> rs.getString("email"),
                200);
        System.out.println("matchingEmails=" + emails);

        // Spring update: number of affected rows, not generated ID.
        int changed = jdbc.update(
                "UPDATE accounts SET balance = balance + ? WHERE id = ?",
                25, 1L);
        System.out.println("changed=" + changed);

        Integer aliceBalance = jdbc.queryForObject(
                "SELECT balance FROM accounts WHERE id = ?",
                Integer.class, 1L);
        System.out.println("aliceBalance=" + aliceBalance);

        int missing = jdbc.update(
                "UPDATE accounts SET balance = balance + ? WHERE id = ?",
                25, 999L);
        System.out.println("missingChanged=" + missing);
    }
}
```

Key details to note:

- The SQL string `SELECT id, balance FROM accounts WHERE email = ?` **does not change** across the three searches; only `ps.setString(1, ...)` changes the value.
- Strings with single quotes are inserted and read successfully because `JdbcTemplate` also binds data for `INSERT`.
- The string `' OR 1=1 --` is not executed as an SQL condition, so it matches no email in the table.
- `PreparedStatement`/`ResultSet` are closed via try-with-resources; `Connection` is closed last.
- `JdbcTemplate` operates on the same H2 database as plain JDBC; therefore both access paths see the same data.
- `JdbcTemplate.query(...)` takes a `RowMapper`, inside which you do not call `rs.next()`; the template already iterates through each row.
- `DriverManagerDataSource` is suitable for demos but **not an optimal connection pool for production**. `DB_CLOSE_DELAY=-1` keeps the in-memory database alive across multiple connection closes within the same JVM.

### 9.4. Running the Program

From the project directory:

```bash
gradle run
```

If Gradle Wrapper is present, use `./gradlew run` (Linux/macOS) or `gradlew.bat run` (Windows). Gradle may print build logs; **the lines printed by Java System.out.println** in order are:

```text
found=3:300
strangeInputFound=false
reusedId=2
countAtLeast200=2
matchingEmails=[bob@example.test, O'Reilly@example.test]
changed=1
aliceBalance=125
missingChanged=0
```

Verify each result:

1. Three `INSERT` statements create ID 1 (100), ID 2 (200), ID 3 (300).
2. Binding `O'Reilly@example.test` as the exact literal string yields `found=3:300`.
3. The value `' OR 1=1 --` is not a stored email; using a prepared statement returns false, without turning the SQL into "return all rows."
4. Changing the marker to `bob@example.test` on the same statement finds ID 2.
5. `balance >= 200` matches Bob (200) and O'Reilly (300), so `countAtLeast200=2` and the list contains two emails sorted by ID.
6. `UPDATE ... WHERE id=1` changes Alice from 100 to 125, affected row = 1; ID 999 does not exist so affected row = 0.

**Demo limitations:** The code illustrates separating data/SQL structure; it does not yet configure pooling, transactions/services, authorization, migrations, or business constraints of a real system.

## 10. Workflow for Applying in a Spring Repository

An example of a well-structured repository flow:

```text
Controller:
  receives filter, sort, user/tenant
    |
    v
Service:
  verifies permissions, validates input, business transaction
    |
    v
Repository:
  selects predefined structural SQL
  uses @Qualifier if the system has multiple data sources
  binds data using ? or named parameters
    |
    v
JdbcTemplate / NamedParameterJdbcTemplate
    |
    v
DataSource / JDBC Driver / Database
```

Before shipping SQL from a repository to production, self-check:

1. Has every untrusted value been bound using a parameter?
2. Is any structural SQL element still concatenated directly from the request, such as table, column, direction, or predicate? If so, has an allowlist or controlled query builder been used?
3. Do the value order/types match the `?` positions and column types?
4. If input contains `'`, `%`, `_`, Unicode, or NULL, does the query preserve the intended semantics?
5. If a list is needed, does `IN` have a reasonable number of markers and handle empty lists?
6. Does the SQL restrict by tenant/access permissions properly, preventing data leaks outside scope?
7. Do write statements have proper transaction boundaries and check affected rows?
8. For multi-result queries, is pagination/sorting applied where needed?
9. Are sensitive personal values/secrets being logged unnecessarily?
10. Have integration tests run against the real production DBMS or an equivalent engine, not only H2?

## 11. Self-Check Questions

1. Why is `String sql = "SELECT ... WHERE email = '" + email + "'"` unsafe even if the email format has already been validated?
2. In JDBC, which marker does `ps.setString(1, value)` bind to? Why is index 0 not used?
3. When a user enters `O'Reilly@example.test`, what does PreparedStatement do differently from manual string concatenation?
4. What effect does binding the value `' OR 1=1 --` to `WHERE email = ?` have on the **SQL structure**?
5. Why can't you use `ORDER BY ?` to select a sort column name from a request? How should an allowlist be designed?
6. If a user selects three IDs, why is `IN (?)` with a Java `List<Long>` generally not equivalent to `IN (?, ?, ?)`?
7. How does `setNull(1, Types.VARCHAR)` differ from `WHERE nickname IS NULL`?
8. Can a `PreparedStatement` be reused after execution? Do old parameter values remain or disappear automatically?
9. When do you call JDBC's `executeQuery`, `executeUpdate`, and `execute`?
10. Why does Spring `JdbcTemplate` reduce boilerplate code but **not make** concatenating SQL from user input safe?
11. Can you state that PreparedStatement always runs faster than Statement? What factors must be measured?
12. Does using a prepared statement automatically guarantee transactions, access control, or concurrency locking?

**Takeaway:** `PreparedStatement` is the **boundary between SQL syntax decided by code and values supplied by data**. Place `?` at value positions and bind using JDBC/Spring; do not substitute values by string concatenation and do not try to bind structural SQL elements. Complete security also requires authorization, validation, transactions, and testing with real data.

### References

- Oracle Java — [PreparedStatement: Creating and Supplying Parameters](https://docs.oracle.com/javase/tutorial/jdbc/basics/prepared.html).
- Java SE 17 — [java.sql.PreparedStatement API](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/PreparedStatement.html).
- Spring Framework 6.2 — [JDBC Core and JdbcTemplate](https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/core.html).
- Spring Framework 6.2 — [JdbcTemplate API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html).
- OWASP — [SQL Injection Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html).
