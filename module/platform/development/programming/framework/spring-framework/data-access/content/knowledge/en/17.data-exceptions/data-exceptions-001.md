# DataAccessException: Root of the Data Access Exception Hierarchy in Spring

`DataAccessException` is the **root exception** of the data access exception hierarchy provided by the Spring Framework. When using Spring JDBC, Spring-integrated JPA/Hibernate, or other data access support components, many driver- and storage-technology-specific errors are converted into **subclasses of `org.springframework.dao.DataAccessException`**. As a result, the service layer can react based on the *meaning of the error* — constraint violation, invalid query, concurrent locking error, connection loss — instead of depending on error codes from a specific database vendor.

The core point: `DataAccessException` is an **abstract class**, extending `org.springframework.core.NestedRuntimeException` and indirectly extending `RuntimeException`. It is the root of the **Spring data exception hierarchy**, **not** the root of all Java exceptions or every error that can occur in a database. Applications do not need to declare `throws DataAccessException` on every method because it is an *unchecked exception*.

## 1. The Problem DataAccessException Solves

When working directly with JDBC, many operations throw `java.sql.SQLException` (a checked exception). Programs often have to inspect the SQLState, vendor error code, or driver-specific exception class to determine the cause:

```java
try {
    // connection.prepareStatement(...), executeUpdate(), ...
} catch (java.sql.SQLException ex) {
    String sqlState = ex.getSQLState();
    int vendorCode = ex.getErrorCode();
    // How these two values are interpreted depends on the database and driver.
}
```

This is an **illustrative snippet** of plain JDBC, not a standalone Java program. Looking at a generic `SQLException` alone does not tell you for sure whether the error is a duplicate key, timeout, or SQL syntax error. If service code depends directly on the SQLState of one DB, switching technologies or drivers becomes harder.

Spring provides **exception translation**: the data access layer receives the underlying technology's error, classifies it, and creates a meaningful exception in Spring's hierarchy, usually preserving the original cause.

```text
JDBC / JPA / Hibernate / driver
       |
       | SQLException or persistence exception
       v
Spring JDBC template / ORM exception translator
       |
       v
org.springframework.dao.DataAccessException
       |
       +-- DataIntegrityViolationException
       +-- BadSqlGrammarException
       +-- EmptyResultDataAccessException
       +-- QueryTimeoutException
       +-- OptimisticLockingFailureException
       +-- ...
       |
       v
Service handles according to business policy
```

**Practical benefits:**

1. **A common exception contract**: the service can catch `DataIntegrityViolationException` whether the DAO is implemented with JDBC or ORM, as long as that access path applies appropriate exception translation.
2. **Meaningful classification**: you can distinguish errors that require fixing data, fixing SQL, concurrency conflicts, or infrastructure failures.
3. **Less boilerplate**: you do not have to catch and convert `SQLException` in every method using `JdbcTemplate`.
4. **Preserves original information**: you can usually inspect the underlying exception via `getCause()`/`getMostSpecificCause()` for diagnostics.
5. **Transaction-friendly**: by default, an unchecked error thrown out of a Spring-managed `@Transactional` method causes the transaction to roll back.

Do not interpret "database-independent" as Spring always translating the exact same error into the exact same subclass across every driver. Classification depends on the original exception type, SQLState/vendor code, translator configuration, and access API; testing against the actual stack remains important.

## 2. Position of DataAccessException in the Java Hierarchy

```text
java.lang.Throwable
  └── java.lang.Exception
      └── java.lang.RuntimeException
          └── org.springframework.core.NestedRuntimeException
              └── org.springframework.dao.DataAccessException (abstract)
                  ├── NonTransientDataAccessException (abstract)
                  ├── TransientDataAccessException (abstract)
                  ├── RecoverableDataAccessException
                  └── some other specialized branches, e.g. ScriptException
```

The main branches have the following handling semantics:

