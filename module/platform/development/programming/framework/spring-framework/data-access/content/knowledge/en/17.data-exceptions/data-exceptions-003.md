# SQLExceptionTranslator and Choosing How to Classify Data Exceptions

## 1. Goal: From JDBC Errors to Application-Meaningful Errors

In Spring Framework – Data Access, JDBC operations can throw `java.sql.SQLException`. This exception provides information from the driver and database, but class names, error codes, and messages are not completely uniform across PostgreSQL, MySQL, Oracle, SQL Server, or different JDBC drivers. If the service layer must understand every error code of every database, business code becomes tightly coupled to infrastructure and breaks easily when changing drivers.

`org.springframework.jdbc.support.SQLExceptionTranslator` is a **classification strategy**: it takes an `SQLException` and converts it into an exception within the `org.springframework.dao.DataAccessException` hierarchy. `JdbcTemplate` and related components use this mechanism to present data access failures more consistently.

Three separate questions must be understood:

1. **What is the actual JDBC error?** Read `SQLException`, `SQLState`, vendor code, cause chain, and driver information.
2. **What does Spring classify this error into?** For example, `DuplicateKeyException`, `DataIntegrityViolationException`, `BadSqlGrammarException`, `CannotAcquireLockException`, or `UncategorizedSQLException`.
3. **What should the application do?** Fix input, handle conflict, roll back, perform bounded retries, or report an infrastructure error. The translator **does not retry automatically, does not commit/roll back instead of the transaction manager, and does not decide HTTP status codes**.

This lesson focuses on Spring JDBC 6.x and Java 17+. For modules using another Spring Framework version, verify the default translator and mapping tables for that exact version.

## 2. The Path of an SQLException in Spring JDBC

~~~text
SQL + parameters
    |
    v
JdbcTemplate.query/update/batchUpdate/execute
    |
    v
JDBC driver + database
    |
    +-- success --> mapped value/list
    |
    +-- SQLException
            |
            v
       SQLExceptionTranslator
            |
            +-- matches subclass / SQLState / vendor code --> specific DataAccessException
            |
            +-- no match --> fallback; if still unclassifiable:
                                 UncategorizedSQLException at JdbcTemplate layer
            |
            v
       Repository -> Service -> transaction / API boundary
~~~

For example, an `INSERT` violating a unique key may be classified by Spring as `DuplicateKeyException`. However, the outcome **is not an absolute guarantee**: the `SQLException` type thrown by the driver, `SQLState`, vendor code, translator strategy, and Spring version all affect the result.

`DataAccessException` is an **unchecked** exception (extending `RuntimeException`), saving callers from declaring `throws SQLException` on every `JdbcTemplate` operation. That **does not** mean every error is transient or retryable.

## 3. Contract of SQLExceptionTranslator

Core interface:

~~~java
package org.springframework.jdbc.support;

import java.sql.SQLException;
import org.springframework.dao.DataAccessException;

@FunctionalInterface
public interface SQLExceptionTranslator {
    DataAccessException translate(
        String task, String sql, SQLException ex);
}
~~~

This is a **simplified signature for learning**, not code to recreate in a project. Parameter meanings:

| Parameter | Meaning | Points to remember |
| --- | --- | --- |
| `task` | Description of the operation, e.g. `"insert employee"` | Provides context for messages/logs |
| `sql` | Related SQL statement; may be `null` | Do not assume full SQL is always present; avoid exposing sensitive data |
| `ex` | Original `SQLException` | Contains SQLState, vendor code, type, cause, and next-exception chain |
| Return value | Classified `DataAccessException`, **or `null`** | `null` means the translator did not recognize it, not that the SQL succeeded |

Common pitfall: calling `translator.translate(...)` **directly** can return `null`. Conversely, inside `JdbcTemplate`'s execution flow, if no translator recognizes the error, the template has a mechanism to throw `UncategorizedSQLException`. Do not write:

~~~java
DataAccessException result = translator.translate(task, sql, ex);
// Incorrect if assuming result is always non-null:
throw result;
~~~

