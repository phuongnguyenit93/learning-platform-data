# TransactionException and Transaction Infrastructure Errors

## 1. Objective and Position in the Spring Model

When a method annotated with `@Transactional` fails, the error does not necessarily come from a SQL statement or business logic. Spring may also fail to open a transaction, detect that a transaction has already been marked rollback-only, fail to commit/rollback, or reject improper usage of the transaction API. This group of errors is represented by `org.springframework.transaction.TransactionException` and its subclasses.

This lesson focuses on **Spring's transaction model**, specifically the meaning of exceptions at the boundary between the application, `PlatformTransactionManager`, and the storage system. After this lesson, you should be able to:

1. Distinguish business errors, data access errors, and errors from transaction coordination infrastructure.
2. Identify important `TransactionException` types, when they occur, and the degree of certainty about data state.
3. Correctly explain `UnexpectedRollbackException` when a transaction has been marked rollback-only.
4. Investigate root causes, decide on handling/retries, and verify rollback/commit using data.
5. Write integration tests for real transaction paths and unit tests simulating errors at the transaction manager.

Scope: **Spring Framework 6.x, imperative transaction model with JDBC**; examples use Java 17+, Spring Boot 3.3.x, H2, Spring Test/JUnit 5. With JPA, JTA, or reactive transactions, some errors may surface at different times and be translated into different exception types. Do not infer from an exception name that every database or every transaction manager behaves identically.

## 2. Three Error Sources to Separate

Keep the following model in mind before reading a stack trace:

```text
HTTP / job / caller
      |
      v
@Transactional proxy / TransactionInterceptor
      |              |
      |              +-- PlatformTransactionManager
      |                       | begin / join
      |                       | commit / rollback
      v                       v
Service -> Repository/JdbcTemplate -> Connection / Database
```

| Error source | Examples | Meaning |
| --- | --- | --- |
| **Business / Java** | `IllegalArgumentException`, `BusinessRuleException` | Code decided the operation is invalid; rollback rules depend on the exception and configuration |
| **Data access** | `DataIntegrityViolationException`, `CannotGetJdbcConnectionException` | Spring translated a DB access error into the `org.springframework.dao.DataAccessException` hierarchy |
| **Transaction infrastructure** | `CannotCreateTransactionException`, `UnexpectedRollbackException`, `TransactionSystemException` | Spring/transaction manager encountered an error creating, joining, ending, or using a transaction |

**`DataAccessException` is not a subclass of `TransactionException`.** Both are separate runtime exception hierarchies. SQL errors thrown by `JdbcTemplate` are usually `DataAccessException`; commit/rollback errors from `PlatformTransactionManager` usually belong to the `TransactionException` family, **but not always**: `JdbcTransactionManager` can translate errors at the commit/rollback step into `DataAccessException`, matching `JdbcTemplate`'s exception translation mechanism.

`@Transactional` rolls back by default when a `RuntimeException` or `Error` escapes the method through the transaction interceptor; checked exceptions do not trigger rollback by default (unless configured otherwise). Because both `TransactionException` and `DataAccessException` are runtime exceptions, they usually trigger the default rollback rule **if thrown within the scope the interceptor is still handling**. However, an error thrown inside `commit()` or `rollback()` itself cannot simply be treated as "a business exception causing Spring to roll back": the transaction manager may have already finished or be in an indeterminate state.

## 3. At Which Stages Can a Transaction Fail?

```text
(1) Receive service call through proxy
       |
(2) TransactionManager.getTransaction(...)
       |  cannot open -> CannotCreateTransactionException
       v
(3) Run service / SQL
       |  DB error -> DataAccessException, or business error
       v
(4) Choose commit or rollback per rules / rollback-only
       |
       +-- rollback-only while caller attempts commit
       |         -> UnexpectedRollbackException
       |
       +-- commit/rollback resource error
       |         -> TransactionSystemException or DataAccessException
       v
(5) Cleanup / return result to caller
```

| Timing | Questions to investigate | What can be concluded about data? |
| --- | --- | --- |
| **Not yet started** | Is there connectivity? Right manager configured? Missing transaction capability? | If the transaction was never created, nothing from that transaction committed; side effects elsewhere may still exist |
| **Inside method** | Which statement failed? Did the exception escape through the proxy? Was the transaction rollback-only? | Cannot conclude commit; let the boundary finish and re-read data |
| **At commit** | Did the database confirm commit or just drop connection/time out? | **Outcome may be unknown**; do not assume rollback by default |
| **At rollback** | Did rollback succeed or throw a new error? | Cannot guarantee all changes were discarded if rollback failed; must verify |
| **After transaction ends** | Did a synchronization callback, event publish, or non-DB task fail? | Data may already be committed even though caller receives an exception from post-commit work |

