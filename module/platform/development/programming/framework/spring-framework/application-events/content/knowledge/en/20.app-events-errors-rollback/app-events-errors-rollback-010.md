# Recording Errors Without Masking the Root Cause in Spring Application Events

In systems using **Spring Framework Application Events**, an error can appear at the event publisher, an event listener, the transaction manager, the logging/metric step, or an external service called from a listener. **Recording errors without masking the root cause** means capturing enough information to diagnose the failure while preserving the **original exception, cause chain, and rollback decision** required by the business logic.

The danger is not merely "forgetting to log an error," but also flawed recording patterns that let a secondary error (such as a telemetry outage) replace the primary cause (such as insufficient inventory), or cause a transaction to **commit successfully even though a mandatory listener failed**.

Lesson objectives:

- Distinguish the **initial business failure** from **failures raised while observing/recording**.
- Understand how exceptions travel through `ApplicationEventPublisher`, `@EventListener`, `@TransactionalEventListener`, synchronous/asynchronous multicasters, and transactions.
- Preserve the original exception when logging, enriching context, translating to another business exception, or handling multiple errors at once.
- Design observability, retries, and post-commit processing without **misstating data state**.
- Verify with a runnable Java 17+ example using Spring Framework, Spring JDBC, and H2.

## 1. Error Categories to Distinguish

Consider placing an order:

```text
OrderService.placeOrder()
  |
  +-- INSERT order (transaction T1)
  +-- publishEvent(OrderSubmitted)
          |
          +-- InventoryListener
          |     +-- check inventory
          |     +-- may throw InventoryUnavailable
          |
          +-- AuditListener / Logger / Telemetry
                +-- may fail due to lost connection
  |
  +-- COMMIT or ROLLBACK T1 (depending on flow and configuration)
```

A **primary/root failure** is the error that prevents a request from fulfilling its business contract, such as `InventoryUnavailableException` from an inventory check. A **secondary failure** is an error occurring *while handling or recording the primary failure*, such as a metrics backend disconnect. If the primary exception is lost, logs show only "Metrics unavailable" and operators investigate the wrong direction.

An exception can carry several pieces of information:

| Element | Why preserve it |
| --- | --- |
| **Exception type** | Classify the error and apply proper retry/rollback rules |
| **Message** | Describe the specific meaning; avoid logging secrets |
| **Stack trace** | Where the failure actually originated |
| **`getCause()` chain** | Underlying cause of a higher-level wrapper exception |
| **`getSuppressed()`** | Secondary failures that must not replace the primary |
| **Event context** | `eventId`, `orderId`, `eventType`, listener name, transaction phase, attempt |
| **Outcome** | Transaction commit/rollback, listener success/failure, message delivery status |

Two guiding principles:

1. **Never replace the root cause with a logging/observability failure.** If you must also report a secondary failure, attach it without destroying the primary.
2. **Never alter business decisions just to get clean logs.** If a listener failure must roll back the transaction, do not swallow the exception to make the request look successful.

## 2. How Do Exceptions Travel Through the Spring Event Bus?

### 2.1. Default Synchronous Listener

`ApplicationEventPublisher.publishEvent(...)` is not a durable message queue. With the default `SimpleApplicationEventMulticaster`, listeners are called **on the publisher's thread** unless another executor is configured. By default there is **no `ErrorHandler`**: a RuntimeException from a listener can halt the current multicast pass and **propagate back to the publish call**.

```java
@Component
class StockListener {
    @EventListener
    public void onOrderSubmitted(OrderSubmitted event) {
        throw new IllegalStateException("Inventory unavailable");
    }
}
```

This is **illustrative skeleton code**, assuming `OrderSubmitted` is a valid event class and the listener is discovered by Spring. When the publisher is inside a `@Transactional` method, an uncaught exception can escape the service, triggering rollback by default if it is a `RuntimeException` or `Error`.

**Ordering note:** there is no guarantee remaining listeners will be invoked if a synchronous listener throws an exception. Exception handling is part of the multicaster's behavior; do not assume "publishing an event" means "every listener received and finished processing it."

### 2.2. Catching Only to Log and **Rethrowing the Same Exception**

```java
try {
    applicationEventPublisher.publishEvent(event);
} catch (RuntimeException original) {
    log.error("Failed to publish eventId={}, orderId={}",
            event.eventId(), event.orderId(), original);
    throw original;
}
```