Instead, if **invoking the translator manually in a JDBC adapter**, you must decide the fallback:

~~~java
DataAccessException translated =
    translator.translate("load report", sql, originalSqlException);

if (translated != null) {
    throw translated;
}
throw new org.springframework.jdbc.UncategorizedSQLException(
    "load report", sql, originalSqlException);
~~~

The snippet above is a **code fragment** whose variables `translator`, `sql`, and `originalSqlException` are provided by the caller, not a standalone program. Prefer letting `JdbcTemplate` manage resources and translation whenever possible.

A custom translator should **preserve the original `SQLException` in the cause chain** so `SQLState` and driver codes remain inspectable. When a custom error code is not recognized, return `null` so fallback can run; do not force every unfamiliar error into an overly specific subtype.

## 4. Three Input Signals: Exception Type, SQLState, and Vendor Code

`SQLException` carries multiple complementary sources of information:

| Signal | Example | Strength | Limitation |
| --- | --- | --- | --- |
| Java subclass | `SQLIntegrityConstraintViolationException`, `SQLSyntaxErrorException`, `SQLTimeoutException` | Modern JDBC drivers can classify directly | Drivers may throw generic `SQLException` or insufficiently specific subclasses |
| `getSQLState()` | `"23505"`, `"42000"`, `"40001"` | SQLState standard has cross-DBMS meaning | Compliance, extended codes, and detailed semantics vary; sometimes `null` |
| `getErrorCode()` | MySQL `1062`, Oracle `1` (e.g., duplicate key) | Can distinguish very specific vendor cases | Not portable: identical numbers can mean different things in other DBs |
| `getNextException()` / `getCause()` | Constraint error nested inside a batch error | More accurate diagnostics when a general error wraps a specific one | Not every translator/driver traverses every element identically |

**SQLState** is usually 5 characters; the first two characters denote the *class*. Common illustrative examples:

| SQLState class | General interpretation |
| --- | --- |
| `08` | Connection-related error |
| `22` | Invalid data/value |
| `23` | Data integrity constraint violation |
| `40` | Transaction rollback/serialization/deadlock per DB rules |
| `42` | SQL syntax or permission/object-access error per some drivers |
| `HY` | Vendor/ODBC-defined status codes, without uniform standard semantics across DBs |

For example, `23505` usually indicates a **unique violation**, `23503` usually a **foreign-key violation**, and `40001` usually a serialization failure. However, whether Spring returns `DuplicateKeyException` or another subtype **depends on the translator**. Do not handle errors solely with `sqlState.startsWith("23")` when the business requirement is "duplicate unique key", because class 23 also covers foreign key, NOT NULL, and check constraints.

The `sql` parameter passed to the translator supports diagnostic messages, not a source of truth for guessing errors by searching for `"INSERT"`/`"UPDATE"`. In particular, do not inspect driver message text like `"duplicate entry"` to drive stable logic.

## 5. DataAccessException: What Does Classification Mean to Callers?

Spring's hierarchy has many subtypes. Key subtypes in the Data Access layer:

| Group / exception | Common meaning | Appropriate handling |
| --- | --- | --- |
| `DuplicateKeyException` | Specifically recognized unique/primary key violation | Handle duplicate ID, idempotency, or conflict response |
| `DataIntegrityViolationException` | Constraint/data violation, including unique if not classified more specifically | Validate data, constraints, and business rules; **do not retry blindly** |
| `BadSqlGrammarException` | SQL/query structure incompatible with DB, e.g. syntax/wrong column or table name | Fix SQL, schema, migration; do not treat as a user input error by default |
| `QueryTimeoutException` | Operation timed out per driver/DB/framework mechanism | Check timing, transaction, and outcome status before retrying |
| `CannotAcquireLockException` | Failed to acquire lock per recognized error type | Consider retrying a new transaction with backoff, if the operation is safe |
| `PessimisticLockingFailureException` | Lock failure under the broader classification branch | Check lock contention, deadlock, isolation |
| `CannotSerializeTransactionException` | Unable to serialize transaction | Retry the **entire transaction** when idempotency is ensured |
| `DataAccessResourceFailureException` | DB/connection resource inaccessible | Monitor infrastructure, configuration, network |
| `UncategorizedSQLException` | JDBC error occurred but could not be classified specifically | Keep SQLState/vendor code, observe, and add appropriate cases |

