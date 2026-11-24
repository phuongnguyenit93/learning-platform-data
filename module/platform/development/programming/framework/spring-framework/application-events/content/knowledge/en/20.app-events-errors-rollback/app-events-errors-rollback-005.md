# Errors in @TransactionalEventListener

## 1. Why Are Errors in Transaction-Bound Listeners Dangerous?

`@TransactionalEventListener` ties **application event** handling to a *phase* of the transaction that published the event. This is very useful for running logic before commit or after the transaction outcome is decided, yet **an exception in a listener does not always have the same consequence**.

For example, `OrderService` writes an order inside transaction T1 and publishes `OrderPlaced`. Then:

- A `BEFORE_COMMIT` listener checks a mandatory condition and throws an error: **T1 can roll back** because the error occurred before commit.
- An `AFTER_COMMIT` listener sends a notification and throws an error: **T1 has already committed; T1 cannot be rolled back just because the listener failed**.
- An `AFTER_ROLLBACK` listener logs the failure and itself throws an error: T1 **has already rolled back**; it cannot "roll back again" or restore the original transaction.
- If the event is published **outside a transaction** and `fallbackExecution = false` (default), the listener **does not run**, so there is no error from that listener method during that event publication.

Diagram:

~~~text
@Transactional OrderService.create()
    |
    +-- BEGIN T1
    +-- INSERT orders
    +-- publishEvent(OrderPlaced)
    |      (registers transaction synchronization)
    |
    +-- BEFORE_COMMIT listener
    |      +-- succeeds ----------------------------------+
    |      +-- throws RuntimeException -> rolls back T1   |
    |                                                     |
    +-- COMMIT T1 <---------------------------------------+
    |      |
    |      +-- AFTER_COMMIT listener
    |              +-- error here DOES NOT reverse T1 commit
    |
    +-- ROLLBACK T1 (if transaction fails)
           |
           +-- AFTER_ROLLBACK listener
                   +-- error here DOES NOT roll back T1 further
~~~

**Learning objective:** distinguish errors that affect the commit decision from errors occurring after the transaction has completed; understand the exception path in Spring Framework; and design post-commit error handling without creating a false sense of safety.

## 2. The Four Phases and Exception Impact

| `@TransactionalEventListener` Phase | When it runs | If the listener throws a RuntimeException in a standard imperative transaction |
| --- | --- | --- |
| `BEFORE_COMMIT` | Inside the `TransactionSynchronization.beforeCommit(...)` callback, before commit | The exception can propagate to the commit process, causing T1 to **roll back**; the caller may see the error |
| `AFTER_COMMIT` (**default**) | Inside the `afterCompletion(STATUS_COMMITTED)` callback of the transactional event mechanism | **T1 has already committed**. The exception is logged by the transaction synchronization utility and normally **does not propagate back to the caller** |
| `AFTER_ROLLBACK` | Inside the `afterCompletion(STATUS_ROLLED_BACK)` callback | **T1 has already rolled back**; the handler error is logged and does not turn rollback into commit |
| `AFTER_COMPLETION` | Inside `afterCompletion(...)` when the transaction completes, whether committed or rolled back | The transaction outcome is already determined; the handler error is logged and does not alter that outcome |

This is the behavior of **Spring Framework 6.2 with standard imperative transactions**, such as `DataSourceTransactionManager`. It is based on how Spring implements `TransactionalApplicationListenerSynchronization` and invokes `TransactionSynchronization` callbacks.

### Subtle Point: AFTER_COMMIT Is Not Directly Equivalent to afterCommit()

The phase name `AFTER_COMMIT` easily leads one to think the listener method runs inside `TransactionSynchronization.afterCommit()`. However, in Spring 6.2's transactional event implementation, Spring registers:

~~~java
// Pseudocode describing part of the dispatch mechanism, not a public API to call:
beforeCommit(...) {
    if (phase == BEFORE_COMMIT) processEvent();
}

