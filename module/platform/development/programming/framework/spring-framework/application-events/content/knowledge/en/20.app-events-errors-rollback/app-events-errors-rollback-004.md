# Exceptions in Spring Framework After-Commit Listeners: What Happens to the Completed Transaction?

## 1. Core Problem

Suppose a service creates an order inside a transaction and publishes an event:

```java
@Transactional
public void placeOrder(String id) {
    orderRepository.save(new Order(id));
    publisher.publishEvent(new OrderPlaced(id));
}
```

A listener sends a confirmation email after commit:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void sendConfirmation(OrderPlaced event) {
    emailService.send(event.orderId());
}
```

These are **illustrative snippets**, not standalone programs; `Order`, `OrderPlaced`, repository, and email service are application-defined.

**Question:** If `emailService.send(...)` throws a `RuntimeException`, is the order row in the DB rolled back? Does the caller receive the exception? Can we retry by calling `placeOrder()` again?

Three critical points:

1. **The main transaction has already committed** before the `AFTER_COMMIT` listener runs. An exception in the listener **cannot reverse the commit**.
2. With `@TransactionalEventListener(AFTER_COMMIT)` in Spring Framework's standard imperative transaction synchronization mechanism, the handler is triggered at the **`afterCompletion(STATUS_COMMITTED)`** phase. An exception in `afterCompletion` is **logged by Spring rather than propagated back to the caller** through this callback path. Therefore, the caller may observe the service method returning normally even though post-processing failed.
3. This **differs** from the direct `TransactionSynchronization.afterCommit()` callback: an exception from `afterCommit()` directly **is propagated back to the commit caller** per the API, though the primary data has already committed and **still cannot be rolled back**.

Therefore, never design a rule stating "if the caller sees no error, the email was definitely sent successfully." Nor should you re-invoke the entire order-creation business operation when only the post-commit step failed: doing so risks creating duplicate orders or duplicate side effects.

This lesson focuses on **Spring Framework Application Events** and imperative transactions managed by `PlatformTransactionManager`, such as Spring JDBC/JPA. With reactive transactions (`ReactiveTransactionManager`), the transaction context and callback path differ; apply the corresponding reactive documentation.

## 2. Transaction Lifecycle and Where the Exception Occurs

The `OrderPlaced` event is published *inside* the transaction, yet the `AFTER_COMMIT` listener does not process immediately:

```text
Caller
  |
  v
@Transactional OrderService.placeOrder()
  |
  +-- BEGIN T1
  +-- INSERT order
  +-- publishEvent(OrderPlaced)
  |      |
  |      +-- register TransactionalEventListener for T1
  |
  +-- return from method body
  |
  +-- COMMIT T1 succeeded
  |
  +-- T1 completion callback with STATUS_COMMITTED
  |      |
  |      +-- @TransactionalEventListener(AFTER_COMMIT)
  |             |
  |             +-- send email / call API / write audit
  |             |
  |             +-- may THROW EXCEPTION
  |                    |
  |                    +-- logged in afterCompletion path
  |                    +-- DOES NOT roll back T1
  |
  +-- cleanup transaction resources
  |
  v
