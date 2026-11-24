# ApplicationEventMulticaster ErrorHandler in Spring Framework

## 1. The Problem: When One Listener Fails, What Happens to the Remaining Listeners?

`ApplicationEventPublisher.publishEvent(...)` allows one component in a Spring application to publish an event so multiple independent listeners can react together. In the default configuration, Spring uses `SimpleApplicationEventMulticaster` to dispatch events **synchronously on the publisher's thread**. An important question arises when a listener throws an exception:

- Is the exception forwarded back to the caller of `publishEvent(...)`?
- Are the remaining listeners for the **same event** still called?
- Does the current transaction commit or roll back?
- Can the error be logged without breaking the core business flow?
- Does the handling change when using `@Async` or an executor for the multicaster?

`SimpleApplicationEventMulticaster.setErrorHandler(...)` is the configuration point for the policy of **handling errors raised while the multicaster invokes a listener**. The `org.springframework.util.ErrorHandler` interface has only one method:

~~~java
void handleError(Throwable t);
~~~

When a listener throws an error, the multicaster can hand that error off to the configured `ErrorHandler`. **If the handler returns normally, the error is considered handled at the multicast layer and other listeners get a chance to continue running. If the handler rethrows the exception, the exception continues propagating along the appropriate call path.**

**The impact on transactions is not decided solely by having an `ErrorHandler`.** It depends on the transaction manager, processing phase, exception type, `@Transactional` boundary, and whether the error ultimately escapes the transactional method. In particular, a handler that logs and swallows an error can allow the core transaction **to still commit even though a listener failed**.

## 2. Where Does ApplicationEventMulticaster Sit in the Processing Flow?

Involved components:

| Component | Role |
| --- | --- |
| `ApplicationEventPublisher` | API for publishing events from application code; `publishEvent` returns `void`. |
| `ApplicationEventMulticaster` | Infrastructure that dispatches events to matching `ApplicationListener` instances. |
| `SimpleApplicationEventMulticaster` | Default implementation, supporting a custom executor and `ErrorHandler`. |
| `ApplicationListener<E>` | Interface-based listener, receiving events via `onApplicationEvent(E)`. |
| `@EventListener` | Annotation marking a listener method; Spring registers an adapter so the method participates in the multicaster. |
| `ErrorHandler` | `handleError(Throwable)` callback for errors occurring while a listener is invoked by the multicaster. |
| `TaskExecutor` | Can run certain listeners asynchronously if configured on the multicaster. |

Default diagram, **no ErrorHandler and no async**:

~~~text
OrderService
    |
    | publisher.publishEvent(OrderSubmitted)
    v
SimpleApplicationEventMulticaster
    |
    +--> listener A: succeeds
    |
    +--> listener B: throw IllegalStateException
    |           |
    |           +-- exception escapes listener
    |
    X--> listener C: not called in this multicast pass
    |
    v
publishEvent(...) throws exception to caller
~~~

The Javadoc of `SimpleApplicationEventMulticaster.setErrorHandler(...)` explicitly states that **by default there is no ErrorHandler**: an error from one listener stops the current multicast pass and is propagated back to the publisher. This is the default for the synchronous listener call path. If a dedicated executor is used, the exception may occur on the executor's thread, so you cannot expect the publisher to receive it by default.

When installing a **log and suppress** handler:

~~~text
OrderService
    |
    | publisher.publishEvent(OrderSubmitted)
    v
SimpleApplicationEventMulticaster
    |
    +--> listener A: succeeds
    |
    +--> listener B: throw IllegalStateException
    |           |
    |           v
    |       ErrorHandler.handleError(error)
    |           |
    |           +-- log/metric and DO NOT rethrow
    |
    +--> listener C: still called
    |
    v
publishEvent(...) can return normally
~~~

**This is not a retry mechanism.** The handler is called when an error occurs; Spring does not automatically re-invoke the failing listener, does not undo partially executed side effects, and does not automatically route the message to a dead-letter queue.

## 3. Common Error Policies: Propagate and Suppress

From a business perspective, there are two main behavior groups:

### 3.1. Propagate: Keep the Error in the Call Path

When there is no handler, or the handler rethrows the error:

- A listener throws an exception → synchronous event dispatch is interrupted at that error.
- The `publishEvent(...)` call can throw the exception to the caller.
- If this error escapes a `@Transactional` method and matches Spring's rollback rules, the transaction may be rolled back.
- Listeners invoked **before** the failing listener may already have produced side effects; do not assume everything can be rolled back.

An illustrative handler:

~~~java
multicaster.setErrorHandler(error -> {
    System.err.println("Listener failed: " + error.getMessage());
    if (error instanceof RuntimeException re) {
        throw re;
    }
    throw new IllegalStateException("Listener error", error);
});
~~~

*This is an illustrative configuration snippet, not a complete program. Use it only when you genuinely want to signal failure through the call path. An error in a listener or in the handler itself can prevent subsequent listeners from running.*

### 3.2. Suppress: Record the Error and Continue

When the handler does not rethrow:

- The multicaster continues processing the other listeners in that event dispatch pass, according to the current dispatch mechanism.
- The publisher **does not observe that error via an exception**.
- The enclosing transaction can proceed and commit, because the listener error no longer escapes to fail the transactional method.
- The designer must provide logging, metrics, alerting, or compensating processing; otherwise, business errors can be hidden.

~~~java
multicaster.setErrorHandler(error -> {
    // Illustration: record error and return normally.
    System.err.println("Listener error: " + error.getMessage());
});
~~~

You should not view `suppress` as "safer" in every case. For example, if a listener only records a secondary metric, logging and continuing may be reasonable; however, if a listener enforces a mandatory order invariant and gets suppressed, committing the primary data can leave the system inconsistent.

### 3.3. Spring's Two Sample Handlers

Spring provides sample strategies in `org.springframework.scheduling.support.TaskUtils`:

- `TaskUtils.LOG_AND_SUPPRESS_ERROR_HANDLER`: logs the error and handles it without propagating the exception.
- `TaskUtils.LOG_AND_PROPAGATE_ERROR_HANDLER`: logs the error and propagates the exception.

These two instances help clearly distinguish **logging** from **propagation**. Logging an error does not imply rollback; propagating the error to the caller or executor is what affects the execution flow and may trigger rollback rules.

## 4. Configuring the Multicaster Using the Standard Bean Name

An `ApplicationContext` has one multicaster by default. When you need to change the strategy, you can provide a bean with the exact name **`applicationEventMulticaster`**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.ApplicationEventMulticaster;
import org.springframework.context.event.SimpleApplicationEventMulticaster;

@Configuration
public class EventMulticasterConfig {

    @Bean(name = "applicationEventMulticaster")
    ApplicationEventMulticaster applicationEventMulticaster() {
        SimpleApplicationEventMulticaster multicaster =
                new SimpleApplicationEventMulticaster();

        multicaster.setErrorHandler(error -> {
            // Illustrative example: record and suppress.
            System.err.println("Event listener failed: " + error);
        });

        return multicaster;
    }
}
~~~

*This is a configuration class that can be integrated into a running Spring application. A complete, runnable Java 17+ example is in Section 5.*

**Important regarding bean name:** Spring looks up the multicaster by the name `applicationEventMulticaster` to use at the `ApplicationContext` level. If you name it `myMulticaster` without configuring additional integration mechanisms, you cannot rely solely on the bean having the right type to conclude it will replace the default multicaster.

Several points to consider:

- `setErrorHandler(...)` is a configuration method on **`SimpleApplicationEventMulticaster`**, not a method on the `ApplicationEventMulticaster` interface.
- `ErrorHandler` only receives `Throwable`; **it does not directly receive the event or the listener name**. If you want to log `eventId`, correlation ID, or the exact handler name, you need additional logging/tracing at the listener or an appropriate wrapper layer.
- A policy on the multicaster is context-wide and can affect **many different event types**, including framework-published events—not just a single business listener.
- You do not need to configure a `TaskExecutor` to use `ErrorHandler`. The default synchronous executor is the choice that helps learners clearly see the exception path.

## 5. Complete Runnable Example: Default vs. With ErrorHandler

This example uses **Java 17+, Maven, and Spring Framework 6.2.9**. We create two separate `AnnotationConfigApplicationContext` instances:

1. The first context does not declare an `ErrorHandler`. The second listener throws an error; the third listener does not run; the publisher catches the exception.
2. The second context declares a multicaster with a handler that logs and suppresses. The second listener still throws an error, but the handler handles it and the third listener is invoked.

No Spring Boot, web server, database, or executor configuration is needed, so the output printed by the code is deterministic.

### 5.1. Directory Structure

~~~text
multicaster-error-handler-demo/
├── pom.xml
└── src/main/java/EventErrorHandlerDemo.java
~~~

### 5.2. File pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>multicaster-error-handler-demo</artifactId>
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
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 5.3. File src/main/java/EventErrorHandlerDemo.java

~~~java
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.ApplicationEventMulticaster;
import org.springframework.context.event.EventListener;
import org.springframework.context.event.SimpleApplicationEventMulticaster;
import org.springframework.core.annotation.Order;

public class EventErrorHandlerDemo {

    public record OrderSubmitted(String id) {}

    public static class Listeners {

        @EventListener
        @Order(10)
        public void first(OrderSubmitted event) {
            System.out.println("listener-1: " + event.id());
        }

        @EventListener
        @Order(20)
        public void fails(OrderSubmitted event) {
            System.out.println("listener-2: throws");
            throw new IllegalStateException("simulated failure");
        }

        @EventListener
        @Order(30)
        public void last(OrderSubmitted event) {
            System.out.println("listener-3: " + event.id());
        }
    }

    // Case A: uses default multicaster, no ErrorHandler.
    @Configuration(proxyBeanMethods = false)
    public static class DefaultConfig {

        @Bean
        public Listeners listeners() {
            return new Listeners();
        }
    }

    // Case B: replaces multicaster with a bean of the standard name.
    @Configuration(proxyBeanMethods = false)
    public static class SuppressConfig {

        @Bean
        public Listeners listeners() {
            return new Listeners();
        }

        @Bean(name = "applicationEventMulticaster")
        public ApplicationEventMulticaster applicationEventMulticaster() {
            SimpleApplicationEventMulticaster multicaster =
                    new SimpleApplicationEventMulticaster();

            multicaster.setErrorHandler(error ->
                System.out.println("ErrorHandler: " + error.getMessage())
            );

            return multicaster;
        }
    }

    public static void main(String[] args) {
        System.out.println("=== DEFAULT ===");
        try (var context =
                new AnnotationConfigApplicationContext(DefaultConfig.class)) {
            try {
                context.publishEvent(new OrderSubmitted("ORD-7"));
                System.out.println("publisher: returned");
            } catch (IllegalStateException ex) {
                System.out.println("publisher: caught " + ex.getMessage());
            }
        }

        System.out.println("=== SUPPRESS ===");
        try (var context =
                new AnnotationConfigApplicationContext(SuppressConfig.class)) {
            context.publishEvent(new OrderSubmitted("ORD-8"));
            System.out.println("publisher: returned");
        }
    }
}
~~~

### 5.4. Compile and Run