`DuplicateKeyException` is a subtype of `DataIntegrityViolationException`; therefore catching `DataIntegrityViolationException` also covers recognized unique errors, but **you cannot infer the reverse**—not every `DataIntegrityViolationException` is a duplicate key.

Do not label the entire table "transient". Some branches of `DataAccessException` reflect transient or non-transient issues, yet application behavior still must evaluate write side effects, transactions, timeouts, and retry safety. For instance, receiving `QueryTimeoutException` **does not guarantee** the database did not execute the operation, especially when a connection drops or commit status is uncertain.

## 6. Three Main Classification Strategies and the Spring 6.x Default

### 6.1. SQLExceptionSubclassTranslator

`org.springframework.jdbc.support.SQLExceptionSubclassTranslator` recognizes JDBC 4 subclasses such as `SQLSyntaxErrorException`, `SQLIntegrityConstraintViolationException`, `SQLTimeoutException`, and several additional cases. If information is insufficient, it falls back to `SQLStateSQLExceptionTranslator`.

**Since Spring Framework 6.0, this is the standard default translator** when no special vendor configuration file is present. Advantages: less database coupling, no need to probe vendor codes via metadata, and usually sufficient for modern JDBC systems.

Remember: two drivers may report the same duplicate-key error using different subclasses/SQLStates. Classification results can then differ even though the business SQL is identical.

### 6.2. SQLStateSQLExceptionTranslator

`org.springframework.jdbc.support.SQLStateSQLExceptionTranslator` uses SQLState/class and certain known specific codes to classify errors. It does not need to detect the database product name and is usually placed **after** the primary translator.

Suitable when the driver supplies reliable SQLStates or when you need a portable fallback. It cannot map every situation precisely, because the same SQLState class can encompass multiple distinct causes.

### 6.3. SQLErrorCodeSQLExceptionTranslator

`org.springframework.jdbc.support.SQLErrorCodeSQLExceptionTranslator` relies on **vendor-specific error codes** via a database's `SQLErrorCodes` configuration. Spring has `SQLErrorCodesFactory`, which reads the database name from `DatabaseMetaData.getDatabaseProductName()` to select the appropriate error-code table.

This strategy can distinguish errors better when subclass/SQLState is insufficient, in exchange for needing to verify database names, error codes, and configuration. `sql-error-codes.xml` is bundled in Spring JDBC, and **an application-supplied file of the same name at the classpath root** can cause Spring to automatically choose the vendor-code strategy per 6.x documentation. When a custom file is placed on the classpath, you must understand its override/configuration scope and test all DB types the application uses.

**Do not equate "Spring ships built-in vendor code tables" with "Spring 6 always uses vendor code tables by default".** Without a user configuration file or explicit translator configuration, Spring 6's normal default is `SQLExceptionSubclassTranslator`.

### 6.4. Decision Table

| Observed condition | Recommended strategy | Verification |
| --- | --- | --- |
| Spring 6 project, modern JDBC driver; no specific classification issue | Keep default `SQLExceptionSubclassTranslator` with SQLState fallback | Integration tests for real errors |
| Driver throws generic `SQLException` but SQLState has standard values | Rely on SQLState fallback; customize only if results fall short of business needs | Test constraint, timeout, and lock errors |
| A specific vendor code requires more accurate mapping | Choose `SQLErrorCodeSQLExceptionTranslator` / `SQLErrorCodes` for that DB | Verify product name, code, fallback |
| Need a specialized exception policy with small scope | Use `setCustomTranslator(...)` on the specific `JdbcTemplate` | Return exception only on matching case, otherwise `null` |
| Application uses multiple database engines | Prefer general classification; customize **conditionally per DB** if needed | Test matrix across each driver/version |
| Unknown error, insufficient evidence | Keep `UncategorizedSQLException` or appropriate broad type, add telemetry | Do not assume it is retryable |