Caller continues; does not necessarily receive post-commit error
```

**Note:** You should not strictly describe `@TransactionalEventListener(AFTER_COMMIT)` as "Spring calls `TransactionSynchronization.afterCommit()`." In terms of **business semantics**, both happen after a successful commit, but **their callback paths and exception propagation rules differ**. Spring uses `TransactionalApplicationListenerSynchronization` to process event phases; for the annotation listener's `AFTER_COMMIT` phase, the event is processed matching `STATUS_COMMITTED` inside `afterCompletion(...)`.

This difference explains why test code or logging can produce unexpected results: you see a stack trace from the listener in the logs, yet `placeOrder()` still returns normally.

## 3. Comparing Exceptions Across Transaction Phases

| Where the exception occurs | Is T1 data committed yet? | Common impact |
| --- | --- | --- |
| Inside the `@Transactional` body before commit | No | Unchecked exception escaping through proxy usually causes T1 to roll back per default rules |
| Synchronous `@EventListener` invoked when publishing inside T1 | No | If the exception escapes to the `@Transactional` boundary, T1 can roll back |
| `@TransactionalEventListener(BEFORE_COMMIT)` | No | Exception propagates in the commit path; can prevent commit and cause rollback |
| `@TransactionalEventListener(AFTER_COMMIT)` | **Already committed** | T1 does not roll back; in the standard after-completion mechanism the exception is logged, not propagated to the caller |
| `@TransactionalEventListener(AFTER_ROLLBACK)` | T1 already rolled back | Exception does not undo the rollback outcome; usually logged in the completion callback |
| `@TransactionalEventListener(AFTER_COMPLETION)` | T1 already completed | Cannot change the transaction outcome; exception handled per the completion callback |
| **Direct** `TransactionSynchronization.afterCommit()` | **Already committed** | Runtime exception can **propagate to the commit caller**, but does not roll back T1 |
| Direct `TransactionSynchronization.afterCompletion(...)` | Already completed | Runtime exception is logged, not propagated via the standard callback mechanism |

**Key distinction:** `AFTER_COMMIT` denotes timing relative to the transaction; it does not mean "an error at this moment will roll back." Exception propagation rules also depend on **the exact callback API** being used.

The `TransactionSynchronization` documentation explicitly states:
- `afterCommit()` can propagate `RuntimeException` to the caller.
- `afterCompletion(int)` logs `RuntimeException` without propagating it to the caller.
- After commit/rollback, transaction resources may still be accessible; if a new DB write is needed, use an independent transaction, typically `PROPAGATION_REQUIRES_NEW`.

## 4. Minimal Example: A Listener Throwing an Exception

```java
@Component
class OrderEvents {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    void whenOrderCommitted(OrderPlaced event) {
        System.out.println("after commit listener invoked");
        throw new IllegalStateException("mail server unavailable");
    }
}
```

This is **illustrative code**, requiring `OrderPlaced`, a Spring-managed bean, and an event published inside a transaction.

When the service is called through the transaction proxy, it commits T1 successfully and then Spring processes the callback. A standard Spring Framework implementation may log at `ERROR` level with information similar to:

```text
TransactionSynchronization.afterCompletion threw exception
java.lang.IllegalStateException: mail server unavailable
```

This is an **illustrative log format**, not an exact mandated output string: logger, version, configuration, and stack trace may vary.

**Do not read logs to conclude that T1 rolled back.** Query the data after the transaction to verify whether T1 committed. With a post-commit error, all of these can be true simultaneously:

```text
orders has new record = true
email sent successfully = false
caller receives exception = false
```

The third state depends on the specific callback; for a standard `@TransactionalEventListener(AFTER_COMMIT)` running via the synchronous completion callback, the error is typically logged and not propagated to the caller. If the application uses listener fallback, an executor, or custom event infrastructure, you must verify the actual execution path.

## 5. Runnable Java 17+ Example: Logged Error and Error Recorded via a New Transaction

The complete example below uses **Spring Framework 6.2.12**, **Spring JDBC**, in-memory H2, and Gradle; no Spring Boot. It simulates external notification failure across two orders:

- **Order A:** the listener throws `IllegalStateException` out of the `AFTER_COMMIT` method. Spring logs the exception via the `afterCompletion` path; the order-creation transaction already committed, and the caller still finishes normally in this setup.
- **Order B:** the listener catches the exception, calls `FailureAuditWriter` through a Spring bean proxy with `@Transactional(REQUIRES_NEW)`, saves a `failure_audit` row in a second transaction, and then finishes the callback normally.
- Results are verified by querying the DB after each call, rather than inferring from an exception being thrown on some thread.

### 5.1. Directory Structure

```text
after-commit-errors-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/AfterCommitErrorsDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'after-commit-errors-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.12'
    implementation 'org.springframework:spring-jdbc:6.2.12'
    runtimeOnly 'com.h2database:h2:2.3.232'
}

