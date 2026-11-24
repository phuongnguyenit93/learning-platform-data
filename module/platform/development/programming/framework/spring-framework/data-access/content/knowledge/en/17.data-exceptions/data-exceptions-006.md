# BadSqlGrammarException and SQL Errors in Spring JDBC

## 1. What Can We Learn from BadSqlGrammarException?

When an application queries the database through `JdbcTemplate`, a message like the following may appear:

```text
org.springframework.jdbc.BadSqlGrammarException:
PreparedStatementCallback; bad SQL grammar
[SELECT missing_column FROM customer WHERE id = ?]
```

This is an **example message format**, not a fixed log format across every Spring version or JDBC driver. Real output also includes detailed messages and the underlying `SQLException` cause returned by the driver.

What to understand: `BadSqlGrammarException` indicates that **the SQL statement was rejected by the database/driver and Spring classified that error under the invalid SQL group**. The mistake may be a syntax error, or it may be a nonexistent table/column, wrong schema, identifier issue, or syntax incompatible with the active DBMS. Therefore, reading the word "grammar" alone is not enough to pinpoint the fault.

After this lesson, you will be able to:

1. Recognize `BadSqlGrammarException` and its place in the `DataAccessException` hierarchy.
2. Understand how `SQLExceptionTranslator` converts JDBC errors into Spring exceptions.
3. Inspect the offending SQL, original `SQLException`, `SQLState`, and database error code.
4. Distinguish invalid SQL errors from duplicate keys, missing rows, connection errors, and API misuse.
5. Fix the root cause at the right layer, test on the target database, and avoid pointless retries.

The primary scope is **Spring JDBC**. A similar exception name may appear in another data technology, but you should not assume the translation pipeline and remediation are identical.

## 2. What Is BadSqlGrammarException and Where Does It Sit in the Exception Tree?

The exact class is:

```java
org.springframework.jdbc.BadSqlGrammarException
```

In Spring Framework 6.x, the core inheritance hierarchy is:

```text
java.lang.RuntimeException
  └─ org.springframework.core.NestedRuntimeException
      └─ org.springframework.dao.DataAccessException
          └─ org.springframework.dao.NonTransientDataAccessException
              └─ org.springframework.dao.InvalidDataAccessResourceUsageException
                  └─ org.springframework.jdbc.BadSqlGrammarException
```

Important consequences:

- **Unchecked exception:** `BadSqlGrammarException` is a `RuntimeException`, so applications are not forced to declare `throws` or `catch` under Java's checked exception rules.
- **Data-access-strategy independence at parent levels:** business logic can catch `DataAccessException` to handle multiple error categories uniformly; however, catching too broadly loses the ability to distinguish causes.
- **Not a transient error:** this class belongs to the `NonTransientDataAccessException` branch. Re-running the exact same SQL with the same schema and conditions will normally keep failing until the cause is fixed. Do not apply automatic retries as you might for certain temporary connection failures.
- **Retains the JDBC cause:** when Spring creates `BadSqlGrammarException` from JDBC, it keeps the original `SQLException` so driver-supplied details can be traced.

Characteristic APIs:

| API | Value | Diagnostic meaning |
| --- | --- | --- |
| `ex.getSql()` | `String` | SQL that Spring recorded as failing; usually still contains `?` placeholders. |
| `ex.getSQLException()` | Original `SQLException` | Lets you read `getSQLState()`, `getErrorCode()`, `getMessage()`, and chained errors. |
| `ex.getCause()` / `getRootCause()` | `Throwable` | Supports walking the cause chain; always check types before casting. |
| `ex.getMessage()` | Diagnostic string | Contains operation/SQL/driver context, not a stable message format for programmatic parsing. |

Never expose `getMessage()` directly in an HTTP response: the message can leak schema, SQL, or internal details and is not a stable error contract for clients.

## 3. Why Does the Program Receive BadSqlGrammarException Instead of SQLException?

Plain JDBC typically deals with `java.sql.SQLException`, which is a checked exception. Spring JDBC performs translation via `SQLExceptionTranslator`:

```text
Repository / Service
      |
      | calls JdbcTemplate.query(...), update(...), execute(...)
      v
JdbcTemplate + PreparedStatement / CallableStatement
      |
      | JDBC driver validates SQL against database
      v
SQLException (SQLState, vendor error code, message)
      |
      v
SQLExceptionTranslator
      |
      +-- classifiable: BadSqlGrammarException / other DataAccessException
      |
      +-- not specifically classifiable: UncategorizedSQLException (for example)
      v
Java code receives DataAccessException (RuntimeException)
```