The most common mistake is **equating "caller received an exception" with "database rolled back"**. An exception can occur **after SQL has been sent or after the database accepted commit**. If the network drops at commit time, the application may not know for sure whether the database committed. For operations with business side effects, blind retries can create duplicate records or repeat an already-succeeded transaction.

## 4. The `TransactionException` Family: Meaning and Handling

`TransactionException` is an abstract class in `org.springframework.transaction`, extending `NestedRuntimeException` (a `RuntimeException`). Do not instantiate this class directly; Spring and transaction managers throw concrete subclasses.

### 4.1. Common Types

| Exception type | Typical situation | Approach |
| --- | --- | --- |
| `CannotCreateTransactionException` | Cannot start a transaction because a resource could not be obtained or the underlying transaction API rejected it | Check connectivity, DB availability, pool, credentials, manager, and root cause |
| `UnexpectedRollbackException` | Outer scope attempts to commit, but the physical transaction already rolled back or was marked rollback-only | Trace the scope that set rollback-only; check propagation and catch sites |
| `TransactionSystemException` | System error during commit/rollback or in the underlying transaction mechanism | Inspect `cause`, `getApplicationException()`, and `getOriginalException()`; verify data state |
| `TransactionTimedOutException` | Transaction deadline exceeded and detected by infrastructure | Analyze queries/locks, timeouts, connection pool, and detection timing |
| `TransactionUsageException` and subclasses | Invalid usage of transaction API/state | Fix code or configuration; retrying will not fix a design bug |
| `HeuristicCompletionException` | Distributed transaction coordinator reports a heuristic outcome, possibly inconsistent commit/rollback | Reconcile each resource; recovery procedure needed, do not assume atomic rollback |

Some concrete subclasses of `TransactionUsageException`:

- `IllegalTransactionStateException`: invalid transaction operation or state; e.g., using a propagation incompatible with the current transaction.
- `InvalidIsolationLevelException`: requested isolation level is not supported by the transaction manager/resource.
- `NoTransactionException`: API expects a transaction status but none is active, e.g., calling `TransactionAspectSupport.currentTransactionStatus()` outside an interceptor context.
- `InvalidTimeoutException`: declared transaction timeout is invalid.

Unsupported transaction creation/suspension scenarios can raise `NestedTransactionNotSupportedException` or `TransactionSuspensionNotSupportedException`. For example, `PROPAGATION_NESTED` requires corresponding savepoint support; do not assume every JPA/JTA transaction manager supports it.

### 4.2. `CannotCreateTransactionException`: Failure Before Business Logic Runs

Suppose the transaction manager needs to acquire a JDBC connection and begin a transaction:

```text
Service proxy
  -> transactionManager.getTransaction(...)
      -> DataSource.getConnection()
          -> pool exhausted / DB unreachable
      -> BEGIN failed
  -> CannotCreateTransactionException
Service body: has not run
```

This case differs from SQL errors **after** a transaction has started. Seeing `CannotCreateTransactionException` alone is not enough to blame only a crashed DB: pool exhaustion, misconfiguration, underlying resources, or driver errors can also cause it. Inspect the **cause chain** and exact logs at `getTransaction` time.

**Handling:** inspect pool metrics (active, idle, pending), database connection limits, DNS/network, credentials, the active transaction manager bean, and load pressure. Consider bounded retries with backoff and idempotency only once confirmed transient; misconfiguration or missing permissions cannot be fixed by infinite retries.

### 4.3. `UnexpectedRollbackException`: Rollback Decided Yet Caller Expects Commit

This is a special case in `PROPAGATION_REQUIRED`:

```text
Outer @Transactional (REQUIRED)
    INSERT outer
    |
    +--> Inner @Transactional (REQUIRED), called THROUGH PROXY
             INSERT inner
             throw IllegalStateException
             -> inner's interceptor marks shared transaction rollback-only
    |
    catch IllegalStateException in outer
    return normally
    |
Outer interceptor tries to commit
    -> sees rollback-only -> rollback
    -> throws UnexpectedRollbackException to caller
```