| Branch | Meaning | Should you retry automatically? |
| --- | --- | --- |
| `NonTransientDataAccessException` | A similar operation will normally fail unless the cause is fixed: invalid SQL, constraint violation, unexpected returned data... | **Do not** retry blindly |
| `TransientDataAccessException` | An error considered potentially temporary, such as certain timeouts or concurrency conflicts | **May consider** bounded retries, after confirming safety/idempotency |
| `RecoverableDataAccessException` | Recoverable after a **recovery action** by the application; at a minimum, closing the old connection and obtaining a new one may be required | Do not retry as-is on the failed resource; a recovery procedure is required |
| `DataAccessException` (root) | Generic type for catching or declaring data errors across layers | Not enough information to decide policy |

`DataAccessException` belongs to the `org.springframework.dao` namespace. Despite the package name `dao`, it is not limited to traditional DAO patterns; Spring's JDBC templates and ORM integration mechanisms also use this hierarchy.

### Representative Subclass Tree (abbreviated, not an exhaustive API list)

```text
DataAccessException
├── NonTransientDataAccessException
│   ├── DataIntegrityViolationException
│   │   └── DuplicateKeyException
│   ├── InvalidDataAccessResourceUsageException
│   │   └── BadSqlGrammarException
│   ├── DataRetrievalFailureException
│   │   └── IncorrectResultSizeDataAccessException
│   │       └── EmptyResultDataAccessException
│   ├── InvalidDataAccessApiUsageException
│   ├── NonTransientDataAccessResourceException
│   │   └── DataAccessResourceFailureException
│   └── UncategorizedDataAccessException
├── TransientDataAccessException
│   ├── ConcurrencyFailureException
│   │   ├── OptimisticLockingFailureException
│   │   └── PessimisticLockingFailureException
│   │       └── CannotAcquireLockException
│   ├── QueryTimeoutException
│   └── TransientDataAccessResourceException
└── RecoverableDataAccessException
```

The edges in the diagram represent typical Spring Framework inheritance relationships; a few less common subclasses are omitted. An important example:

```java
try {
    // Call DAO / JdbcTemplate ...
} catch (org.springframework.dao.DuplicateKeyException ex) {
    // DuplicateKeyException is a subclass of DataIntegrityViolationException,
    // NonTransientDataAccessException and DataAccessException.
}
```

The snippet above is a **catch illustration**, without a standalone runnable program. If you need to catch duplicate/constraint violation errors more generally, consider catching `DataIntegrityViolationException` instead of just one subclass, because the granularity of the translated exception may vary.

## 3. Subclasses to Recognize in a Spring Application

| Specific exception | Common situation | Appropriate response |
| --- | --- | --- |
| `DuplicateKeyException` | INSERT/UPDATE violates PRIMARY KEY or UNIQUE | Report duplicate data, avoid retrying the same request |
| `DataIntegrityViolationException` | Violates UNIQUE, FOREIGN KEY, NOT NULL, or other constraints | Check business rules and input data |
| `BadSqlGrammarException` | Invalid SQL, nonexistent table/column name, syntax error | Fix code/migration/schema, do not retry as-is |
| `EmptyResultDataAccessException` | API expects one record, but the query returns 0 | Handle "not found" per the method/API contract |
| `IncorrectResultSizeDataAccessException` | API requires a specific number of rows, but a different count is returned | Check the query and cardinality assumptions |
| `OptimisticLockingFailureException` | Entity version no longer matches, concurrent update detected | Prompt the client to reload data / resolve conflict |
| `CannotAcquireLockException` | Database cannot grant a lock under current conditions and timeout | Diagnose contention; bounded retry if safe |
| `QueryTimeoutException` | Query exceeded timeout or was stopped due to timeout | Check SQL, load, timeout, and retryability |
| `DataAccessResourceFailureException` | Unable to access the data resource, e.g. connection error | Check DB, pool, network, credentials, service health |
| `InvalidDataAccessApiUsageException` | Misuse of API/framework contract, missing parameter, or invalid operation | Fix the API-calling code |
| `UncategorizedDataAccessException` | Spring could not classify the error more specifically | Inspect cause, SQLState/vendor code, and logging |