## 7. Fallback, Precedence, and Non-Matching Cases

An `AbstractFallbackSQLExceptionTranslator` layer can try a custom translator first, then the primary strategy, and then fallback. In Spring 6.1+, `setCustomTranslator(...)` is the proactive way to specify an override translator.

General chain in a vendor-code configuration:

~~~text
custom override (if present)
        |
        +-- unrecognized / returns null
        v
SQLErrorCodes table / vendor code
        |
        +-- unrecognized
        v
SQLExceptionSubclassTranslator
        |
        +-- unrecognized
        v
SQLStateSQLExceptionTranslator
        |
        +-- unrecognized
        v
null from translator
        |
        v
JdbcTemplate throws UncategorizedSQLException
~~~

Some `SQLErrorCodeSQLExceptionTranslator` configurations also have custom translators attached to `SQLErrorCodes` and `CustomSQLErrorCodesTranslation`; exact ordering follows the documentation of the Spring version in use. The diagram above is a learning aid and does not detail every branch or all `BatchUpdateException` cases.

Implementation rule: **only override exceptions you identify with evidence**, keeping fallback intact so standard behavior is not lost. Writing a custom translator that always returns `DataIntegrityViolationException` for every `SQLException` will misclassify network or syntax errors as data integrity violations.

## 8. Runnable Java 17 Example: Observing Classification Strategies

The following example constructs **simulated** `SQLException`s **without connecting to a DB**. It helps illustrate the difference between subclass/SQLState and vendor codes we declare ourselves. Results depend on Spring JDBC pinned at **6.2.14** and do not represent every real driver.

Create structure:

~~~text
sql-translation-demo/
  pom.xml
  src/main/java/example/SqlTranslationDemo.java
~~~

