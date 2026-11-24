# Synchronous Listener Exceptions: Error Propagation and Rollback in Spring Application Events

In Spring Framework Application Events, a **synchronous** `@EventListener` method does not act like a message consumer decoupled from the caller. With the default configuration, `ApplicationEventPublisher.publishEvent(...)` invokes listeners on the **same thread**, before the `publishEvent` call completes. If a listener throws an exception and no error-handling mechanism intercepts it, the exception can propagate back to where the event was published. This is especially important if the event is published **inside a database transaction**: a failure in one listener can cause the core business operation to roll back.

This lesson focuses on the questions: where does a synchronous listener's exception go, does it block other listeners, when does the DB roll back, what happens if you catch the error or configure an `ErrorHandler`, and how to accurately test the outcome.

## 1. The Default Execution Model

In a typical Spring `ApplicationContext`, the event multicaster is `SimpleApplicationEventMulticaster`. By default, it executes listeners synchronously in the caller thread and **has no `ErrorHandler`**.

~~~text
OrderService.createOrder()
    |
    +-- INSERT order                       [transaction may be open]
    |
    +-- applicationEventPublisher.publishEvent(OrderCreated)
           |
           +-- listener A @EventListener   [same thread]
           |      +-- business operation
           |      +-- throw IllegalStateException(...)
           |
           +-- listener B                   [usually not called
           |                                  if A's error is unhandled]
           |
           +-- exception propagates back to publishEvent()
    |
    +-- exception may continue out to the transaction interceptor
           |
           +-- decides commit/rollback per rollback rules
~~~

Key point to remember: `publishEvent` **does not mean "put in a queue and return immediately"** in the default configuration. If a listener runs slowly, the publisher is slowed down. If a synchronous listener throws an unchecked exception, the publisher can receive that exact exception.

When we say "the subsequent listener does not run", that is the semantics of **the same synchronous multicast with the default configuration and an unhandled error**. Do not extrapolate it to a system configured with an executor, an `ErrorHandler`, or multiple contexts with different topologies.

| Property | Common Default | Meaning |
| --- | --- | --- |
| `ApplicationEventPublisher.publishEvent(event)` | Delegates to the context's multicaster | Does not return results from listeners |
| `SimpleApplicationEventMulticaster` | Synchronous if no `TaskExecutor` is configured | Publisher and listener share the same thread |
| `ErrorHandler` | None | An unhandled exception stops the multicast and propagates back to the publisher |
| `@EventListener` | Method on a Spring-managed bean | Can return another event, though this does not replace error handling |
| `@Order` | Does not enforce a specific business order unless declared | Can explicitly order invocations when needed; does not create a transaction boundary |

## 2. Which Path Does an Exception Propagate Along?

Suppose a service publishes an event:

~~~java
@Service
class OrderService {
    private final ApplicationEventPublisher publisher;

    OrderService(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    void submit(String id) {
        publisher.publishEvent(new OrderSubmitted(id));
        System.out.println("publish returned");
    }
}

record OrderSubmitted(String id) {}

@Component
class ValidationListener {
    @EventListener
    void onSubmit(OrderSubmitted event) {
        throw new IllegalStateException("invalid order: " + event.id());
    }
}
~~~

This is a **snippet inside a Spring application**, requiring imports for `@Service`, `@Component`, `ApplicationEventPublisher`, and `@EventListener`. With a default synchronous listener, `submit` is interrupted at the `publishEvent` call; the line `publish returned` **is not printed** because `IllegalStateException` is uncaught. The caller of `submit` can catch the exception just like catching an error from an ordinary service call.

There is no automatic retry, dead-letter queue, or replay mechanism simply from using `ApplicationEventPublisher`. If a listener throws an exception, the state of listeners **that completed earlier** is not automatically restored. In particular, HTTP/email side effects sent before the exception cannot be rolled back along with a JDBC transaction.

### Do Subsequent Listeners Still Run?

With synchronous multicasting and no `ErrorHandler`, an exception from listener A usually causes the multicast to **stop at A**; listener B, which would have been called after A, is not executed. When you want to test this case, set an explicit order:

~~~java
@Component
class OrderedListeners {
    @EventListener
    @Order(0)
    public void first(OrderSubmitted event) {
        throw new IllegalStateException("failed first");
    }

    @EventListener
    @Order(10)
    public void second(OrderSubmitted event) {
        System.out.println("second");
    }
}
~~~

This is an illustrative snippet. In the default mode, `second` does not print when `first` throws an exception. `@Order` only specifies the **listener invocation order**, not an error-isolation mechanism or transaction boundary.

## 3. Why Can a Listener Cause a Database Rollback?

The Spring transaction interceptor or `TransactionTemplate` manages the transaction **around the business code**. If a synchronous listener runs within this scope, its exception can propagate back to the transaction manager.

Example of a service annotated with `@Transactional`:

~~~java
@Transactional
public void placeOrder(CreateOrderCommand command) {
    orderRepository.insert(command);
    publisher.publishEvent(new OrderPlaced(command.id()));
}
~~~

This is a snippet: the repository, command, event, and publisher are defined by the application. Suppose the call goes **through the Spring proxy**, the transaction has started, and a synchronous `@EventListener` throws an uncaught `IllegalStateException`: the exception escapes the `placeOrder` method. Under the default rollback rules, Spring marks it for rollback and the DB operations participating in the **same transaction** are undone.

It is not that "the event rolls back the transaction by itself", but rather a causal chain:

1. The listener is invoked **inside** `publishEvent`.
2. The listener throws an exception; no handler intercepts it.
3. The exception escapes the service method/transaction callback.
4. The transaction interceptor/manager applies the rollback rules.
5. The transaction rolls back; uncommitted JDBC/JPA changes of that transaction are discarded.

### Default Rollback Rules

With `@Transactional` under the common configuration of Spring Framework 6.x:

| Error escaping the transactional method | Default | Notes |
| --- | --- | --- |
| `RuntimeException` (e.g., `IllegalStateException`) | Rollback | This is the common case for synchronous listeners |
| `Error` | Rollback | Should not use `Error` to signal business errors |
| Checked `Exception` thrown directly by the service | Normally no rollback | Can configure `rollbackFor` |
| Exception caught by the service and not rethrown | Transaction can commit | Unless already rollback-only or another transaction error occurred |
| No transaction at publish time | No shared DB transaction to roll back | Autocommitted operations are not automatically undone |

Starting from Spring Framework 6.2, an application can opt into a broader default rollback policy via transaction management configuration, so check the **actual version and rollback rules** rather than treating the table as absolute.

Example when a *service method* intentionally throws a checked exception:

~~~java
@Transactional(rollbackFor = BusinessRuleException.class)
public void executeCommand() throws BusinessRuleException {
    // ... DB operations
    throw new BusinessRuleException("Rejected");
}
~~~

This is a snippet, requiring `BusinessRuleException extends Exception` to be defined and the method to actually be handled by the transaction interceptor. `rollbackFor` explicitly specifies the policy for that exception. **Do not mechanically apply the service's checked-exception rule directly to an `@EventListener` method**, because Spring's event adapter has its own exception-wrapping step.

## 4. Subtle Case: Checked Exceptions in @EventListener

Spring allows an `@EventListener` method to declare checked exceptions, but **a checked exception raised from a listener is wrapped into `java.lang.reflect.UndeclaredThrowableException`** because `ApplicationEventPublisher` works with runtime exceptions.

Example:

~~~java
@EventListener
public void onOrder(OrderSubmitted event) throws IOException {
    throw new IOException("external system unavailable");
}
~~~

This is a snippet (requiring `java.io.IOException` to be imported). In a call through Spring's listener adapter, the exception propagating back to the publisher can be an `UndeclaredThrowableException` whose cause is `IOException`. The wrapper class is **unchecked**, so if it escapes the transaction interceptor, default rollback can occur even though the original exception was checked.

Therefore, it is necessary to distinguish:

- **Checked exception thrown by the `@Transactional` service itself**: under Spring 6.x default rollback rules, it normally does not trigger a rollback.
- **Checked exception thrown by an `@EventListener` method via Spring's listener adapter**: wrapped into `UndeclaredThrowableException`, which is a runtime exception; the rollback outcome can differ.
- **Exception caught by an `ErrorHandler` or caller**: the wrapper might not escape the transaction boundary; the outcome also depends on the transaction state and other handling.

Do not write a test that only does `assertThrows(IOException.class, ...)` for the entire `publishEvent` flow and assume it always holds. Check the **actual exception observed at the publisher** along with its cause.

## 5. Catching Exceptions in the Service Changes the Outcome

Suppose a listener throws an error, yet the application service decides to continue:

~~~java
@Transactional
public void placeOrder(CreateOrderCommand command) {
    orderRepository.insert(command);

    try {
        publisher.publishEvent(new OrderPlaced(command.id()));
    } catch (IllegalStateException ex) {
        log.warn("Optional listener failed", ex);
    }
}
~~~

This is a snippet, requiring `log`, the repository, and the business class. If no other component marks `rollbackOnly`, the transaction can **commit** even though a listener failed. However, because the default multicast is aborted at the throwing listener, **subsequent listeners may still not have been called**. Catching at the caller does not turn back time to continue running listener B.

### When Business Logic Requires Rollback Even After Catching the Exception

Use rollback-only within the proper scope when you want to capture the error while preventing commit:

~~~java
@Transactional
public void placeOrder(CreateOrderCommand command) {
    orderRepository.insert(command);

    try {
        publisher.publishEvent(new OrderPlaced(command.id()));
    } catch (IllegalStateException ex) {
        TransactionAspectSupport.currentTransactionStatus()
            .setRollbackOnly();
        log.warn("Transaction must not commit", ex);
    }
}
~~~

This is a snippet depending on the active transaction interceptor and `TransactionAspectSupport`. `currentTransactionStatus()` can only be used when there is a Spring-managed transaction status in the appropriate context; do not call it arbitrarily outside a transaction. A clearer alternative when using `TransactionTemplate` is `status.setRollbackOnly()`.

**Nested transactions warning:** a transaction participating in an outer transaction may have already been marked rollback-only in another layer. Catching the exception in the outer layer does not necessarily make the commit succeed; you may encounter `UnexpectedRollbackException`. Catching an exception does not clear a rollback-only flag that has already been set.

### Do Not Call External Systems Before Commit Just Because a Listener Is Synchronous

If a listener has already sent an email or HTTP request before an error occurs and the transaction rolls back, the email/request may still exist. If a side effect must wait for commit, use `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)`; if sending intent must not be lost after a crash, use a transactional outbox or a durable publication-recording mechanism.

## 6. Customizing the SimpleApplicationEventMulticaster ErrorHandler

Spring supports providing a bean named `applicationEventMulticaster` to customize how listeners are handled. When no `ErrorHandler` is configured, an unhandled exception propagates to the publisher and can stop the invocation of subsequent listeners.

An **illustrative** configuration using a handler that logs the error and **does not rethrow**:

~~~java
@Configuration
class EventMulticasterConfiguration {

    @Bean(name = "applicationEventMulticaster")
    ApplicationEventMulticaster applicationEventMulticaster() {
        SimpleApplicationEventMulticaster multicaster =
            new SimpleApplicationEventMulticaster();

        multicaster.setErrorHandler(error ->
            System.err.println(
                "Listener failed: " + error.getClass().getSimpleName()
            )
        );

        return multicaster;
    }
}
~~~

This is a configuration snippet in Spring, requiring imports for `@Configuration`, `@Bean`, `ApplicationEventMulticaster`, and `SimpleApplicationEventMulticaster`. In production, use contextual logging/metrics; `System.err` only helps make the example clear.

When the handler **suppresses** the exception and returns normally, the multicaster can proceed to invoke the next listener. `publishEvent` can also return normally, so the transaction **does not automatically roll back solely because the error was suppressed**.

Conversely, the handler can **log and rethrow** the exception; in that case propagation and rollback can occur as if there were no handler. Spring also provides convenience ErrorHandlers such as `TaskUtils.LOG_AND_SUPPRESS_ERROR_HANDLER` and `TaskUtils.LOG_AND_PROPAGATE_ERROR_HANDLER` in appropriate situations.

| Policy | Does exception reach publisher? | Next listener? | Risk |
| --- | --- | --- | --- |
| Default, no `ErrorHandler` | Yes, in synchronous dispatch | Usually stops at the failing listener | Core business operation may roll back due to a secondary failure |
| Handler logs and suppresses | No, if the handler handles it completely | Can continue | Hides serious errors and lets the transaction commit |
| Handler logs and rethrows | Yes | Stops when the error escapes | Still coupled with the core business operation |
| Asynchronous dispatch via executor | Cannot assume the exception reaches the caller | Depends on executor/handler | Requires dedicated error tracking and context |

**Do not enable global suppression just to "ignore errors"**. It affects every listener going through that multicaster, including listeners whose failure might reflect a data invariant that must not be ignored. If only one listener is best-effort, consider handling it locally inside the listener or moving the task to an appropriate asynchronous/durable mechanism.

## 7. Synchronous Listeners Differ from Async Listeners at Error Boundaries

With `@Async @EventListener` or a multicaster with an executor, a listener can run on a different thread. In that case, an asynchronous listener's exception **is not propagated directly** back to the caller of `publishEvent`. The exception-handling mechanism depends on `AsyncUncaughtExceptionHandler`, the returned `Future`, the executor, and the configuration.

~~~java
@Async
@EventListener
public void onOrderCreated(OrderCreated event) {
    notificationSender.send(event.orderId());
}
~~~

This is a snippet, requiring `@EnableAsync` to be enabled and a `notificationSender` bean/object to be provided. Do not use it as proof that the email was definitely sent when `publishEvent` returns.

**Transaction implication:** JDBC transactions are usually bound to the calling thread. An async task on another thread does not automatically join the publisher's transaction. An async exception does not automatically roll back the original transaction; conversely, the data seen by the async listener might not be committed yet at the time it runs. If the requirement is to run only after commit, use an appropriate transaction-bound listener and design an async execution mechanism **after commit** if needed.

`@TransactionalEventListener(AFTER_COMMIT)` differs from a regular synchronous `@EventListener`: it registers processing based on the transaction outcome. Once the transaction has committed, an exception occurring in after-commit work **cannot undo the already completed commit**; error reporting to the caller and logging also depend on transaction synchronization and configuration. Therefore, critical side effects need retry, idempotency, and dedicated error observability.

Do not use `@Async` as a simple trick to fix rollback errors. It changes consistency, completion ordering, and error-observability boundaries.

## 8. Java 17+ Integration Example: Verifying Propagation, Rollback, Catch, and No Transaction

The following test suite uses **Spring Context + Spring Test + Spring JDBC + H2 + JUnit 5**. All significant JDBC operations and publish calls run inside `TransactionTemplate` when a transaction is needed; the test itself does not carry `@Transactional` to avoid the test transaction rolling back at the end of the method.

Objectives:

1. No error: both `@Order(0)` and `@Order(10)` run, `publishEvent` returns, DB commits.
2. First listener throws `IllegalStateException` inside a transaction: publisher receives the error, subsequent listener does not run, both service and listener data roll back.
3. No transaction: error still reaches the caller, but the listener's INSERT statement may have **autocommitted** and is not undone.
4. Service catches the exception inside a transaction: transaction does not roll back just because a caught error occurred, if rollback-only was not marked.
5. Service catches the error but sets rollback-only: the database rolls back even though the exception is not rethrown.

### 8.1. build.gradle

~~~groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    testImplementation platform('org.springframework:spring-framework-bom:6.2.9')
    testImplementation 'org.springframework:spring-context'
    testImplementation 'org.springframework:spring-jdbc'
    testImplementation 'org.springframework:spring-tx'
    testImplementation 'org.springframework:spring-test'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'

    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
    testRuntimeOnly 'com.h2database:h2:2.3.232'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

In a Spring Boot project that already has a BOM/dependency management, prefer the versions managed by Boot to avoid mixing incompatible Spring Framework modules. The test example uses Java 17; the Gradle wrapper configuration is provided by the project.

### 8.2. src/test/java/example/events/SyncListenerExceptionTest.java

~~~java
package example.events;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.ArrayList;
import java.util.List;

import javax.sql.DataSource;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.transaction.support.TransactionTemplate;

@SpringJUnitConfig(SyncListenerExceptionTest.Config.class)
class SyncListenerExceptionTest {

    @Autowired ApplicationEventPublisher publisher;
    @Autowired JdbcTemplate jdbc;
    @Autowired TransactionTemplate tx;
    @Autowired Trace trace;

    @BeforeEach
    void prepare() {
        jdbc.execute("CREATE TABLE IF NOT EXISTS orders (" +
            "id VARCHAR(50) PRIMARY KEY)");
        jdbc.execute("CREATE TABLE IF NOT EXISTS audit (" +
            "id VARCHAR(50) PRIMARY KEY)");
        jdbc.update("DELETE FROM audit");
        jdbc.update("DELETE FROM orders");
        trace.clear();
    }

    @Test
    void successCallsBothListenersAndCommits() {
        tx.executeWithoutResult(status -> {
            insertOrder("OK");
            publisher.publishEvent(new OrderCreated("OK", false));
            trace.add("returned:OK");
        });

        assertEquals(
            List.of("first:OK", "second:OK", "returned:OK"),
            trace.snapshot()
        );
        assertEquals(1, orders("OK"));
        assertEquals(1, audit("OK"));
    }

    @Test
    void failureStopsMulticastAndRollsBack() {
        IllegalStateException error = assertThrows(
            IllegalStateException.class,
            () -> tx.executeWithoutResult(status -> {
                insertOrder("FAIL");
                publisher.publishEvent(
                    new OrderCreated("FAIL", true));
                trace.add("returned:FAIL");
            })
        );

        assertEquals("blocked:FAIL", error.getMessage());
        assertEquals(List.of("first:FAIL"), trace.snapshot());
        assertEquals(0, orders("FAIL"));
        assertEquals(0, audit("FAIL"));
    }

    @Test
    void failureOutsideTransactionCannotUndoAutocommit() {
        assertThrows(
            IllegalStateException.class,
            () -> publisher.publishEvent(
                new OrderCreated("OUT", true))
        );

        assertEquals(List.of("first:OUT"), trace.snapshot());
        assertEquals(1, audit("OUT"));
    }

    @Test
    void catchingExceptionAllowsCommit() {
        tx.executeWithoutResult(status -> {
            insertOrder("CATCH");
            try {
                publisher.publishEvent(
                    new OrderCreated("CATCH", true));
            } catch (IllegalStateException expected) {
                trace.add("caught:CATCH");
            }
        });

        assertEquals(
            List.of("first:CATCH", "caught:CATCH"),
            trace.snapshot()
        );
        assertEquals(1, orders("CATCH"));
        assertEquals(1, audit("CATCH"));
    }

    @Test
    void rollbackOnlyWorksEvenWhenExceptionIsCaught() {
        tx.executeWithoutResult(status -> {
            insertOrder("MARK");
            try {
                publisher.publishEvent(
                    new OrderCreated("MARK", true));
            } catch (IllegalStateException expected) {
                status.setRollbackOnly();
                trace.add("marked:MARK");
            }
        });

        assertEquals(
            List.of("first:MARK", "marked:MARK"),
            trace.snapshot()
        );
        assertEquals(0, orders("MARK"));
        assertEquals(0, audit("MARK"));
    }

    private void insertOrder(String id) {
        jdbc.update("INSERT INTO orders(id) VALUES (?)", id);
    }

    private int orders(String id) {
        return jdbc.queryForObject(
            "SELECT COUNT(*) FROM orders WHERE id = ?",
            Integer.class, id
        );
    }

    private int audit(String id) {
        return jdbc.queryForObject(
            "SELECT COUNT(*) FROM audit WHERE id = ?",
            Integer.class, id
        );
    }

    record OrderCreated(String id, boolean fail) { }

    static final class Trace {
        private final List<String> lines = new ArrayList<>();

        void add(String line) {
            lines.add(line);
        }

        List<String> snapshot() {
            return List.copyOf(lines);
        }

        void clear() {
            lines.clear();
        }
    }

    static final class OrderedListeners {
        private final JdbcTemplate jdbc;
        private final Trace trace;

        OrderedListeners(JdbcTemplate jdbc, Trace trace) {
            this.jdbc = jdbc;
            this.trace = trace;
        }

        @EventListener
        @Order(0)
        public void first(OrderCreated event) {
            trace.add("first:" + event.id());
            jdbc.update("INSERT INTO audit(id) VALUES (?)",
                event.id());

            if (event.fail()) {
                throw new IllegalStateException(
                    "blocked:" + event.id());
            }
        }

        @EventListener
        @Order(10)
        public void second(OrderCreated event) {
            trace.add("second:" + event.id());
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class Config {

        @Bean
        DataSource dataSource() {
            return new DriverManagerDataSource(
                "jdbc:h2:mem:listener_exception;DB_CLOSE_DELAY=-1",
                "sa", ""
            );
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource ds) {
            return new JdbcTemplate(ds);
        }

        @Bean
        DataSourceTransactionManager transactionManager(
                DataSource ds) {
            return new DataSourceTransactionManager(ds);
        }

        @Bean
        TransactionTemplate transactionTemplate(
                DataSourceTransactionManager manager) {
            return new TransactionTemplate(manager);
        }

        @Bean
        Trace trace() {
            return new Trace();
        }

        @Bean
        OrderedListeners listeners(JdbcTemplate jdbc, Trace trace) {
            return new OrderedListeners(jdbc, trace);
        }
    }
}
~~~

### 8.3. How to Run and Understand the Results

In a project with a Gradle wrapper:

~~~bash
./gradlew test --tests "example.events.SyncListenerExceptionTest"
~~~

On Windows PowerShell:

~~~powershell
./gradlew.bat test --tests "example.events.SyncListenerExceptionTest"
~~~

The strings in `Trace` are verified via assertions, **not the full Gradle stdout**. When the tests pass, we have the observable results:

| Test | Expected Trace | orders | audit |
| --- | --- | --- | --- |
| `successCallsBothListenersAndCommits` | `first:OK`, `second:OK`, `returned:OK` | OK = 1 | OK = 1 |
| `failureStopsMulticastAndRollsBack` | Only `first:FAIL` | FAIL = 0 | FAIL = 0 |
| `failureOutsideTransactionCannotUndoAutocommit` | Only `first:OUT` | No order recorded | OUT = 1 |
| `catchingExceptionAllowsCommit` | `first:CATCH`, `caught:CATCH` | CATCH = 1 | CATCH = 1 |
| `rollbackOnlyWorksEvenWhenExceptionIsCaught` | `first:MARK`, `marked:MARK` | MARK = 0 | MARK = 0 |

**Why does the audit insert also roll back in the FAIL test?** `JdbcTemplate` in the listener runs on the same thread, uses the same `DataSourceTransactionManager`, and participates in the JDBC transaction opened by the service. If the listener writes to a different database or calls an external API, do not assume that side effect automatically joins the original transaction.

**Why doesn't trace roll back?** `Trace` is an in-memory Java list, not part of the JDBC transaction. It intentionally keeps a record that the listener ran, even though the SQL statements were subsequently rolled back.

**Why use `TransactionTemplate` instead of `@Transactional` in the test?** To make the commit/rollback timing explicit and verify directly after each transaction. With an application using `@Transactional`, the result is similar if the interceptor actually wraps the transaction, the call goes through the proxy, and the rollback rules match. Do not put `@Transactional` on the whole JUnit test and expect `AFTER_COMMIT` to run mid-test; Spring TestContext has a default test-transaction rollback mechanism.

The test pattern uses the real `ApplicationEventPublisher` of the Spring context, rather than directly calling `OrderedListeners.first(...)`. Therefore, the test verifies both Spring's registration and invocation of `@EventListener` and the behavior of `SimpleApplicationEventMulticaster`.

## 9. Diagnostic: When Does an Error Roll Back, and When Does It Not?

| Scenario | Does publisher see the error? | Does transaction roll back? | What to check |
| --- | --- | --- | --- |
| Sync listener throws `IllegalStateException` in `@Transactional` and error escapes | Yes | Usually yes, per rollback rules | Does the service call go through the proxy? |
| Sync listener throws error outside a transaction | Yes | No shared transaction to roll back | Did autocommit side effects already happen? |
| Caller catches error, no rollback-only | Caller catches it | Can commit | Did any transaction already mark rollback-only? |
| Caller catches and sets rollback-only | Caller catches it | Yes | Was status marked in the right transaction? |
| Global `ErrorHandler` suppresses | Usually no | Not solely due to the suppressed error | Was a critical error accidentally ignored? |
| `@Async` listener throws error | Usually not via sync path | Does not directly roll back the original transaction | `AsyncUncaughtExceptionHandler`/executor/metrics |
| `@TransactionalEventListener(AFTER_COMMIT)` throws error | Depends on callback/synchronization | **Does not undo an already completed commit** | Retry/compensation and error observability |

### Logging and Tracing with Enough Context

When debugging, log `eventType`, `eventId`, `aggregateId`, listener class/method, exception type, transaction status, and correlation ID. **Do not log sensitive payloads** unnecessarily. If using proxies or async, also log the thread and publish point to identify processing boundaries.

For exceptions that may cause a rollback, also test:

- DB values after the transaction ends (read back from an independent transaction/connection);
- which listeners were invoked and which were not;
- the actual exception reaching the caller, including the `UndeclaredThrowableException` wrapper;
- external side effects if any (mock gateway, outbox record);
- cases where the error was caught or suppressed by an ErrorHandler, avoiding the assumption that the transaction still rolls back.

## 10. System Design: Do Not Let Listeners Hide Core Business Decisions

An event listener is appropriate when a group of independent tasks **reacts** to a domain event. However, if "failure of step B must cancel step A" is a mandatory invariant, using an application service that calls B explicitly within the same transaction is usually easier to read and maintain than relying on a hidden listener.

Example:

~~~java
@Transactional
public void confirmOrder(String id) {
    inventoryService.reserve(id);   // mandatory step
    orderRepository.confirm(id);
    publisher.publishEvent(new OrderConfirmed(id)); // notification
}
~~~

This is a snippet, not a standalone file. When an event is only for updating metrics or sending notifications, consider appropriate best-effort or after-commit handling. For tasks that must be delivered durably outside the process, a **transactional outbox** records business data and sending intent in the same transaction, then delivers via a worker with retry and idempotency; do not treat the default `ApplicationEventPublisher` as a durable message queue.

### Pre-Implementation Checklist

1. Is the current listener **sync**, `@Async`, or run on an executor by a custom multicaster?
2. Is there an `ErrorHandler`? Does it log/suppress or log/rethrow?
3. Is the event published **before, during, or after** the transaction?
4. When a listener fails, must the core business operation roll back? Are the rollback rules right?
5. Where does the caller catch exceptions? At what point was the transaction marked rollback-only?
6. If the listener executes before commit, are there non-rollbackable side effects?
7. Do integration tests cover success, exception, catch, rollback-only, and outside-transaction cases?
8. If retry/durability is needed, where do event persistence and idempotency live?

## 11. Self-Check Questions

**Question 1:** In the default configuration, if a synchronous `@EventListener` throws `IllegalStateException`, can `publishEvent` return normally?

Usually **no**: the exception propagates back to the publisher and the current multicast stops. Only when catching code or an appropriate `ErrorHandler` is present does the propagation path differ.

**Question 2:** Does a listener's exception always roll back the database?

**No.** There must be an active transaction wrapping the publish call, the error must escape to the boundary/transaction manager under the rollback rules, or the transaction must be marked rollback-only. If the error is caught or the event is published outside a transaction, the outcome differs.

**Question 3:** Is a checked exception in an `@EventListener` method the same as a checked exception thrown directly from a `@Transactional` service?

Not entirely. Spring's listener adapter wraps checked exceptions into an unchecked `UndeclaredThrowableException` when propagating back to the publisher, so rollback rules may evaluate the wrapper type, not only the original type.

**Question 4:** Does placing `@Order(0)` and `@Order(10)` make the second listener still run when the first listener throws an exception?

Not in the default synchronous configuration without error handling. `@Order` only orders invocations; it does not catch exceptions. A suppressing `ErrorHandler` can change whether subsequent listeners continue to be called.

**Question 5:** Does using `@Async` for a listener guarantee that errors do not affect the transaction while still ensuring reliable processing?

No. Async decouples the exception propagation path from the caller, but it does not guarantee that the listener has completed, nor retry or durability. The system must monitor errors and design appropriate handling.

**Remember:** exceptions from a synchronous `@EventListener` **usually propagate back to `publishEvent` and interrupt the multicast**. Rollback only occurs when the transaction boundary and rollback rules produce that result. Understanding error catching, `ErrorHandler`, checked-exception wrappers, and async dispatch is essential to designing safe events.

## References

- [Spring Framework – ApplicationContext: Event Listeners, Asynchronous Listeners, and Multicaster](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework – SimpleApplicationEventMulticaster API](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring Framework – EventListener API: Exception Handling](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/EventListener.html)
- [Spring Framework – @Transactional and Rollback Rules](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html)
- [Spring Framework – Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