This is an **illustrative snippet**: the application must supply `applicationEventPublisher`, `event`, and logger `log`. Pass `original` as the exception parameter so the logging system records the stack trace. The `throw original` statement does not create a new error that loses context; it preserves the original exception object. In environments requiring rollback, the root cause still propagates out to the transaction interceptor.

However, if logging or telemetry itself can throw an exception, the snippet above can still be replaced by a secondary failure. For an unreliable reporter, isolate it as in Section 4.

### 2.3. Catching and **Swallowing the Error** Changes Transaction Behavior

**Dangerous pattern:**

```java
@Transactional
public void placeOrder() {
    repository.save(order);
    try {
        applicationEventPublisher.publishEvent(new OrderSubmitted(order.getId()));
    } catch (Exception ex) {
        log.error("Event listener failed", ex);
        // Do not throw, do not mark rollback-only.
    }
    // Method can return normally -> transaction may COMMIT.
}
```

This is **intentionally flawed illustrative code**, not a standalone runnable class. If business rules require the inventory-check listener to succeed before commit, catching the error this way hides the failure and may allow persisting an invalid order.

There are valid **best-effort** cases that should not affect the transaction (such as a non-critical metric), yet those must be decided at the business-contract level with dedicated failure tracking. Never label a critical invariant check "best-effort" just to avoid rollback.

## 3. Preserving `cause`, `suppressed`, and Stack Trace

### 3.1. If Wrapping an Exception, Always Keep `cause`

Avoid:

```java
catch (IOException ex) {
    throw new IllegalStateException("Cannot send notification");
}
```

Details about `IOException`, the network stack trace, and nested causes have vanished from the new exception.

Prefer:

```java
catch (IOException ex) {
    throw new IllegalStateException("Cannot send notification", ex);
}
```

`getCause()` will point to the original `IOException`. Wrapping an exception makes sense when crossing an **abstraction boundary**: for instance, from raw Java I/O errors to named application errors. Avoid wrapping the same exception at every method layer if doing so only produces repetitive messages.

### 3.2. If the Recorder Also Fails, Use Suppressed for Secondary Errors

```java
RuntimeException primary = ...;  // Business error to preserve.
try {
    failureRecorder.record(primary);
} catch (RuntimeException reportingFailure) {
    if (reportingFailure != primary) {
        primary.addSuppressed(reportingFailure);
    }
}
throw primary;
```

This is **illustrative code**. It preserves `primary` itself so the transaction/caller layer can classify rollback properly. `reportingFailure` is attached to `primary.getSuppressed()`, so it is not "lost," yet it does not displace the root error.

Never call `addSuppressed(primary)` on `primary` itself: Java forbids self-suppression. For severe system errors (`VirtualMachineError`, critical resource exhaustion...), do not apply an overly broad `catch (Throwable)` policy just to keep logs tidy. Catch the error types the reporter can reasonably throw and preserve the JVM's fatal-error handling mechanisms.

### 3.3. Avoid Throwing New Exceptions Inside `finally`

Bad pattern:

```java
try {
    inventory.reserve(orderId);   // Throws error A.
} finally {
    auditStore.flush();            // If this throws error B, B masks error A.
}
```

The snippet above only illustrates the `finally` principle. If both operations fail, the exception from `finally` can replace the exception already propagating out. **Try-with-resources** in Java manages suppressed exceptions automatically for many resource-closing situations, making it generally better than hand-written `finally` blocks that easily mask errors.

If a critical manual cleanup step is mandatory, design it so cleanup failures are recorded/coordinated without arbitrarily replacing the business exception. Likewise, if cleanup is required to preserve data integrity, do not simply swallow it; surface both primary and secondary failures to an appropriate recovery mechanism.

### 3.4. Do Not Log the Same Stack Trace at Every Layer

If one exception is logged in the listener, the publisher, the service, and HTTP advice, it produces multiple copies of the same stack trace. That is not always "better recording." Designate a **primary error-reporting owner layer**; lower layers can add context when needed without pointlessly duplicating logs. If an error is rewrapped, keep its cause; if converted into an API response, do not leak sensitive stack trace details to clients.

## 4. Runnable Java 17+ Example: Telemetry Failure Does Not Mask Listener Error; Transaction Rolls Back

This example uses Spring Context, Spring JDBC, and H2. In the **correct scenario**, a synchronous listener throws `IllegalStateException`; application code tries to record the failure via telemetry, which also throws. The program attaches the telemetry error to **suppressed** and rethrows the listener's exception so `TransactionTemplate` rolls back the order record.

