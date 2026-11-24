# Do Not Equate Every DataAccessException with a Business Error

## 1. The Problem: A Data Access Error Is Not Automatically a Business Error

In Spring Framework, `org.springframework.dao.DataAccessException` is the root of the exception hierarchy used to describe **failures while accessing data**. `JdbcTemplate`, Spring JDBC utilities, and certain JPA/Hibernate integrations can translate storage-technology errors into exceptions in this hierarchy.

However, **an error at the data layer does not inherently carry the same meaning as a business error**. For example:

- A user registers with an already existing email: if the operation is creating an account and violates specifically the email unique constraint, the application can return a business error like `EMAIL_ALREADY_USED`.
- SQL references a nonexistent column: that is usually a code or schema/migration bug, not bad user input.
- The database loses connection: that is an infrastructure incident, not a business rule.
- A single-row query returns no records: sometimes that is valid and should return `Optional.empty()`; in another flow, it represents a missing resource or a broken invariant.
- A deadlock or timeout: may be a temporary issue needing controlled retries, not proof that the business request permanently failed.

**A mistake to avoid** is catching every `DataAccessException` and always returning the same message such as "Invalid information", "Already exists", or HTTP 400:

```java
// Anti-pattern: hiding every technical cause under one business label.
try {
    accountRepository.insert(email);
} catch (DataAccessException ex) {
    throw new BusinessException("Invalid information");
}
```

This is only an **anti-pattern snippet**, not a standalone program; `BusinessException` is a hypothetical type. If the DB cannot connect or the code contains invalid SQL, this snippet misleads users, skews error metrics, and complicates investigation.

Proper design requires **evaluating the exception type + operation context + specific data constraint + recoverability** before deciding whether to translate into a business error.

## 2. Separating Three Layers of Meaning: Persistence, Domain, and API

Consider an account registration application:

```text
HTTP request / message
        │
        ▼
Application service
  ├── Validates business rules
  ├── Decides operations and transactions
  └── Converts DB errors with confirmed meaning into domain errors
        │
        ▼
Repository / JdbcTemplate
        │  SQL + prepared parameters
        ▼
Database / JDBC driver
        │  SQLException (SQLState, vendor error code, cause)
        ▼
Spring SQLExceptionTranslator
        │  DataAccessException and subclasses
        ▼
Application service handles selectively
        │
        ▼
API layer converts result/domain error into an appropriate response
```

Specific roles:

1. **Persistence exception** (e.g., `DuplicateKeyException`, `BadSqlGrammarException`): describes a data access failure, carrying technical details to aid resolution.
2. **Domain/application exception** (e.g., `EmailAlreadyUsedException`, `OrderStateConflictException`): expresses **the rules and contract of a specific use case**, remaining meaningful even if you later migrate from JDBC to another technology.
3. **API error** (e.g., error code `EMAIL_ALREADY_USED` with HTTP 409): how the error is presented to callers per the communication contract. HTTP status codes are not an inherent property of `DataAccessException`.

Do not create a global mapping table such as "every `DataIntegrityViolationException` is HTTP 409" or "every `DataAccessException` is HTTP 400". The exact same exception can carry different meanings depending on where it occurs.

### Example: One DB Error, Three Interpretations

A unique constraint violation can be:

- **Duplicate email during registration:** business conflict `EMAIL_ALREADY_USED`.
- **Internal transaction ID generated twice due to a bug:** a system bug to investigate, not the user's fault.
- **Repeated idempotency key:** possibly a valid retry request; read the prior result and verify payload per the idempotency contract rather than returning "email already exists".

Seeing the name `DuplicateKeyException` alone is **not enough** to decide the API's response.

## 3. Spring's Exception Hierarchy and Its Meaning

`DataAccessException` is an **unchecked exception** (extending `NestedRuntimeException`), so the repository layer is not forced to declare `throws`. It is designed to reduce code coupling to specific data technologies.

Notable branches:

