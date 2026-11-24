# Default Rollback for RuntimeException and Error in Spring Framework

## 1. Learning Objectives

The **default rollback rule** for declarative transactions in Spring is very specific: when a `RuntimeException` or an `Error` exits a call managed by transaction advice, Spring requests a rollback. A typical **checked exception**, such as `IOException`, does not automatically cause the transaction to roll back by default.

This can easily be surprising. If a service saves data and then throws `IOException`, the caller still receives the error, yet the data **may have already been committed**. Conversely, an `IllegalStateException` or `AssertionError` passing through the transaction interceptor usually causes changes belonging to the same transaction to be rolled back.

After this lesson, you can:

- Distinguish `RuntimeException`, `Error`, and checked `Exception` in Java.
- Understand how Spring decides whether to **commit or roll back**, and the conditions under which an exception is actually seen by the interceptor.
- Explain the outcome of an exception caught inside a method versus an exception caught by the caller **outside the proxy**.
- Verify with Java 17+, Spring Boot, Spring JDBC, and H2 examples: cases for `RuntimeException`, `Error`, checked exceptions, `rollbackFor`, and `noRollbackFor`.
- Recognize the impact of nested `REQUIRED` transactions, self-invocation, post-commit exceptions, and non-transactional resources.

This lesson belongs to the **Rollback Rules** topic of the Spring Framework — transaction-management module. The content primarily covers Spring declarative transactions running through a proxy with a single database. Other transaction mechanisms may have their own specifics.

## 2. The Throwable Hierarchy: Compiler and Transaction Rules Are Separate Concepts

Simplified Java type hierarchy diagram:

```text
java.lang.Throwable
├── java.lang.Error
│   ├── AssertionError
│   ├── LinkageError
│   └── OutOfMemoryError
└── java.lang.Exception
    ├── java.lang.RuntimeException
    │   ├── IllegalArgumentException
    │   ├── IllegalStateException
    │   └── NullPointerException
    └── checked exceptions (examples)
        ├── IOException
        ├── SQLException
        └── ReflectiveOperationException
```

Regarding Java compiler checks, `RuntimeException` and `Error` are **unchecked** groups: calling code is not required to declare `throws` or `catch`. Most subclasses of `Exception` that are not `RuntimeException` are **checked**, forcing callers to handle or declare them.

Regarding Spring, under the default transaction policy:

| Throwable exiting through the interceptor | Category | Triggers default rollback? |
| --- | --- | --- |
| `IllegalArgumentException` | `RuntimeException` | Yes |
| `IllegalStateException` | `RuntimeException` | Yes |
| `NullPointerException` | `RuntimeException` | Yes |
| Spring `DataAccessException` | `RuntimeException` | Yes |
| `AssertionError` | `Error` | Yes |
| `OutOfMemoryError` | `Error` | Spring attempts rollback per the rule; no guarantee the JVM still has sufficient resources |
| `IOException` | Checked `Exception` | No |
| `SQLException` thrown directly | Checked `Exception` | No |
| Method returns normally after catching an error | No Throwable exits | Usually attempts to commit, unless the transaction is already rollback-only or another error occurs |

**`Error` does not extend `Exception`.** Therefore `catch (Exception ex)` does not catch `AssertionError`, yet Spring's default rollback rule still includes `Error`. This is behavior of the transaction infrastructure and does not depend on whether the client uses `catch (Exception)`.

A practical point: the JDBC API has checked `SQLException`, but Spring's `JdbcTemplate` typically translates database access errors into subclasses of `DataAccessException`, which are unchecked `RuntimeException`s. Examine the **actual Throwable type exiting the service** rather than guessing from the lower-level API's type.

## 3. When Does Spring Decide to Roll Back?

`@Transactional` only describes metadata. For imperative transactions through a Spring AOP proxy, the typical flow is:

