# SQLState, Vendor Error Codes, and Corresponding Translators in Spring JDBC

## 1. The Problem to Solve

When a database rejects a statement, the JDBC driver typically throws `SQLException`. The exact same duplicate-key failure can carry different **SQLState** and **vendor error codes** across PostgreSQL, MySQL, Oracle, and SQL Server. If the service checks vendor-specific numbers directly, business logic becomes coupled to the driver and hard to maintain.

Spring Data Access uses `SQLExceptionTranslator` to map JDBC errors to the unchecked `DataAccessException` hierarchy. APIs like `JdbcTemplate` perform this translation step during JDBC handling. The service can distinguish duplicate-key errors, constraint violations, invalid SQL, or resource failures without maintaining an error-code lookup table for every database.

~~~text
JdbcTemplate executes SQL
          |
          v
JDBC driver -> SQLException
               |-- getSQLState()      : "23505", "23000", "42000", ...
               |-- getErrorCode()     : 1062, 1, 2627, 0, ...
               |-- Java subclass      : SQLSyntaxErrorException, ...
               |-- cause/nextException (if any)
          |
          v
SQLExceptionTranslator
          |
          v
DataAccessException
    |-- DuplicateKeyException
    |-- DataIntegrityViolationException
    |-- BadSqlGrammarException
    |-- CannotAcquireLockException
    |-- ...
          |
          v
Service decides response, rollback, or retry based on business logic
~~~

This lesson focuses on the three JDBC diagnostic signals, the corresponding translators, the fallback order in Spring 6.x, and how to test translation results. **There is no fixed 1-to-1 mapping across all drivers**: the resulting Spring exception type depends on the signals provided by the driver, the chosen translator, and configuration.

## 2. What Information Does `SQLException` Provide?

Core APIs:

~~~java
// Illustrative fragment; ex is the SQLException thrown by the JDBC driver.
String state = ex.getSQLState();
int vendorCode = ex.getErrorCode();
String message = ex.getMessage();
Throwable cause = ex.getCause();
SQLException next = ex.getNextException();
~~~

- `getSQLState()`: SQL state code usually consisting of **5 characters**. The first two characters indicate the error group/class; the last three indicate the subclass. May return `null`.
- `getErrorCode()`: integer defined by the driver/database vendor; `0` **does not mean success**.
- Java subclass of `SQLException`: since JDBC 4, many drivers report more specific types, such as `SQLSyntaxErrorException`.
- `getMessage()`: human-readable text that can change across versions, locales, and drivers; do not parse messages with regex for core logic.
- `getCause()` and `getNextException()`: may contain the underlying cause or a chain of additional errors, especially when batch/driver layers wrap exceptions multiple levels deep.

### SQLState: Class and Subclass

| SQLState/class | Common meaning | Example |
| --- | --- | --- |
| `08` | Connection exception | DB connection failure |
| `22` | Data exception | Data overflow / invalid type conversion |
| `23` | Integrity constraint violation | UNIQUE, NOT NULL, FOREIGN KEY, CHECK |
| `28` | Invalid authorization | Access denied |
| `40` | Transaction rollback | Serialization failure, deadlock depending on DB |
| `42` | Syntax error/access rule violation | Invalid SQL, nonexistent table/column |
| `HY` | Status group widely used by drivers | `HY000`: general error |

For example, PostgreSQL commonly reports `23505` for UNIQUE, `23503` for FOREIGN KEY, `23502` for NOT NULL, `40001` for serialization failure, and `40P01` for deadlock. These codes are **DB-specific examples**, not a promise that every DBMS emits the same codes.

Looking only at the first two characters `23` is not enough to conclude "duplicate key": the same class also covers FK, CHECK, and NOT NULL errors. To return a business response, you need granular classification and to know which constraint was violated.

### Vendor Error Code: DBMS-Specific Numbers

| DB/driver | Common duplicate-key signal | Notes |
| --- | --- | --- |
| MySQL/MariaDB | Error code `1062`, SQLState usually `23000` | Duplicate entry |
| Oracle | Error code `1` (`ORA-00001`) | Unique constraint violated |
| SQL Server | Error code `2627` or `2601` | Primary/unique constraint or unique index violation |
| PostgreSQL | SQLState `23505` | In many cases vendor code is meaningless or `0` |