Related classes:

- `org.springframework.jdbc.support.SQLExceptionTranslator`: interface with method `translate(String task, String sql, SQLException ex)`.
- `SQLExceptionSubclassTranslator`: uses JDBC 4 subclasses (such as `SQLSyntaxErrorException`) and delegates to the `SQLState`-based translator when needed.
- `SQLStateSQLExceptionTranslator`: classifies by the `SQLState` code supplied by the database.
- `SQLErrorCodeSQLExceptionTranslator`: supports vendor-specific error-code mapping tables, useful for legacy compatibility or custom classifications.

In Spring Framework 6.x, `SQLExceptionSubclassTranslator` is the default translation path; when `sql-error-codes.xml` is present at the classpath root, the system may use `SQLErrorCodeSQLExceptionTranslator`. Applications can also configure a custom translator on `JdbcTemplate`. Thus, **the exact same database error does not necessarily become the exact same `DataAccessException` subclass in every project**.

Conceptual example:

```java
// Plain JDBC: callers typically must handle SQLException.
try (PreparedStatement ps = connection.prepareStatement(
        "SELECT missing_column FROM customer")) {
    try (ResultSet rs = ps.executeQuery()) {
        // ...
    }
} catch (SQLException ex) {
    // Inspect SQLState / vendor error code and decide how to handle.
}
```

This is only an **illustrative snippet**, requiring `connection` and `java.sql.*` imports; it has no `main` and cannot run standalone. For the same error, calls through `JdbcTemplate` normally return a Spring-translated `DataAccessException`. `@Repository` by itself does not turn every plain-JDBC block catching `SQLException` into `BadSqlGrammarException`; you must use the appropriate API/translation mechanism.

### Why Doesn't the Name Necessarily Mean a "Missing Comma"?

The name "bad SQL grammar" is quite broad. Spring documentation defines this error for invalid SQL and explicitly mentions cases such as *no such table* or *no such column*. For example:

```sql
-- Syntax error:
SELEC id FROM customer;

-- Overall valid grammar, but references a nonexistent column:
SELECT missing_column FROM customer;

-- Valid structure, but the table does not exist in the current schema:
SELECT id FROM customer_not_created;
```

All three can be reported by the driver under the SQL error group, then translated by Spring into `BadSqlGrammarException`. However, **exact classification depends on the driver and translator**; do not treat the exception name alone as sole proof of the cause.

## 4. Common SQL Errors and Where to Check

| Symptom | Possible cause | First things to check |
| --- | --- | --- |
| `syntax error near ...` | Wrong keyword, comma, parentheses, alias, clause order. | Full SQL, error position reported by driver, dialect syntax. |
| `table ... not found` / `relation does not exist` | Migrations not applied, wrong schema, connected to wrong DB, table name casing mismatch. | DataSource/URL, active schema, migrations, actual table name. |
| `column ... not found` | Wrong column, alias, schema change, DTO mapping differs from SQL name. | DDL, projection, actual column name, alias and case sensitivity. |
| `unknown function` | Calling a function absent in DB, wrong schema, or another vendor's syntax. | DB version, function signature, dialect, execution privileges. |
| `invalid identifier` / quoted name error | Identifier collides with SQL keyword or improper quoting/casing. | RDBMS quoting/casing rules; actual SQL sent. |
| SQL works on H2 but fails on PostgreSQL/MySQL | Dialect differences, inconsistent data types/`RETURNING`/`LIMIT`/`UPSERT`. | Re-test with integration tests on the production DB engine. |
| SQL has `?` placeholders but mismatched arguments | Wrong bind count or type, or wrong args passed in code. | `JdbcTemplate` overload, argument list; **do not assume** the error is always `BadSqlGrammarException`. |

**Distinguish three cause layers:** SQL *syntax* (statement structure), *schema* (objects referenced by SQL), and *environment* (DB URL, schema search path, migration version, permissions). An SQL statement that compiles in environment A can still fail in B if the schema differs.

### Easily Overlooked Identifier Error Example

```sql
SELECT c.email
FROM customer AS c
WHERE customer.id = ?;
```

In many RDBMSs, once alias `c` is defined, referencing `customer.id` in the same query can be invalid; you usually must use `c.id`. Something that looks like "SQL grammar" may simply be an alias mistake.