**Not every "no data" situation is an exception.** For example, `JdbcTemplate.query(...)` can normally return an empty list. `queryForObject(...)` requires exactly one row, so it can throw `EmptyResultDataAccessException`. Similarly, `JdbcTemplate.update(...)` usually returns an affected row count of `0` without throwing an exception if the SQL executed validly.

A subclass does not necessarily originate from only one DB engine. The same `DataIntegrityViolationException` can result from various constraints; do not automatically assume UNIQUE/HTTP 409 from that superclass alone. Likewise, do not infer a definite database outage from the exception name alone: it could be an invalid statement caused by code.

## 4. SQLException Translation Mechanism in Spring JDBC

`JdbcTemplate` encapsulates repetitive tasks: acquiring a connection via `DataSource`, preparing and executing SQL, releasing resources appropriately for the transaction, and then translating `SQLException` into `DataAccessException`. The translation interface is `org.springframework.jdbc.support.SQLExceptionTranslator`:

```java
public interface SQLExceptionTranslator {
    // The actual signature includes nullable annotations depending on the Spring version.
    DataAccessException translate(String task, String sql, SQLException ex);
}
```

This is an API signature representation for learning, not a file to declare in your project (Spring already provides the interface). The translator uses information from the original exception, such as:

- Subclasses of `SQLException` (JDBC 4: e.g., `SQLSyntaxErrorException`, `SQLIntegrityConstraintViolationException`, `SQLTransientException`);
- `SQLState` per standard and database implementation;
- Vendor-specific error code, if the translator is configured to use vendor error codes;
- The SQL statement and operation being performed, used as diagnostic information.

Since Spring Framework **6.0**, the default translator for most JDBC paths is `SQLExceptionSubclassTranslator`, with fallback to `SQLStateSQLExceptionTranslator`. `SQLErrorCodeSQLExceptionTranslator` can still be used when configured directly or when a `sql-error-codes.xml` file recognized by Spring is on the classpath; it relies on database error codes. Do not assume every application is using a vendor-code-based translator.

Example flow:

```text
H2: SQLException for UNIQUE constraint
      |
      v
JdbcTemplate -> SQLExceptionTranslator
      |
      v
DataIntegrityViolationException / DuplicateKeyException
      |
      v
DAO/Service handles per the rule disallowing duplicate emails
```

ORM paths do not go through `SQLExceptionTranslator` in all cases: JPA/Hibernate has its own exceptions, which are handled by Spring's ORM support components or the `@Repository` translation mechanism when properly configured.

## 5. Runnable Java 17+ Example: Observing DataAccessException with Spring JDBC and H2

This example does not require Spring Boot or a separate DB server. It uses **Spring Framework 6.2.19 + H2 2.3.232** to create an in-memory database, sequentially triggering a constraint error, empty result, too many rows, and an SQL error. File structure:

```text
dataaccess-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── DataAccessExceptionDemo.java
```

File `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>dataaccess-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.19</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
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
                    <mainClass>demo.DataAccessExceptionDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/demo/DataAccessExceptionDemo.java`:

```java
package demo;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.dao.DataAccessException;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.dao.IncorrectResultSizeDataAccessException;
import org.springframework.jdbc.BadSqlGrammarException;
import org.springframework.jdbc.core.JdbcTemplate;

public final class DataAccessExceptionDemo {
    private DataAccessExceptionDemo() {
    }

    public static void main(String[] args) {
        JdbcDataSource dataSource = new JdbcDataSource();
        dataSource.setURL("jdbc:h2:mem:dao_demo;DB_CLOSE_DELAY=-1");
        dataSource.setUser("sa");
        dataSource.setPassword("");

        JdbcTemplate jdbc = new JdbcTemplate(dataSource);

        jdbc.execute("""
                CREATE TABLE accounts (
                    id BIGINT PRIMARY KEY,
                    email VARCHAR(128) NOT NULL UNIQUE
                )
                """);
        jdbc.update("INSERT INTO accounts (id, email) VALUES (?, ?)",
                1L, "a@example.test");
        jdbc.update("INSERT INTO accounts (id, email) VALUES (?, ?)",
                2L, "b@example.test");

        try {
            jdbc.update("INSERT INTO accounts (id, email) VALUES (?, ?)",
                    3L, "a@example.test");
        } catch (DataIntegrityViolationException ex) {
            System.out.println("constraint=" + (ex instanceof DataAccessException));
        }

        try {
            jdbc.queryForObject(
                    "SELECT email FROM accounts WHERE id = ?",
                    String.class, 999L);
        } catch (EmptyResultDataAccessException ex) {
            System.out.println("empty=" +
                    (ex instanceof IncorrectResultSizeDataAccessException));
        }

        try {
            jdbc.queryForObject("SELECT email FROM accounts", String.class);
        } catch (IncorrectResultSizeDataAccessException ex) {
            System.out.println("too-many=" + ex.getActualSize());
        }

        try {
            jdbc.queryForObject(
                    "SELECT unknown_column FROM accounts",
                    String.class);
        } catch (BadSqlGrammarException ex) {
            System.out.println("bad-sql=" + (ex instanceof DataAccessException));
        }
    }
}
```

In a terminal in the `dataaccess-demo` directory, using Java 17+ and Maven:

```bash
java -version
mvn -q compile exec:java
```

Stdout from the **program** when run with the dependency versions and H2 above:

```text
constraint=true
empty=true
too-many=2
bad-sql=true
```

Explanation of the four cases:

1. **UNIQUE violation**: the table allows an email to appear only once. `JdbcTemplate.update` converts H2's error into a subclass of `DataIntegrityViolationException`; the handler catches the appropriate group. The expression `instanceof DataAccessException` is `true` due to inheritance.
2. **Not found via `queryForObject`**: querying ID 999 returns no rows, so `EmptyResultDataAccessException` is thrown. This is also a subclass of `IncorrectResultSizeDataAccessException`.
3. **Two rows when only one is required**: `queryForObject` across the whole table throws `IncorrectResultSizeDataAccessException`; `getActualSize()` reports `2`.
4. **Invalid column name**: H2 reports an SQL error; the JDBC translator converts it into `BadSqlGrammarException`. This is also a `DataAccessException`.

**Testing note:** the exact subclass name for a vendor SQL exception may depend on the translator/driver, so the example catches `DataIntegrityViolationException` instead of relying on every DBMS always producing `DuplicateKeyException`. Result-size exceptions are determined by Spring's `queryForObject` contract, not necessarily because the database rejected the SELECT statement.

### Comparison with Plain JDBC

In plain JDBC, an INSERT violating UNIQUE typically causes `executeUpdate()` to throw `SQLException` (checked). When using `JdbcTemplate`, the error is wrapped and classified. **The SQL still fails the same way**; Spring only provides a uniform exception type and resource management support.

`JdbcTemplate` does not automatically turn all invalid business conditions into exceptions. For example:

```java
int affected = jdbc.update(
        "UPDATE accounts SET email = ? WHERE id = ?",
        "new@example.test", 123456L);
System.out.println(affected); // 0: Valid SQL, but no matching rows.
```

This is a **snippet inside a method that already has `JdbcTemplate jdbc`**, not runnable standalone. If business logic requires exactly one row to be updated, the service needs to check `affected != 1` and decide to throw an appropriate domain exception. You cannot assume every missing-data case will produce `EmptyResultDataAccessException`.

## 6. Handling Exceptions by Level of Specificity

Exceptions should be handled at the **layer that has enough information to make a decision**. The DAO primarily reports data errors; the service determines business rules; the controller/API maps them to the external protocol. There is no rule that every `DataAccessException` must be caught in the DAO.

Example service code snippet (assuming `JdbcTemplate jdbc` is injected and an `Account` model exists):