**`getSQLState()` is completely different from `getErrorCode()`.** Do not compare a number `23505` against `getErrorCode()` just because it matches PostgreSQL's SQLState string. Always record both fields when diagnosing.

## 3. Java JDBC Exception Subclasses

JDBC 4 defines subclasses with specialized semantics:

| JDBC subclass | Error hint |
| --- | --- |
| `SQLSyntaxErrorException` | Invalid SQL syntax or access rule |
| `SQLIntegrityConstraintViolationException` | Integrity constraint |
| `SQLTransactionRollbackException` | Transaction was rolled back |
| `SQLTransientConnectionException` | Connection error classified by driver as transient |
| `SQLTimeoutException` | Operation timeout |

However, not every driver uses specialized subtypes with the same level of detail. A driver may use a generic `SQLException`, adding an SQLState or vendor code. Spring therefore provides translators that use additional signals and fallback.

Plain Java recognition example:

~~~java
// Illustrates a plain-JDBC SQLException handling branch.
if (ex instanceof java.sql.SQLIntegrityConstraintViolationException) {
    // Constraint violation occurred; not necessarily a duplicate key.
}
~~~

In regular Spring code, there is no need to repeat this check when the operation already goes through `JdbcTemplate`: Spring translates it to `DataAccessException` first.

## 4. `DataAccessException`: What Does the Translation Result Mean?

`org.springframework.dao.DataAccessException` is Spring's unchecked root exception across multiple data access technologies. Notable subclasses:

| Spring exception | Semantic scope | Handling direction |
| --- | --- | --- |
| `DuplicateKeyException` | Duplicate primary key/UNIQUE | May report a conflict if appropriate for business logic |
| `DataIntegrityViolationException` | Constraint/data integrity violation | Check constraints and data |
| `BadSqlGrammarException` | Incompatible SQL or schema | Fix query/migration |
| `CannotAcquireLockException` | Recognized lock acquisition failure/contention | Consider conditional retry |
| `QueryTimeoutException` | Query timeout | Investigate load and execution outcome |
| `DataAccessResourceFailureException` | DB resource/connection failure | Check infrastructure |
| `UncategorizedSQLException` | Could not classify precisely | Inspect the original SQLException |

`DuplicateKeyException` **extends** `DataIntegrityViolationException`. When business logic only needs to know data violated a constraint, catching the parent class is usually more stable. Catch the subclass only when a specialized response for duplicate keys is needed.

The Spring exception normally retains the initial `SQLException` as its cause; you can still read SQLState/vendor code for investigation. Do not turn every `DataIntegrityViolationException` into an "email already exists" message: it could be NOT NULL, FK, or CHECK.

## 5. Three Spring JDBC Translators and Fallback Order

The `org.springframework.jdbc.support.SQLExceptionTranslator` interface has the method:

~~~java
// Simplified signature to illustrate the API; not a standalone file.
DataAccessException translate(
        String task, String sql, SQLException ex);
~~~

With a custom translator, `translate` can return `null` to allow the next step to proceed; Spring's standard translators have built-in fallback mechanisms.

### `SQLExceptionSubclassTranslator`

- Inspects **JDBC 4 subclasses** and a few special signals.
- If unable to classify from the subtype, delegates to `SQLStateSQLExceptionTranslator`.
- **Since Spring Framework 6.0, this is the standard default choice** of Spring JDBC when no special vendor-codes configuration is present.

### `SQLStateSQLExceptionTranslator`

- Uses `SQLException.getSQLState()`, especially the **two-character class** and certain specific codes.
- Does not require a connection to detect the database product name.
- Relatively portable, though unable to distinguish all vendor errors; commonly serves as the **fallback** for subclass or error-code translators.

### `SQLErrorCodeSQLExceptionTranslator`

- Uses `SQLErrorCodes` containing per-database mappings, typically based on **vendor codes**, which is more precise for known products.
- `SQLErrorCodesFactory` selects the mapping via `DatabaseMetaData.getDatabaseProductName()` when a `DataSource` is provided.
- If an application `sql-error-codes.xml` exists at the **classpath root**, Spring JDBC may use this error-code strategy by convention.
- Can be enabled explicitly on `JdbcTemplate` via `setExceptionTranslator(...)`.
- When no vendor mapping matches, it falls back through subclass and then SQLState.