| Group/type | Technical info | Handling implication |
| --- | --- | --- |
| `NonTransientDataAccessException` | Repeating the same operation under the same conditions will usually keep failing until the cause is fixed | Do not retry blindly |
| `TransientDataAccessException` | Operation **might** succeed if retried without modifying the request | Retry only after checking safety and transactions |
| `RecoverableDataAccessException` | Recoverable after an appropriate recovery action, such as obtaining a new connection | Recover and retry the **entire transaction**, do not treat as a business error |
| `UncategorizedDataAccessException` | Underlying error could not be classified precisely | Preserve cause; investigate, do not guess business meaning |
| `DataIntegrityViolationException` | Data constraint violation or integrity error recognized by the translator | Identify **which constraint** and **which use case** before translating to domain |
| `DuplicateKeyException` | Primary/unique key violation; a subclass of `DataIntegrityViolationException` | Can become a domain conflict if it matches a business unique key |
| `EmptyResultDataAccessException` | Code expected at least one result, but the query returned none | May be valid absence, 404, or an invariant error depending on the API |
| `IncorrectResultSizeDataAccessException` | Returned row count differed from what code expected | Multiple rows when expecting one is usually a design/data bug |
| `BadSqlGrammarException` | Invalid SQL (may also be caused by a nonexistent column/table) | Usually a bug/migration issue requiring a system fix |
| `InvalidDataAccessApiUsageException` | Data API used against its contract | Usually an application bug |
| `PessimisticLockingFailureException` | Failure related to pessimistic locking | Consider retry/backoff or conflict depending on the use case |
| `OptimisticLockingFailureException` | Optimistic version conflict detected by the framework | May be a business conflict if the API uses version/ETag |
| `QueryTimeoutException` | Query exceeded allowed time | Execution failure; do not interpret as "not found" |
| `DataAccessResourceFailureException` | Data resource failed, e.g., unable to connect to DB | Infrastructure failure, handle per system availability |

**Note on class names:** `BadSqlGrammarException` lives in `org.springframework.jdbc`; most other types in the table live in `org.springframework.dao`. Classes like `DeadlockLoserDataAccessException` were deprecated in Spring 6.x releases; prefer the `PessimisticLockingFailureException`/`CannotAcquireLockException` branch when handling lock mechanisms.

The exception name is a **useful technical classification**, not absolute proof that a business rule failed. Not every driver, database, or translator produces the same level of subclass granularity.

### Better Branching Example

```java
try {
    repository.save(request);
} catch (DuplicateKeyException ex) {
    // Only convert into a domain error if you are certain the unique constraint
    // this operation can violate carries that exact business meaning.
    throw new EmailAlreadyUsedException(ex);
}
// Do not catch-all DataAccessException to convert every error into EmailAlreadyUsed.
```

This is an **illustrative snippet**, relying on a repository and domain exception in a real application. On tables with multiple unique constraints, identify the exact meaningful constraint, or use dedicated access operations to reduce the chance of misinterpretation.

## 4. How Spring Translates SQLException, and Why Not to Rely Strictly on Exception Names

When a JDBC driver reports `SQLException`, it usually includes:

- `SQLState`: standard or vendor code, e.g. `23505` typically represents a unique error in H2/PostgreSQL.
- `getErrorCode()`: vendor numeric error code.
- `getMessage()` and `getNextException()`: description and chained information from the driver.
- `SQLException` subtype: e.g., `SQLIntegrityConstraintViolationException` or `SQLTransientException`.

Spring's `SQLExceptionTranslator` maps that information into the `DataAccessException` tree. Since Spring Framework 6.x, the default translator for `JdbcTemplate` is `SQLExceptionSubclassTranslator`, with SQLState fallback. `SQLErrorCodeSQLExceptionTranslator` can be used to apply vendor-specific codes or custom mappings when needed. This explains why **the exact same constraint violation can be classified at different levels of granularity** across drivers/configurations.

Do not write business logic relying solely on English strings inside `SQLException.getMessage()`. Messages can vary across versions, localization, drivers, and DBs. When distinguishing multiple unique constraints in the same operation, design named constraints, build mappings tested on the exact DB, and keep safe fallback handling.

Methods from `NestedRuntimeException` such as `getRootCause()` and `getMostSpecificCause()` help trace the root cause. Example **illustrative Java utility snippet**:

```java
import java.sql.SQLException;

static void diagnose(DataAccessException failure) {
    Throwable mostSpecific = failure.getMostSpecificCause();
    if (mostSpecific instanceof SQLException sql) {
        System.out.println("SQLState=" + sql.getSQLState());
        System.out.println("VendorCode=" + sql.getErrorCode());
    }
}
```