afterCompletion(status) {
    if (phase == AFTER_COMMIT && status == STATUS_COMMITTED)
        processEvent();
    else if (phase == AFTER_ROLLBACK && status == STATUS_ROLLED_BACK)
        processEvent();
    else if (phase == AFTER_COMPLETION)
        processEvent();
}
~~~

Therefore, two callback APIs must be distinguished:

- `TransactionSynchronization.afterCommit()`: a `RuntimeException` **can propagate to the caller** even though the DB has committed.
- `TransactionSynchronization.afterCompletion(int)`: exceptions are **logged by Spring rather than propagated further** in the standard callback sequence.

`@TransactionalEventListener(AFTER_COMMIT)` on the imperative path above falls under **the second case**. Avoid writing documentation or tests asserting "an exception at `AFTER_COMMIT` always causes the caller to receive an error." Behavior may differ if the application writes its own transaction manager, dispatch, error handler, or invokes handlers manually.

Source in Spring 6.2: `TransactionalApplicationListenerSynchronization.PlatformSynchronization` and `TransactionSynchronizationUtils.invokeAfterCompletion(...)`; see documentation links at the end of the lesson.

### BEFORE_COMMIT Does Not Guarantee the Commit Will Succeed

`BEFORE_COMMIT` is called **before** commit so it can fail and cause the transaction to roll back. However, **a listener succeeding does not guarantee T1 will definitely commit**. Commit can still fail due to database constraints, network issues, deadlocks, the transaction being marked rollback-only, or errors in other steps.

Therefore, **do not send emails, charge cards, or publish irrevocable messages from `BEFORE_COMMIT`** if the system must guarantee side effects only occur after the transaction has committed.

## 3. When Is an Event Published, and When Does the Listener Actually Run?

Distinguish three milestones:

1. `ApplicationEventPublisher.publishEvent(event)` is called **inside T1**.
2. For `@TransactionalEventListener` with an active matching transaction, Spring **registers a synchronization** at event publication time. The listener method does not necessarily run immediately.
3. When T1 reaches the configured phase, Spring invokes the listener method.

~~~text
service:
  transaction BEGIN
  INSERT
  publishEvent(event)    -> registers phase callback
  return from method
  transaction interceptor:
      beforeCommit -> commit/rollback -> afterCompletion
           |
           +-- @TransactionalEventListener method is called at the right phase
~~~

Consequently, an exception in `BEFORE_COMMIT` can occur **after the service method body has finished executing**, during the transaction interceptor's commit-handling step. If the service has:

~~~java
@Transactional
public void placeOrder() {
    repository.save(...);
    publisher.publishEvent(new OrderPlaced(...));
    System.out.println("service body finished");
}
~~~

The line "service body finished" may have already printed **before** the `BEFORE_COMMIT` listener throws an error and T1 rolls back. A log saying "service reached the end of the method" is not proof that the transaction committed.

Conversely, `AFTER_COMMIT` can run after the DB commits but before the transaction manager finishes cleanup. An exception in the listener method at this point does not make already committed data revert to its previous state.

## 4. Runnable Java 17+ Example: Three Error Types, Two DB Outcomes

This example uses **Spring Framework 6.2.19**, Spring JDBC, and in-memory H2. No Spring Boot needed. Four scenarios run sequentially:

1. Order 101: all listeners succeed -> T1 commits.
2. Order 102: `BEFORE_COMMIT` listener throws an error -> T1 rolls back; caller catches exception.
3. Order 103: `AFTER_COMMIT` listener throws an error -> T1 already committed; error is logged by Spring; caller does not catch the error along the standard `afterCompletion` path.
4. Order 104: the service itself throws an error -> T1 rolls back; `AFTER_ROLLBACK` listener still runs.

### Project Structure

~~~text
transactional-event-errors/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/TransactionEventErrorDemo.java
~~~

File `settings.gradle`:

~~~groovy
rootProject.name = 'transactional-event-errors'
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.19'
    implementation 'org.springframework:spring-jdbc:6.2.19'
    runtimeOnly 'com.h2database:h2:2.3.232'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.TransactionEventErrorDemo'
}
~~~

File `src/main/java/demo/TransactionEventErrorDemo.java`:

~~~java
package demo;

import javax.sql.DataSource;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.stereotype.Component;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Configuration
@EnableTransactionManagement
@ComponentScan(basePackageClasses = TransactionEventErrorDemo.class)
public class TransactionEventErrorDemo {

    @Bean
    DataSource dataSource() {
        var ds = new DriverManagerDataSource();
        ds.setDriverClassName("org.h2.Driver");
        ds.setUrl("jdbc:h2:mem:listener_errors;DB_CLOSE_DELAY=-1");
        ds.setUsername("sa");
        ds.setPassword("");
        return ds;
    }

    @Bean
    JdbcTemplate jdbcTemplate(DataSource ds) {
        return new JdbcTemplate(ds);
    }

    @Bean
    PlatformTransactionManager transactionManager(DataSource ds) {
        return new DataSourceTransactionManager(ds);
    }

    public static void main(String[] args) {
        try (var ctx = new AnnotationConfigApplicationContext(
                TransactionEventErrorDemo.class)) {

            JdbcTemplate db = ctx.getBean(JdbcTemplate.class);
            db.execute("CREATE TABLE orders (id BIGINT PRIMARY KEY)");

            OrderService service = ctx.getBean(OrderService.class);

            // A: T1 commits normally.
            service.place(101L, Scenario.OK);

            // B: BEFORE_COMMIT fails, caller receives exception.
            try {
                service.place(102L, Scenario.FAIL_BEFORE_COMMIT);
            } catch (IllegalStateException ex) {
                System.out.println("caller caught before 102");
            }

            // C: AFTER_COMMIT fails, DB already committed.
            // With default Spring synchronization callback,
            // exception is logged; this line does not need a catch.
            service.place(103L, Scenario.FAIL_AFTER_COMMIT);

            // D: service itself requests rollback.
            try {
                service.place(104L, Scenario.FAIL_IN_SERVICE);
            } catch (IllegalArgumentException ex) {
                System.out.println("caller caught service 104");
            }

            Integer count = db.queryForObject(
                "SELECT COUNT(*) FROM orders", Integer.class);
            System.out.println("committed orders=" + count);
        }
    }
}

enum Scenario {
    OK,
    FAIL_BEFORE_COMMIT,
    FAIL_AFTER_COMMIT,
    FAIL_IN_SERVICE
}

record OrderPlaced(long orderId, Scenario scenario) {}

@Component
class OrderService {
    private final JdbcTemplate db;
    private final ApplicationEventPublisher publisher;

    OrderService(JdbcTemplate db, ApplicationEventPublisher publisher) {
        this.db = db;
        this.publisher = publisher;
    }

    @Transactional
    public void place(long id, Scenario scenario) {
        db.update("INSERT INTO orders (id) VALUES (?)", id);
        publisher.publishEvent(new OrderPlaced(id, scenario));

        if (scenario == Scenario.FAIL_IN_SERVICE) {
            throw new IllegalArgumentException("service failed");
        }
    }
}

@Component
class OrderListeners {

    @TransactionalEventListener(
        phase = TransactionPhase.BEFORE_COMMIT)
    public void beforeCommit(OrderPlaced event) {
        System.out.println("before commit " + event.orderId());

        if (event.scenario() == Scenario.FAIL_BEFORE_COMMIT) {
            throw new IllegalStateException("before listener failed");
        }
    }

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT)
    public void afterCommit(OrderPlaced event) {
        System.out.println("after commit " + event.orderId());

        if (event.scenario() == Scenario.FAIL_AFTER_COMMIT) {
            throw new IllegalStateException("after listener failed");
        }
    }

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_ROLLBACK)
    public void afterRollback(OrderPlaced event) {
        System.out.println("after rollback " + event.orderId());
    }
}
~~~