Key point: two *logical* transaction scopes can participate in **the same physical transaction**. Catching the exception in outer only handles the Java exception; it **does not clear the rollback-only marker** on the physical transaction. Spring throws `UnexpectedRollbackException` so the caller does not mistake a rollback for a commit.

Not every caught `RuntimeException` produces `UnexpectedRollbackException`. If an error is thrown and caught **entirely inside the same method** before the interceptor sees it and nothing marks rollback-only, the outer scope can commit. Nor should you raise an error via `this.innerMethod()` expecting inner's `@Transactional` metadata to apply: internal calls typically bypass the Spring proxy.

**Handling:** determine which method marked rollback-only, who calls whom via proxy, propagation, repository/ORM behavior, and which business scope truly needs atomicity. If an operation must be independent of the outer transaction, design the boundary and `REQUIRES_NEW` intentionally (including connection cost); do not change propagation merely to "make the exception disappear".

### 4.4. `TransactionSystemException`: Infrastructure Failure on Completion

`TransactionSystemException` usually signals a transaction system error during `commit` or `rollback`. Notably, when the application throws an exception **and the rollback step also fails**, the infrastructure exception can mask the original exception. Spring provides:

- `getApplicationException()`: the preserved application exception, if present.
- `getOriginalException()`: prefers the original application exception; if absent, returns the cause of `TransactionSystemException`.
- `getCause()`: direct cause of the transaction failure.

```java
// Illustrative snippet used at an error-handling boundary, not a standalone program.
catch (TransactionSystemException ex) {
    Throwable original = ex.getOriginalException();
    log.error("Transaction system failure; original={}",
            original == null ? "(unknown)" : original.toString(), ex);
    throw ex;
}
```

The snippet above assumes `log` is declared and the application is at a layer authorized to handle/log errors. When logging, avoid printing passwords, connection strings containing secrets, or personal data. If the failure occurred at commit, do not claim the DB definitely rolled back without verifying the outcome.

### 4.5. `TransactionTimedOutException`: Timeout Is Not an "Abort Everything" Clock

Transaction timeouts are enforced jointly by Spring/driver/database; detection depends on the manager, database, statement, and when infrastructure checks the deadline. `@Transactional(timeout = 3)` **does not guarantee** every CPU task, HTTP request, or non-database I/O will abort at exactly 3 seconds. A timeout may cause the transaction to roll back, or surface when a query/commit is checked; inspect context and post-boundary state.

When hitting timeouts, inspect lock waits, slow queries, pool starvation, JDBC statement-level timeouts, database timeouts, and request timeouts; note outer/inner timeouts can be governed by propagation. Do not raise timeouts endlessly to mask a slow query or lock deadlock.

### 4.6. `HeuristicCompletionException` and Degrees of Certainty

In distributed transactions, a coordinator can report that participants completed inconsistently (heuristic outcome). This is a warning about **cross-resource consistency**, not a business exception you can `catch` and ignore as if nothing happened. Data reconciliation, compensation, and clear operational decisions are required. With single-datasource JDBC transactions, you will not normally encounter this type.

## 5. When an Exception Occurs, When Do Rollback Rules Actually Run?

Consider a normal service using a transaction manager/JDBC:

| Event | Rule and typical result |
| --- | --- |
| Method throws `IllegalArgumentException` out through transactional interceptor | Requests rollback by default |
| Method throws checked `IOException` out, no `rollbackFor` | **Does not** request rollback by default just for that exception |
| Method throws checked `IOException`, declared `@Transactional(rollbackFor = IOException.class)` | Spring requests rollback when the error escapes through interceptor |
| Method catches all errors before returning | Interceptor may see normal return; if transaction is already rollback-only, it still rolls back |
| Inner `REQUIRED` fails, outer catches exception | Shared physical transaction may already be rollback-only; outer commit raises `UnexpectedRollbackException` |
| Transaction manager `commit()` fails | Data outcome depends on what completed; **do not** assume rollback succeeded |
| JDBC query throws `DataIntegrityViolationException` | Belongs to `DataAccessException`, not `TransactionException`; usually triggers rollback if escaping interceptor |