```java
public void createAccount(long id, String email) {
    try {
        jdbc.update(
                "INSERT INTO accounts (id, email) VALUES (?, ?)",
                id, email);
    } catch (org.springframework.dao.DuplicateKeyException ex) {
        throw new IllegalStateException("Account ID or email already exists", ex);
    }
}
```

This is a **component snippet**, without a complete Spring configuration. `IllegalStateException` only illustrates converting into a message/domain error with a cause; real applications should define consistent domain exceptions. **Do not always assume `DuplicateKeyException` occurred because of `email`**: it could be due to a duplicate `id`. If the API needs to respond accurately, it must determine which constraint was violated based on system rules rather than guessing from an arbitrary SQL error message.

For queries where data is optional:

```java
public java.util.Optional<String> findEmail(long id) {
    java.util.List<String> emails = jdbc.queryForList(
            "SELECT email FROM accounts WHERE id = ?",
            String.class, id);
    return emails.stream().findFirst();
}
```

This is also a **component snippet**; because ID is the primary key, there is at most one row. It returns `Optional.empty()` if no data is found, expressing "may be absent" in the method contract instead of requiring the caller to handle an exception.

If a flow genuinely wants to return 404 when not found, the service/API can convert `EmptyResultDataAccessException` or `Optional.empty()` into a domain "not found". However, `DataAccessException` **does not automatically map to HTTP status codes**: neither Spring MVC nor Spring Boot will automatically turn every subclass into 404/409 unless the application declares appropriate handling.

### Catch Order Matters

Catch **more specific classes first**, and parent classes afterward:

```java
try {
    // Data access via Spring.
} catch (org.springframework.dao.DuplicateKeyException ex) {
    // Unique/primary key conflict recognized by the translator.
} catch (org.springframework.dao.DataIntegrityViolationException ex) {
    // Remaining types of constraint violations.
} catch (org.springframework.dao.DataAccessException ex) {
    // Data access errors not handled in the branches above.
}
```

This is an illustrative snippet (the `try` body depends on business logic). If you put `catch (DataAccessException)` first, Java will report the subsequent subclass `catch` blocks as unreachable. Avoid catching the root exception and returning success, as that hides real failures.

## 7. Relationship with @Repository and JPA/Hibernate

When using `JdbcTemplate`, exception translation resides directly inside the JDBC execution path. With code using **JPA/Hibernate directly**, the provider may throw `jakarta.persistence.PersistenceException`, `OptimisticLockException`, or Hibernate-specific exceptions. Spring can translate them into the `DataAccessException` hierarchy, but the translation path must be properly integrated and configured.

Example Spring-managed DAO:

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Repository;

@Repository
public class AccountJpaDao {
    @PersistenceContext
    private EntityManager entityManager;

    public Object find(long id) {
        return entityManager.find(AccountEntity.class, id);
    }
}
```

This snippet **illustrates usage in a JPA-configured application**; `AccountEntity` is assumed to be annotated with `@Entity`, and the build requires a suitable JPA provider/transaction manager. `@Repository` marks a persistence-layer bean. When the application registers `PersistenceExceptionTranslationPostProcessor` along with appropriate `PersistenceExceptionTranslator` beans (or uses supporting auto-configuration), persistence exceptions can be translated through the `@Repository` bean proxy.

**Important limitations:**

- Simply annotating a class with `@Repository` **does not automatically guarantee** every native exception is translated if the post-processor/translator mechanism is not active.
- Exceptions can occur during `flush()` or **transaction commit**, after the DAO code has already returned. In that case, the catch site and translation behavior may differ from a normal repository method call.
- Per the JPA contract, `EntityManager.find(...)` can return `null` if the entity is not found; it does not automatically throw `EmptyResultDataAccessException` like `JdbcTemplate.queryForObject(...)`.
- Certain Java or mapping errors do not fit `DataAccessException`; do not force every `IllegalArgumentException`/`NullPointerException` into a database error.

**Reading from a DAO-swappability perspective:** If the service layer cares about the "concurrently updated" rule, it should handle `OptimisticLockingFailureException` or a corresponding domain exception, rather than depending directly on the exception name of a specific Hibernate version.

## 8. DataAccessException and Transaction Rollback

Because every `DataAccessException` is a `RuntimeException`, **by default**, such an exception escaping a Spring-managed transactional method marks the transaction for rollback.

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.jdbc.core.JdbcTemplate;

@Service
public class RegistrationService {
    private final JdbcTemplate jdbc;

    public RegistrationService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void register(long accountId, String email) {
        jdbc.update("INSERT INTO accounts (id, email) VALUES (?, ?)",
                accountId, email);
        jdbc.update("INSERT INTO registration_events (account_id) VALUES (?)",
                accountId);
    }
}
```