~~~text
Default in Spring 6.x:
    SQLExceptionSubclassTranslator
        |
        +-- recognizes JDBC subtype
        |
        +-- fallback -> SQLStateSQLExceptionTranslator
                               |
                               +-- unclassifiable -> general error

When vendor mapping is enabled:
    SQLErrorCodeSQLExceptionTranslator
        |
        +-- custom translator / custom mappings (if present)
        +-- DB's SQLErrorCodes
        +-- fallback -> SQLExceptionSubclassTranslator
                             |
                             +-- fallback -> SQLStateSQLExceptionTranslator
~~~

**Common misconception:** `SQLErrorCodeSQLExceptionTranslator` does not always compare `getErrorCode()`. `SQLErrorCodes` has a `useSqlStateForTranslation` property. For example, Spring's PostgreSQL mapping enables it to match **SQLState** instead of vendor numbers.

With the vendor strategy, precedence typically runs through custom translator/mappings if configured, error-code group mappings, and fallback. Custom settings like `customSqlExceptionTranslator` on `SQLErrorCodes` can affect resolution order. Verify the order on your actual Spring version instead of assuming all Spring releases behave identically.

## 6. Runnable Java 17 Program: Demonstrating the Three Strategies

The following example intentionally creates **simulated** `SQLException`s with SQLState, JDBC subclass, and vendor code to illustrate the translators. It **does not connect to a DB**, so stdout does not depend on external drivers.

Project structure:

~~~text
translator-demo/
├── pom.xml
└── src/main/java/demo/TranslatorDemo.java
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>translator-demo</artifactId>
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
                <configuration>
                    <mainClass>demo.TranslatorDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/TranslatorDemo.java**

~~~java
package demo;

import java.sql.SQLException;
import java.sql.SQLSyntaxErrorException;
import org.springframework.dao.DataAccessException;
import org.springframework.jdbc.support.SQLErrorCodeSQLExceptionTranslator;
import org.springframework.jdbc.support.SQLErrorCodes;
import org.springframework.jdbc.support.SQLExceptionSubclassTranslator;
import org.springframework.jdbc.support.SQLExceptionTranslator;
import org.springframework.jdbc.support.SQLStateSQLExceptionTranslator;

public final class TranslatorDemo {
    public static void main(String[] args) {
        SQLException stateError =
                new SQLException("unique violation", "23505", 0);

        SQLException subclassError =
                new SQLSyntaxErrorException("bad SQL", "42000", 0);

        SQLException vendorError =
                new SQLException("duplicate entry", "HY000", 1062);

        SQLErrorCodes vendorCodes = new SQLErrorCodes();
        vendorCodes.setDuplicateKeyCodes("1062");

        SQLExceptionTranslator stateTranslator =
                new SQLStateSQLExceptionTranslator();
        SQLExceptionTranslator subclassTranslator =
                new SQLExceptionSubclassTranslator();
        SQLExceptionTranslator vendorTranslator =
                new SQLErrorCodeSQLExceptionTranslator(vendorCodes);

        print("SQLState 23505", stateTranslator, stateError);
        print("JDBC subclass", subclassTranslator, subclassError);
        print("Vendor 1062", vendorTranslator, vendorError);
    }

    private static void print(
            String label,
            SQLExceptionTranslator translator,
            SQLException original) {
        DataAccessException mapped = translator.translate(
                "demo", "INSERT INTO sample (id) VALUES (?)", original);

        if (mapped == null) {
            throw new IllegalStateException(
                    "Could not translate: " + label);
        }

        System.out.println(
                label + ": " + mapped.getClass().getSimpleName());
    }
}
~~~

In the `translator-demo/` directory, with JDK 17+ and Maven 3.9+, run:

~~~bash
mvn -q compile exec:java
~~~