This snippet is **not standalone** because it requires importing `org.springframework.dao.DataAccessException` and placing the method inside a class. Moreover, `getMostSpecificCause()` is not guaranteed to always be an `SQLException`; it could be another cause. In real applications, log technical details in a controlled manner and never expose SQL statements or sensitive data in API responses.

## 5. When Does a DataAccessException Truly Map to a Business Error?

You can convert a technical exception into a domain error when all three conditions hold:

1. **The use case has a defined rule**: e.g., each email belongs to at most one account.
2. **There is evidence the exception corresponds to that exact rule**: e.g., an `INSERT` into a table with only one unique constraint on email, or a mechanism identifying the exact constraint.
3. **The domain/API publishes corresponding behavior**: e.g., reporting "Email is already in use", allowing the client to change the email and retry.

You must also look at the operation:

| Situation | Appropriate handling | Why |
| --- | --- | --- |
| Registering an existing email, confirmed email unique constraint | Convert to `EmailAlreadyUsedException` | Defined business rule |
| Fetching an optional record that does not exist | Return `Optional.empty()` | "No result" is a valid outcome |
| Fetching a required resource by ID that does not exist | Can become `AccountNotFoundException` | Use case requires existence |
| Query expecting uniqueness returns 2 rows | Investigate invariant/schema, do not return `NotFound` | Data exists, but row count is wrong |
| Unique key on an internal table collides due to a bug | System error | Not a user-driven conflict |
| Foreign key / CHECK / NOT NULL violated | Inspect specific constraint and call | Could be a mapper bug, stale data, or bad request |
| Query timed out | Report appropriate technical error, observe and fix | Insufficient evidence of invalid data |
| DB unreachable | Handle outage/availability, do not return "invalid data" | Infrastructure issue, may need circuit breaker |
| Invalid SQL or missing migration | Application needs code/schema fix | Cannot ask the user to change email to fix it |

**Principle:** handle as a business error only when you can explain **which rule was violated** and **what the caller can do next**.

### Why Doesn't Checking "Already Exists?" Replace a Unique Constraint?

Business flow:

```text
Request A: SELECT email -> absent
Request B: SELECT email -> absent
Request A: INSERT email -> succeeds
Request B: INSERT email -> DB reports unique violation
```

Two requests run concurrently, so prechecking is insufficient against race conditions. The database constraint enforces uniqueness; the application handles the **true conflict** when the constraint is violated. You may precheck to improve messages, but never rely on it for correctness.

## 6. Complete Example: Translating Only Duplicate Email While Preserving Technical SQL Errors

This Spring Boot 3.5.7, Java 17+, Spring JDBC, and H2 example demonstrates three cases:
- Duplicate email → domain exception `EmailAlreadyUsedException`.
- Missing record in optional lookup API → `Optional.empty()`.
- Nonexistent SQL column → technical `BadSqlGrammarException`, **not turned into** `EmailAlreadyUsedException`.

Project:

```text
data-access-exception-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/daoerror/
    │   └── DataAccessExceptionDemoApplication.java
    └── resources/
        ├── schema.sql
        └── application.properties
```

**`pom.xml`**:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>data-access-exception-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

**`src/main/resources/schema.sql`**:

```sql
CREATE TABLE accounts (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE
);
```

**`src/main/resources/application.properties`**:

```properties
spring.datasource.url=jdbc:h2:mem:dao_exception_demo;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
spring.main.banner-mode=off
logging.level.root=ERROR
```

**`src/main/java/com/example/daoerror/DataAccessExceptionDemoApplication.java`**:

```java
package com.example.daoerror;

import java.util.Optional;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.jdbc.BadSqlGrammarException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import org.springframework.stereotype.Service;

@SpringBootApplication
public class DataAccessExceptionDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DataAccessExceptionDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(AccountService service, JdbcTemplate jdbc) {
        return args -> {
            service.register("an@example.test");

            System.out.println("Existing found: " +
                    service.findId("an@example.test").isPresent());
            System.out.println("Missing returned empty: " +
                    service.findId("missing@example.test").isEmpty());

            try {
                service.register("an@example.test");
            } catch (EmailAlreadyUsedException ex) {
                System.out.println("Business exception: " +
                        ex.getClass().getSimpleName());
            }

            try {
                jdbc.queryForObject(
                        "SELECT missing_column FROM accounts",
                        String.class);
            } catch (BadSqlGrammarException ex) {
                System.out.println("Technical SQL exception: " +
                        ex.getClass().getSimpleName());
            }
        };
    }
}

@Repository
class AccountRepository {
    private final JdbcTemplate jdbc;

    AccountRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    void insert(String email) {
        jdbc.update("INSERT INTO accounts (email) VALUES (?)", email);
    }

    Long findId(String email) {
        return jdbc.queryForObject(
                "SELECT id FROM accounts WHERE email = ?",
                Long.class,
                email);
    }
}

@Service
class AccountService {
    private final AccountRepository repository;

    AccountService(AccountRepository repository) {
        this.repository = repository;
    }

    public void register(String email) {
        try {
            repository.insert(email);
        } catch (DuplicateKeyException ex) {
            // In the sample schema, email is the unique key supplied by the client.
            throw new EmailAlreadyUsedException(ex);
        }
    }

    public Optional<Long> findId(String email) {
        try {
            // Querying id by unique email returns at most one row.
            return Optional.ofNullable(repository.findId(email));
        } catch (EmptyResultDataAccessException ex) {
            // For an optional lookup API, having no record is normal.
            return Optional.empty();
        }
    }
}

final class EmailAlreadyUsedException extends RuntimeException {
    EmailAlreadyUsedException(Throwable cause) {
        super("Email is already registered", cause);
    }
}
```

The package-private classes `AccountRepository`, `AccountService`, and `EmailAlreadyUsedException` are placed in the same file as the public class matching the filename. Spring component scanning from package `com.example.daoerror` picks up `@Repository` and `@Service`. `JdbcTemplate` is configured by `spring-boot-starter-jdbc` with the H2 `DataSource`.

Run inside `data-access-exception-demo`:

```bash
mvn -q spring-boot:run
```

With a **fresh H2 database and empty table**, the four lines printed by the program are:

```text
Existing found: true
Missing returned empty: true
Business exception: EmailAlreadyUsedException
Technical SQL exception: BadSqlGrammarException
```

Additional messages from Maven/JVM depend on the environment. Results assume Spring JDBC 6.2.x in Spring Boot 3.5.7 and the H2 JDBC driver recognizing unique SQLState `23505`. On another DB/driver, **exception granularity must be verified with integration tests**.

Flow explanation:

1. Registering `an@example.test` the first time: `INSERT` succeeds.
2. Reading the existing email with `queryForObject(...)` returns an ID; looking up a nonexistent email causes `queryForObject` to throw `EmptyResultDataAccessException` and the service chooses `Optional.empty()`.
3. Registering the same email again: H2 hits the unique violation, Spring translates it to `DuplicateKeyException`; **only** the `register` service converts the error to `EmailAlreadyUsedException`.
4. Querying `missing_column` is a schema mistake. Spring throws `BadSqlGrammarException`; code does not catch it in the service as a business error. The demo catches it in the runner solely to illustrate and print the error type; real applications must log and investigate it.
5. `EmailAlreadyUsedException` still retains the original `cause` to assist diagnostics, while the domain message contains no SQL, table names, or internal details.

**Limitations of the example:** the table has only one natural unique constraint on `email` besides the database-generated primary key, and the statement passes only `email`. With tables having multiple unique constraints, catching every `DuplicateKeyException` in a complex operation can misinterpret the failure; identify the exact constraint/data source before reporting `EMAIL_ALREADY_USED`.

## 7. EmptyResult: A Normal Outcome in One API, an Error in Another

`EmptyResultDataAccessException` typically occurs when a method such as `JdbcTemplate.queryForObject(...)` expects one row, yet the query returns **0 rows**. It should not be equated with `NotFound` in every case.

Examples:

- `Optional<User> findByEmail(email)`: a user lacking that email may be a valid result; return `Optional.empty()`.
- `User getById(id)` in a use case requiring the user to exist: can convert to `UserNotFoundException` (if access conditions and API contract permit).
- `loadSystemConfiguration("required-key")`: missing mandatory configuration is a system error, not a client 404.
- `findExactlyOneActiveSubscription(userId)`: if logic requires there always be exactly one row, zero rows may violate a business invariant and need separate handling.

In particular, **do not mask** `IncorrectResultSizeDataAccessException` caused by **multiple rows** inside a broad `catch` returning "not found". When a query designed for one record returns multiple records, that may indicate a missing unique constraint, join bug, or corrupt data.