In the **intentionally flawed scenario**, the service swallows the same listener error; the transaction completes normally and the record commits. The result demonstrates that a log line is no substitute for propagation.

### 4.1. Directory Structure

```text
event-error-cause-demo/
├── pom.xml
└── src/main/java/EventErrorCauseDemo.java
```

### 4.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>event-error-cause-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.9</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.9</version>
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
                <version>3.5.1</version>
                <configuration>
                    <mainClass>EventErrorCauseDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 4.3. `src/main/java/EventErrorCauseDemo.java`

```java
import org.h2.jdbcx.JdbcDataSource;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.event.EventListener;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

public class EventErrorCauseDemo {

    public record OrderSubmitted(long id) {}

    public static final class InventoryListener {
        @EventListener
        public void onOrderSubmitted(OrderSubmitted event) {
            throw new IllegalStateException(
                    "inventory unavailable for order " + event.id());
        }
    }

    public static final class FailureRecorder {
        public void record(long orderId, RuntimeException primary) {
            // Simulate telemetry system encountering an outage.
            throw new IllegalStateException("telemetry offline");
        }
    }

    private static void reportWithoutMasking(
            long orderId,
            RuntimeException primary,
            FailureRecorder recorder) {

        System.out.println("record: order=" + orderId
                + " primary=" + primary.getMessage());

        try {
            recorder.record(orderId, primary);
        } catch (RuntimeException reportingFailure) {
            if (reportingFailure != primary) {
                primary.addSuppressed(reportingFailure);
            }
        }
    }

    private static int count(JdbcTemplate jdbc, long id) {
        Integer value = jdbc.queryForObject(
                "SELECT COUNT(*) FROM purchase_orders WHERE id = ?",
                Integer.class, id);
        return value == null ? 0 : value;
    }

    public static void main(String[] args) {
        var ds = new JdbcDataSource();
        ds.setURL("jdbc:h2:mem:error_cause_demo;DB_CLOSE_DELAY=-1");
        ds.setUser("sa");

        var jdbc = new JdbcTemplate(ds);
        jdbc.execute(
                "CREATE TABLE purchase_orders (id BIGINT PRIMARY KEY)");

        var tx = new TransactionTemplate(
                new DataSourceTransactionManager(ds));
        var recorder = new FailureRecorder();

        try (var context = new AnnotationConfigApplicationContext()) {
            context.registerBean(InventoryListener.class);
            context.refresh();

            // Correct scenario: primary is still thrown so transaction rolls back.
            try {
                tx.executeWithoutResult(status -> {
                    jdbc.update(
                            "INSERT INTO purchase_orders(id) VALUES (?)", 42L);

                    try {
                        context.publishEvent(new OrderSubmitted(42L));
                    } catch (RuntimeException primary) {
                        reportWithoutMasking(42L, primary, recorder);
                        throw primary;
                    }
                });
            } catch (IllegalStateException primary) {
                System.out.println(
                        "caller: primary=" + primary.getMessage());
                System.out.println(
                        "caller: suppressed="
                        + primary.getSuppressed()[0].getMessage());
            }

            System.out.println("database: order 42 count=" + count(jdbc, 42L));

            // Wrong scenario: exception is swallowed -> may commit.
            tx.executeWithoutResult(status -> {
                jdbc.update(
                        "INSERT INTO purchase_orders(id) VALUES (?)", 43L);

                try {
                    context.publishEvent(new OrderSubmitted(43L));
                } catch (IllegalStateException ignored) {
                    System.out.println(
                            "unsafe: swallowed=" + ignored.getMessage());
                    // ONLY TO ILLUSTRATE THE BUG: do not throw, do not mark rollback-only.
                }
            });

            System.out.println("database: order 43 count=" + count(jdbc, 43L));
        }
    }
}
```

Run in the project directory, with JDK 17+, Maven, and permission to download dependencies on the first run:

```bash
mvn -q compile exec:java
```

Lines printed by **the program**, in order (ignoring external Maven and framework logs):

```text
record: order=42 primary=inventory unavailable for order 42
caller: primary=inventory unavailable for order 42
caller: suppressed=telemetry offline
database: order 42 count=0
unsafe: swallowed=inventory unavailable for order 43
database: order 43 count=1
```

Analysis:

1. `InventoryListener` is a Spring bean with `@EventListener`; by default it is invoked synchronously when `context.publishEvent(...)` runs.
2. The listener call throws `IllegalStateException` for order `42`. `reportWithoutMasking(...)` prints the primary error info and attempts to record telemetry; telemetry also fails, but that exception is placed into `primary.getSuppressed()`.
3. `primary` itself is rethrown from the `TransactionTemplate` callback. Spring rolls back order `42`'s transaction, and the caller sees **the inventory error is still primary** while the telemetry error remains in suppressed.
4. For order `43`, the program intentionally swallows `IllegalStateException`. `TransactionTemplate` sees no error leave the callback, the transaction completes normally, and order `43` commits.
5. The demo uses `System.out` so stdout is deterministic; real applications use structured logging/tracing and avoid letting auxiliary reporters raise new errors. Use the `unsafe` branch only for learning and testing—**never apply it to business flows requiring a listener to succeed before commit**.

`TransactionTemplate` creates a real transaction on H2; `JdbcTemplate` and `DataSourceTransactionManager` share the same `DataSource`, so the `INSERT` belongs to the active transaction. Thus `count=0` and `count=1` reflect real database rollback and commit outcomes, not merely listener logs.

## 5. Multicaster `ErrorHandler`: Choosing "Log and Ignore" vs. "Log and Propagate"

`SimpleApplicationEventMulticaster` exposes `setErrorHandler(ErrorHandler)`. Under the default contract, with no handler, a synchronous listener exception propagates back to the publisher. When configuring an `ErrorHandler`, you must explicitly choose how to handle it.

Spring provides suggested handlers in `org.springframework.scheduling.support.TaskUtils`:

| Policy | Meaning | Risk / application |
| --- | --- | --- |
| **No ErrorHandler configured** | Synchronous listener exceptions propagate by default | Appropriate when mandatory listeners must drive rollback |
| `TaskUtils.LOG_AND_PROPAGATE_ERROR_HANDLER` | Logs error and keeps propagating | Useful when logging at multicaster while preserving propagation to publisher |
| `TaskUtils.LOG_AND_SUPPRESS_ERROR_HANDLER` | Logs and **suppresses** exception | Can hide errors from publisher; unsuitable for steps that must trigger rollback |

Illustrative configuration for a Spring application, **not an addition to the standalone program in Section 4**:

```java
@Configuration
class EventMulticasterConfiguration {

    @Bean(name = "applicationEventMulticaster")
    ApplicationEventMulticaster eventMulticaster() {
        SimpleApplicationEventMulticaster multicaster =
                new SimpleApplicationEventMulticaster();

        multicaster.setErrorHandler(
                TaskUtils.LOG_AND_PROPAGATE_ERROR_HANDLER);

        return multicaster;
    }
}
```

The snippet above requires imports for `@Configuration`, `@Bean`, `ApplicationEventMulticaster`, `SimpleApplicationEventMulticaster`, and `TaskUtils`. The bean name `applicationEventMulticaster` is the framework-recognized name used to dispatch Spring application events. When using Spring Boot, you do not need to define this configuration yourself unless you genuinely need to override the defaults.

**Do not choose `LOG_AND_SUPPRESS` just to clear errors off a dashboard.** It alters event propagation mechanics; a suppressed exception can allow a service transaction to proceed as if no error occurred. Explicitly distinguish mandatory listeners from best-effort listeners, and separate them architecturally if their error policies differ.

### Asynchronous Multicasters Behave Differently

If the multicaster is configured with a `TaskExecutor`, some listeners may run on the executor. Exceptions may go to the executor/error handler and **do not necessarily propagate back to the publisher** or stop other listeners from running. Absence of an exception on the publisher side **does not prove listeners succeeded**.

Nor should you assume every listener runs on the executor: some transaction-bound listeners declare that they do not support async multicasting and still run on the publishing thread to bind properly to the transaction. Always verify the exact listener type, multicaster setup, and API version.

## 6. `@Async`, `@TransactionalEventListener`, and Rollback Boundaries

### 6.1. `@Async` Listeners

An `@EventListener` method using `@Async` is processed via Spring's async mechanism when properly configured. An error in a listener on another thread **cannot by default roll back the publishing thread's transaction**. For `void` async methods, configure `AsyncUncaughtExceptionHandler`; for `Future`/`CompletableFuture`, errors must be observed via completion state. Never infer that listener errors were handled simply because `publishEvent(...)` returned.