Also watch out for column names like `order` or `user`, which may collide with keywords depending on the DB. Quoting syntax is inconsistent: some DBMSs use double quotes, while others use backticks or square brackets. Do not swap quote characters blindly as a universal trick across RDBMSs.

## 5. Reading Standard Details from the Exception to Isolate the Error

In Spring JDBC error handling, catch `BadSqlGrammarException` at the layer responsible for diagnostics or error mapping, then extract information from both the exception itself and its JDBC cause.

```java
import java.sql.SQLException;
import org.springframework.jdbc.BadSqlGrammarException;

try {
    jdbcTemplate.queryForObject(
            "SELECT missing_column FROM customer WHERE id = ?",
            String.class, customerId);
} catch (BadSqlGrammarException ex) {
    // SQL that JdbcTemplate recorded as executing:
    String sql = ex.getSql();

    // Original error from the JDBC driver:
    SQLException jdbcError = ex.getSQLException();

    String state = jdbcError == null ? null : jdbcError.getSQLState();
    Integer vendorCode =
            jdbcError == null ? null : jdbcError.getErrorCode();

    // Use the application's centralized logging system; this example
    // only illustrates the diagnostic data to capture.
    System.err.println("SQLState=" + state + ", vendorCode=" + vendorCode);
    System.err.println("SQL=" + sql);

    throw ex;
}
```

This is an **illustrative code snippet in a repository**, requiring `jdbcTemplate` and `customerId`; it is not a standalone runnable program. In production, use a logger and request correlation ID; never print SQL/parameters containing sensitive data publicly.

Meaning of each field:

1. **`getSql()`:** identifies which statement failed, especially when multiple query branches exist. It may still contain `?` placeholders and does not necessarily include bound values. Do not try to manually concatenate values in place of `?` to "reconstruct" the SQL.
2. **`getSQLException().getSQLState()`:** string code returned by the driver per SQLState standards or vendor extensions. The first two characters usually indicate the error group; not every database always returns a complete/useful code.
3. **`getSQLException().getErrorCode()`:** vendor-specific integer code; interpret only against the documentation of that exact DBMS and driver.
4. **`getSQLException().getMessage()`:** message from the database, which may name the missing object or error position. Do not rely on localized message substrings for business logic.
5. **`getSQLException().getNextException()`:** some drivers provide a chain of additional JDBC errors; useful when the root message is insufficient.
6. **`getRootCause()` and stack trace:** show the Spring/JDBC call site and original exception. Preserve the cause when wrapping exceptions.

For example, in H2, a "column not found" error typically has `SQLState = 42S22`; class `42` only indicates the SQL syntax/access-rule group, while `S22` is the specific code. In PostgreSQL, "undefined column" is typically `42703`. **Do not hardcode** a single code to detect errors across all RDBMSs.

## 6. Runnable Java 17+ Demo: Intentionally Triggering an SQL Error and Diagnosing It

This demo uses **Spring JDBC + in-memory H2**, completely separate from real application code. The program creates a table with a `full_name` column, inserts a valid record, and then intentionally queries `missing_column` to trigger an SQL error. Finally, it queries the table properly to prove a bad SQL query does not corrupt valid data.

Structure:

```text
bad-sql-grammar-demo/
├── build.gradle
└── src/
    └── main/
        └── java/
            └── Demo.java
```

`build.gradle` (Gradle Groovy DSL, with JDK 17+):

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-jdbc:6.2.12'
    runtimeOnly 'com.h2database:h2:2.3.232'
}

application {
    mainClass = 'Demo'
}
```

`src/main/java/Demo.java`:

```java
import java.sql.SQLException;

import org.springframework.jdbc.BadSqlGrammarException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

public final class Demo {

    private static final String WRONG_SQL =
            "SELECT missing_column FROM customer WHERE id = ?";