Run inside the project directory with JDK 17+ and Gradle; if a Gradle Wrapper is present you can use the wrapper:

~~~bash
gradle run --quiet
# Linux/macOS: ./gradlew run --quiet
# Windows: gradlew.bat run --quiet
~~~

**Lines intentionally printed by the program via `System.out`** (ERROR logs from Spring for scenario 103 may appear interleaved, possibly including a stack trace):

~~~text
before commit 101
after commit 101
before commit 102
after rollback 102
caller caught before 102
before commit 103
after commit 103
after rollback 104
caller caught service 104
committed orders=2
~~~

Explanation of each scenario:

| Order | Which listeners run? | DB outcome | What does the caller see? |
| --- | --- | --- | --- |
| 101 | BEFORE_COMMIT, AFTER_COMMIT | Commit | Normal return |
| 102 | BEFORE_COMMIT throws error; AFTER_ROLLBACK | Rollback | `IllegalStateException` (caught) |
| 103 | BEFORE_COMMIT; AFTER_COMMIT throws error | **Committed** | On the standard `afterCompletion` callback, Spring **logs the error**; caller receives no exception from this listener |
| 104 | AFTER_ROLLBACK; BEFORE_COMMIT does not run | Rollback | `IllegalArgumentException` from service (caught) |

**Easy data-level verification:** at the end of the program `committed orders=2`, consisting of orders **101 and 103**. The post-commit listener error **does not make order 103 disappear**. Orders 102 and 104 do not exist because their T1 transactions rolled back.

**Stdout warning:** the demo does not configure a specific logging setup. The `after listener failed` error stack trace printed by Spring can be long and environment-dependent. The lines in the output block are those printed directly by the demo, not the entirety of console output.

## 5. Why Might an AFTER_COMMIT Exception Only Appear in Logs?

In Spring 6.2's imperative implementation:

1. `@TransactionalEventListener(AFTER_COMMIT)` registers a `TransactionSynchronization`.
2. After the actual commit, Spring invokes `afterCompletion(STATUS_COMMITTED)`.
3. The transactional event synchronization invokes the listener; the listener throws an exception.
4. `TransactionSynchronizationUtils.invokeAfterCompletion(...)` catches `Throwable` from each callback and **logs an ERROR**; cleanup continues.
5. The main commit result of T1 remains successful.

This has two consequences:

- **Do not use `try/catch` around `service.place()` as the sole mechanism to detect every `AFTER_COMMIT` post-processing failure.** In the demo, the caller does not see the post-commit failure for 103 via an exception.
- **Do not treat "service returned successfully" as "all listeners completed successfully."** Success of T1 and success of post-T1 side effects are two separate states.

### Exceptions for Other Execution Paths

The table above does not mean every exception of every Spring listener type is swallowed:

- A **regular** `@EventListener` running synchronously inside `publishEvent(...)` can throw an error right at publish time; if the error escapes the service, the active transaction can roll back.
- With `fallbackExecution = true` when there is **no transaction**, a transactional listener may be invoked immediately; at that point it is no longer an `afterCompletion` callback of a T1, so error propagation depends on the dispatch path and multicaster configuration.
- `TransactionSynchronization.afterCommit()` written **directly** is a different API; an exception in that callback can propagate to the caller even though the commit completed.
- A listener with `@Async`, a custom multicaster/executor, or an error handler has its own error-handling mechanism; async errors cannot be assumed to propagate back to the thread that called publish.
- In **reactive transactions** (Spring 6.1+), the transaction context lives in the Reactor Context and phase callbacks may execute via `Mono`. Exceptions can affect reactive signals differently from the imperative path; verify with `ReactiveTransactionManager` and your specific subscription setup rather than mechanically applying the imperative `TransactionSynchronizationUtils` error-swallowing rule.