```text
Caller
  |
  v
Spring AOP proxy of the service
  |
  v
TransactionInterceptor
  |-- determine transaction attributes
  |-- PlatformTransactionManager starts or joins a transaction
  |
  v
Service body -> repository/JdbcTemplate -> DB
  |
  +-- normal return --------------------> commit if possible
  |
  +-- RuntimeException/Error -----------> rollback by default
  |
  +-- checked Exception ----------------> commit by default
                                         (if no additional rollback rule applies)
  |
  v
Interceptor completes the transaction
  |
  v
Caller receives return value/exception
```

Pseudocode modeling the core rule of `DefaultTransactionAttribute.rollbackOn(Throwable)`:

```java
boolean rollbackOn(Throwable throwable) {
    return throwable instanceof RuntimeException
        || throwable instanceof Error;
}
```

This is **Java pseudocode illustrating the rule**, not the full Spring source code or a standalone runnable class. It answers “does this exception type mark a rollback?”, while the transaction manager is responsible for managing the connection and committing or rolling back the actual resource.

For a method that starts its own transaction:

1. Spring starts the transaction before running the method body.
2. The method updates the DB through resources participating in the right transaction.
3. If the method throws a `RuntimeException` or `Error` out of the proxy, the interceptor chooses rollback.
4. If the method throws a checked exception not covered by a rollback rule, the interceptor may **commit first** and then rethrow the exception to the caller.
5. If the method completes normally, the interceptor attempts to commit, unless the status is already rollback-only or another error occurs.

Distinguish between “Spring **requests** a rollback” and “the rollback has **completed** on the database”. Cases involving lost connections, different transaction managers, or severe infrastructure failures may require verifying the DB outcome separately.

## 4. Essential Scenarios

### 4.1. RuntimeException Usually Triggers Rollback

```java
@Transactional
public void reserve() {
    inventory.decrease();
    orderRepository.save();
    throw new IllegalStateException("cannot finish");
}
```

This snippet is illustrative and omits the definitions of `inventory` and `orderRepository`. If both changes participate in the same Spring transaction and the runtime exception escapes through the proxy, rollback reverts both. This is why the default rule fits many programming errors or unrecoverable states.

Spring does not distinguish a “minor business error” from a “severe system error” based on the exception message. If the exception is a `RuntimeException`, the default rule rolls back unless overridden with an appropriate policy.

### 4.2. Error Also Triggers Rollback by Default

```java
@Transactional
public void writeAndFailForDemo() {
    repository.save();
    throw new AssertionError("simulated error");
}
```

This is illustrative and omits the repository. When `AssertionError` escapes through the transaction interceptor, Spring requests a rollback. We can deliberately use `AssertionError` in tests to demonstrate this branch. **Do not use `OutOfMemoryError`, `StackOverflowError`, or `LinkageError` for business control flow**, because the process or JVM may no longer be recoverable. You should not broadly catch every `Error` and continue running the application as if it were a normal business error.

### 4.3. Checked Exceptions Usually Do Not Trigger Rollback by Default

```java
@Transactional
public void importFile() throws IOException {
    repository.save();
    throw new IOException("read next line failed");
}
```

This is illustrative. By default, `IOException` is a checked exception. Spring may commit the record written by `save()` and then rethrow `IOException`; the caller seeing an error **does not mean** the data was rolled back. If business rules require the entire import to either succeed or be cancelled, configure `rollbackFor = IOException.class` or handle the boundary/error mechanism appropriately.

### 4.4. Catching Inside the Method Changes What the Interceptor Sees

```java
@Transactional
public void saveAndHandle() {
    repository.save();
    try {
        throw new IllegalStateException("temporary failure");
    } catch (IllegalStateException ex) {
        log.info("Handled failure");
    }
}
```

This illustrative code omits the repository/logger. The method returns normally and Spring **no longer sees** `IllegalStateException` escaping. If the transaction has not been marked rollback-only and the DB remains valid, it can commit.

Conversely, if the caller catches `IllegalStateException` **outside the `@Transactional` method**:

```java
try {
    orderService.saveThenFail();
} catch (IllegalStateException ex) {
    // The transaction interceptor already saw the exception before the caller.
}
```