When implementing asynchronous logging/tracing:

- Attach `eventId`, `aggregateId`, and `traceId` to the event or propagate context via supported mechanisms; do not assume MDC/`ThreadLocal` travels automatically to every executor.
- Log attempt count and listener name during retries.
- Do not use `Thread.sleep(...)` to "wait for listeners" in tests; use completion handles or latches/test support.
- Choose appropriate retry, dead-letter, or outbox mechanisms for events that must be processed durably.

### 6.2. Transaction-Phase-Bound Listeners

`@TransactionalEventListener` lets you pick phases:

| Phase | Timing | Error-recording caveats |
| --- | --- | --- |
| `BEFORE_COMMIT` | Before committing the source transaction | Appropriate RuntimeExceptions can fail the commit and trigger rollback |
| `AFTER_COMMIT` (default) | After successful commit | Record failure separately; **cannot roll back an already committed transaction** |
| `AFTER_ROLLBACK` | After the transaction rolls back | Record the rollback cause; avoid throwing new errors that mask the root cause |
| `AFTER_COMPLETION` | After completion regardless of commit/rollback | Observe outcome; cleanup/telemetry should avoid replacing primary failures |

Illustrative example independent of the JDBC demo in Section 4:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void sendNotification(OrderSubmitted event) {
    notificationGateway.send(event.id());
}
```

This snippet requires corresponding beans and imports. If sending the notification fails, the source transaction's order **is still committed**. Never catch the error and say "the order rolled back." Record a separate notification-delivery state, with retry/backoff or a Transactional Outbox if delivery must not be lost.

Specifically, post-completion transaction callbacks have their own rules for **logging/propagating exceptions**, so **you cannot apply a blanket conclusion** that "every exception from `@TransactionalEventListener` propagates back to the service." Check the phase and transaction manager. With `AFTER_COMMIT`, the commit outcome is already decided; whether an exception surfaces to the caller or only in logs, it does not change committed data.

### 6.3. `@Transactional` and Checked Exceptions

Under Spring's default declarative transaction rules, `RuntimeException` and `Error` trigger rollback, while **checked exceptions normally do not** (unless configured via rollback rules). You can use `rollbackFor`, `noRollbackFor`, or global rule configuration where appropriate.

Example:

```java
@Transactional(rollbackFor = IOException.class)
public void process() throws IOException {
    // If IOException escapes transaction boundary -> rollback.
}
```

This is **illustrative code**. Not every `Exception` type has the same rollback behavior. If you wrap an `IOException` inside an `IllegalStateException` with a cause, understand that you may change rollback classification at the transaction layer; do so intentionally, not merely to write a log message.

## 7. Log Enough to Investigate Without Leaking Data

A useful error record should have a **stable structure** and sufficient context:

```text
level=ERROR
component=OrderEventListener
eventType=OrderSubmitted
eventId=evt-5d1...
aggregateId=order-42
phase=BEFORE_COMMIT
operation=reserveInventory
outcome=failed
exceptionType=InventoryUnavailableException
message="inventory unavailable"
traceId=<trace identifier, if any>
```

These values **only illustrate the format**, not output from the Java example. In production logs, you should:

1. Store **the stack trace of the primary exception** or an error-tracking system linked to it; logging only `ex.getMessage()` is usually insufficient.
2. Log only necessary identifiers such as event ID, aggregate ID, listener name, transaction phase, attempt, and trace ID. Avoid logging full payloads containing PII, tokens, passwords, or payment card data.
3. Distinguish **event published**, **listener succeeded**, **transaction committed**, and **message sent to external system** — those are distinct states.
4. Use structured logging/tracing to attach correlation without altering exception types. With async, verify context propagation across the executor instead of assuming thread-locals are present.
5. Assign **primary logging responsibility** to the layer that decided how to handle the error; other layers can enrich context without endlessly repeating the same stack trace.
6. For critical failures, do not rely solely on volatile logs: use durable state, outboxes, retries, or alerting systems per SLA requirements.

Example preserving the cause chain in a logger:

```java
try {
    orderService.placeOrder(command);
} catch (InventoryUnavailableException ex) {
    log.error("Cannot place order, orderId={}, eventId={}",
            command.orderId(), command.eventId(), ex);
    throw ex;
}
```

The snippet above is **illustrative code**, depending on application classes and a configured logger. The final parameter is the exception, preserving the stack trace; `throw ex` leaves the original exception intact. When constructing error responses, use stable business error codes rather than copying raw stack traces into public responses.

## 8. Handling Multiple Listeners: Do Not Fake "Partial Success" by Swallowing Errors

If an event has multiple listeners:

```text
publish(OrderSubmitted)
    |
    +-- ValidateInventory      (mandatory)
    +-- UpdateSearchIndex      (best-effort/async)
    +-- SendConfirmationEmail  (after commit)
    +-- RecordMetric           (best-effort)