This is a **component class of a Spring application**, assuming tables `accounts` and `registration_events` exist, a suitable `DataSource`/transaction manager is configured, and Spring invokes the method through a transactional proxy. If the second INSERT fails and `DataAccessException` escapes `register`, Spring rolls back all changes belonging to the same transaction.

Common pitfalls:

1. `@Transactional` only takes effect when the call goes through an active transaction interception mechanism. Calling `new RegistrationService(...)` manually or via self-invocation bypasses the proxy and can skip the transaction.
2. By default, Spring rolls back on `RuntimeException` and `Error`. Checked exceptions do not automatically roll back unless configured via `rollbackFor` (or other rules).
3. If you catch `DataAccessException` **inside** a transaction and still return normally, the transaction management code may no longer receive the failure signal; depending on the DB technology, the transaction may also already be marked rollback-only. Do not swallow errors.
4. `@Transactional(noRollbackFor = SomeDataAccessException.class)` can override the default. Use this only with a clear design, because committing after a data access failure can easily violate invariants.
5. With JPA, constraint violations may surface at flush or commit time; the observed failure point is not necessarily the line calling `save(...)`.

**Do not catch an error inside a transaction and immediately re-run the SQL on the same persistence context/connection** if the DB has put the transaction into an aborted state or the persistence context is no longer consistent. Evaluate rollback and start a new transaction at an appropriate boundary.

## 9. Classifying Errors to Choose a Remediation Strategy

There should not be a single global `catch (DataAccessException) { retry(); }`. The strategy depends on the subclass and business logic:

| Error group | Example | Typically appropriate policy |
| --- | --- | --- |
| Non-transient | `BadSqlGrammarException` | Fix the SQL, schema, or migration |
| Non-transient | `DataIntegrityViolationException` | Validate data/constraints; return an appropriate business error |
| Non-transient | `EmptyResultDataAccessException` | Clarify contract: is not-found valid? |
| Transient | `QueryTimeoutException` | Inspect load, timeout, performance, and bounded retry if safe |
| Transient | `CannotAcquireLockException` | Consider retrying the entire transaction with backoff and a retry limit |
| Transient | `OptimisticLockingFailureException` | Reload the latest version and reconcile; do not silently overwrite the newer version |
| Recoverable | `RecoverableDataAccessException` | Recover connection/resource, then retry the whole operation when safe |
| Resource failure | `DataAccessResourceFailureException` | Check infrastructure availability, connection pool state, circuit breaker |

**"Transient" does not mean you can retry arbitrarily.** Only retry when the operation is safe to re-execute: idempotent, does not cause duplicate emails/payments, has clear commit status, and uses timeouts and backoff. Usually you must retry **the entire transaction in a new invocation**, rather than retrying a single SQL statement mid-way through a failed transaction. Optimistic locking errors require resolving concurrent data changes; blindly incrementing the version and rewriting stale values easily causes *lost updates*.

If you cannot determine for sure whether a commit succeeded after a network error, retrying a write without an idempotency key or deduplication lock can produce duplicate side effects. Proper API/transaction design is required; this cannot be inferred from the exception class alone.