    public static void main(String[] args) {
        DriverManagerDataSource dataSource = new DriverManagerDataSource(
                "jdbc:h2:mem:bad_sql_demo;DB_CLOSE_DELAY=-1", "sa", "");

        JdbcTemplate jdbc = new JdbcTemplate(dataSource);

        jdbc.execute("""
                CREATE TABLE customer (
                    id BIGINT PRIMARY KEY,
                    full_name VARCHAR(100) NOT NULL
                )
                """);

        jdbc.update(
                "INSERT INTO customer (id, full_name) VALUES (?, ?)",
                1L, "An");

        try {
            jdbc.queryForObject(WRONG_SQL, String.class, 1L);
            throw new AssertionError(
                    "Expected BadSqlGrammarException");
        } catch (BadSqlGrammarException ex) {
            SQLException jdbcError = ex.getSQLException();
            if (jdbcError == null || jdbcError.getSQLState() == null) {
                throw new IllegalStateException(
                        "Expected SQLState from H2", ex);
            }

            String state = jdbcError.getSQLState();
            System.out.println("caught=" + ex.getClass().getSimpleName());
            System.out.println("sqlStateClass=" + state.substring(0, 2));
            System.out.println("sqlMatches=" + WRONG_SQL.equals(ex.getSql()));
        }

        Integer rows = jdbc.queryForObject(
                "SELECT COUNT(*) FROM customer", Integer.class);
        System.out.println("rows=" + rows);
    }
}
```

In the project directory, run:

```bash
gradle run
```

If the project already includes the Gradle Wrapper, you can run `./gradlew run` on Linux/macOS or `.\gradlew.bat run` in Windows PowerShell. Spring and H2 dependencies will be downloaded from Maven Central if not already cached locally.

**Stdout printed by `Demo.main()`** (excluding Gradle logs and library startup output):

```text
caught=BadSqlGrammarException
sqlStateClass=42
sqlMatches=true
rows=1
```

How to read the output:

- `caught=BadSqlGrammarException`: Spring translated the driver error into the corresponding subclass.
- `sqlStateClass=42`: H2 reported an error in the SQL syntax/access group; no need to rely on the entire vendor-specific code.
- `sqlMatches=true`: `getSql()` recorded the exact failing query.
- `rows=1`: the previous `INSERT` succeeded; the bad query did not erase already-written data. The demo does not wrap the operations in a transaction.

The example uses `DriverManagerDataSource` to keep the test environment simple; this is not a production connection pool. Do not treat the output above as a guarantee for other DBs or application-customized translators.

### Replacing the Bad Query with the Right Query

Simply replace `WRONG_SQL` with a valid query:

```sql
SELECT full_name FROM customer WHERE id = ?;
```

Then the statement can return `"An"` as in the example. At the same time, you must **remove the block intentionally expecting an exception** in the `try` block; do not run the failure assertion once the SQL is fixed. When the error stems from a missing column in the schema, the fix may be a real migration/schema update rather than arbitrarily changing the SQL.

## 7. Frequently Confused Data Error Types

Not every error occurring during a query is `BadSqlGrammarException`. Here are cases to distinguish:

| Situation | Spring exception you may encounter | Meaning |
| --- | --- | --- |
| Invalid SQL syntax, nonexistent table/column | `BadSqlGrammarException` | SQL was deemed invalid by the driver/database per translator classification. |
| Valid `SELECT` returns no rows with `queryForObject` expecting one row | `EmptyResultDataAccessException` | No data returned; the SQL syntax itself is valid. |
| `queryForObject` expects one row, but query returns multiple rows | `IncorrectResultSizeDataAccessException` | Result count violates the application contract. |
| `INSERT` violates unique/primary key | `DuplicateKeyException` or `DataIntegrityViolationException` group | Constraint violation, not automatically an SQL grammar mistake. |
| `INSERT` violates NOT NULL/FK/CHECK | `DataIntegrityViolationException` | Data does not satisfy DB constraints. |
| Unable to obtain JDBC connection | `CannotGetJdbcConnectionException` (or another connection-error group) | System has no connection to execute the query. |
| Driver throws an SQL error the translator cannot classify specifically | `UncategorizedSQLException` | Requires inspecting `SQLException` and translator setup. |
| Misusing parameter API from Java before sending SQL | Possibly `InvalidDataAccessApiUsageException` or another error | Not the same as database SQL grammar. |

These are **typical classification examples, not absolute rules for every driver/translator**. When an application has a custom exception translator or uses ORM/JPA/R2DBC instead of JDBC, the exact subclass may differ.

### "No Data" vs. "Invalid SQL"

Suppose table `customer` is valid, but no record with `id=99` exists:

```java
String name = jdbcTemplate.queryForObject(
        "SELECT full_name FROM customer WHERE id = ?",
        String.class, 99L);