For production systems, distinguish and test **the transaction manager type**, **phase**, **how the listener executes**, and **the exception-handling path**.

## 6. BEFORE_COMMIT Errors Have Different Semantics from AFTER_COMMIT Errors

Choose `BEFORE_COMMIT` when the listener's operation **must be part of the transaction decision**:

~~~java
@Component
class InvariantCheckListener {

    @TransactionalEventListener(
        phase = TransactionPhase.BEFORE_COMMIT)
    public void validate(OrderPlaced event) {
        if (violatesBusinessInvariant(event)) {
            throw new IllegalStateException("Cannot commit order");
        }
    }

    private boolean violatesBusinessInvariant(OrderPlaced event) {
        // Pseudocode: real logic must be based on application business rules.
        return false;
    }
}
~~~

This is an **illustrative bean snippet**, not a standalone runnable file. It clarifies the phase's semantics rather than replacing business invariant checks inside the aggregate/service.

**Why not put all business validation into event listeners?** Core rules should generally be enforced **before or while updating the aggregate**, where the business flow is easy to trace. Use a `BEFORE_COMMIT` listener for cross-cutting validation or supplemental operations that must share the transaction when genuinely appropriate; avoid moving domain invariants into a hard-to-see callback.

If a `BEFORE_COMMIT` listener writes data within the same T1 and then throws an error, those changes can also roll back with T1 when sharing the same transaction resource. However, if the listener already called **an HTTP API, sent an email, or opened `REQUIRES_NEW` to commit independently** before throwing, rolling back T1 **does not automatically undo** those external side effects.

## 7. Writing Audits or Error Logs in AFTER_ROLLBACK Requires a New Transaction

Example: order placement fails, and the application wants to persist an `order_failure_log` for investigation. An `AFTER_ROLLBACK` listener is a reasonable hook in terms of timing, but the original transaction **has already ended**. During the callback, old transaction resources may still be bound to the thread; a direct `save()` operation does not guarantee a new commit.

Recommended pattern:

~~~java
@Component
class FailureListener {
    private final FailureAuditWriter writer;

    FailureListener(FailureAuditWriter writer) {
        this.writer = writer;
    }

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_ROLLBACK)
    public void onFailure(OrderPlaced event) {
        writer.persistFailure(event.orderId());
    }
}

@Component
class FailureAuditWriter {
    private final FailureLogRepository repository;