File `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>sql-translation-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.14</version>
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
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

File `src/main/java/example/SqlTranslationDemo.java`:

~~~java
package example;

import java.sql.SQLException;
import java.sql.SQLIntegrityConstraintViolationException;
import java.sql.SQLSyntaxErrorException;
import java.sql.SQLTimeoutException;

import org.springframework.dao.DataAccessException;
import org.springframework.jdbc.support.SQLExceptionSubclassTranslator;
import org.springframework.jdbc.support.SQLExceptionTranslator;
import org.springframework.jdbc.support.SQLErrorCodeSQLExceptionTranslator;
import org.springframework.jdbc.support.SQLErrorCodes;

public class SqlTranslationDemo {

    private static void printCategory(
            String label,
            SQLExceptionTranslator translator,
            SQLException original) {

        DataAccessException translated =
            translator.translate("sample operation", "SELECT 1", original);

        String category = translated == null
            ? "null"
            : translated.getClass().getSimpleName();

        System.out.println(label + " -> " + category);
    }

    public static void main(String[] args) {
        SQLExceptionTranslator standard =
            new SQLExceptionSubclassTranslator();

        printCategory("unique", standard,
            new SQLIntegrityConstraintViolationException(
                "duplicate key", "23505", 0));

        printCategory("syntax", standard,
            new SQLSyntaxErrorException("invalid SQL", "42000", 0));

        printCategory("timeout", standard,
            new SQLTimeoutException("request timed out", "HYT00", 0));

        printCategory("unknown", standard,
            new SQLException("unrecognized", "ZZ999", 0));

        SQLErrorCodes vendorCodes = new SQLErrorCodes();
        vendorCodes.setDuplicateKeyCodes("7777");

        SQLExceptionTranslator vendor =
            new SQLErrorCodeSQLExceptionTranslator(vendorCodes);

        printCategory("vendor", vendor,
            new SQLException("simulated vendor violation", "HY000", 7777));
    }
}
~~~

Run in the project directory with **JDK 17+ and Maven 3.x** (Maven downloads libraries if not yet cached):

~~~bash
mvn -q compile exec:java -Dexec.mainClass=example.SqlTranslationDemo
~~~

Expected output with Spring JDBC 6.2.14:

~~~text
unique -> DuplicateKeyException
syntax -> BadSqlGrammarException
timeout -> QueryTimeoutException
unknown -> null
vendor -> DuplicateKeyException
~~~

Explanation:

- `unique`: the constraint violation subclass plus SQLState `23505` is enough for Spring to recognize duplicate key.
- `syntax`: the JDBC syntax error subclass is classified as `BadSqlGrammarException`.
- `timeout`: JDBC `SQLTimeoutException` is classified as `QueryTimeoutException`.
- `unknown`: calling the translator directly returns `null` because no matching signal is present; if run through `JdbcTemplate`, the template layer creates an uncategorized exception.
- `vendor`: code **7777 is completely simulated for this lesson**. Only the custom `SQLErrorCodes` configuration turns that error into `DuplicateKeyException`. Do not put this code into production without DB documentation proving its meaning.

Although the program runs, **this only tests translator behavior**; it cannot prove a real JDBC driver will emit the simulated `SQLException`/SQLState/vendor code.

## 9. Applying a Translator on JdbcTemplate in a Spring Application

Most applications using `JdbcTemplate` do not need to call `SQLExceptionTranslator` manually. Calling `jdbcTemplate.update(...)` automatically translates `SQLException` into `DataAccessException`:

~~~java
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class EmployeeRepository {
    private final JdbcTemplate jdbc;

    public EmployeeRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void addEmployee(long id, String name) {
        jdbc.update(
            "INSERT INTO employee(id, full_name) VALUES (?, ?)",
            id, name
        );
    }
}
~~~

This is a **Spring JDBC component**, requiring a `JdbcTemplate` bean, `DataSource`, driver, and an actual `employee` table. You cannot run this single class with `javac` without declaring Spring dependencies. When a JDBC error occurs, callers can catch the corresponding `DataAccessException` subtype; do not assume this repository always throws one single subtype across every DB.

### Configuring a Vendor-Code Translator for a JdbcTemplate

When there is evidence requiring vendor-code mapping:

~~~java
import javax.sql.DataSource;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.SQLErrorCodeSQLExceptionTranslator;

@Configuration
public class JdbcTranslationConfig {
    @Bean
    public JdbcTemplate jdbcTemplate(DataSource dataSource) {
        JdbcTemplate template = new JdbcTemplate(dataSource);
        template.setExceptionTranslator(
            new SQLErrorCodeSQLExceptionTranslator(dataSource)
        );
        return template;
    }
}
~~~

- `SQLErrorCodeSQLExceptionTranslator(dataSource)` uses metadata to find the database product name and code table; this operation may open a connection when initializing the translator. When you do not want to access metadata, you can use the constructor taking the exact database name such as `"PostgreSQL"` (if the name and mapping are verified).
- `template.setExceptionTranslator(...)` **applies only to that `JdbcTemplate` instance**. Other `JdbcTemplate` instances created separately or managed by other configurations do not automatically inherit this policy.
- This example declares one `JdbcTemplate` bean; in Spring Boot, inspect existing auto-configured beans and configure DI so repositories receive the intended instance. Avoid creating multiple templates unintentionally.
- Do not change the translator just to try to "make errors go away". A translator **only changes how errors are interpreted**; it does not fix invalid SQL, schemas, deadlocks, or constraint-violating data.

## 10. Bounded Customization Without Losing Fallback

### 10.1. Custom Translator via setCustomTranslator (Spring 6.1+)

Suppose a database has a vendor code **confirmed by official documentation** to represent a specific constraint error; we can add a custom exception mapping. The snippet below uses placeholder code `7777` to illustrate syntax:

~~~java
import java.sql.SQLException;

import org.springframework.dao.DataAccessException;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.support.SQLErrorCodeSQLExceptionTranslator;

SQLErrorCodeSQLExceptionTranslator translator =
    new SQLErrorCodeSQLExceptionTranslator(dataSource);

translator.setCustomTranslator(
    (String task, String sql, SQLException exception) -> {
        if (exception.getErrorCode() == 7777) {
            return new DataIntegrityViolationException(
                task + ": custom constraint", exception);
        }
        return null; // Allow vendor mapping and fallback to continue.
    }
);

jdbcTemplate.setExceptionTranslator(translator);
~~~

This is a **configuration fragment** in a context where `dataSource` and `jdbcTemplate` already exist, not a standalone Java class. You should also check the **database product name** before using a vendor code in a multi-DB application; the same numeric code can represent a different failure.

If configuring via `SQLErrorCodes` suffices, assigning the code to the right category can be simpler than a custom callback. Still, **do not reuse a code table for a different database** merely because the desired exception name is the same.

### 10.2. Customizing via SQLErrorCodes

Unit test example without connecting to a DB:

~~~java
SQLErrorCodes codes = new SQLErrorCodes();
codes.setDuplicateKeyCodes("7777");

SQLErrorCodeSQLExceptionTranslator translator =
    new SQLErrorCodeSQLExceptionTranslator(codes);
~~~

Like the example in section 8, this is simulated code. In production, vendor codes must be verified against the DB/driver and updated under version control. Placing `sql-error-codes.xml` at the classpath root can declare codes per database, but you must verify its exact structure and default-replacement scope; do not copy an old file from one Spring version to a newer one without checking changes in the code tables.

### 10.3. Avoiding the Legacy customTranslate Hook in New Code

Some older Spring examples override `SQLErrorCodeSQLExceptionTranslator.customTranslate(...)`. **This method has been deprecated since Spring 6.1**; for new code on Spring 6.1+, prefer `setCustomTranslator(...)` (or provide an implementation with clear fallback). When maintaining legacy applications, consult the exact Javadoc of the running version before changing the extension mechanism.

## 11. Classification Is Technical Data, Not a Business Conclusion

The same exception may require different application policies:

- If `DuplicateKeyException` occurs when creating a new resource: you may return a conflict or report that the name/ID already exists.
- If a duplicate key occurs on an idempotency key of an already-processed request: you may need to **read the previous result** and return the same result, depending on the API contract; do not assume it is a user error by default.
- If `DataIntegrityViolationException` comes from a foreign key: it could be a missing referenced entity or a bug in write ordering; inspect the actual constraint.
- If `CannotAcquireLockException`: you may retry a **new** transaction with backoff, jitter, and a retry limit, but only after verifying idempotency and operation state.
- If `QueryTimeoutException`: timeout does not mean the write never reached the DB or never committed. With a timeout/disconnect at commit time, the state may be **uncertain**.
- If `BadSqlGrammarException`: usually an application/migration bug; never return raw SQL, stack traces, or schema details to the client.

A service layer can handle broad groups:

~~~java
import org.springframework.dao.DataAccessException;
import org.springframework.dao.DataIntegrityViolationException;

public void perform() {
    try {
        repository.save();
    } catch (DataIntegrityViolationException ex) {
        // Business: inspect constraint type and respond appropriately.
        throw ex; // Preserve the error in this example.
    } catch (DataAccessException ex) {
        // Infrastructure/other: record appropriate telemetry, rethrow.
        throw ex;
    }
}
~~~

This is an **illustrative code fragment** inside a class with an appropriate `repository.save()`. Catch more specific types before parent types, because `DataIntegrityViolationException` extends `DataAccessException`. Do not turn every `DataAccessException` into HTTP 409; mapping to responses should follow an explicit policy at the API boundary.

### Transactions and Rollback

In a `@Transactional` setup via a Spring proxy, an unchecked `DataAccessException` **is rolled back by default when it escapes through the transaction interceptor**. If you catch the exception, only log it, and return normally, the transaction interceptor may not see the failure; commit/rollback behavior also depends on DB state, transaction status, and how rollback is marked.

- When you want **all-or-nothing**, normally let the exception escape the `@Transactional` method.
- When you want to retry due to deadlock/serialization, normally roll back the failed transaction and retry **the entire unit of work** in a new transaction.
- When you want partial success, you must design separate transactions/chunks, states, and retry/idempotency mechanisms. The translator does not solve these choices.

## 12. Inspecting the Underlying Error to Verify Classification

Looking only at the Spring exception name is often insufficient when investigating an incident. For example, in a batch update, `BatchUpdateException` may wrap another `SQLException` in `getNextException()`, along with an update counts array; many drivers place useful SQLState/vendor codes in the inner exception.

Information to collect in internal logs (with sensitive data masked):

| Field | Why needed |
| --- | --- |
| DB name and driver version | Explains classification differences across environments |
| `DataAccessException` type | Outcome of the active strategy |
| `SQLException` subtype | Available Java JDBC signal |
| `getSQLState()`, `getErrorCode()` | Identifies actual standard/vendor code |
| Cause + next-exception chain | Root error may be wrapped |
| Operation name, request/correlation ID, transaction ID | Links logs for investigation |
| Retry/rollback flags and commit state | Prevents repeating operations when the DB may have already written |

Example Java 17 utility method to find underlying JDBC exceptions (for **diagnostics**, not for choosing categories):

~~~java
import java.sql.SQLException;
import java.util.ArrayDeque;
import java.util.Collections;
import java.util.Deque;
import java.util.IdentityHashMap;
import java.util.Set;

public final class SqlFailureInspector {
    private SqlFailureInspector() {}

    public static void inspect(Throwable failure) {
        if (failure == null) {
            return;
        }

        Deque<Throwable> queue = new ArrayDeque<>();
        Set<Throwable> seen =
            Collections.newSetFromMap(new IdentityHashMap<>());
        queue.add(failure);

        while (!queue.isEmpty()) {
            Throwable current = queue.removeFirst();
            if (!seen.add(current)) {
                continue;
            }

            if (current instanceof SQLException sql) {
                System.out.printf(
                    "%s SQLState=%s vendorCode=%d%n",
                    sql.getClass().getSimpleName(),
                    sql.getSQLState(),
                    sql.getErrorCode()
                );
                if (sql.getNextException() != null) {
                    queue.addLast(sql.getNextException());
                }
            }

            if (current.getCause() != null) {
                queue.addLast(current.getCause());
            }
        }
    }
}
~~~

This method prints only basic metadata; it does not print SQL or JDBC messages containing user data. In production, use a logger with a correlation ID and access-controlled logs. `IdentityHashMap` prevents infinite loops if cause/next chains contain cycles. **Do not call `getNextException()` in place of `getCause()`**: they represent two distinct relationships.

Different Spring versions may handle nested exceptions in `BatchUpdateException` differently; therefore for batches, test on your exact Spring minor version, driver, and database instead of assuming all nested exceptions are automatically traversed by the translator.

## 13. Testing Strategies and Configuration Changes

There should be **two layers of testing**:

**Unit tests for translators (no database required):** construct `SQLException` instances with controlled subtypes, SQLState, and vendor codes; call `translate(...)` and assert the subtype or `null` return, cause preservation, custom precedence, and fallback. The demo in section 8 is an approachable example. If custom mappings exist, test both **matching and non-matching codes** to ensure fallback is not disabled.

**Integration tests with a real DB:** create realistic scenarios in a test environment with a production-compatible schema/driver and run through `JdbcTemplate`:

| Test operation | What to confirm |
| --- | --- |
| `INSERT` duplicating unique/primary key | Actual subtype, SQLState, vendor code, which constraint failed |
| `INSERT` violating foreign key/NOT NULL | Is it distinguished from unique conflict? |
| SQL referencing a nonexistent column/table | Is it classified as `BadSqlGrammarException` or a broader branch? |
| Intentional deadlock or serialization conflict | Exception type and transaction state before retry |
| Database/connection unreachable | Resource failure and timeout duration |
| Batch with one failing item | Outer exception, inner `BatchUpdateException`, and counts array |
| Unknown vendor code/SQLState | Fallback still operates without hiding errors |

With a real database, do not hardcode assumptions like "MySQL 1062 always becomes `DuplicateKeyException`" for every version and strategy. Test on the actual environment rather than relying on error names printed by a driver.

When changing the default translator:
1. Document the **actual issue** (SQLState, vendor code, expected category).
2. Adjust only the scoped strategy/override, keeping fallback.
3. Write unit tests for overridden codes and integration tests for neighboring errors.
4. Verify which `JdbcTemplate` bean repositories actually receive via DI.
5. Measure differences in transaction/retry/HTTP mapping after upgrading Spring or the driver.

## 14. Common Mistakes

- **"All of Spring 6 still defaults to SQLErrorCodeSQLExceptionTranslator."** False: the normal default since Spring 6.0 is the subclass translator, unless special vendor configuration is present.
- **"Every error with SQLState 23 is a duplicate key."** False: it also includes foreign key, CHECK, NOT NULL...
- **"getErrorCode() has global meaning."** False: it is a vendor code; you must know the DB and version.
- **"translate(...) always returns DataAccessException."** False: calling it directly can return `null`; `JdbcTemplate` provides the uncategorized exception fallback.
- **"A custom translator should catch everything to make handling easier for the app."** False: information is lost and retry/HTTP mapping becomes inaccurate.
- **"Changing the translator will fix deadlocks or unique violations."** False: it only changes classification, while the cause lies in data/transactions/DB.
- **"Any DataAccessException is safe to retry."** False: each subtype and commit state must be evaluated; business code must be idempotent.
- **"It is fine to log full SQL and parameters directly."** Risk of data exposure; log error codes and minimized context.
- **"@Repository and JdbcTemplate must share the same exception translation mechanism."** In `JdbcTemplate`, SQLException is translated at the JDBC access point. The `@Repository` + `PersistenceExceptionTranslationPostProcessor` mechanism applies to corresponding persistence framework/DAO APIs and does not replace choosing a `JdbcTemplate`'s `SQLExceptionTranslator`.
- **"SQLState in any cause is automatically found by the translator."** Not guaranteed across all implementations/versions; verify `BatchUpdateException` and actual next-exceptions.

## 15. Workflow for Choosing a Strategy in a Project

**Step 1 — Keep the default strategy until evidence demands a change:** start with Spring 6.x's `SQLExceptionSubclassTranslator`. Test real failures and record which Spring subtypes are returned.

**Step 2 — Cross-check evidence from the driver:** for misclassified errors, record `SQLException` class, `getSQLState()`, `getErrorCode()`, next exception, product name, driver version, and Spring version.

**Step 3 — Choose the smallest customization:** if SQLState suffices for classification, do not add vendor codes unnecessarily; if only one vendor code needs precision, use `SQLErrorCodeSQLExceptionTranslator` or a guarded custom override; if the system spans multiple DBs, test each DB.

**Step 4 — Maintain cause and fallback:** custom translators match only verified cases, return `null` otherwise, and preserve the root cause; do not swallow unknown errors.

**Step 5 — Define separate business policies:** mapping `DataAccessException` to conflict, retry, or server error is the responsibility of the service/API layer and transaction design. Handle duplicate keys differently from deadlocks; retry only when idempotent and after proper rollback.

**Step 6 — Retest when upgrading Spring/drivers:** adding JDBC subclass detection or updating code tables can change returned subtypes even when application SQL has not changed.

## References

- [Spring Framework 6.2 — JDBC Core: SQLExceptionTranslator](https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/core.html) — error translation strategies, default since Spring 6.0, vendor mapping, and custom fallback.
- [Spring Framework 6.2 — SQLExceptionTranslator Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jdbc/support/SQLExceptionTranslator.html) — `translate(...)` contract and nullable return.
- [Spring Framework 6.2 — JdbcAccessor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jdbc/support/JdbcAccessor.html) — `getExceptionTranslator()`, `setExceptionTranslator(...)`, and lazy init.
- [Spring Framework 6.2 — SQLErrorCodeSQLExceptionTranslator Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jdbc/support/SQLErrorCodeSQLExceptionTranslator.html) — vendor codes and configuration.
- [Spring Framework 6.2 — AbstractFallbackSQLExceptionTranslator Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jdbc/support/AbstractFallbackSQLExceptionTranslator.html) — custom translator and fallback.
- [Java SE 17 — SQLException](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/SQLException.html) — SQLState, vendor code, cause, and next-exception chain.