```

If the query returns **0 rows**, the issue lies in `queryForObject`'s contract and is typically `EmptyResultDataAccessException`, not `BadSqlGrammarException`. You need a business decision for not-found: return `Optional.empty()`, 404 at the API, or a meaningful domain result. Do not "fix the SQL" when the table and columns are already right.

### "Duplicate Key" vs. "Invalid SQL"

```sql
INSERT INTO customer (id, full_name) VALUES (1, 'An');
INSERT INTO customer (id, full_name) VALUES (1, 'Binh');
```

The second statement has **valid syntax** yet can violate `PRIMARY KEY`. It belongs to the data integrity error group and should not be handled by tweaking commas or retrying the exact same statement endlessly.

## 8. Step-by-Step Debugging Workflow for BadSqlGrammarException

### Step 1 — Identify the Actual SQL and Caller

From the stack trace, locate the service/repository calling `JdbcTemplate`, `NamedParameterJdbcTemplate`, or the API building SQL. Read `ex.getSql()` if available. Do not edit a similar-looking SQL string in source code that is not actually called on the failing path.

When using named parameters, note that the initial SQL string looks like `:customerId` but after Spring processes it, it becomes `?` at the JDBC layer. Errors from missing named parameter values can occur **before sending SQL to the database**, producing a different exception type.

### Step 2 — Read the Original Message and Driver-Returned Codes

Record `SQLState`, `errorCode`, message, and if needed `nextException`. Check the database, driver version, and active translator. For instance, "column not found" points you to DDL/aliases, whereas "syntax error near LIMIT" points you to the SQL dialect.

### Step 3 — Verify the Exact Data Environment

- Database URL, catalog/schema name, current user, and permissions.
- Which migration version has been applied, and whether columns have the expected names and types.
- Actual DDL versus the deployed entity/DAO.
- Casing/quoting of table and column names.
- Whether multiple instances are deployed against different databases/schemas.

Do not take success on local H2 as proof that production PostgreSQL, MySQL, or Oracle will accept the exact same SQL.

### Step 4 — Test the Query Under Control

Reproduce on a test database with an equivalent schema; use the right dialect and valid parameters. For write operations, test in an isolated environment or a rolled-back transaction as appropriate. Never paste real data or secrets into public debugging tools.

Be careful with SQL containing `?` placeholders: the string shown in logs may not run directly in an SQL console unless you substitute safe test literals of the right types. Keep the same JDBC bind types when reproducing via the application.

### Step 5 — Fix the Root Cause and Write Regression Tests

If caused by a wrong column, fix the code or migration to match the **source-of-truth schema**. If caused by querying the wrong schema, fix the connection configuration/search path. If caused by SQL dialect, choose compatible syntax or query structure. Write an integration test against the target driver, covering the execution path that previously failed.

Do not apply a "fix" like:

```java
try {
    return jdbcTemplate.queryForList(sql);
} catch (BadSqlGrammarException ignored) {
    return java.util.List.of();
}
```

This **hides system bugs and turns a query failure into an empty list**, misleading callers into thinking no data exists. This code merely illustrates an anti-pattern; it requires appropriate variables/imports and is not a standalone program.

## 9. Handling Exceptions at the Right Layer and Avoiding Blind Retries

Because `BadSqlGrammarException` is non-transient, retrying the same SQL without fixing schema/dialect/column names usually yields the same failure. Nor should you use this exception to dump full SQL errors directly back to clients.

In a repository, it is usually best to let the exception propagate (or add useful context and rethrow) so the system observes the failure. At the API boundary, convert it into an **appropriate server error** response per the application contract while logging internal details with a correlation ID.

```java
// Illustrative example, not a standalone class.
try {
    return jdbcTemplate.queryForObject(
            "SELECT full_name FROM customer WHERE id = ?",
            String.class, customerId);
} catch (BadSqlGrammarException ex) {
    SQLException sqlCause = ex.getSQLException();
    String state = sqlCause == null ? null : sqlCause.getSQLState();

    logger.error(
            "CustomerRepository query failed; SQLState={}", state, ex);
    throw ex;
}
```

The snippet above requires `logger`, `jdbcTemplate`, and `customerId` to already exist. In Spring Boot, unhandled exceptions normally pass through the web layer's error handling; mapping them to specific HTTP codes must follow application rules. Do not assume "BadSqlGrammarException = HTTP 400": invalid SQL inside a repository is normally a server-side bug, not proof of invalid client input.

**Distinguish request errors from query errors:** if the user sends invalid parameters, validate input at the boundary. If repository code itself generates invalid SQL, treat it as a deployment/migration bug. Both can appear in the same request, but they require fixes in different places.

### How Are Transactions Affected?

`BadSqlGrammarException` is a `RuntimeException`. Under Spring's default `@Transactional` rules, an unchecked exception escaping a transactional method normally marks it for rollback. However, actual outcomes depend on transaction boundaries, rollback rules, transaction manager type, autocommit, and previously committed operations.

Do not assume "all SQL statements before the error rolled back" if they ran in a separate transaction or autocommit mode. Conversely, do not swallow the exception to continue a transaction when DB/transaction state is no longer clear.

## 10. Testing and Observability

Include the following tests per the lesson goals:

1. **Valid query test:** with a table having `id` and `full_name`, `SELECT full_name ...` returns the expected value for an existing ID.
2. **Invalid query test:** querying a nonexistent column must demonstrate the `SQLException` -> `DataAccessException` translation path, yielding `BadSqlGrammarException` under the current driver setup.
3. **SQLState test:** verify class `42` with H2 on a nonexistent column; do not assert that code `42S22` applies across all RDBMSs.
4. **No-row test:** with valid SQL and a nonexistent ID, properly handle `EmptyResultDataAccessException` or map to a business outcome.
5. **Constraint test:** duplicate key/NOT NULL errors are classified into the integrity group, not mistakenly caught as "no data".
6. **Migration test:** CI or integration tests must apply DDL/migrations matching the target environment before running repository tests.
7. **Transaction path test:** write operations followed by a failing query should have tests confirming proper rollback behavior.
8. **Safe logging:** log task, repository site, SQLState, vendor code, correlation ID, and stack trace internally; guard SQL and parameters containing sensitive information.

`JdbcTemplate` supports configuring a custom `SQLExceptionTranslator`; change the translator only when there is a clear need and tests exist for each error/vendor code. **Changing the translator to make an error "look less severe" does not fix bad SQL**.

## 11. Self-Check Questions

**Question 1.** Is `BadSqlGrammarException` exclusively for misspelled SQL keywords?

No. It can represent invalid SQL caused by nonexistent tables/columns, wrong schemas, or incompatible syntax/dialects. Inspect the original `SQLException` for details.

**Question 2.** With `JdbcTemplate`, why are you not forced to declare `throws SQLException`?

Because Spring uses `SQLExceptionTranslator` to translate JDBC errors into `DataAccessException` subclasses, which are unchecked exceptions, when errors occur through Spring-managed execution paths.

**Question 3.** Which two specific details should be inspected from the JDBC cause?

`SQLException.getSQLState()` and `getErrorCode()`, alongside `getMessage()` and the failing SQL; do not rely solely on the `bad SQL grammar` message.

**Question 4.** What does a valid `SELECT` with zero rows using `queryForObject` typically throw?

`EmptyResultDataAccessException`, which is distinct from an invalid SQL statement.

**Question 5.** Should you automatically retry `BadSqlGrammarException` three times?

Usually no, because it is a non-transient error. Unless SQL/schema/driver changes, repeating the exact same query will not resolve the cause.

**Question 6.** Is a primary-key duplicate necessarily a `BadSqlGrammarException`?

No. Drivers and translators normally classify it as `DuplicateKeyException` or `DataIntegrityViolationException`. The `INSERT` syntax can be completely valid even when data violates a constraint.

## 12. Key Takeaways

```text
JdbcTemplate / Spring JDBC
       |
       v
     SQL query/update
       |
       v