## 10. Inspecting the Root Cause for Diagnostics

`DataAccessException` inherits helper methods for accessing the cause chain from `NestedRuntimeException`:

- `getCause()`: the directly wrapped exception, if any.
- `getRootCause()`: the cause at the end of the chain, which may be `null` if there is no cause.
- `getMostSpecificCause()`: returns the most specific cause; if there is no cause, returns the current exception itself.
- `contains(SomeException.class)`: checks whether a given exception type appears anywhere in the cause chain.

In particular, JDBC exceptions such as `BadSqlGrammarException` also expose `getSQLException()` (and `getSql()`) to inspect the underlying SQL error when needed. Not every `DataAccessException` has a `SQLException` as its cause (for instance, result-size errors originate from Spring's own contract).

Example **utility method** for a handler/logging class:

```java
import java.sql.SQLException;
import org.springframework.dao.DataAccessException;

public static String describeDataAccessError(DataAccessException ex) {
    Throwable deepest = ex.getMostSpecificCause();
    String category = ex.getClass().getSimpleName();

    if (deepest instanceof SQLException sql) {
        return category + " (SQLState=" + sql.getSQLState()
                + ", vendorCode=" + sql.getErrorCode() + ")";
    }

    return category + " (cause=" + deepest.getClass().getSimpleName() + ")";
}
```

This is a **method placed inside a valid class**, not a program with `main`. It uses `instanceof` pattern matching available since Java 16 (compatible with Java 17+). Accessing SQLState/vendor code aids investigation; **do not hardcode HTTP status codes or business messages based on unverified SQLState strings**.

**Security principles when logging errors:** record the error type, SQLState code, trace/correlation ID, and necessary operational metadata; avoid logging full SQL statements with parameters containing passwords, tokens, personal data, card numbers, or secrets. Respond to API callers with safe messages instead of exposing `ex.getMessage()` directly.

## 11. Decision Table at the Service and API Layers

| Scenario | Spring error type you may encounter | Service handling | Illustrative HTTP response when appropriate |
| --- | --- | --- | --- |
| Creating an account with duplicate email | `DuplicateKeyException`/`DataIntegrityViolationException` | Convert to domain conflict after identifying which constraint failed | `409 Conflict` |
| ID lookup requires a record but finds none | `EmptyResultDataAccessException` (with `queryForObject`) | Convert to not-found per contract | `404 Not Found` |
| Query returns two rows when one is required | `IncorrectResultSizeDataAccessException` | Check invariants, DB/schema, and query | Usually a server-side error |
| User submits an old version | `OptimisticLockingFailureException` | Request refresh/state reconciliation | `409 Conflict`, or `412 Precondition Failed` with HTTP `If-Match` |
| DB timing out / connection lost | `QueryTimeoutException`/resource exception | Handle availability, controlled retry, operational logging | Possibly `503 Service Unavailable` |
| Invalid SQL due to missing deployment migration | `BadSqlGrammarException` | Report internal error, fix schema/SQL | `500 Internal Server Error` |

HTTP status codes are **only examples depending on API design**. Spring `DataAccessException` does not set HTTP status codes automatically. Do not turn every `DataIntegrityViolationException` into `409` (it could be a foreign key or NOT NULL error caused by an internal bug), or every `DataAccessException` into `404`.

In a system with multiple DAOs, the service should rely on **business context and sufficiently specific subclasses**. At the boundary layer, a generic handler for `DataAccessException` can ensure errors do not leak externally while logging/preserving the cause for operations.

## 12. Testing Behavior and Common Mistakes

Cases that should be included in integration tests (using H2 for learning and a real DB to verify production behavior):

| Case | Operation | Expected outcome to verify |
| --- | --- | --- |
| Duplicate key | INSERT with an existing email | Catch `DataIntegrityViolationException` or a compatible subclass |
| Not found | `queryForObject` when no row exists | `EmptyResultDataAccessException` |
| Too many results | `queryForObject` when multiple rows exist | `IncorrectResultSizeDataAccessException` |
| No rows but API allows it | `query` with non-matching condition | Empty list, no forced exception |
| UPDATE matches nothing | `JdbcTemplate.update` with absent ID | Row count `0`; service interprets it |
| Invalid SQL | Querying a nonexistent column | Invalid resource usage exception, typically `BadSqlGrammarException` |
| Two-step transaction | INSERT A succeeds, INSERT B violates constraint | Transaction rolls back; A is absent after rollback |
| Optimistic locking | Two requests with the same version | One update wins; the stale request receives a conflict or appropriate exception |
| Transient error | Controlled simulated lock/timeout | Retry only at a safe boundary, with a limit |
| JPA exception translation | ORM-backed repository hits a constraint violation | Verify translation actually works and check flush/commit timing |

**Common design mistakes:**

1. **Confusing `DataAccessException` with `SQLException`.** The former is an unchecked Spring exception; the latter is a checked JDBC exception. Do not catch `SQLException` directly around `JdbcTemplate.queryForObject` expecting it to catch translated errors.
2. **Assuming all DB errors become `DataAccessException`.** Raw JDBC APIs or JPA code outside integration/translators may throw their own exception types.
3. **Catching `DataAccessException` before its subclasses.** This makes specific `catch` blocks unreachable or loses differentiated handling.
4. **Confusing `EmptyResultDataAccessException` with a DB outage.** It may simply mean the result did not match the query contract.
5. **Treating `TransientDataAccessException` as a signal for unlimited retries.** Retrying can duplicate side effects, increase load, or overwrite newer data.
6. **Swallowing exceptions inside a transaction.** The system may partially commit or end up in an unintended rollback-only state.
7. **Rigidly mapping subclasses to HTTP status codes.** You must verify the constraint, business context, and API contract.
8. **Dropping the cause.** When creating a domain exception or logging, retain `ex` as the cause (when appropriate) to preserve JDBC SQLState/driver traceability.
9. **Using unit tests with mocked exceptions as proof of real mapping.** Mockito can verify catch branches; only integration tests verify translator + driver + schema behavior.
10. **Assuming `DataAccessException` is always a user-caused error.** Some are input data errors, while others are SQL, migration, connection, transaction, or code bugs.

**Application checklist:**

- Is the repository layer using `JdbcTemplate`, Spring Data repositories, or JPA/Hibernate APIs directly? Is exception translation actually active on that path?
- **Which** error types does the service need to make decisions; should it catch a subclass or let the exception propagate?
- Is missing data a normal outcome or a contract violation? Choose `query`/`Optional` or `queryForObject` accordingly.
- Are transaction boundaries and rollbacks correct when an exception occurs in the DAO, at flush, or at commit?
- If retrying: are idempotency, a new transaction, retry limits, and backoff in place?
- Are there integration tests with the real database/driver and safe logging for failure scenarios?

**Conclusion:** `DataAccessException` is the foundation for Spring to represent data access errors as runtime exceptions with consistent semantics. Its value lies in **classifying and handling the right subclass**, preserving the technical cause, coordinating with transactions/rollbacks, and placing business policies in the appropriate layer.

## References

- Spring Framework, `DataAccessException` Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/dao/DataAccessException.html
- Spring Framework, DAO Support / Consistent Exception Hierarchy: https://docs.spring.io/spring-framework/reference/data-access/dao.html
- Spring Framework, JDBC Core / `SQLExceptionTranslator`: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring Framework, `SQLExceptionSubclassTranslator` Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/support/SQLExceptionSubclassTranslator.html
- Spring Framework, ORM Exception Translation: https://docs.spring.io/spring-framework/reference/data-access/orm/general.html
- Spring Framework, Transaction Rollback: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html
- Spring Framework, `DataIntegrityViolationException` Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/dao/DataIntegrityViolationException.html
- Spring Framework, `EmptyResultDataAccessException` Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/dao/EmptyResultDataAccessException.html