Normally, when you want to preserve the root exception and guarantee rollback rules, let unrecoverable errors escape across the service boundary. If business logic permits recovery, design the transaction scope explicitly; do not scatter `catch (Exception ignored)` across every layer. When you must proactively request rollback inside a transactional method, you can use `TransactionAspectSupport.currentTransactionStatus().setRollbackOnly()`, though this couples to the Spring transaction interceptor context and should not be the default for business flows.

**Do not manually call `rollback(status)` after `PlatformTransactionManager.commit(status)` has thrown an exception.** By `PlatformTransactionManager`'s contract, status is already completed/cleaned up when `commit` returns, even when it throws; calling `rollback` afterward causes state errors and proves nothing about whether commit took place.

## 6. Hands-On Runnable Example: SQL Errors vs `UnexpectedRollbackException`

We build a Spring Boot example using H2 to clearly see two different exception types: a SQL error inside a service and a rollback-only error at the transaction boundary. The example uses **two separate Spring beans** so the inner call actually passes through a proxy.

### 6.1. Project Structure and Gradle

```text
transaction-errors/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/txerrors/
    │   │   ├── TxErrorsApplication.java
    │   │   ├── InnerStep.java
    │   │   └── WorkflowService.java
    │   └── resources/
    │       ├── application.properties
    │       └── schema.sql
    └── test/java/com/example/txerrors/
        ├── TransactionFailureIntegrationTest.java
        └── TransactionManagerBoundaryTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'transaction-errors'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Use Java 17 or higher and a Gradle version compatible with Spring Boot plugin 3.3.5. If the project was generated via Spring Initializr, the Gradle Wrapper is usually included; if creating files manually, generate the wrapper or use an installed Gradle. This is a full Java/Spring application with JUnit; do not run bare `javac` without configuring Spring dependency classpaths.

`src/main/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:txerrors;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
```

`src/main/resources/schema.sql`:

```sql
CREATE TABLE tx_events (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    code VARCHAR(80) NOT NULL UNIQUE
);
```

The `code` column has a `UNIQUE` constraint to produce a deterministic SQL error. H2 is a test database; production should validate behavior against the real database system.

### 6.2. Startup Application

`src/main/java/com/example/txerrors/TxErrorsApplication.java`:

```java
package com.example.txerrors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TxErrorsApplication {
    public static void main(String[] args) {
        SpringApplication.run(TxErrorsApplication.class, args);
    }
}
```

`src/main/java/com/example/txerrors/InnerStep.java`:

```java
package com.example.txerrors;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InnerStep {
    private final JdbcTemplate jdbc;

    public InnerStep(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional // propagation = REQUIRED by default
    public void writeThenFail() {
        jdbc.update("INSERT INTO tx_events (code) VALUES (?)", "inner");
        throw new IllegalStateException("Simulated failure inside REQUIRED");
    }
}
```

`src/main/java/com/example/txerrors/WorkflowService.java`:

```java
package com.example.txerrors;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class WorkflowService {
    private final JdbcTemplate jdbc;
    private final InnerStep inner;

    public WorkflowService(JdbcTemplate jdbc, InnerStep inner) {
        this.jdbc = jdbc;
        this.inner = inner;
    }

    @Transactional
    public void success() {
        jdbc.update("INSERT INTO tx_events (code) VALUES (?)", "success");
    }

    @Transactional
    public void outerCatchesInnerFailure() {
        jdbc.update("INSERT INTO tx_events (code) VALUES (?)", "outer");

        try {
            inner.writeThenFail(); // through another bean: inner's interceptor runs
        } catch (IllegalStateException expected) {
            // Intentionally caught to illustrate: the Java error disappears,
            // but the physical transaction has already been marked rollback-only.
        }
        // Normal return at the Java level; outer proxy still has to handle commit.
    }

    @Transactional
    public void duplicateKeyFailure() {
        jdbc.update("INSERT INTO tx_events (code) VALUES (?)", "duplicate");
        jdbc.update("INSERT INTO tx_events (code) VALUES (?)", "duplicate");
    }
}
```

When inner throws `IllegalStateException`, inner's Spring interceptor sees a runtime exception, joins the same `REQUIRED` physical transaction, and marks it rollback-only. Outer catches the Java error and returns, but outer's interceptor still detects rollback-only when attempting to commit. In the third method, a database error occurs on the second `INSERT`, which `JdbcTemplate` translates into the `DataAccessException` hierarchy.

### 6.3. Integration Test Observing Data After Transaction Boundaries

`src/test/java/com/example/txerrors/TransactionFailureIntegrationTest.java`:

```java
package com.example.txerrors;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.UnexpectedRollbackException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class TransactionFailureIntegrationTest {
    @Autowired
    private WorkflowService workflow;

    @Autowired
    private JdbcTemplate jdbc;

    @BeforeEach
    void clear() {
        jdbc.update("DELETE FROM tx_events");
    }

    private long countRows() {
        return jdbc.queryForObject(
                "SELECT COUNT(*) FROM tx_events", Long.class);
    }

    @Test
    void normalCompletionCommits() {
        workflow.success();
        assertEquals(1L, countRows());
    }

    @Test
    void catchingInnerFailureStillEndsWithUnexpectedRollback() {
        assertThrows(UnexpectedRollbackException.class,
                workflow::outerCatchesInnerFailure);
        assertEquals(0L, countRows());
    }

    @Test
    void duplicateSqlKeyThrowsDataAccessExceptionAndRollsBack() {
        assertThrows(DataIntegrityViolationException.class,
                workflow::duplicateKeyFailure);
        assertEquals(0L, countRows());
    }
}
```

**Do not place `@Transactional` on this test class.** If the test opens a transaction itself and rolls back at the end, you can observe uncommitted data and inadvertently hide the service's real commit/rollback behavior. Here, each test calls the bean from outside, lets the proxy/service transaction **finish**, and then queries the row count with `JdbcTemplate`.

Expected table:

| Test | Exception caller receives | Row count after call | What is proven |
| --- | --- | ---: | --- |
| `normalCompletionCommits` | None | 1 | Commit succeeded |
| `catchingInnerFailureStillEndsWithUnexpectedRollback` | `UnexpectedRollbackException` | 0 | Outer cannot commit a transaction already marked rollback-only |
| `duplicateSqlKeyThrowsDataAccessExceptionAndRollsBack` | `DataIntegrityViolationException` (usually `DuplicateKeyException` subtype) | 0 | SQL/data-access failures differ from transaction-infrastructure exceptions yet still cause rollback when escaping through proxy |

JUnit does not guarantee test execution order; the table above describes each independent test rather than log order. H2 enables simple, consistent tests, but does not replace locking/isolation tests on a production database.

## 7. Unit Test Simulating Begin Failure and Commit Failure

A real infrastructure failure (dropped connection, failed commit) is hard to trigger reliably across every environment. To **test the API boundary**, a mock transaction manager can be used. The test below only verifies how `TransactionTemplate` propagates exceptions from the manager; **it does not prove the outcome of a real database**.

`src/test/java/com/example/txerrors/TransactionManagerBoundaryTest.java`:

```java
package com.example.txerrors;

import org.junit.jupiter.api.Test;
import org.springframework.transaction.CannotCreateTransactionException;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.TransactionSystemException;
import org.springframework.transaction.support.SimpleTransactionStatus;
import org.springframework.transaction.support.TransactionTemplate;

import static org.junit.jupiter.api.Assertions.assertThrows;

class TransactionManagerBoundaryTest {
    @Test
    void beginFailurePreventsBusinessCallback() {
        PlatformTransactionManager manager = new PlatformTransactionManager() {
            @Override
            public TransactionStatus getTransaction(TransactionDefinition definition) {
                throw new CannotCreateTransactionException("Simulated BEGIN failure");
            }

            @Override
            public void commit(TransactionStatus status) {
                throw new AssertionError("commit must not run");
            }

            @Override
            public void rollback(TransactionStatus status) {
                throw new AssertionError("rollback must not run");
            }
        };

        TransactionTemplate template = new TransactionTemplate(manager);

        assertThrows(CannotCreateTransactionException.class,
                () -> template.execute(status -> {
                    throw new AssertionError("callback must not run");
                }));
    }

    @Test
    void commitFailurePropagatesWithoutManualRollback() {
        PlatformTransactionManager manager = new PlatformTransactionManager() {
            @Override
            public TransactionStatus getTransaction(TransactionDefinition definition) {
                return new SimpleTransactionStatus();
            }

            @Override
            public void commit(TransactionStatus status) {
                throw new TransactionSystemException("Simulated COMMIT failure");
            }

            @Override
            public void rollback(TransactionStatus status) {
                throw new AssertionError("do not roll back after commit failure");
            }
        };

        TransactionTemplate template = new TransactionTemplate(manager);

        assertThrows(TransactionSystemException.class,
                () -> template.execute(status -> "business callback completed"));
    }
}
```

In the first test, `getTransaction` throws before the callback starts: we know the callback never ran. In the second test, the callback finished, but `commit` threw an exception. The transaction manager here intentionally **does not connect to a database**; therefore nothing can be concluded about a real commit. This is why production systems need idempotency and data reconciliation when failures occur at the commit boundary.

To run all **5 tests** (3 integration, 2 unit), in the directory containing `build.gradle`:

```bash
./gradlew test
```

On Windows:

```powershell
.\gradlew.bat test
```

**Expected result:** all 5 tests pass, provided Java 17+, Gradle/dependencies, and the H2 schema are set up properly. The test suite does not print a fixed stdout; inspect JUnit results and the report at `build/reports/tests/test/index.html`. To test real connection drops/timeouts, use a database container and a resource-fault injection tool in a dedicated test environment, then re-verify state after the fault. Never fake an exception and claim you tested DB atomicity.

## 8. Responsible Error Handling at the Boundary

Any transaction error strategy should answer **two independent questions**: *is the cause recoverable?* and *is the operation's state certain?*

| Error | Response approach | Safe to auto-retry? |
| --- | --- | --- |
| `CannotCreateTransactionException` before callback runs | Check connectivity/pool, alert, and limit load | Possibly, if error is transient and operation is idempotent |
| `TransactionUsageException` | Fix transaction configuration or code | Do not retry the same unfixed operation |
| `TransactionTimedOutException` | Measure locks/queries/timeouts; stop unsafe processing chains | Consider only after knowing state and idempotency |
| `UnexpectedRollbackException` | Identify who marked rollback-only and fix boundary/logic | Do not blindly retry to mask a business bug |
| `TransactionSystemException` at commit/rollback | Preserve cause; inspect data and side effects | **Do not auto-retry when commit outcome is unknown** |
| `HeuristicCompletionException` | Reconcile each resource and compensate | A simple retry cannot be treated as recovery |

### 8.1. Idempotency Before Retrying

Suppose a payment creation API has a unique `requestId` supplied by the caller. If the connection drops at commit time, the API may receive an exception even though the database already persisted the payment. If the client resends **the same requestId**, the server must look up the existing outcome before creating a new transaction, or rely on a unique constraint and re-read logic to return the same result safely. Never generate a new requestId on every retry and expect "at least once" to magically become "exactly once".

When a commit failure occurs, the safe workflow is to record the operation identifier, query state from the source of truth, and handle *absent / present / pending reconciliation*. You cannot infer from `catch (TransactionException)` that every change was discarded. For emails, message brokers, or HTTP outside the database transaction, design appropriate outbox/idempotency/compensation.

### 8.2. Logging and Observability

Record facts useful for debugging:

- Request/job/correlation ID and operation ID; transaction/service name, selected transaction manager.
- Phase: acquire connection, begin, SQL, flush, commit, rollback, or post-commit callback.
- **Specific** exception, cause chain; with `TransactionSystemException`, inspect the preserved application exception.
- SQLState/database error code (if available), transaction/query duration, pool usage, lock waits, and timeout timing.
- Post-transaction data evidence: presence or absence of records for a given business key.

In the sample application, you can raise log levels to observe Spring opening and closing transactions:

```properties
logging.level.org.springframework.transaction=TRACE
logging.level.org.springframework.jdbc.datasource=DEBUG
```

Log names/messages vary across versions and managers, so **never write tests depending on fixed log strings**. Never log credentials, sensitive personal data, or full SQL parameters in production logs.

### 8.3. Reading Transaction Status in the Right Context

`TransactionSynchronizationManager.isActualTransactionActive()` can tell whether a transaction is currently marked active by Spring in the current context. It **does not prove** that transaction will commit. `TransactionAspectSupport.currentTransactionStatus()` provides `TransactionStatus` inside a matching interceptor context; calling it outside that context can throw `NoTransactionException`.

With imperative `@Transactional`, context is typically bound to the thread. Do not assume transactions propagate across `@Async` or application-created threads. Reactive transactions use Reactor context and `ReactiveTransactionManager`, requiring handling via publisher signals and reactive operators.

## 9. Misconceptions That Commonly Cause Incidents

1. **"`TransactionException` covers all DB errors."** Wrong: `DataAccessException` is a separate hierarchy and can even appear at commit/rollback depending on the manager.
2. **"Catching an exception means it definitely rolled back."** Wrong: default checked exceptions, post-commit errors, or unknown commit outcomes are counterexamples.
3. **"Outer caught it so the transaction will commit."** Wrong if an inner `REQUIRED` already marked rollback-only.
4. **"Catching `UnexpectedRollbackException` inside the outer method itself."** Usually cannot catch an error thrown by the outer interceptor **after the method body returns**; only callers outside the proxy see it.
5. **"`@Transactional` on inner works automatically when calling `this.inner()`."** Default proxy mode does not intercept self-invocation.
6. **"Rollback failure hides the root cause so it cannot be found."** Inspect the cause chain and, if present, `TransactionSystemException.getOriginalException()`.
7. **"Commit threw an error, so call rollback again."** Violates `PlatformTransactionManager.commit`'s contract; proves nothing about uncommitted data.
8. **"Immediate retry solves every exception."** For unknown commit outcomes, non-idempotent retries can duplicate work.
9. **"`@Transactional` automatically rolls back emails/HTTP calls."** A JDBC transaction only covers participating resources; external side effects require different mechanisms.
10. **"A `@Transactional` test reading data means it committed."** Spring tests usually roll back the test transaction at the end; observe after a real boundary.
11. **"`timeout = N` means the entire request is killed after N seconds."** Transaction timeout depends on infrastructure enforcement and only applies to the managed scope.
12. **"`REQUIRES_NEW` fixes every rollback-only."** It opens an independent transaction, can preserve changes even if outer rolls back, and consumes an extra connection; it must match business invariants.

## 10. Checklist for Diagnosing a Real Transaction Error

Suppose production reports "cannot create order" and the stack trace ends with a `TransactionException`:

1. **Classify** the exact exception; trace the root cause before predicting data state.
2. **Pinpoint the stage**: `getTransaction`, SQL, flush, commit, rollback, callback; note the transaction manager/DB resource.
3. **Check proxy call paths** and propagation: do outer and inner share the same physical transaction?
4. **Check rollback rules**: runtime/checked exceptions, `rollbackFor`, `catch` sites, rollback-only markers.
5. **Read after the boundary** using an independent connection/context, preferably querying by business key/idempotency key.
6. **For commits with unknown status**, pause non-idempotent retries and reconcile before reprocessing.
7. **Reproduce under control**: one integration test for data outcome; one simulated-failure test per relevant boundary.
8. **Fix the root cause** (manager/config, timeout, propagation, business logic, or SQL) and test both success and failure paths.

### Self-Check

**Question 1.** `JdbcTemplate` throws `DuplicateKeyException`. Is this a `TransactionException`?  
**Answer:** No. It belongs to the `DataAccessException` family (specifically a `DataIntegrityViolationException`), though it is still a runtime exception and normally triggers default rollback if it escapes through the transaction interceptor.

**Question 2.** Inner `REQUIRED` throws a runtime exception, outer catches it and returns. Why does the outside caller still receive `UnexpectedRollbackException`?  
**Answer:** Inner's interceptor marked the shared physical transaction rollback-only; outer attempts to commit a transaction no longer allowed to commit, so Spring reports the unexpected rollback.

**Question 3.** Does `TransactionSystemException` during commit allow assuming the database wrote nothing?  
**Answer:** No. In some cases the outcome is unknown; query state using a business identifier and apply idempotency/reconciliation mechanisms.

**Question 4.** When `commit(status)` throws an error, should `rollback(status)` be called immediately?  
**Answer:** No. `PlatformTransactionManager` considers status completed/cleaned up after a commit attempt; calling rollback again on the same status is not a valid recovery method.

**Question 5.** Can a unit test simulating `CannotCreateTransactionException` replace connection-loss testing against a real database?  
**Answer:** No. It verifies the code's exception path; proving real-world impact requires integration tests/controlled resource-fault testing.

## Official Documentation

- [Spring Framework — TransactionException Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/TransactionException.html)
- [Spring Framework — PlatformTransactionManager Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/PlatformTransactionManager.html)
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework — Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html)
- [Spring Framework — Controlling Database Connections / JdbcTransactionManager](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html)
- [Spring Framework — Test-managed Transactions](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html)