then the caller catching the exception does not reverse the rollback decision Spring just executed.

## 5. Runnable Example with Java 17+, Spring Boot, JDBC, and H2

The goal is to **read the data back after the method finishes**, rather than only checking whether an exception appeared. The program uses Spring Boot 3.3.13, Spring JDBC, and in-memory H2, with no web server. Versions are pinned for API reproducibility, not as advice to use older versions in production.

Seven test cases:

1. No error: commit.
2. `IllegalStateException`: default rollback.
3. `AssertionError`: default rollback.
4. `IOException`: commit by default.
5. RuntimeException caught directly inside the service: commit if not rollback-only.
6. Checked exception with `rollbackFor`: rollback.
7. RuntimeException with `noRollbackFor`: commit despite the exception.

### 5.1. Files and Dependencies

```text
spring-rollback-default-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/lesson/rollback/
    │   ├── RollbackApplication.java
    │   └── RollbackService.java
    └── resources/
        └── schema.sql
```

**`settings.gradle`**

```groovy
rootProject.name = 'spring-rollback-default-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'lesson'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
}
```

Spring Boot auto-configures `DataSource`, `JdbcTemplate`, and transaction infrastructure suitable for embedded H2 when dependencies/configuration meet the conditions. `@Transactional` is placed on a Spring-managed service; `CommandLineRunner` calls the service through the proxy from outside.

**`src/main/resources/schema.sql`**

```sql
CREATE TABLE demo_event (
    id INT PRIMARY KEY
);
```

Spring Boot automatically runs `schema.sql` at startup on embedded H2. The cases use distinct IDs, so they can be counted independently.

### 5.2. Service Executing Seven Types of Outcomes

**`src/main/java/lesson/rollback/RollbackService.java`**

```java
package lesson.rollback;

import java.io.IOException;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class RollbackService {
    private final JdbcTemplate jdbc;

    public RollbackService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void normal() {
        insert(1);
    }

    @Transactional
    public void runtimeFailure() {
        insert(2);
        throw new IllegalStateException("runtime-failure");
    }

    @Transactional
    public void errorFailure() {
        insert(3);
        throw new AssertionError("error-failure");
    }

    @Transactional
    public void checkedFailure() throws IOException {
        insert(4);
        throw new IOException("checked-failure");
    }

    @Transactional
    public void caughtRuntime() {
        insert(5);
        try {
            throw new IllegalStateException("caught-failure");
        } catch (IllegalStateException ignored) {
            // Illustration: do not rethrow, do not mark rollback-only.
        }
    }

    @Transactional(rollbackFor = IOException.class)
    public void configuredCheckedFailure() throws IOException {
        insert(6);
        throw new IOException("checked-failure");
    }

    @Transactional(noRollbackFor = IllegalStateException.class)
    public void configuredNoRollback() {
        insert(7);
        throw new IllegalStateException("runtime-failure");
    }

    private void insert(int id) {
        jdbc.update("INSERT INTO demo_event(id) VALUES (?)", id);
    }
}
```

All `@Transactional` methods above are public, non-final, and reside on a Spring bean. `insert` is a private helper; it uses `JdbcTemplate` within the **transaction already opened by the public method**. The helper needs no separate annotation.

The exceptions are thrown **after the INSERT statement**, so if a record disappears, that is evidence of a rollback of the write rather than the program not having written anything.

### 5.3. Caller Running Cases and Observing the DB

**`src/main/java/lesson/rollback/RollbackApplication.java`**