application {
    mainClass = 'demo.AfterCommitErrorsDemo'
}
```

Requires JDK 17+ and Gradle installed. `DriverManagerDataSource` is used for this short exercise; in production, a bounded connection pool with timeouts and usage monitoring is required.

### 5.2. `src/main/java/demo/AfterCommitErrorsDemo.java`

```java
package demo;

import javax.sql.DataSource;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

public class AfterCommitErrorsDemo {

    public record OrderPlaced(String orderId, boolean recordFailure) {}

    public static class OrderService {
        private final JdbcTemplate jdbc;
        private final ApplicationEventPublisher publisher;

        public OrderService(
                JdbcTemplate jdbc,
                ApplicationEventPublisher publisher) {
            this.jdbc = jdbc;
            this.publisher = publisher;
        }

        @Transactional
        public void place(String id, boolean recordFailure) {
            jdbc.update("insert into orders (id) values (?)", id);
            publisher.publishEvent(new OrderPlaced(id, recordFailure));
        }
    }

    public static class FailureAuditWriter {
        private final JdbcTemplate jdbc;

        public FailureAuditWriter(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional(propagation = Propagation.REQUIRES_NEW)
        public void saveFailure(String orderId, String reason) {
            jdbc.update(
                    "insert into failure_audit (order_id, reason) values (?, ?)",
                    orderId, reason);
        }
    }

    public static class NotificationListener {
        private final FailureAuditWriter auditWriter;

        public NotificationListener(FailureAuditWriter auditWriter) {
            this.auditWriter = auditWriter;
        }