```

Using the same error policy for all four listeners can produce wrong results:

- The **mandatory** `ValidateInventory` step should live inside an explicit business transaction, or better yet be called directly in the use case before commit if you do not want to depend on listener ordering. If it fails, the transaction must see the exception/rollback-only state.
- `RecordMetric` must not fail the transaction merely because the metrics backend erred; it can catch and record on a best-effort basis, explicitly and with a circuit breaker if needed.
- `SendConfirmationEmail` should run after commit or via an outbox; an email error **cannot reverse** a committed order.
- `UpdateSearchIndex` can usually be retried or rebuilt from source data; define separate observability criteria for sync lag.

If you need "dispatch to all listeners, collect all errors, and then decide on rollback," the default multicaster **does not automatically provide such an error-aggregation contract**. You need an explicit orchestrator that records each failure and decides whether to throw an aggregate exception or mark rollback-only. Do not configure `LOG_AND_SUPPRESS` and assume it is a complete error-handling mechanism.

## 9. Retries, Idempotency, and Not Equating Errors With Rollback

An error being logged **does not mean** the work will be retried. With in-JVM events, if the process stops after commit before a post-commit callback finishes, a side effect can be lost. If retried carelessly, the side effect can also execute multiple times.

For business operations requiring guaranteed recoverability:

1. Write business data and an **outbox message** in the same transaction.
2. After commit, an independent worker reads the outbox to deliver the event.
3. If delivery fails, record attempt count, structured error, and next retry time; do not replace the original event with the communication error.
4. Consumers process idempotently using event IDs or business keys to stay safe against duplicate delivery.
5. Configure alerts when retry budgets are exceeded, dead-lettered, or processing deadlines pass.

Example of separate statuses:

```text
ORDER: COMMITTED
OUTBOX: PENDING / RETRYING / SENT / DEAD_LETTER
LAST_ERROR: ExternalServiceTimeout (cause preserved)
ATTEMPT: 3
NEXT_RETRY_AT: ...
```

Do not return a "order rolled back" message to the client just because `OUTBOX=RETRYING`. Source transaction state and auxiliary event-processing state are two independent axes.

In distributed workflows, **compensation** is sometimes needed for an already committed step. Compensation is **a new business action**, not a technical rollback of the old transaction. When compensation fails, preserve both the original cause and the compensation failure for investigation.

## 10. Real-World Incident Handling Workflow

When receiving a report that "event was published yet system state is wrong," proceed in order:

1. **Identify the source transaction.** Was the event published inside or outside a transaction? Pre-commit, post-commit, or async?
2. **Identify which listeners actually received the event.** Check event types, `@EventListener` conditions, `@TransactionalEventListener` phases, and `fallbackExecution`; do not infer from publisher logs.
3. **Collect the primary exception.** Capture type, message, cause chain, stack trace, suppressed exceptions, and event context; do not look only at the last error in the logs.
4. **Inspect multicaster configuration.** Is there a custom `ErrorHandler`? A `TaskExecutor`? Is `LOG_AND_SUPPRESS` or `@Async` used?
5. **Cross-check database state.** Query from an independent connection/transaction to confirm commit/rollback; HTTP 500 or a listener error does not prove rollback by itself.
6. **Evaluate secondary failures.** Did monitoring/logging, cleanup, notification, or retry fail as well? Are they masking or replacing the root cause?
7. **Recover at the right layer.** If the source transaction rolled back, handle the original request; if the source transaction committed while a side effect failed, use retry/outbox/compensation per contract.
8. **Add regression tests.** Cover reporter failures, listener failures, async listeners, and commit/rollback timing.

Easily searchable logs help, yet **transaction state verified in the database** is the true evidence for commit/rollback conclusions.

## 11. Testing Critical Scenarios

| Scenario | Expectation | Verification |
| --- | --- | --- |
| Synchronous listener throws `RuntimeException`, uncaught | Exception escapes publisher; source transaction can roll back per policy | Error type and actual data |
| Listener failure + telemetry failure | Primary preserved; secondary resides in suppressed or equivalent structure | `getMessage()`, `getSuppressed()`, stack trace |
| Service catches and swallows listener error | Transaction can commit if not marked rollback-only | Prove via DB query |
| Using multicaster `LOG_AND_SUPPRESS` | Publisher may not receive exception | Test rollback policy instead of only logs |
| Using `LOG_AND_PROPAGATE` | Sync publisher still sees the error | Test exception type and cause |
| `@Async` listener throws | Publisher does not roll back by default since error is on another thread | Handler/completion/error metrics |
| `AFTER_COMMIT` listener throws | Source transaction already committed; handle side-effect failure separately | DB state and retry/outbox |
| Reporter throws from `finally` | Risk of masking prior exception | Test primary stack/cause |
| Checked exception escapes `@Transactional` | Default behavior differs from unchecked | Test `rollbackFor`/actual policy |
| Retries / dual delivery | Non-idempotent side effect is not executed twice | Event ID, inbox/dedup state |

**Testing strategy:** One test uses a real Spring Context + transaction manager like the Section 4 example; another can use a mock reporter to force secondary failures. To verify a propagating error handler, configure the multicaster deliberately and assert exception types. For async, use `CompletableFuture`/latches or a controllable test executor rather than fixed sleeps.

### JUnit 5 Example: Explicitly Verifying Preservation of the Root Error

The snippet below is **illustrative integration code**, requiring a test class, fixtures, and corresponding Maven/JUnit setup:

```java
@Test
void preservesOriginalFailureWhenTelemetryFails() {
    IllegalStateException primary =
            new IllegalStateException("inventory unavailable");

    RuntimeException telemetry =
            new RuntimeException("metrics unavailable");

    try {
        primary.addSuppressed(telemetry);
        throw primary;
    } catch (IllegalStateException caught) {
        assertSame(primary, caught);
        assertEquals("inventory unavailable", caught.getMessage());
        assertSame(telemetry, caught.getSuppressed()[0]);
    }
}
```

This test does not replace a rollback integration test; it only proves the **exception management choice**. An integration test must verify database state after the transaction finishes.

## 12. Self-Assessment Questions

**1. Why can catching, logging, and not throwing be dangerous inside `@Transactional`?**  
Because the transaction interceptor may see the method complete normally and commit changes that ought to have rolled back. If the failure is best-effort, document that decision explicitly; if mandatory, propagate or mark rollback-only per policy.

**2. If telemetry also fails while logging a listener error, how do you avoid masking the listener error?**  
Keep the primary exception object, handle the telemetry failure separately and attach it via `primary.addSuppressed(...)` where appropriate, then rethrow primary.

**3. What is the difference between `new RuntimeException("message")` and `new RuntimeException("message", cause)`?**  
The second constructor preserves the root cause in `getCause()`. The first can lose the causal chain when replacing an older exception.

**4. Does `SimpleApplicationEventMulticaster` always swallow listener exceptions automatically?**  
No. By default, synchronous listener exceptions propagate back to the publisher; custom handlers or executors can change this behavior.

**5. Can an `AFTER_COMMIT` listener throwing an error roll back an already committed transaction?**  
No. Separate processing status and retry/compensation mechanisms are required if business rules demand them.

**6. Why is an HTTP 500 log insufficient proof of transaction rollback?**  
The request may have failed after commit, or the error occurred in an async listener, or the exception was suppressed by a handler. You must cross-check transaction outcomes and database data.

**7. Should you catch every `Throwable` so every error gets recorded?**  
Do not apply indiscriminately. Some `Error`s indicate severe JVM/resource failures; broad catches can disrupt emergency shutdown paths. Catch the right error types you are permitted to handle, preserve the primary failure, and never mask real failure state.

## 13. Official Documentation

- [Spring Framework 6.2.9 — SimpleApplicationEventMulticaster, synchronous default and ErrorHandler](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring Framework 6.2 — Standard and Custom Events](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [Spring Framework 6.2 — Declarative Transaction Rollback Rules](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/rolling-back.html)
- [Spring Framework — Observability Support for Application Events](https://docs.spring.io/spring-framework/reference/integration/observability.html)
- [Java SE 17 — Throwable: cause and suppressed exceptions](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html)