In the directory containing `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=EventErrorHandlerDemo
~~~

Stdout printed by the program; excluding Maven output:

~~~text
=== DEFAULT ===
listener-1: ORD-7
listener-2: throws
publisher: caught simulated failure
=== SUPPRESS ===
listener-1: ORD-8
listener-2: throws
ErrorHandler: simulated failure
listener-3: ORD-8
publisher: returned
~~~

### 5.5. Step-by-Step Explanation

**DEFAULT Case:**

1. `context.publishEvent(new OrderSubmitted("ORD-7"))` hands the payload to the multicaster.
2. Spring invokes `@EventListener` methods according to the declared `@Order` values. `first` prints the order ID first.
3. `fails` prints its message and throws `IllegalStateException`.
4. With no ErrorHandler, the exception escapes the multicast pass to `publishEvent(...)` and is caught by `catch` in `main`.
5. `last` is not called because the multicast pass was aborted. There is no `listener-3` or `publisher: returned` line in the DEFAULT section.

**SUPPRESS Case:**

1. The context has a bean named `applicationEventMulticaster`, so it uses the configured multicaster.
2. The first two listeners still run; `fails` still throws `IllegalStateException`.
3. `ErrorHandler.handleError(Throwable)` is called, prints `ErrorHandler: simulated failure`, and **returns normally**.
4. The multicaster proceeds to invoke `last`, printing `listener-3: ORD-8`.
5. Since no exception propagates out of `publishEvent(...)`, `main` prints `publisher: returned`.

The example has no transaction, so **there is no commit/rollback in the two cases above**. Section 6 explains what changes if the publish call is inside a transactional method.

### 5.6. About @Order

Using `@Order(10)`, `@Order(20)`, and `@Order(30)` helps illustrate the order of listeners for the same event type under synchronous processing. Do not generalize that `@Order` guarantees a workflow across multiple threads, brokers, or async listeners will always complete in order.

## 6. Relationship Between ErrorHandler and Transaction Rollback

This is the most easily misunderstood point of the "Errors and Rollback" topic.

### 6.1. Publishing an Event Inside an Imperative Transaction

Suppose Spring is managing a JDBC/JPA transaction with `PlatformTransactionManager`:

~~~java
@Service
public class CheckoutService {

    private final OrderRepository repository;
    private final ApplicationEventPublisher events;

    public CheckoutService(OrderRepository repository,
                           ApplicationEventPublisher events) {
        this.repository = repository;
        this.events = events;
    }

    @Transactional
    public void checkout(Order order) {
        repository.save(order);              // Not necessarily committed yet.
        events.publishEvent(new OrderPlaced(order.getId()));
    }
}
~~~

*This is an illustrative integration snippet. `OrderRepository`, `Order`, and `OrderPlaced` are application-defined; imports for `@Service`, `@Transactional`, and `ApplicationEventPublisher` are required. This snippet is not standalone like the Section 5 example.*

If `OrderPlaced` is handled by a synchronous listener and a listener throws `IllegalStateException`:

| Scenario | Result for publisher | Possible transaction consequence |
| --- | --- | --- |
| No `ErrorHandler`; runtime exception escapes the `@Transactional` method | Publisher sees the exception. | Under default rollback rules for `RuntimeException`/`Error`, Spring usually rolls back the transaction. |
| Handler **propagates** the error further | Publisher sees the exception. | Usually similar to the row above, if the error escapes the transaction boundary. |
| Handler **suppresses** the error | Publisher can return normally. | The transactional method can complete and **commit** despite the listener failure. |
| Code calling the publisher **catches the exception** and continues | Exception does not necessarily escape the service. | Cannot conclude rollback for sure: it still depends on whether the transaction was already marked rollback-only and on business rules. |
| Listener runs on another thread | Publisher may not directly see the exception. | The original thread's transaction does not automatically roll back just because an external task throws an error. |

**Note:** certain resource operations inside a listener may already have marked the transaction `rollback-only`, even if the outer layer catches or suppresses the exception. In that case, commit can fail or throw `UnexpectedRollbackException`. Therefore, "suppress → definitely commits" is wrong; the accurate conclusion is only that **suppress stops pushing the listener's exception out to the caller**.

### 6.2. Do Side Effects That Occurred Before the Error Automatically Roll Back?

No universal conclusion can be drawn:

- Data writes through the same JDBC/JPA transaction can roll back with the transaction if boundaries and resource participation are right.
- Sending emails, HTTP requests, file writes, or publishing to a broker outside the DB transaction **do not automatically reverse** when the DB rolls back.
- A listener that completed before a subsequent listener threw an error may already have produced side effects in external systems.
- Catching and suppressing an exception does not automatically "recover" a failing listener or undo partially executed operations.

If atomicity across multiple data changes is needed, group the critical logic into the application service's transaction with intentional error handling. If reliable message delivery on successful commit is required, consider a **transactional outbox** rather than placing the entire responsibility on an internal event listener.

### 6.3. ErrorHandler Is Not a Transaction Manager

`ErrorHandler` decides **whether to let an error keep propagating** in the listener call path. It has no `commit`, `rollback`, or `setRollbackOnly` API; it does not automatically know the database state. Whether a transaction commits or rolls back is handled by `PlatformTransactionManager`/`ReactiveTransactionManager` coordinating with interceptors, resources, and rollback rules.

**Dangerous pattern:** using a global `ErrorHandler` to swallow errors from a listener responsible for enforcing a mandatory invariant (such as checking balance or preventing negative inventory). If failure must trigger a rollback, suppressing can break semantics. Move invariant checks into an explicit application service/transaction instead of designing them as an "optional listener".

## 7. AFTER_COMMIT, @TransactionalEventListener, and Error Timing

Spring provides `@TransactionalEventListener` to handle events by transaction phase:

- `BEFORE_COMMIT`: before commit.
- `AFTER_COMMIT`: after a successful commit.
- `AFTER_ROLLBACK`: after rollback.
- `AFTER_COMPLETION`: after commit or rollback.

Example:

~~~java
@Component
class AuditListener {

    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT)
    public void afterCommit(OrderPlaced event) {
        // Callback is executed after the transaction has committed.
        sendAuditMessage(event);
    }
}
~~~

*Illustrative snippet requiring imports for `@Component`, `@TransactionalEventListener`, and `TransactionPhase`. `sendAuditMessage` is a hypothetical business method.*

Here you must separate **two moments in time**:

1. When `publishEvent(...)` runs inside a transaction, Spring may only **register a transaction synchronization** for the listener.
2. After the transaction commits, the `AFTER_COMMIT` callback actually executes the event-handling code.

Therefore, **do not assume that `SimpleApplicationEventMulticaster.ErrorHandler` catches all exceptions raised in an AFTER_COMMIT callback**: the actual handling code runs in a phase managed by transaction synchronization, not necessarily inside the multicaster's listener invocation at publish time. Error policies for transaction-bound callbacks need to be designed and tested separately.

More importantly: **once committed, the original transaction cannot be rolled back** just because an `AFTER_COMMIT` listener failed. A post-commit exception may be logged or affect the caller flow at completion time depending on the mechanism, but it does not make the prior commit "unhappen".

If you need to update the DB in a post-commit callback, a new appropriate transaction is needed; if durable delivery is required, use an outbox/broker with retry and idempotency. Do not use `ErrorHandler` as a mechanism to guarantee post-commit event delivery.

## 8. What Changes When the Multicaster Has a TaskExecutor?

`SimpleApplicationEventMulticaster` also has the API:

~~~java
multicaster.setTaskExecutor(taskExecutor);
~~~

*This is an illustrative configuration snippet; `taskExecutor` is an `Executor`/`TaskExecutor` configured and managed by the application.*

If an asynchronous executor is set:

- Listeners **that support async execution** may be dispatched to an executor thread instead of running on the publisher thread.
- Listener exceptions occur inside the executor's task; they are **not necessarily** propagated back to the thread calling `publishEvent(...)`.
- The multicaster's `ErrorHandler` can still handle exceptions occurring within the listener invocation performed by the multicaster, but the handler's outcome is observed inside the executor task. Rethrowing goes to the executor/task error-handling mechanism rather than automatically returning to the caller.
- One failing listener does not necessarily stop listeners that were already submitted/running on other tasks.
- Thread-local transaction and logging contexts **are not automatically transferred intact** to another executor. Context propagation must be explicitly designed; avoid assuming the same transaction.
- **Not all listeners can be moved to async.** Some `ApplicationListener` implementations declare `supportsAsyncExecution() = false`, such as transaction-synchronized listeners, and must still run on the original thread to preserve appropriate constraints.

Comparison table:

| Aspect | Default synchronous multicaster | Multicaster with async executor |
| --- | --- | --- |
| Execution location | Publisher's thread. | Can be an executor thread for supported listeners. |
| ErrorHandler suppress | Usually proceeds to call the next listener. | Errors are handled per task; other tasks may already be running. |
| ErrorHandler rethrow | Can throw back to the publisher. | Can throw inside the executor; the publisher does not necessarily see it. |
| Completion order | Predictable in simple examples with `@Order`. | Should not rely on completion order. |
| Thread-local transaction | Synchronous listeners can see the active transaction. | Listeners on another thread do not automatically join that transaction. |
| Rollback on exception | Can occur if the exception escapes the boundary. | Does not automatically roll back the original thread's transaction due to an error in an async task. |

Do not use async merely to avoid exceptions propagating back to the publisher. Doing so also changes ordering, transaction context, error observability, and task lifecycle.

## 9. Distinguishing Multicaster ErrorHandler and @Async Exception Handling

There are two asynchronous mechanisms that are very easy to confuse:

### 9.1. Async Configured by the Multicaster

~~~java
SimpleApplicationEventMulticaster multicaster =
        new SimpleApplicationEventMulticaster();
multicaster.setTaskExecutor(executor);
multicaster.setErrorHandler(error -> report(error));
~~~

*Illustrative code snippet; `executor` and `report` are application-defined components.*

In this case, the multicaster is what **orchestrates invoking the listener** on the executor and can wrap the call with `ErrorHandler`. Still, the caller has no guarantee of receiving exceptions on the same thread.

### 9.2. Async on the @EventListener Method Itself

~~~java
@Async
@EventListener
public void sendNotification(OrderPlaced event) {
    notificationGateway.send(event.orderId());
}
~~~

*Illustrative snippet inside a Spring bean; requires `@EnableAsync`, imports for `@Async`/`@EventListener`, and an application-defined `notificationGateway`.*

Here, the multicaster invokes the listener method's adapter, while `@Async` offloads the actual execution to an executor via AOP. Exceptions occurring afterward **do not necessarily pass through the multicaster's `ErrorHandler`**.

For `@Async void` methods, Spring has `AsyncUncaughtExceptionHandler` to handle uncaught exceptions. If the method uses an appropriate return type such as `CompletableFuture`, errors can be represented by a failed future and handled wherever the future is observed. `@EventListener @Async` also does not support publishing follow-up events simply via a return value.

**Rule:** when investigating why "the handler didn't catch the error", first determine whether the exception occurred **inside the multicaster's listener invocation**, **inside the multicaster's task executor**, **inside a decoupled `@Async` invocation**, or **inside a post-commit callback**. Looking only at the annotation name is not enough to assert that an ErrorHandler will be invoked.

## 10. Choosing a Policy Based on Listener Criticality

A sound strategy is not always "log and suppress" or always "fail fast"; side effects must be classified:

| Type of work | Suggested policy |
| --- | --- |
| Mandatory pre-commit invariant check | Usually placed inside the application service/transaction so exceptions are governed by the rollback policy; do not use global suppress. |
| Mandatory data update in the same transaction | Execute within a clear boundary and propagate on failure if required by business logic. |
| Optional metrics or telemetry recording | Can be suppressed with monitoring, since a metric failure should not break core business logic. |
| Sending emails, webhooks, calling external systems | Consider outbox/queue + retry/idempotency; do not just suppress and assume successful delivery. |
| Building rebuildable projections | Can be processed/retried independently, provided there is a durable source event and replay capability. |
| Post-commit listener | Define an error policy for callbacks/workers; do not expect rollback of an already committed transaction. |

**Do not configure an ErrorHandler that "swallows every Throwable" in production if you have both critical and auxiliary listeners.** `Throwable` includes serious `Error`s; global suppression policies require careful consideration. In practice, recoverable errors are usually handled directly in the listener/adapter or listener types are separated architecturally, rather than applying a blind policy across every event in the context.

For business workflows that require guaranteed completion, prioritize **explicit consistency and retryability** over a publisher flow that always returns success.

## 11. Logging, Metrics, and Error Diagnostics

`ErrorHandler.handleError(Throwable)` does not automatically provide `eventId`, event type, bean name, or listener method name. Logging just the exception string often lacks context. You should enrich at the listener or instrumentation layer:

- `eventType`, `eventId`, `aggregateId`/`orderId` if available.
- Listener/handler name and the operation being performed.
- Processing timestamp, duration, and attempt count.
- `traceId`/`correlationId`, taking care with thread propagation when using async.
- Stack trace/exception type and disposition: suppressed, propagated, retried, or sent to DLQ.
- Error metrics and alerts for critical listeners; a suppressing handler must not erase operational signals.

Example of a listener adding context before the error propagates:

~~~java
@EventListener
public void reserveStock(OrderPlaced event) {
    try {
        stockService.reserve(event.orderId());
    } catch (RuntimeException ex) {
        logger.error("reserveStock failed for orderId={}",
                event.orderId(), ex);
        throw ex; // If you want to preserve propagate semantics.
    }
}
~~~

*Illustrative code snippet inside a bean: `stockService`, `logger`, and `OrderPlaced` are required application components; not a standalone program.*

If logging in both the listener and the ErrorHandler, avoid duplicating logs excessively for the same exception. You can use metric counters in the handler and log once in full where sufficient context exists.

## 12. Testing: Verify Side Effects, Not Just Logs

A test suite for ErrorHandler should verify **observable outcomes**, rather than just checking stdout:

1. **No handler, synchronous:** listener B throws an exception; publisher receives the error; listener C has not run.
2. **Suppressing handler:** listener B throws an error, yet the handler is called once; listener C still runs; publisher does not see B's error.
3. **Propagating handler:** listener B throws an error; handler rethrows; exception propagates to the appropriate call path; listener C does not run when synchronous.
4. **With @Order:** when testing which listener is "subsequent", set `@Order` explicitly in synchronous scenarios.
5. **Inside @Transactional:** verify data after commit/rollback using a real database or transactional test; do not infer solely from the presence or absence of an exception while overlooking rollback-only.
6. **With an async executor:** use `CountDownLatch` or `Awaitility`/wait conditions with timeouts; do not assert unguaranteed ordering.
7. **With @Async void:** verify the `AsyncUncaughtExceptionHandler` mechanism rather than assuming the multicaster ErrorHandler handles it.
8. **With AFTER_COMMIT:** verify whether the callback was invoked, where exceptions are recorded, and how the original transaction committed.
9. **External side effects:** simulate mid-flight failures and retries, verifying no duplicate sends or lost mandatory work.
10. **Startup/shutdown events:** a global multicaster configuration can affect framework lifecycle listeners; test key behaviors after replacing the bean.

### Example of State-Based Testing Instead of Stdout

When writing integration tests, you can replace `System.out.println` calls in `Listeners` with a `List<String> calls` owned by the test fixture. The default scenario expects `["first", "fails"]` and an exception; the suppress scenario expects `["first", "fails", "last"]` and one recorded error. With async, use a thread-safe collector and await rather than assuming listeners finish before `publishEvent(...)` returns.

Avoid configuring a global `ErrorHandler` that makes tests "all green" simply because errors were suppressed; assert both error/metric counts and resulting data.

## 13. Common Configuration Mistakes

1. **Wrong bean name**: `myEventMulticaster` instead of `applicationEventMulticaster`; the context may keep using the default multicaster.
2. **Confusing logger with policy**: a handler that just logs and returns is suppressing, not propagating; the transaction may proceed.
3. **Assuming failing listeners are automatically retried**: `ErrorHandler` has no retry queue or persistence.
4. **Assuming subsequent listeners always run**: if the handler rethrows or there is no handler on a synchronous multicaster, the multicast may stop before later listeners.
5. **Assuming earlier listeners are completely rolled back**: emails/HTTP/side effects outside the DB transaction do not automatically roll back.
6. **Applying suppress to mandatory invariants**: the DB may commit even though a critical business step failed.
7. **Confusing async with sync**: exceptions on an executor thread do not automatically return to the publisher; `@Order` does not guarantee async completion order.
8. **Expecting the multicaster ErrorHandler to handle every @Async exception**: an async method executed via proxy afterward has its own exception management path.
9. **Expecting ErrorHandler to roll back after AFTER_COMMIT**: the original transaction has already committed and cannot be reversed because a post-commit callback failed.
10. **Swallowing all Throwables indiscriminately**: can hide serious system errors or silence alerting signals.
11. **Not measuring suppressed errors**: the publisher sees success while consumers may have failed to finish their work.
12. **Not testing transaction-bound callbacks**: many errors occur outside the multicaster call at publish time.
13. **Thinking @Order means an atomic workflow**: listener ordering does not turn fan-out into a transactional message batch.
14. **Testing only the happy path**: you must test no-handler, suppress, propagate, async, rollback, and partial side effects.

## 14. Decision Summary for a Scenario

Suppose the `OrderSubmitted` event has three listeners:

- `ValidateOrder`: verifies mandatory invariants.
- `RecordMetric`: records statistics.
- `SendReceipt`: sends a confirmation email.

You should not simply configure a global suppressing `ErrorHandler` and let all three listeners run arbitrarily. A clearer design:

1. Execute `ValidateOrder` as a mandatory step inside the application service/transaction so validation errors can prevent commit.
2. `RecordMetric` can use an error policy that logs metrics/errors without breaking checkout if it is genuinely an optional task.
3. `SendReceipt` should go through a queue/outbox or worker with retry/idempotency if losing the email after commit is unacceptable.
4. If a global multicaster handler is still used, document the policy for each listener type and avoid accidentally hiding critical errors.

The decision question is not "Which ErrorHandler makes the code throw the fewest exceptions?" but **"Which errors must fail the entire business operation, and which can continue while still being recorded and handled later?"**

## 15. Knowledge Self-Check

**Question 1.** Without configuring an ErrorHandler, the second listener in a synchronous multicast pass throws `IllegalStateException`. What happens?

**Answer:** The error usually stops the current multicast pass and propagates to the publisher; subsequent listeners are not called. This is the default behavior of `SimpleApplicationEventMulticaster` when no async executor is used.

**Question 2.** Does `setErrorHandler(error -> logger.error("...", error))` make Spring automatically roll back the transaction?

**Answer:** No. A handler that logs and returns is suppressing, so the listener error no longer automatically propagates to the transaction interceptor. The transaction can continue/commit, unless it was already marked rollback-only or another error occurred. If there is no transaction, there is nothing to roll back.

**Question 3.** Why can a failing listener still allow the publisher to return normally?

**Answer:** An `ErrorHandler` caught the error and returned normally; the multicaster considers that exception handled and can proceed to other listeners.

**Question 4.** Can `ErrorHandler` be used to retry a failing listener?

**Answer:** The interface itself only receives `Throwable` and contains no retry/ack/replay API. To retry, you may need custom logic, a queue/outbox, or an appropriate framework; it is not built in by default.

**Question 5.** `@Async @EventListener` throws an error after the method has been scheduled. Is the multicaster ErrorHandler guaranteed to receive the error?

**Answer:** No. Errors inside an async method are handled via the async/executor mechanism; for `void`, look at `AsyncUncaughtExceptionHandler`.

**Question 6.** If a `@TransactionalEventListener(AFTER_COMMIT)` listener fails, can it roll back the original transaction?

**Answer:** No. The commit has already occurred before the callback. Design error handling, retries, and a new transaction separately.

**Question 7.** When the multicaster has a TaskExecutor, why doesn't the publisher automatically see the listener's exception?

**Answer:** The error may occur in a task on another thread after the `publishEvent(...)` method has already returned. Propagation in an executor differs from propagation on a synchronous call stack.

**Question 8.** How do `TaskUtils.LOG_AND_SUPPRESS_ERROR_HANDLER` and `LOG_AND_PROPAGATE_ERROR_HANDLER` differ?

**Answer:** Both log the error, but the suppress handler does not rethrow it; the propagate handler rethrows the error up the appropriate call path. In the async case, the "call path" may be the executor task rather than the publisher.

## References

- [Spring Framework 6.2.9 Javadoc — SimpleApplicationEventMulticaster](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html): `setErrorHandler`, default exception handling, `setTaskExecutor`, and async limitations.
- [Spring Framework Reference — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html): configuring the `applicationEventMulticaster` bean, `@EventListener`, ordering, async, and error handling.
- [Spring Framework Javadoc — ApplicationEventPublisher](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/ApplicationEventPublisher.html): `publishEvent` semantics and event handoff.
- [Spring Framework Javadoc — ErrorHandler](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/util/ErrorHandler.html): `handleError(Throwable)` interface.
- [Spring Framework Javadoc — TaskUtils](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/scheduling/support/TaskUtils.html): `LOG_AND_SUPPRESS_ERROR_HANDLER` and `LOG_AND_PROPAGATE_ERROR_HANDLER`.
- [Spring Framework Reference — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): `@TransactionalEventListener` phases and transaction conditions.
- [Spring Framework Reference — Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html): default rollback for RuntimeException/Error and rollback rule configuration.