When an API needs to return zero or multiple records without throwing on 0 rows, use `query(...)` returning a list:

```java
List<Long> ids = jdbcTemplate.query(
        "SELECT id FROM accounts WHERE email = ?",
        (rs, rowNum) -> rs.getLong("id"),
        email);
```

Illustrative snippet inside a method that already has `JdbcTemplate jdbcTemplate` and `String email`. In this API, an empty list is a normal outcome. However, when the contract requires a single unique record, preserve invariant checks rather than blindly taking the first element.

## 8. DataIntegrityViolationException Does Not Mean "Always Duplicate Data"

`DuplicateKeyException` is a subclass of `DataIntegrityViolationException`, yet the general category also covers errors such as:

- Foreign key: referencing a nonexistent parent record, or trying to delete a referenced record.
- `NOT NULL`: code binds `NULL` to a required column.
- `CHECK`: data violates a schema constraint.
- Certain mapping/type issues or other constraints classified under integrity by the translator.

Do not write:

```java
try {
    jdbcTemplate.update(sql, params);
} catch (DataIntegrityViolationException ex) {
    throw new EmailAlreadyUsedException(ex); // Wrong: could be FK/NOT NULL/CHECK.
}
```

This is an anti-pattern. A DB constraint may reflect a business rule, yet proper mapping requires **constraint name/violation type/request context**. Without sufficient evidence, let the technical error propagate through the application layer or wrap it as an infrastructure error while preserving cause; never guess and assign a business error code.

**Example distinguishing FK:**
- Client sends a deleted `customerId`, and the contract requires the customer to exist: you may return `CUSTOMER_NOT_FOUND` or conflict, depending on semantics.
- Repository code fetches the wrong ID due to a bug: system error; returning `CUSTOMER_NOT_FOUND` to the user masks the bug.

Write tests for each constraint that should translate to domain errors, rather than only asserting "throws DataIntegrityViolationException".

## 9. Being Retryable Does Not Mean Retrying Is Always Safe

`TransientDataAccessException` suggests an error might disappear on re-invocation, yet the application must answer four questions:

1. **Is the operation idempotent?** Reads are usually easier to retry than writes; retrying an `INSERT` without an idempotency key can create duplicate records.
2. **Did the prior attempt commit?** A timeout or disconnect can leave the caller **unsure** whether the write committed. Immediate retry could execute it twice.
3. **Is the transaction still usable?** After certain SQL errors, the current transaction or connection is no longer usable. You must roll back and retry in a new transaction/connection.
4. **What are the retry limits?** Max attempts, backoff with jitter, deadline, logs/metrics—avoid amplifying load while the DB is struggling.

Policy examples: for a simple read query hitting `CannotAcquireLockException` or timeout, bounded retries may be fine **if** logic and isolation permit. For writes with external effects (sending emails, charging money, emitting events), design idempotency or an outbox before auto-retrying. Never apply an unbounded retry interceptor across all `DataAccessException`s.

`RecoverableDataAccessException` refers to recoverability via an **extra recovery step**, at minimum acquiring a new connection and retrying the transaction; it is not a domain error either. `NonTransientDataAccessException` indicates retrying the same request is usually futile until the cause is fixed.

### Relationship with @Transactional

Under Spring Framework's default configuration, an **unchecked** exception escaping a `@Transactional` method causes the transaction to be marked for rollback. Both `DataAccessException` and custom domain exceptions extending `RuntimeException` fall into this group by default.

Catching a `DataAccessException` and **swallowing it** to return success can corrupt transaction state or let logic proceed on inconsistent data. With JPA/Hibernate, the resource may already have marked the transaction rollback-only; even if the method tries to return normally, `UnexpectedRollbackException` can still occur at commit.

If you want to retry an operation inside a transaction, normally place the retry loop **outside** the transaction boundary so each attempt gets a new transaction (or use `TransactionTemplate` to start fresh transactions). Calling a `@Transactional` method on the same instance may bypass the Spring proxy; do not assume the annotation applies under self-invocation.

## 10. Mapping to HTTP/API: Context Determines the Response Code

Selections aligned with **use-case contracts**:

| Scenario | Typically appropriate API outcome | Rationale/limitations |
| --- | --- | --- |
| Duplicate email at registration, confirmed constraint | `409 Conflict` + code `EMAIL_ALREADY_USED` | Client can pick a different email |
| Invalid request prior to DB access | `400 Bad Request` or `422 Unprocessable Content` per contract | Input validation, not inferred from `DataAccessException` |
| Required record does not exist | `404 Not Found` if caller is permitted to know | Derived from resource semantics |
| Version/ETag conflict during update | `409 Conflict` or `412 Precondition Failed` per HTTP contract | Concurrency precondition defined |
| DB outage with temporary policy | `503 Service Unavailable` or appropriate 5xx | Never disclose internal connection details |
| Bad SQL or missing migration | `500 Internal Server Error` | Technical bug needing a fix |
| Query timeout | Appropriate 5xx per deployment layer, not 404/400 by default | May require dedicated timeout/retry policy |
| Uncategorized exception | Generic 5xx error and correlation ID | Insufficient basis to assign a business rule |

HTTP status codes and application error codes must align with the active API contract. The table above is **guidance**, not a mandatory Spring mapping. In particular, HTTP 409 is for meaningful conflicts in the **requested resource's state**, not every DB error.

### ControllerAdvice Should Handle Only Intentional Domain Exceptions

The snippet below is an **additional illustration** for apps with `spring-boot-starter-web`, not part of section 6's console project:

```java
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiErrorAdvice {
    @ExceptionHandler(EmailAlreadyUsedException.class)
    ResponseEntity<Map<String, String>> emailConflict(
            EmailAlreadyUsedException ex) {
        return ResponseEntity.status(HttpStatus.CONFLICT).body(
                Map.of(
                        "code", "EMAIL_ALREADY_USED",
                        "message", "Email is already in use"));
    }
}
```

This example assumes `EmailAlreadyUsedException` is a type in the project and properly imported. Because section 6's demo lacks Spring Web, **do not copy this file into that project without adding `spring-boot-starter-web`** and adjusting packages/imports; in real apps, the handler belongs in the proper Java package with MVC tests.

Do not add:

```java
@ExceptionHandler(DataAccessException.class)
@ResponseStatus(HttpStatus.BAD_REQUEST)
void everythingIsBadRequest(DataAccessException ex) { /* ... */ }
```

This is an anti-pattern: it disguises SQL errors/lost connections as HTTP 400. If the app has a fallback handler for technical errors, return a generic response without leaking internal details, while logging the exception and correlation ID. Avoid "catch and forget".

## 11. Logging and Observability: Preserve Technical Details Server-Side

When the application converts an exception into a business error, do not lose `cause`. Example:

```java
final class EmailAlreadyUsedException extends RuntimeException {
    EmailAlreadyUsedException(Throwable cause) {
        super("Email is already registered", cause);
    }
}
```

Externally, the API returns only safe error codes/messages; server-side, the cause remains available for investigation when needed. However, avoid logging the entire stack trace redundantly at the repository, service, and controller for the same request if monitoring already logs at the outer boundary.

Useful details for internal logs/metrics/traces:

- Operation name: `AccountRepository.insert`, table/constraint name if safe to log.
- Subclass name: `DuplicateKeyException`, `BadSqlGrammarException`...
- SQLState and vendor error code when available, to distinguish JDBC causes.
- Request/correlation ID and use-case name.
- Connection acquisition time, query duration, retry count, and pool metrics when investigating incidents.

Never put passwords, connection URLs with secrets, full SQL containing user values, personal data, or raw database exception messages into client responses or inappropriate log levels.

Business and technical metrics should also be separated: `registration.email_conflict` reflects the use case; `db.query_timeout`, `db.connection_failure`, `db.sql_error` reflect system reliability. Lumping every failure into one "validation_failed" metric skews product analytics and operational alerts alike.

## 12. Testing So Exceptions Are Not Conflated

A useful test suite for the registration use case:

1. **Valid insert:** save a new email, assert the record exists.
2. **Duplicate on the right constraint:** insert the same email twice; assert the service throws `EmailAlreadyUsedException` and preserves `DuplicateKeyException` as cause (on the H2 driver used in the example).
3. **Missing email in optional lookup:** `findId(...)` returns `Optional.empty()`, does not throw a domain exception.
4. **Bad SQL:** intentionally run SQL with a nonexistent column in a separate test; assert the data error remains `BadSqlGrammarException`, not converted into `EmailAlreadyUsedException`.
5. **Other constraints:** on a real table with FK/CHECK/NOT NULL, prove those errors are **not mistakenly converted** into duplicate email.
6. **Multiple rows for a single-row query:** confirm the system does not return "not found" when data/queries actually violate invariants.
7. **Outage/timeout:** through appropriate integration/chaos tests, verify infrastructure errors are reported safely, retries are bounded, and side effects are not replayed.
8. **Transaction rollback:** in a multi-statement use case, confirm an unchecked error rolls back uncommitted changes and retries do not reuse a failed transaction.
9. **API contract:** test that responses return the proper business code for confirmed conflicts, while SQL/DB errors do not leak internal messages or turn into HTTP 400.

Whenever changing the DB, driver, or Spring version, re-run at least the critical exception-translation tests. Do not assume SQLState mappings and exception subclasses are identical across H2, PostgreSQL, MySQL, or SQL Server.

### Test Anti-Pattern to Recognize

```java
// Wrong: only tests that "every DataAccessException is converted to 400".
assertThatThrownBy(() -> service.register("x@example.test"))
        .isInstanceOf(BusinessException.class);
```

This is an illustrative pseudo-test snippet (requiring a test framework and corresponding app classes). It fails to reveal whether the underlying error was a duplicate, broken SQL, or a dropped DB connection. Valuable tests must **control the cause** and assert the **exact mapping for each use case**.

## 13. Decision Checklist When Encountering DataAccessException

Before writing `catch`:

1. **Which query/operation is this?** Optional read, required read, versioned update, or unique resource creation?
2. **What is the specific exception?** `DuplicateKeyException`, `EmptyResultDataAccessException`, `BadSqlGrammarException`, or another type?
3. **Do we know the exact constraint or invariant violated?** If not, do not assign a business error code.
4. **Can the caller fix the request?** Only when a clear domain rule exists should you guide them to change input.
5. **Is it safe to retry?** Evaluate idempotency, transactions, and commit status, not just the name `TransientDataAccessException`.
6. **What must be rolled back, observed, or alerted?** Preserve cause, log/metric in the right group, avoid sensitive info.
7. **What does the API contract require?** Translate domain errors at the boundary with clear codes; keep infrastructure errors on the infrastructure path.

**Coding rule:** handle the **most specific meaningful exception**, right at the layer that understands the operation's business rules. Errors without a business handling rule should propagate to the technical error boundary rather than being forced into a generic business error.

## 14. Knowledge Self-Check

1. Why is `DuplicateKeyException` insufficient to conclude "Email already exists" in a table with multiple unique constraints?
2. For `findOptionalByEmail`, when should `EmptyResultDataAccessException` become `Optional.empty()`?
3. If a service catches `DataAccessException` and always returns HTTP 400, which infrastructure errors does it mask?
4. A `QueryTimeoutException` occurs after a write statement: can you be certain the database did not commit? Why must you not retry infinitely?
5. Why is `BadSqlGrammarException` usually an operational/code issue rather than a user business error?
6. When using `@Transactional`, what happens by default when an unchecked exception escapes a method?
7. Why is passing tests on H2 insufficient to confirm PostgreSQL/MySQL driver translation?
8. Distinguish the business error code `EMAIL_ALREADY_USED` from the exception type `DataIntegrityViolationException` in terms of layer responsibility.

You can consider this lesson mastered when you consistently distinguish **the data access cause**, **the affected business rule**, and **how errors are reported to clients**.

## 15. Official Documentation

- [Spring Framework — DAO Support / Consistent Exception Hierarchy](https://docs.spring.io/spring-framework/reference/6.2/data-access/dao.html)
- [Spring Framework — JDBC Core / SQLExceptionTranslator](https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/core.html)
- [Spring Framework — DataAccessException Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/dao/DataAccessException.html)
- [Spring Framework — DataIntegrityViolationException Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/dao/DataIntegrityViolationException.html)
- [Spring Framework — DuplicateKeyException Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/dao/DuplicateKeyException.html)
- [Spring Framework — EmptyResultDataAccessException Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/dao/EmptyResultDataAccessException.html)
- [Spring Framework — SQLExceptionSubclassTranslator Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/jdbc/support/SQLExceptionSubclassTranslator.html)
- [Spring Framework — Declarative transaction rollback](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/rolling-back.html)