        @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
        public void onOrderPlaced(OrderPlaced event) {
            System.out.println("listener attempted: " + event.orderId());

            try {
                // Simulate the notification-sending system encountering an error.
                throw new IllegalStateException("notification unavailable");
            } catch (IllegalStateException ex) {
                if (event.recordFailure()) {
                    // T2: new transaction after order T1 has committed.
                    auditWriter.saveFailure(
                            event.orderId(), ex.getMessage());
                    return;
                }

                // Case A: let exception escape the listener.
                throw ex;
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class AppConfig {

        @Bean
        DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl(
                    "jdbc:h2:mem:after_commit_errors;DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        PlatformTransactionManager transactionManager(
                DataSource dataSource) {
            return new DataSourceTransactionManager(dataSource);
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        OrderService orderService(
                JdbcTemplate jdbc,
                ApplicationEventPublisher publisher) {
            return new OrderService(jdbc, publisher);
        }

        @Bean
        FailureAuditWriter failureAuditWriter(JdbcTemplate jdbc) {
            return new FailureAuditWriter(jdbc);
        }

        @Bean
        NotificationListener notificationListener(
                FailureAuditWriter auditWriter) {
            return new NotificationListener(auditWriter);
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            OrderService orders = context.getBean(OrderService.class);

            jdbc.execute(
                    "create table orders (id varchar(40) primary key)");
            jdbc.execute(
                    "create table failure_audit ("
                    + "order_id varchar(40) primary key, "
                    + "reason varchar(100) not null)");

            // A: listener throws exception in AFTER_COMMIT.
            orders.place("A", false);
            System.out.println("service A returned");
            System.out.println("after A: orders=" + count(jdbc, "orders")
                    + ", audits=" + count(jdbc, "failure_audit"));

            // B: listener catches error and writes audit via REQUIRES_NEW.
            orders.place("B", true);
            System.out.println("service B returned");
            System.out.println("after B: orders=" + count(jdbc, "orders")
                    + ", audits=" + count(jdbc, "failure_audit"));
        }
    }

    private static int count(JdbcTemplate jdbc, String table) {
        // table only accepts two constant names in main(), not user input.
        return jdbc.queryForObject(
                "select count(*) from " + table, Integer.class);
    }
}
```

Run:

```bash
gradle -q run
```

Lines **intentionally printed by the program via `System.out.println`**, in order:

```text
listener attempted: A
service A returned
after A: orders=1, audits=0
listener attempted: B
service B returned
after B: orders=2, audits=1
```

In addition to the six lines above, the console **may show error logs and a stack trace** from Spring when listener A throws the exception:

```text
TransactionSynchronization.afterCompletion threw exception
java.lang.IllegalStateException: notification unavailable
```

This is a representative log snippet, **not** part of fixed-format stdout. It does not change the six `System.out.println` lines above.

### 5.3. Why Do Both Orders Still Exist?

**Case A:**

1. `context.getBean(OrderService.class)` retrieves the service through the Spring transaction proxy. `place("A", false)` starts transaction T1.
2. The service inserts `orders(A)` and publishes `OrderPlaced("A", false)` inside T1.
3. The `AFTER_COMMIT` listener is registered to wait for T1's outcome; it **does not run immediately on publish**.
4. T1 commits successfully. Then listener `onOrderPlaced` runs, prints `listener attempted: A`, and throws `IllegalStateException`.
5. Spring catches the exception in the completion callback and logs the error; T1 **has already committed** and does not roll back. Along this path, `orders.place(...)` still returns and `main` prints `service A returned`.
6. Subsequent queries confirm `orders=1`, `audits=0`. The program does not automatically produce an audit row when only logging the exception.

**Case B:**

1. Creates `orders(B)` in a new transaction T1-B, then publishes the event with `recordFailure=true`.
2. T1-B commits. The post-commit listener simulates a notification error.
3. The listener **catches** the error and calls **another bean**, `FailureAuditWriter.saveFailure(...)`, annotated with `@Transactional(REQUIRES_NEW)`. Spring creates a new transaction T2 to insert `failure_audit(B, reason)`.
4. T2 commits independently; the listener returns normally. After the caller returns, DB queries confirm `orders=2`, `audits=1`.
5. Both orders `A` and `B` exist because **both order-creation transactions committed**; only order B has an audit failure row because it was handled and durably saved through T2.

**Limitation of the example:** `REQUIRES_NEW` demonstrates saving a **DB failure record** after commit. It **does not guarantee** that the notification task is retried or completed. To have retries, you need a worker, state, and a re-execution mechanism. If T2's DB also fails, a separate error policy is required; you cannot silently treat the notification as completed.

## 6. Do Not Confuse Direct `afterCommit()` with `@TransactionalEventListener(AFTER_COMMIT)`

Two paths that are often conflated in brief explanations:

### 6.1. Direct Callback from `TransactionSynchronization`

```java
TransactionSynchronizationManager.registerSynchronization(
    new TransactionSynchronization() {
        @Override
        public void afterCommit() {
            throw new IllegalStateException("direct callback error");
        }
    });
```

This is **illustrative code**, which must be called while transaction synchronization is active; imports for `TransactionSynchronization` and `TransactionSynchronizationManager` are required.

Per the `TransactionSynchronization.afterCommit()` contract, a runtime exception from a direct callback **is propagated** to the commit caller. Even if the caller sees the exception, the primary data may **already have committed**. If the caller unconditionally retries the entire command upon seeing an exception, there is a risk of creating duplicate data.

### 6.2. `@TransactionalEventListener` Listener

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onCommitted(OrderPlaced event) {
    throw new IllegalStateException("listener callback error");
}
```

This is **illustrative code**. In Spring Framework's standard implementation using `afterCompletion(STATUS_COMMITTED)`, an exception thrown by the listener is normally **logged and not propagated** to the caller. The result is still that T1 committed.

### 6.3. Practical Conclusion

| API | When does the callback run? | Where does a runtime exception go? | Can T1 roll back? |
| --- | --- | --- | --- |
| Direct `TransactionSynchronization.afterCommit()` | After commit | Can propagate to commit caller | **No**, T1 already committed |
| `@TransactionalEventListener(AFTER_COMMIT)` | After commit, via completion callback | Logged, not propagated in the standard callback path | **No**, T1 already committed |
| Direct `TransactionSynchronization.afterCompletion(status)` | After commit/rollback | Logged, not propagated in the standard helper | **No**, transaction already completed |
| `@TransactionalEventListener(BEFORE_COMMIT)` | Before commit | Can propagate and cause commit to fail | **Possible**, since T1 has not committed yet |

The core point is not whether the caller sees an exception. **The data truth is that the transaction has committed**, so replay/compensation must be designed as a **separate business flow**, not an automatic rollback.

## 7. Why Is `@Transactional(REQUIRED)` Not Enough When Writing to the DB After Commit?

A common mistake is assuming that if a post-commit listener simply calls a repository with default `@Transactional`, Spring will automatically open a new transaction:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onCommitted(OrderPlaced event) {
    auditRepository.save(...);
}
```

This is an illustrative snippet, not a standalone program. After commit, resources such as a JDBC `Connection`/JPA persistence context may **still be bound to the thread** until cleanup. Spring's Javadoc warns that DB-accessing code at this moment can participate in the old transaction resources while **no commit follows**, so the new write **is not saved as expected**.

To require a new DB commit, use:

```java
@Service
public class AuditWriter {

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void record(String orderId, String errorMessage) {
        // Insert audit row / update retry status.
    }
}
```

This is illustrative code. Call `auditWriter.record(...)` **through another Spring-managed bean** so it goes through the transaction proxy. `REQUIRES_NEW` creates an independent physical transaction that commits or rolls back on its own. Do not use `this.record(...)` inside the same bean if using default proxy mode: self-invocation bypasses transactional advice.

A programmatic equivalent is a `TransactionTemplate` configured with `TransactionDefinition.PROPAGATION_REQUIRES_NEW`. This is useful when you want explicit transaction control from a callback without needing a separate proxy.

**Important:** If the listener runs after T1 finishes but before resource cleanup, `REQUIRES_NEW` may need another JDBC connection. Production connection pools must be sized for concurrency; do not treat opening a new transaction as free.

## 8. Is Catching Exceptions in the Listener Enough to Guarantee Work Is Never Lost?

**No.** `try/catch` only lets you decide **what to do at the moment the error appears**. It does not itself guarantee that the error will be persisted, the task will be retried, or the process will stay alive long enough to handle it.

Appropriate pattern for best-effort post-commit work:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void handle(OrderPlaced event) {
    try {
        mailClient.sendOrderConfirmation(event.orderId());
    } catch (RuntimeException ex) {
        metrics.counter("order.notification.failed").increment();
        log.error("Notification failed for order {}", event.orderId(), ex);
    }
}
```

This is an illustrative code snippet; `mailClient`, `metrics`, and `log` are application dependencies. It provides **observability** into failures without creating a work record for recovery. If the listener swallows the exception without logs/metrics, failures become invisible.

Pattern that persists a retry request after an error:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void handle(OrderPlaced event) {
    try {
        mailClient.sendOrderConfirmation(event.orderId());
    } catch (RuntimeException ex) {
        retryWriter.recordForRetry(
                event.orderId(), ex.getClass().getSimpleName());
    }
}
```

This is also illustrative code; `retryWriter` is **another bean** with `@Transactional(REQUIRES_NEW)`, used to persist the work needing retry. In addition, a worker is needed to read the retry table, re-execute with backoff, mark success/failure, and avoid duplicate processing.

**A failure window still exists:** If the JVM dies after T1 commits but before the listener or `retryWriter` runs, **there is no retry record**. Thus, the catch-and-T2 pattern **only improves recoverability when the error is actually observed**, and does not protect against lost work in all scenarios.

## 9. Transactional Outbox: When Post-Commit Failures Must Not Lose Tasks

For critical work (sending legal notifications, accounting sync, publishing events to a broker, invoicing), the main transaction must commit together with **the intent to perform the work**. A common approach is the **transactional outbox**:

```text
BEGIN transaction T1
  |
  +-- INSERT order
  +-- INSERT outbox(orderId, eventId, payload, status=NEW)
  |
COMMIT T1
  |
  +-- separate worker reads committed outbox
       |
       +-- call email / broker / external service
       |
       +-- success -> mark DONE
       +-- failure -> store retry_count, next_attempt_at
       |
       +-- retry with backoff, idempotency, and dead-letter
```

The outbox guarantees that **the business record and the follow-up work record** commit or roll back together. When the process dies after commit, a worker can still resume from the outbox record. This mechanism does not automatically guarantee exactly-once delivery; the external system may already have received the side effect before the worker marks `DONE`, so retries can send duplicates.

Design requirements:

- `eventId`/idempotency key sent with requests if supported by the external system.
- Unique constraint or processed state to avoid creating duplicate tasks.
- Retry only transient errors; use backoff and attempt limits.
- Dead-letter/quarantine for configuration errors or invalid payloads.
- Monitoring of pending/failed counts, oldest task age, latency, and retry rate.
- Strategy for when the external system succeeds but updating local status fails.

**Outbox differs from `@TransactionalEventListener(AFTER_COMMIT)`**: the callback only schedules in-process execution; an outbox has a **committed DB record** to recover across crashes. Both can be combined (the callback nudges the worker to process early), but the worker must still read the durable outbox rather than treating the callback as the source of truth.

## 10. Do Not Retry the Entire Service Just Because of a Post-Commit Error

Suppose T1 committed `orders(O-7)` but sending the email failed. If the system calls again:

```java
orderService.place("O-7");
```

you may hit a duplicate key error or create a second order if IDs are newly generated. Even if the service is idempotent, other side effects may repeat.

**Retry the failed task**, do not blindly retry the original command. Example:

```text
Order service: COMMITTED order O-7
Notification: FAILED to send for O-7

Retry target:
  sendNotification(orderId="O-7", notificationId="...")
not:
  createOrderAgain(...)
```

When designing APIs:

- Separate the state of **order created** from **notification pending/sent/failed**.
- If the API returns 200 after T1 commits, do not promise the notification has already been sent unless there is proof of completion.
- If the API must reflect secondary status, return or expose an explicit async state (e.g., `notificationStatus=PENDING`), rather than turning a committed transaction into "transaction failed."
- If a direct `TransactionSynchronization.afterCommit()` callback throws an exception causing the request to report an error, the caller still needs idempotency and to distinguish actual DB state before retrying.
- Use a correlation ID linking request, transaction, outbox task, and external request.

Resending an email/HTTP call may succeed on the external system while the client hits a timeout. When retrying, use an idempotency key or check state to avoid duplicate sends.

## 11. `@Async` Changes the Exception Path

A listener can be both async and transaction-bound:

```java
@Async("notificationExecutor")
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void handle(OrderPlaced event) {
    mailClient.sendOrderConfirmation(event.orderId());
}
```

This is an illustrative snippet, requiring `@EnableAsync`, an appropriate executor bean, and a Spring-managed listener. Spring registers the transaction callback on the publisher thread; after commit, async advice can offload execution to a worker thread.

When a `void` async listener throws an exception:

- The exception occurs on the **worker thread**, not on the publisher's original call stack.
- `AsyncUncaughtExceptionHandler` or logging is the usual observability channel for uncaught exceptions.
- It does not automatically propagate back to the original transaction to roll back.
- You should not expect `TransactionSynchronization.afterCompletion` to catch exceptions occurring **after** the executor accepts the task; the transaction callback may already have finished scheduling.
- Executor rejection **at submission time** is also an error type that needs separate monitoring.
- The worker thread does not automatically inherit the publisher's JDBC/JPA transaction. If writing to the DB from the worker, open an appropriate transaction in a proxied service.
- `@Async` does not make events durable; tasks can be lost on shutdown/crash without a persistent queue.

Example of configuring an async error handler (illustrative code):

```java
@Configuration
@EnableAsync
public class AsyncErrorConfig implements AsyncConfigurer {

    @Override
    public AsyncUncaughtExceptionHandler
            getAsyncUncaughtExceptionHandler() {
        return (error, method, args) ->
                System.err.println(
                        "async failure: " + method.getName()
                                + ": " + error.getMessage());
    }
}
```

Requires imports for `Configuration`, `EnableAsync`, `AsyncConfigurer`, and `AsyncUncaughtExceptionHandler`. In production, replace `System.err` with structured logs, metrics, tracing, and controlled recovery.

**Be careful with error naming:** "listener failed after commit" can refer to an exception in a **synchronous callback** or an exception in an **async worker** scheduled after commit. Both error-reporting paths differ, yet neither **can roll back T1's already committed data**.

## 12. The Listener Might Not Run at All Without a Transaction

`@TransactionalEventListener` defaults to `AFTER_COMMIT`, but it only registers with a transaction when the event is published in an appropriate transaction context. When there is no transaction:

- Default `fallbackExecution=false`: the listener **is skipped**.
- `fallbackExecution=true`: the listener can run via a fallback path **not bound to a real commit**.

Example:

```java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT,
        fallbackExecution = true)
public void handle(OrderPlaced event) {
    // May run without a transaction.
}
```

This is illustrative code, not complete code. If a listener runs via fallback while **there is no transaction**, do not continue assuming its exceptions are handled identically to a real transaction's `afterCompletion(STATUS_COMMITTED)`. Therefore, tests must distinguish these two paths.

Common reasons an event appears to be inside a transaction when it is actually not:

- Calling a `@Transactional` method from the same bean via `this.method()`, bypassing the transaction proxy.
- Creating a bean via `new` instead of having Spring manage it.
- Publishing an event from another async thread before commit: the new thread does not automatically inherit the imperative transaction context.
- A test that has not actually committed or is using the wrong transaction manager.

For reactive applications, transactions live in the Reactor Context; use the publisher/context APIs per Spring reactive documentation instead of assuming `ThreadLocal`.

## 13. Testing and Verifying Post-Commit Exceptions

### 13.1. Tests You Should Have

1. **T1 commits, listener throws exception:** verify the order still exists in the DB after the call.
2. **Caller observation:** with a standard `@TransactionalEventListener(AFTER_COMMIT)` listener, verify the caller can complete normally even though the framework logs an error in the completion callback; do not assert on overly specific log message strings.
3. **Direct `afterCommit()` callback:** verify the exception can propagate to the caller while T1 still commits. Do not confuse the two APIs.
4. **T1 rolls back before commit:** the `AFTER_COMMIT` listener does not run.
5. **Listener catches error:** when the handler catches the exception and calls `REQUIRES_NEW`, the failure record commits independently.
6. **Error while writing audit T2:** rolls back T2; verify T1 remained committed and the system tracks audit failures.
7. **Async listener:** use `CountDownLatch`/future/Awaitility with timeouts to wait; do not rely on arbitrary `Thread.sleep()`.
8. **No transaction / fallback:** verify `fallbackExecution=false` skips the event; test `fallbackExecution=true` separately.
9. **Process crash / retry:** integration test the outbox to verify the worker recovers unprocessed work after restart.
10. **Idempotency:** replay the same event; do not create duplicate audit/notification records or new orders.

### 13.2. Avoiding `@Transactional` Tests That Only Auto-Rollback

In Spring Test, a `@Transactional` test method is typically rolled back at the end of the test by default. If a test publishes an event inside a transaction and asserts right after publishing, `AFTER_COMMIT` **has not run yet**; if the test transaction ultimately rolls back, the listener **never runs**.

You can use `TestTransaction.flagForCommit()` and `TestTransaction.end()` inside a Spring-managed transactional test to explicitly commit before asserting:

```java
TestTransaction.flagForCommit();
TestTransaction.end();

// After commit, check the DB and post-commit results.
```

This is an **illustrative snippet**, requiring Spring Test and importing `org.springframework.test.context.transaction.TestTransaction`. Alternatively, write an integration test without wrapping the test method in a default transaction, letting your service call commit on its own before asserting.

**Right evidence:** inspect persisted data in the database / observe task status, rather than relying solely on log exceptions, method return values, or a boolean variable sitting on another thread.

## 14. Common Mistakes and Fixes

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `AFTER_COMMIT` listener throws an exception yet the order still exists | Transaction T1 already committed before the callback ran | This is the intended semantics; handle post-commit errors as independent work |
| Caller does not receive an exception despite a stack trace in logs | Handler ran via `afterCompletion(STATUS_COMMITTED)`; exception was logged in the callback helper | Use metrics/retry/task status rather than relying on caller exceptions |
| Custom `afterCommit()` callback causes request error yet DB has record | Direct callback propagates exceptions after commit | Read actual state and design idempotency; do not retry blindly |
| Audit written in listener does not persist in DB | Old transaction resources still bound, no new commit | Call a `@Transactional(REQUIRES_NEW)` bean or equivalent `TransactionTemplate` |
| `REQUIRES_NEW` has no effect | Self-invocation via `this`, bean not proxied | Extract service into an injected Spring bean |
| `AFTER_COMMIT` listener does not run | Event not published inside a transaction or T1 rolled back | Verify real transaction and default `fallbackExecution=false` |
| Async listener fails without publisher knowing | Error occurred on executor thread | `AsyncUncaughtExceptionHandler`, logs, metrics, and persistent retry |
| `catch` error yet notification still lost after crash | Work not persisted alongside T1 | Transactional outbox or durable queue |
| Email sent twice on retry | Missing idempotency key | Deduplicate by event ID/notification ID |
| Worker does not complete after restart | Used only in-memory Application Events | Persisted outbox/task store and checkpointed worker |
| Test does not receive after-commit event | Test transaction not committed yet or auto-rolled back | Explicitly commit/end test transaction before assertion |
| Connection exhaustion when T2 writes audit | `REQUIRES_NEW` may need an independent connection | Size connection pool, concurrency, and timeouts |

## 15. After-Commit Listener Design Checklist

Before implementing a post-commit task, answer:

- **At what point did T1 commit?** Understand that `@TransactionalEventListener(AFTER_COMMIT)` does not run in a transaction that can still roll back.
- **Who sees the exception?** Standard `@TransactionalEventListener(AFTER_COMMIT)` differs from a direct `TransactionSynchronization.afterCommit()` callback.
- **Is T1's success independent of the post-commit side effect?** If yes, represent separate statuses such as `PENDING`, `SUCCEEDED`, `FAILED`.
- **Where should errors be stored?** If writing to the DB after commit, open a new transaction using `REQUIRES_NEW`.
- **What if the process dies after T1 commits?** If work must not be lost, write an outbox record inside T1 itself and process via a durable worker.
- **Is retry safe?** Retry the **failed side effect**, do not blindly repeat the committed command; include an idempotency key.
- **Does the listener run sync or async?** Exception policy, threading, executor, backpressure, and shutdown must match.
- **Have tests verified the real DB?** Do not check only logs or caller exceptions.

**Conclusion:** An exception in a post-commit listener **cannot roll back an already committed transaction**. Specifically with `@TransactionalEventListener(AFTER_COMMIT)` in imperative Spring Framework, errors raised through the completion callback are typically logged without **propagating back to the caller**, whereas a direct `TransactionSynchronization.afterCommit()` callback has a different propagation mechanism. Manage post-commit work as an **independent step with state, error observability, its own transaction, and a recovery mechanism**, rather than attempting to apply rollback or retry the entire original business operation.

## Official References

- [Spring Framework 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [Spring Framework — `@TransactionalEventListener` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
- [Spring Framework — `TransactionSynchronization.afterCommit()` and `afterCompletion()`](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html)
- [Spring Framework source — `TransactionalApplicationListenerSynchronization`](https://github.com/spring-projects/spring-framework/blob/v6.2.12/spring-tx/src/main/java/org/springframework/transaction/event/TransactionalApplicationListenerSynchronization.java)
- [Spring Framework source — `TransactionSynchronizationUtils`](https://github.com/spring-projects/spring-framework/blob/v6.2.12/spring-tx/src/main/java/org/springframework/transaction/support/TransactionSynchronizationUtils.java)
- [Spring Framework — Transaction Propagation and `REQUIRES_NEW`](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework — Rollback Rules](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/rolling-back.html)