**Expected stdout from the program** (excluding Maven's own logs):

~~~text
SQLState 23505: DuplicateKeyException
JDBC subclass: BadSqlGrammarException
Vendor 1062: DuplicateKeyException
~~~

Explanation:

1. The SQLState translator uses status `23505` to classify duplicate key.
2. The JDBC subclass translator recognizes `SQLSyntaxErrorException` and classifies it as `BadSqlGrammarException`.
3. The vendor translator is given `SQLErrorCodes` with `duplicateKeyCodes=1062`, so it maps vendor number `1062` to `DuplicateKeyException` even though the simulated SQLState is `HY000`.

**This is an exception-translation test, not a database integration test.** With a real DB, capture the actual SQLState/errorCode from the driver, then verify which `DataAccessException` type your `JdbcTemplate` configuration produces.

## 7. Real Errors Through `JdbcTemplate`

A DAO layer using `JdbcTemplate` does not need to catch checked `SQLException` on every query:

~~~java
// Code fragment placed inside a DAO that has JdbcTemplate jdbcTemplate.
jdbcTemplate.update(
        "INSERT INTO account (id, email) VALUES (?, ?)",
        id, email);
~~~

When the database rejects the statement, `JdbcTemplate` invokes its translator and throws `DataAccessException`. Service code can catch the appropriate type:

~~~java
// Business logic fragment, not yet a standalone Java class.
try {
    accountDao.create(id, email);
} catch (org.springframework.dao.DuplicateKeyException ex) {
    throw new AccountAlreadyExistsException(email, ex);
}
~~~

`AccountAlreadyExistsException` is a **custom application-defined exception** in this example. Only return an "account already exists" response when you have verified the duplicate-key constraint matches the business rule; do not infer it from any arbitrary integrity error.

Catch `DataAccessException` only at the layer capable of deciding how to handle it. Do not catch everything and return the same HTTP code. Connection failures, invalid SQL, and duplicate data have different natures.

## 8. When to Enable the Vendor-Code Translator?

In an application using Spring 6.x, subclass + SQLState fallback is usually sufficient for common errors. Enable `SQLErrorCodeSQLExceptionTranslator` when a specific driver error requires precise classification by vendor code or the default mapping does not meet your requirements.

It can be configured explicitly:

~~~java
// Spring @Bean integration fragment; requires imports for DataSource,
// JdbcTemplate, SQLErrorCodeSQLExceptionTranslator, and @Bean.
@Bean
JdbcTemplate jdbcTemplate(DataSource dataSource) {
    JdbcTemplate template = new JdbcTemplate(dataSource);
    template.setExceptionTranslator(
            new SQLErrorCodeSQLExceptionTranslator(dataSource));
    return template;
}
~~~

When created from a `DataSource`, the translator can access `DatabaseMetaData` to discover the database product name. Ensure connectivity and initialization lifecycle readiness. If specific vendor mapping is not yet needed, keeping the default is usually simpler.

Spring bundles `org/springframework/jdbc/support/sql-error-codes.xml` for familiar databases. Code groups can include `duplicateKeyCodes`, `badSqlGrammarCodes`, `dataIntegrityViolationCodes`, `cannotAcquireLockCodes`, `deadlockLoserCodes`, `dataAccessResourceFailureCodes`, and others.

### Custom `sql-error-codes.xml` at the Classpath Root

An application can place `sql-error-codes.xml` at the classpath root (such as `src/main/resources/sql-error-codes.xml` in a Maven/Gradle application) to declare custom mappings. The presence of this file is also a signal that causes Spring JDBC to select the error-code strategy by convention.

Minimal example structure for MySQL:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="http://www.springframework.org/schema/beans
                           https://www.springframework.org/schema/beans/spring-beans.xsd">
    <bean id="MySQL"
          class="org.springframework.jdbc.support.SQLErrorCodes">
        <property name="duplicateKeyCodes" value="1062"/>
    </bean>
</beans>
~~~

This is a syntax-learning example; **do not use it to replace the entire production mapping** just to recognize `1062`, because a custom file can affect other error groups. Use built-in mappings first, and customize only when you have evidence from the real driver/database.

Besides XML configuration, `SQLErrorCodes` can be instantiated directly, as in the runnable program in section 6. That approach suits unit tests or mappings needing special control.

## 9. Custom Translator and Fallback

When specialized rules are required, Spring 6.1+ supports `setCustomTranslator(...)` on translators extending `AbstractFallbackSQLExceptionTranslator`. This is preferred over overriding `customTranslate(...)`, which has been deprecated since Spring 6.1.

Example when an application uses only PostgreSQL and has verified that `40P01` corresponds to deadlock:

~~~java
// Configuration fragment; dataSource and jdbcTemplate are already created.
SQLErrorCodeSQLExceptionTranslator translator =
        new SQLErrorCodeSQLExceptionTranslator(dataSource);

translator.setCustomTranslator((task, sql, exception) -> {
    if ("40P01".equals(exception.getSQLState())) {
        return new org.springframework.dao.CannotAcquireLockException(
                "Deadlock while " + task, exception);
    }
    return null; // Other errors continue through mapping and fallback.
});

jdbcTemplate.setExceptionTranslator(translator);
~~~

Note not to map every type of transaction failure to `CannotAcquireLockException`: choose mappings according to exact driver semantics and Spring version. The mapping above illustrates the custom mechanism; Spring already has PostgreSQL deadlock mappings and may use a corresponding exception type.

In addition to a directly attached custom translator, `SQLErrorCodes` also supports **`customSqlExceptionTranslator` and custom translations**. Depending on version/configuration, custom steps are tried before the general error-code table, and only then fallback. Returning `null` from a custom translator means it did not handle that case; do not return a generic exception for every input unless you intend to erase existing classifications.

Always test both codes that **hit the custom rule** and codes that **miss it** to ensure fallback still works. If there is no real need, keeping the default translator leaves the system with less configuration.

## 10. Logging and Diagnosing Errors Properly

A `DataAccessException` typically keeps `SQLException` in its cause chain. You can walk it to extract the original codes:

~~~java
// Code fragment while handling DataAccessException ex;
// log is the application's logger, not a variable defined here.
Throwable cursor = ex;
while (cursor != null) {
    if (cursor instanceof java.sql.SQLException sqlEx) {
        log.warn("dbFailure state={} code={}",
                sqlEx.getSQLState(),
                sqlEx.getErrorCode());
        break;
    }
    cursor = cursor.getCause();
}
~~~

The snippet above stops at the first `SQLException` in the cause chain. With `BatchUpdateException`, you should also inspect `getNextException()`, `getUpdateCounts()`, or `getLargeUpdateCounts()`; a driver may store detailed errors in those places. Count results also depend on the driver and do not always identify which exact item failed.

Good practices for production observability:

- Log **Spring exception type, full SQLState, vendor code, operation name, database product/driver version, and trace ID**; do not rely solely on the message.
- Never log passwords, tokens, personal data, or SQL containing sensitive literals; retain only necessary details and follow application security policies.
- Before calling `substring(0, 2)` to extract the SQLState class, verify it is non-null and at least 2 characters long.
- Do not parse `SQLException.getMessage()` as a stable contract: messages can vary by version or locale.
- If error translation looks wrong, compare actual codes on the **deployed DB**, not just H2/in-memory tests.
- Keep the cause when wrapping exceptions; do not create a `RuntimeException("DB error")` that discards all context.

## 11. Business Responses, Rollback, and Retry

**The translator only classifies errors.** It does not automatically decide retries or transaction boundaries.

- `DuplicateKeyException`, many `DataIntegrityViolationException`s, and `BadSqlGrammarException`: usually require fixing data/queries or reporting a conflict; retrying as-is rarely helps.
- Lock errors, serialization failures, or temporary resource issues: may be retried after confirming the transaction rolled back properly, the operation is safe to re-run, with backoff and retry limits.
- Timeouts: do not assume the DB did not commit. Evaluate transaction outcome, idempotency, and side-effect consequences before retrying.

When `@Transactional` is properly applied via a Spring proxy, `DataAccessException` is a runtime exception, so escaping the method normally triggers rollback by default. If the service catches the exception and does not rethrow it, the transaction **may** still commit other changes depending on rollback-only status. That behavior is independent of which translator was used.

Do not automatically convert every `DataAccessException` into HTTP 409. A duplicate UNIQUE key may mean a conflict, whereas a connection failure or bad SQL grammar is usually a system error; the final decision depends on service context.

## 12. Before-and-After Scenarios

### A. Migrating from MySQL to PostgreSQL

**Before:** the service checked `getErrorCode() == 1062` to report a duplicate key. After migration, PostgreSQL typically reports `23505` in SQLState, so the logic misses it.

**After:** use Spring's `DuplicateKeyException`/`DataIntegrityViolationException`, keep SQLState/vendor code for logging, and run integration tests against real PostgreSQL. The service needs no vendor switch table.

### B. Receiving SQLState `23000`

**Wrong:** `23000` means "duplicate email".

**Right:** `23` is the integrity class; `23000` is still too broad. You need vendor code, mapping, constraint name, or business data to distinguish UNIQUE from FK/NOT NULL.

### C. Adding a `sql-error-codes.xml` File

**Before:** Spring 6.x default uses subclass + SQLState fallback.

**After:** if a custom file exists at the classpath root, the default strategy may switch to vendor codes. You must test critical mappings and fallback, rather than copying a minimal XML and accidentally losing other code groups.

### D. Batch Failure

**Wrong:** read only the wrapper message and automatically retry the entire batch.

**Right:** inspect `BatchUpdateException`, update counts, and next exceptions, ensuring transaction/rollback and idempotency before retrying.

## 13. Common Mistakes and Exercises

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Confusing SQLState with vendor code | Wrong matches on other DBs | Read the two APIs separately |
| Relying on class `23` to conclude duplicate | Misses FK/NOT NULL/CHECK | Classify the constraint carefully |
| Thinking Spring 6.x always prioritizes vendor-code translator | Misunderstands default behavior | Check subclass/SQLState fallback and configuration |
| Thinking `SQLErrorCodeSQLExceptionTranslator` always uses vendor numbers | Misunderstands PostgreSQL mapping | Check `useSqlStateForTranslation` |
| Catching all integrity errors and returning one message | Reports inaccurate business error | Verify constraint type |
| Swallowing `DataAccessException` inside a transaction | May commit remaining work | Let exception propagate or explicitly manage rollback |
| Retrying timeouts/locks indefinitely | Creates load and duplicate effects | Cap retries, use backoff, ensure idempotency |
| Losing cause when wrapping exceptions | Cannot diagnose root issue | Retain the original exception as cause |

Self-check:

1. `SQLState=23505`, `errorCode=0`: the primary duplicate signal is **SQLState**, not the number `0`.
2. `SQLState=HY000`, `errorCode=1062` from MySQL: a **vendor-code translator with mapping 1062** has the advantage.
3. `SQLSyntaxErrorException` in default Spring 6.x: **`SQLExceptionSubclassTranslator`** can translate it to `BadSqlGrammarException`.
4. `SQLState=23503` from PostgreSQL: typically a **foreign-key violation**, not "duplicate email".
5. Wanting to retry a lock error: verify **transaction outcome, idempotency, and retry budget** first.
6. New unrecognized vendor error code: inspect subclass/SQLState/cause, then add only a **verified mapping**, keeping fallback intact.

## 14. Key Takeaways

- **SQLState**: typically a 5-character status string; the first two characters represent the class.
- **Vendor error code**: database/driver number; may be `0` even when an error occurred.
- **JDBC subclass**: error-type signal on `SQLException` when implemented appropriately by the driver.
- **Spring 6.x default**: `SQLExceptionSubclassTranslator` with `SQLStateSQLExceptionTranslator` fallback.
- **Vendor strategy**: `SQLErrorCodeSQLExceptionTranslator` uses per-database `SQLErrorCodes`, custom mappings, and fallback. Some DBs match by SQLState instead of vendor numbers.
- **`DataAccessException`** makes services less dependent on drivers; you still must rely on business logic to decide responses, rollback, and retry.

**References:**

- [Spring Framework — JDBC Core, Using SQLExceptionTranslator](https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/core.html)
- [Spring Framework — DAO Support and Exception Hierarchy](https://docs.spring.io/spring-framework/reference/6.2/data-access/dao.html)
- [Spring Framework — SQLStateSQLExceptionTranslator API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/jdbc/support/SQLStateSQLExceptionTranslator.html)
- [Spring Framework — SQLExceptionSubclassTranslator API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/jdbc/support/SQLExceptionSubclassTranslator.html)
- [Spring Framework — SQLErrorCodeSQLExceptionTranslator API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/jdbc/support/SQLErrorCodeSQLExceptionTranslator.html)
- [Spring Framework — Vendor code mappings](https://github.com/spring-projects/spring-framework/blob/6.2.x/spring-jdbc/src/main/resources/org/springframework/jdbc/support/sql-error-codes.xml)