SQLException returned by driver/database
  ├─ SQLState
  ├─ vendor error code
  └─ message / nextException
       |
       v
SQLExceptionTranslator
       |
       v
BadSqlGrammarException (a DataAccessException branch)
       |
       v
Inspect getSql() + getSQLException()
       |
       v
Compare SQL + schema + dialect + environment
       |
       v
Fix the root cause and write integration tests
```

**Core rule:** `BadSqlGrammarException` tells you Spring classified an SQL error into the invalid-SQL group; it **does not by itself pinpoint the exact cause**. Read the executed SQL, inspect the original `SQLException`, verify schema/dialect/connection, and fix the root cause. Do not turn SQL failures into empty results, do not leak sensitive info, and do not retry without justification.

### Official References

- Spring Framework Reference — *Using SQLExceptionTranslator* in JDBC Core: https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/core.html
- Spring Framework Javadoc — `BadSqlGrammarException`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/BadSqlGrammarException.html
- Spring Framework Javadoc — `SQLExceptionTranslator`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/support/SQLExceptionTranslator.html
- Spring Framework Javadoc — `SQLExceptionSubclassTranslator`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/support/SQLExceptionSubclassTranslator.html
- Spring Framework Javadoc — `InvalidDataAccessResourceUsageException`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/dao/InvalidDataAccessResourceUsageException.html
- H2 Database — *Error Codes*: https://h2database.com/html/error-codes.html