```java
package lesson.rollback;

import java.io.IOException;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootApplication
public class RollbackApplication {
    public static void main(String[] args) {
        SpringApplication.run(RollbackApplication.class, args);
    }

    @Bean
    CommandLineRunner examples(RollbackService service, JdbcTemplate jdbc) {
        return args -> {
            service.normal();
            System.out.println("normal=" + count(jdbc, 1));

            try {
                service.runtimeFailure();
            } catch (IllegalStateException ignored) {
                // Caller catches the error after the interceptor rolls back.
            }
            System.out.println("runtime=" + count(jdbc, 2));

            try {
                service.errorFailure();
            } catch (AssertionError ignored) {
                // Custom-thrown AssertionError specifically for the demo.
            }
            System.out.println("error=" + count(jdbc, 3));

            try {
                service.checkedFailure();
            } catch (IOException ignored) {
                // Checked exception does not trigger rollback by default.
            }
            System.out.println("checked=" + count(jdbc, 4));

            service.caughtRuntime();
            System.out.println("caught=" + count(jdbc, 5));

            try {
                service.configuredCheckedFailure();
            } catch (IOException ignored) {
                // rollbackFor requested a rollback.
            }
            System.out.println("checkedRollbackFor=" + count(jdbc, 6));

            try {
                service.configuredNoRollback();
            } catch (IllegalStateException ignored) {
                // noRollbackFor changed the rule for this exception.
            }
            System.out.println("noRollbackRuntime=" + count(jdbc, 7));
        };
    }

    private static int count(JdbcTemplate jdbc, int id) {
        Integer value = jdbc.queryForObject(
            "SELECT COUNT(*) FROM demo_event WHERE id = ?",
            Integer.class, id
        );
        return value;
    }
}
```

The Spring Boot application scans `RollbackService` in a suitable subpackage because it shares the `lesson.rollback` package with the application. `examples` receives the service via dependency injection, so calls like `service.runtimeFailure()` go through the proxy. The runner is not annotated with `@Transactional`, so `count` queries execute **after each service call's transaction has ended**.

In real products, you should not broadly catch `Error` or try to keep running after a severe JVM error. Here we only catch **an `AssertionError` created by the demo itself**, to illustrate rollback and let the program continue running subsequent cases.

### 5.4. Running and Expected stdout

Requires JDK 17+ and Gradle 8.x. Run in the `spring-rollback-default-demo` directory:

```bash
gradle bootRun
```

If the project already includes the Gradle Wrapper, use `./gradlew bootRun` on Linux/macOS or `gradlew.bat bootRun` on Windows. Because the code depends on Spring and H2, plain `javac` with only the JDK classpath cannot compile these files.

Ignoring Spring Boot and Gradle logs, the seven `System.out.println` lines of the program are:

```text
normal=1
runtime=0
error=0
checked=1
caught=1
checkedRollbackFor=0
noRollbackRuntime=1
```

| Method | Error exiting through interceptor | Rollback rule | Remaining rows |
| --- | --- | --- | --- |
| `normal` | None | Commit | 1 |
| `runtimeFailure` | `IllegalStateException` | Default: roll back RuntimeException | 0 |
| `errorFailure` | `AssertionError` | Default: roll back Error | 0 |
| `checkedFailure` | `IOException` | Default: do not roll back checked exception | 1 |
| `caughtRuntime` | None, method returns normally | Commit if not rollback-only | 1 |
| `configuredCheckedFailure` | `IOException` | `rollbackFor = IOException.class` | 0 |
| `configuredNoRollback` | `IllegalStateException` | `noRollbackFor` | 1 |

**Key observation:** even though the caller catches the exception in each case, the data may be committed or rolled back depending on the throwable type and applicable rollback rule. Adding `try/catch` in the caller after the method ends **does not** change the outcome already decided by the transaction interceptor.

### 5.5. Line-by-Line Modification Exercises

- Remove `rollbackFor` from `configuredCheckedFailure` and relaunch with a fresh DB: the `checkedRollbackFor` line becomes 1.
- Remove `noRollbackFor` from `configuredNoRollback`: the `noRollbackRuntime` line becomes 0.
- Change `checkedFailure` to `@Transactional(rollbackFor = IOException.class)`: the `checked` line becomes 0.
- Change `caughtRuntime` to rethrow the exception and add a catch outside in the runner: the `caught` line becomes 0.
- Move the `IllegalStateException` catch from the service out to the caller: the transaction interceptor gets to see the exception and rolls back by default.