    FailureAuditWriter(FailureLogRepository repository) {
        this.repository = repository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void persistFailure(long orderId) {
        repository.save(new FailureLog(orderId));
    }
}
~~~

This snippet **is not standalone**, because `FailureLogRepository` and `FailureLog` are application-dependent types and require imports for `Propagation`, `Transactional`, and stereotype annotations. The key point is that the listener calls **another bean through a Spring proxy** so `REQUIRES_NEW` actually opens T2.

Notes:

- T2 has its own commit/rollback. If T2 fails, T1's rollback **does not change**, and the error may be logged by Spring inside the `afterCompletion` callback.
- `this.persistFailure()` called directly inside the same bean typically bypasses the transaction proxy; do not use self-invocation expecting `REQUIRES_NEW`.
- If an audit must **be guaranteed to survive even a system crash**, a post-rollback callback can still be lost. You should also establish a durable error source, separate transaction, queue, or appropriate audit-persistence mechanism. An outbox written *inside T1* will also roll back with T1, so it **cannot by itself record a rolled-back transaction failure**.

## 8. Should You Catch Exceptions Directly Inside the Listener?

There is no single `catch` approach for every business case. Catch errors **when the listener genuinely has a recovery policy**. For example:

~~~java
// Illustration: assumes real retry/monitoring configuration in the application.
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterCommitted(OrderPlaced event) {
    try {
        notificationGateway.enqueue(event.orderId());
    } catch (TransientGatewayException ex) {
        metrics.counter("order_notification_failure").increment();
        errorReporter.report(event.orderId(), ex);
        // Could mark for retry in a durable system.
    }
}
~~~

This snippet illustrates **the context of a listener with dependencies**, not standalone Java. If `metrics` or `errorReporter` also fails, an explicit handling policy is still required. Recording metrics or logs **does not by itself recreate a failed notification**.

Options:

| Need | Suitable strategy |
| --- | --- |
| Mandatory pre-commit work; error must roll back T1 | Execute within T1; `BEFORE_COMMIT` can be used when architecturally appropriate |
| Work that does not affect already committed data | `AFTER_COMMIT` with clear error monitoring |
| Retryable post-commit side effect | Hand off to a worker/job or durable, idempotent message transport |
| Must not lose events on process crash | **Transactional outbox** written in the same business transaction |
| Persist failure log after rollback | Independent T2 via `REQUIRES_NEW` or another durable recording channel |
| Want to roll back the DB when email fails | Atomicity cannot be guaranteed solely via post-commit callbacks; redesign workflow or use an appropriate distributed mechanism |

### Why Not Just Retry Directly Inside the Listener Method?

Some transient errors (timeouts, connection resets) may fit bounded retries with backoff and idempotency. However, retrying **synchronously inside the callback** also carries risks:

- Holds the request/transaction completion open longer than necessary.
- Sends the same side effect multiple times if a timeout occurs after the target system succeeded.
- Still loses all pending work if the process dies.
- In `AFTER_COMPLETION`, the final error may only be logged so the caller does not automatically know compensation is needed.

For reliable integration, an outbox + worker retry is generally better suited than "catch and retry a few times inside the listener."

## 9. If Multiple Listeners Handle an Event, How Do Errors Affect Them?

Do not assume an event has exactly one handler. For instance, `OrderPlaced` might have:

~~~text
OrderPlaced
    +-- BEFORE_COMMIT: check policy
    +-- AFTER_COMMIT : write audit
    +-- AFTER_COMMIT : enqueue notification
    +-- AFTER_ROLLBACK: record error details
~~~

Scenarios:

- An error in one `BEFORE_COMMIT` callback can halt the commit process, so callbacks in the same phase that have not run yet **may not be called** and T1 rolls back.
- An error in one `afterCompletion` callback on the standard imperative path is logged, and the utility continues iterating through the remaining synchronizations. You should **not** rely on listener ordering to guarantee business invariants unless explicitly designed and tested.
- `@Order` can change priority among listeners/synchronizations, but **cannot change the fact that T1 already committed or rolled back**, nor give a post-commit exception the ability to undo T1.
- A failing listener may already have executed **a partial side effect** before throwing an exception. On reprocessing, design for idempotency (e.g., unique key by event ID).
- If using a custom `applicationEventMulticaster` or asynchronous listeners, lifecycle and exception policies must be verified in a real environment.

### Errors When Publishing Outside a Transaction

By default, `fallbackExecution = false`:

~~~java
@TransactionalEventListener
public void onPlaced(OrderPlaced event) { ... }
~~~

If `publishEvent(...)` happens **outside a matching transaction**, the transaction-bound callback is skipped. There is no exception because the listener does not run.

You can enable:

~~~java
@TransactionalEventListener(fallbackExecution = true)
public void onPlacedEvenWithoutTx(OrderPlaced event) { ... }
~~~

However, when running outside a transaction, **this cannot be interpreted as after-commit**; the listener runs via the fallback path. If the absence of a transaction is a programming bug, do not use fallback to mask it. Ensure the publisher runs inside a managed transaction or use another direct publishing API suited to the use case.

## 10. Testing Exceptions and Rollback for @TransactionalEventListener

A good test suite must verify **both observable exceptions and actual commit/rollback data**:

| Test | What to assert |
| --- | --- |
| BEFORE_COMMIT listener throws `RuntimeException` | Caller may receive the error; T1 data row does not exist; AFTER_COMMIT does not run |
| AFTER_COMMIT listener throws `RuntimeException` | T1 data **still exists**; handler error is detected via logging/monitoring, not concluded from `assertThrows` at caller |
| Service throws exception before commit | T1 rolls back; AFTER_ROLLBACK is called if the event was published inside T1 |
| AFTER_ROLLBACK listener throws error | Does not alter T1 outcome; error reporting must still detect the callback failure |
| Event published outside transaction | Listener does not run by default; test separately when `fallbackExecution` is enabled |
| Post-commit listener calls T2 `REQUIRES_NEW` and T2 rolls back | T1 still exists; T2 has no data; retry/alerting mechanisms trigger |
| Multiple post-completion callbacks exist | Verify which callbacks are invoked and log errors under the specific configuration |

**Note on `@Transactional` in tests:** a `@Transactional` test may be rolled back by the test framework by default at the end; its `AFTER_COMMIT` callbacks will not run as expected unless the test configures commit. For integration tests, you can use `TestTransaction.flagForCommit()`/`end()` or manage transactions outside the test and read the DB after completion. Do not mistake default test rollbacks for listener bugs.

**Logging:** in systems using Logback/Log4j2, you can enable DEBUG for `org.springframework.transaction` and watch ERRORs in `TransactionSynchronizationUtils`. Logs help detect exceptions that are recorded without propagating back to the caller; combine them with metrics/alerts for critical tasks.

## 11. Incident Diagnostic Checklist

When you see "the order was saved yet the listener reported an error," check:

1. **Which phase does the listener use?** `BEFORE_COMMIT`, `AFTER_COMMIT`, `AFTER_ROLLBACK`, or `AFTER_COMPLETION`?
2. **Did T1 data actually commit?** Read the DB using an independent connection/transaction after the service finishes.
3. **Did the exception happen in the service body, at publish time, before commit, or after completion?** Stack trace and timing help distinguish.
4. **Did the caller catch the exception?** With imperative `AFTER_COMMIT` via `afterCompletion`, usually not; check logs/metrics.
5. **Was the event published inside a transaction?** With no transaction and fallback disabled, the listener does not run.
6. **Does the listener run async?** If so, errors occur on another thread/task and transaction context is not automatically propagated.
7. **Does the listener write to the DB after commit/rollback?** If so, verify the new transaction and `REQUIRES_NEW` proxy rather than trusting `repository.save()` returning normally.
8. **If the handler fails, is the task retried?** Is there a durable channel, idempotency, dead-letter, or appropriate alerting?
9. **Are there multiple listeners?** `@Order`, pre-completion callback exceptions, and post-completion callback exceptions can behave differently.
10. **Which transaction manager / application model?** Imperative JDBC/JPA differs from reactive R2DBC; test against the actual implementation.

### Key Takeaways

~~~text
BEFORE_COMMIT exception
    -> Can cause T1 to roll back; caller may receive error.

AFTER_COMMIT exception
    -> T1 already committed; error does not auto-undo T1.
    -> With Spring 6.2 imperative @TransactionalEventListener:
       runs via afterCompletion, usually logged, not rethrown.

AFTER_ROLLBACK exception
    -> T1 already rolled back; handler error does not change outcome.

To guarantee post-processing:
    -> Do not rely solely on caller's try/catch.
    -> Design retry/idempotency, outbox, or durable workflow.
~~~

## Official Documentation

- [Spring Framework 6.2 – Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [TransactionalEventListener – Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
- [TransactionSynchronization – Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html)
- [Spring source – TransactionalApplicationListenerSynchronization](https://github.com/spring-projects/spring-framework/blob/v6.2.x/spring-tx/src/main/java/org/springframework/transaction/event/TransactionalApplicationListenerSynchronization.java)
- [Spring source – TransactionSynchronizationUtils](https://github.com/spring-projects/spring-framework/blob/v6.2.x/spring-tx/src/main/java/org/springframework/transaction/support/TransactionSynchronizationUtils.java)