Make changes only in the demo project; when rerunning, use a clean in-memory H2 instance. Do not reason from stale record counts left over from a previous run.

## 6. rollbackFor, noRollbackFor, and Precedence

`@Transactional` lets you declare exception-specific policies:

```java
@Transactional(rollbackFor = IOException.class)
public void importRecord() throws IOException {
    persist();
    throw new IOException("cannot finish");
}
```

With `rollbackFor = IOException.class`, `IOException` and its subclasses match the rule. Conversely:

```java
@Transactional(noRollbackFor = IllegalStateException.class)
public void auditAttempt() {
    persistAudit();
    throw new IllegalStateException("already processed");
}
```

In the second snippet, Spring may commit `persistAudit()` and then throw the exception. Both snippets are illustrative, omitting definitions for `persist`/`persistAudit`, and do not compile standalone.

**Principle: the more specific rule wins.** If a transaction attribute has multiple rules, Spring finds the rule matching the closest throwable class in the hierarchy; for example, `rollbackFor = Exception.class` and `noRollbackFor = DuplicateRequestException.class` usually causes `DuplicateRequestException` not to roll back because that rule is more specific. `RollbackRuleAttribute` selects by class hierarchy, avoiding reliance on message content. Prefer class-based rules over string names that match a partial class name and could unintentionally match something else.

When using XML, `rollback-for` and `no-rollback-for` attributes also exist in `<tx:method>`:

```xml
<tx:advice id="txAdvice" transaction-manager="transactionManager">
    <tx:attributes>
        <tx:method name="import*" rollback-for="java.io.IOException"/>
        <tx:method name="*" />
    </tx:attributes>
</tx:advice>
```

This XML fragment specifies rules, but requires an appropriate AOP pointcut/advisor, manager, and Spring context to take effect. Avoid adding both an XML transaction advisor and an annotation advisor with different policies on the same method unless advisor stacking is explicitly controlled.

## 7. Boundaries of the Default Rule: Proxy, Propagation, and Resources

### 7.1. Finding an Annotation Does Not Guarantee Advice Ran

In standard Spring AOP proxy mode, internal calls via `this.method()` bypass the proxy:

```java
@Service
class OrderService {
    public void process() {
        this.persistAndFail();
    }

    @Transactional
    public void persistAndFail() {
        save();
        throw new IllegalStateException("failure");
    }
}
```

This code is illustrative and omits `save()`. If `process()` has no transaction and is called from outside, `this.persistAndFail()` **does not pass through its own transaction interceptor**; a runtime exception will not make Spring roll back operations that already auto-committed. A similar issue occurs when creating objects with `new` instead of obtaining a Spring bean.

However, if `process()` is already running inside a transaction opened by an outer scope, `persistAndFail()` still **participates in the existing transaction** even though self-invocation is not separately intercepted by advice. Therefore the accurate statement is “the inner annotation is not applied”, not “self-invocation never has a transaction”.

### 7.2. Nested REQUIRED Can Create Rollback-Only

If service A has a `REQUIRED` transaction and calls another service B also configured with `REQUIRED` through a proxy, the two scopes can share the same physical transaction:

```text
Outer @Transactional(REQUIRED) -- starts transaction T
   |
   +-- Inner @Transactional(REQUIRED) -- joins T
             |
             +-- throws IllegalStateException
                  -> Inner interceptor marks T rollback-only
   |
   +-- Outer catches and continues
   |
   +-- Outer tries to commit T
        -> rolls back T; may report UnexpectedRollbackException
```

An inner exception may have already **marked the entire shared transaction** rollback-only before the outer scope catches the exception. Catching on the outer side does not automatically clear this flag. In contrast, `REQUIRES_NEW` opens a separate physical transaction: once it has committed, an outer rollback later will not undo the inner transaction. Evaluate business invariants and propagation rather than assuming every method has an independent commit.

### 7.3. No Rollback for Non-Transactional Side Effects

If a service writes to the DB and also sends an email, publishes to Kafka, calls a REST API, or writes a file, a local transaction manager does not automatically control side effects outside the DB. A Spring rollback after a RuntimeException only reverts changes **belonging to managed transactional resources**. For event-emitting systems, transactional outbox and idempotent consumers can be used when reliable coordination is needed.

### 7.4. Exceptions Occurring After Commit Do Not Undo the Commit

A transactional method can finish committing, and then an `afterCommit` callback or HTTP response serialization step raises a RuntimeException. The caller receives an error **after** the data has already committed. When an error happens right at the commit command and the ACK is lost, the outcome may even be **indeterminate**; do not use the exception type alone to conclude a rollback occurred. In such cases, look up operation IDs, idempotency, and reconciliation.

## 8. Catching Exceptions Inside a Transaction: When Does Rollback Still Happen?

You should not claim that “catch and return always commits” in every case. Exceptions to that:

- An inner `REQUIRED` scope already marked the transaction rollback-only; the outer scope attempting to commit may encounter `UnexpectedRollbackException`.
- A SQL error may put the DB transaction into an aborted state; even if code catches the exception, commit may fail.
- Application code may explicitly call `TransactionAspectSupport.currentTransactionStatus().setRollbackOnly()`.
- There may be a constraint violation on flush or another error at commit time, separate from the business exception caught by the code.

If you need to return a business result while **still requiring a rollback**, you can intentionally mark rollback-only, or better yet design exceptions and handling at the service boundary:

```java
@Transactional
public BusinessResult apply() {
    try {
        persistChanges();
        return BusinessResult.success();
    } catch (BusinessFailure ex) {
        TransactionAspectSupport.currentTransactionStatus()
            .setRollbackOnly();
        return BusinessResult.failure(ex.getMessage());
    }
}
```

This is illustrative architectural code, omitting definitions for `BusinessResult`, `BusinessFailure`, and `persistChanges`. Marking rollback-only ties the business service directly to Spring's transaction API; use it only when the return contract requires it.

## 9. Error Is a System Failure: Do Not Treat Rollback as Safe Recovery

`Error` is rolled back by default because when an operation is severely interrupted, committing partial data is a risky choice. However, `OutOfMemoryError`, `StackOverflowError`, and some `LinkageError`s can indicate the JVM is no longer operating normally. In this situation:

- Spring can only **attempt** to invoke rollback if the transaction interceptor is still able to run.
- An uncommitted database transaction may be recovered/rolled back by the DB when the connection closes, though exact behavior depends on the driver and DB.
- Do not catch `Throwable` at the business layer and return HTTP 200 as if every error were handled.
- Operations require monitoring, process recovery, and checking transaction/DB state; do not use `AssertionError` in production to signal ordinary business errors.

In the demo, `AssertionError` is created deliberately and does not put the JVM into a resource-exhausted state, so it can be caught in the runner to demonstrate Spring's policy.

## 10. Testing the Actual Outcome, Avoiding False Positives

A meaningful test should verify **the DB state after the call**, not just check `assertThrows`:

1. Set up independent test data and call a Spring-managed service through its proxy.
2. Execute at least one INSERT/UPDATE statement, then throw the appropriate exception.
3. Catch the exception outside the service call and read back from the DB.
4. For a RuntimeException or Error in a normal local transaction, assert that the changes were rolled back.
5. For a checked exception without rollback configuration, assert the commit outcome if that is the scenario under test.
6. Add tests for `rollbackFor`, `noRollbackFor`, exceptions caught inside the service, inner `REQUIRED` scopes, and non-DB side effects.
7. With JPA, check `flush`, the persistence context, constraints, and actual transaction scope, since SQL may be pushed to the DB lazily.

**Spring TestContext pitfall:** a `@Transactional` test method is typically rolled back by the framework at the end of the test. A `REQUIRED` service will join the test's transaction; a test that “sees no row at the end” does not yet prove the service rolled back under the right policy. When verifying commit/rollback, use a non-transactional test or control the test transaction and read the DB outside that scope.

You can temporarily enable logs for the transaction interceptor and JDBC manager:

```properties
logging.level.org.springframework.transaction.interceptor=TRACE
logging.level.org.springframework.jdbc.datasource.DataSourceTransactionManager=DEBUG
```

Logs reveal which methods are actually intercepted, whether the manager opens a transaction, and whether it commits or rolls back. Even so, the strongest evidence remains reading back the data state after the transaction finishes.

## 11. Checklist When a RuntimeException Still Leaves Data Saved

| What to check | What may have happened |
| --- | --- |
| Is the bean Spring-managed? | `new` prevents advice from processing the annotation |
| Did the call go through the proxy? | Self-invocation skips advice for the inner method |
| Did the exception escape the intercepted method? | Catching internally makes the interceptor see a normal return |
| Is there a `noRollbackFor` or special global rule? | An explicit policy overrode the default |
| Was the transaction already rollback-only from another scope? | The outcome may only be decided at outer commit |
| Did a `REQUIRES_NEW` transaction already commit? | An outer rollback does not undo an inner commit |
| Do all operations use the same transaction manager/resource? | A different connection/DB does not participate in the rollback |
| Did the exception occur before or after commit? | A post-commit error does not undo durable data |
| Is there an auto-rolling-back test transaction? | The test may produce a misleading conclusion |
| Did the DB confirm the outcome? | A commit failure with a lost ACK can lead to an indeterminate outcome |

Do not fix a missing-transaction bug by adding `rollbackFor = Exception.class` to every method. If the proxy is not running or the data lives outside a transactional resource, that rule remains inert metadata.

## 12. Self-Check

**Question 1.** A `@Transactional` method INSERTs two rows and then throws an `IllegalArgumentException` that escapes the proxy. What happens by default?

**Answer:** This is a `RuntimeException`; Spring requests a rollback. If both INSERTs belong to the same transaction and the rollback succeeds, neither is committed.

**Question 2.** Does `AssertionError` trigger rollback by default even though it does not extend `Exception`?

**Answer:** Yes. The default rule includes `Error`. That does not mean severe Errors can be safely recovered in the JVM.

**Question 3.** A `@Transactional` method INSERTs and throws checked `IOException`; the caller catches the error. Is the DB guaranteed to be empty?

**Answer:** No. Checked exceptions do not trigger rollback by default, so if the commit succeeds, the record remains. `rollbackFor = IOException.class` is needed if the business logic requires cancellation.

**Question 4.** A RuntimeException is raised inside a method but caught and returned; does it roll back by default?

**Answer:** Usually no, because the interceptor does not see an escaping exception; however, the transaction can still roll back if it was marked rollback-only or hits a resource failure.

**Question 5.** Why can an outer `@Transactional` test sometimes be misleading?

**Answer:** Because the test's transaction may automatically roll back at the end of the test. A `REQUIRED` service may simply join that transaction, failing to prove independent commit/rollback behavior as in real runtime execution.

**Question 6.** The caller receives a RuntimeException from a post-commit step. Is the DB guaranteed to have rolled back?

**Answer:** No. A completed commit cannot be reversed by a subsequent exception. Check the actual data state and idempotency when the outcome could be ambiguous.

**Question 7.** Does `@Transactional(noRollbackFor = IllegalStateException.class)` on another method break the default rule?

**Answer:** It is an intentional override; Spring can commit even though this exception type escapes, provided the transaction can still commit.

## 13. References

- Spring Framework — Rolling Back a Declarative Transaction: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html
- Spring Framework — Using `@Transactional`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework 6.1 — `Transactional` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/transaction/annotation/Transactional.html
- Spring Framework — Transaction Propagation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Boot 3.3 — System Requirements: https://docs.spring.io/spring-boot/3.3/system-requirements.html

**Key takeaway:** in Spring's default declarative transaction configuration, `RuntimeException` and `Error` passing through the transaction interceptor **trigger rollback**, whereas checked exceptions generally **do not**. Reaching the right conclusion requires knowing whether the call went through a proxy, which transaction is being managed, and whether data was already committed; verify the DB state rather than looking at the exception alone.