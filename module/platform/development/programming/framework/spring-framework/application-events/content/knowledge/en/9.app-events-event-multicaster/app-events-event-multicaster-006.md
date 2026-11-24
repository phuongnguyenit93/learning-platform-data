# Multicaster ErrorHandler in Spring Framework Application Events

## 1. The Problem ErrorHandler Solves

In Spring Framework, `ApplicationEventPublisher.publishEvent(...)` sends an event to matching registered listeners. The component that performs dispatching is `ApplicationEventMulticaster`; the common implementation Spring uses by default is `SimpleApplicationEventMulticaster`.

Suppose an `OrderSubmitted` event has three listeners:

- Listener A writes an audit log.
- Listener B updates metrics.
- Listener C sends a notification.

If listener A throws an exception, the question is not only "how should it be logged?" but also: **does the exception propagate back to the event publisher, and do listeners B/C still run?** The answer depends on how the multicaster is configured and whether listeners run synchronously or asynchronously.

The multicaster's `ErrorHandler` is a callback of type `org.springframework.util.ErrorHandler`, with the method:

```java
void handleError(Throwable t);
```

This callback can be attached to `SimpleApplicationEventMulticaster` using `setErrorHandler(...)`. When a listener throws an error within the multicaster's direct invocation scope, Spring passes the `Throwable` to the callback. **What `ErrorHandler` does next** determines whether the error is ignored to continue or rethrown to the calling thread.

This is an error-control mechanism **when dispatching events within the same `ApplicationContext`**. It does not on its own provide retries, intentional transaction rollback, durable queues, dead-letter queues, or cross-process notifications.

## 2. Position of ErrorHandler in the Event Path

Typical processing flow:

```text
ApplicationEventPublisher.publishEvent(event)
    |
    v
ApplicationEventMulticaster.multicastEvent(event)
    |
    +--> identify matching ApplicationListeners
    |
    +--> listener 1 ---> succeeds
    |
    +--> listener 2 ---> throws Throwable
    |                        |
    |                        +--> ErrorHandler.handleError(error)
    |                                  |
    |                                  +--> returns normally: continues loop
    |                                  |
    |                                  +--> rethrows error: error continues propagating
    |
    +--> listener 3 (if the dispatch loop continues)
```

At a conceptual level, `SimpleApplicationEventMulticaster`'s listener-invoking method behaves equivalently to:

```java
// Code illustrating the mechanism, not a full copy of Spring source code.
if (errorHandler != null) {
    try {
        invokeActualListener(listener, event);
    } catch (Throwable error) {
        errorHandler.handleError(error);
    }
} else {
    invokeActualListener(listener, event);
}
```

Key points to grasp:

1. `ApplicationEventMulticaster` is the **dispatch contract**; `setErrorHandler` belongs to the `SimpleApplicationEventMulticaster` implementation. Not every custom multicaster implementation has the same error-catching policy.
2. With `@EventListener`, Spring creates an adapter implementing `ApplicationListener`. Synchronous exceptions thrown by the listener method normally pass through the multicaster's call path, so `ErrorHandler` can receive them.
3. `ErrorHandler` receives **the error**, and is not automatically given the event object, listener name, or processing result. If logging by `eventId`/`listenerName` is needed, a separate context-recording mechanism must be designed.
4. `ErrorHandler` does not produce another event and does not decide whether a listener matches by type or `@EventListener(condition=...)`; it handles **failure at invocation time** of an already selected listener.
5. Because the parameter is `Throwable`, the handler can even receive fatal `Error`s. A suppress policy should not unconditionally swallow system errors such as `OutOfMemoryError`.

## 3. Three Common Policies

| Policy | In a synchronous multicaster | Suitable when |
| --- | --- | --- |
| No `ErrorHandler` set (default) | Exception normally propagates back from `publishEvent`; listener loop stops at the unhandled error | The listener is a mandatory part of the operation and the caller must know about failure |
| Handler **records and returns** (*suppress*) | After the handler returns, the multicaster continues invoking remaining listeners | Listeners are independent and one failure must not block others; proper monitoring/recovery exists |
| Handler **rethrows** (*propagate*) | Exception continues propagating; subsequent listeners in the same synchronous loop do not run | Failure must be reported to the caller, while centralizing logging or diagnostic enrichment |

The key behavior can be expressed as a decision table:

| Configuration | A succeeds | B throws exception | Do subsequent C listeners run? | Does the publisher see B's exception? |
| --- | --- | --- | --- | --- |
| Synchronous, no handler | Yes | Not handled at multicaster | **No**, if B throws before C | **Yes**, unless caught outside |
| Synchronous, suppress handler | Yes | Handler handles and returns | **Yes**, if no other error occurs | **No**, for suppressed errors |
| Synchronous, rethrow handler | Yes | Handler rethrows error | **No**, if B throws before C | **Yes**, unless caught outside |
| Asynchronous `TaskExecutor` | Depends on task | Handler runs on the assigned listener's task thread | No completion-order guarantee; other tasks may still run | Typically **does not** receive task execution exception on the `publishEvent` thread |

"Continues" here only means **the remaining listeners are generally still attempted** after the handler returns. It does not guarantee those listeners succeed, nor does it mean a failed listener is retried.

## 4. Configuration in Spring: Bean Named `applicationEventMulticaster`

When creating `ApplicationContext`, Spring looks for a bean with the **exact name** `applicationEventMulticaster`. If absent, the context uses the default multicaster. To change the error-handling policy, the direct approach is declaring a `SimpleApplicationEventMulticaster` with that standard bean name:

```java
@Configuration
class EventConfig {

    @Bean(name = AbstractApplicationContext.APPLICATION_EVENT_MULTICASTER_BEAN_NAME)
    SimpleApplicationEventMulticaster applicationEventMulticaster() {
        SimpleApplicationEventMulticaster multicaster =
                new SimpleApplicationEventMulticaster();

        multicaster.setErrorHandler(error -> {
            // Appropriate only when listener errors are allowed to be ignored.
            System.err.println("Event listener failed: " + error.getMessage());
        });

        return multicaster;
    }
}
```

Required imports for this snippet include `org.springframework.context.annotation.Configuration`, `Bean`, `org.springframework.context.event.SimpleApplicationEventMulticaster`, and `org.springframework.context.support.AbstractApplicationContext`.

This is an **illustrative configuration snippet** to place inside a Spring application, not a standalone program. If integrating into Spring Boot, you can likewise declare the bean in a `@Configuration` class scanned by the application; configuring the multicaster bean does not require a Boot-specific API.

Notes:

- **The bean name determines whether Spring uses it as the context's event multicaster**. Declaring a bean named `customMulticaster` and expecting it to automatically replace the default is incorrect.
- Merely changing `userEnteredValue` or writing listener code does not configure `ErrorHandler`. The error policy lives on the multicaster, not on individual `@EventListener` annotations.
- You cannot conclude that "every event in the system uses one `ErrorHandler`" if the application has multiple `ApplicationContext` instances, another custom multicaster, or separate messaging mechanisms.
- A callback logging only `getMessage()` is insufficient for production diagnostics. Log the stack trace, event type/correlation ID when possible, and per-listener metrics.

## 5. Runnable Example: Default Stops, Suppress Handler Continues

This example uses **Java 17+** and **Spring Framework 6.2.12** with Maven. It creates two independent `ApplicationContext` instances:

- The first context uses the default multicaster.
- The second context declares an `ErrorHandler` that records the error and returns.

In each context, the first listener intentionally throws `IllegalStateException`; the second listener prints a message when called. `@Order` establishes a clear order to illustrate synchronous behavior.

Structure:

```text
multicaster-errors/
├── pom.xml
└── src/main/java/demo/MulticasterErrorDemo.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>multicaster-errors</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
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
                <version>3.5.1</version>
                <configuration>
                    <mainClass>demo.MulticasterErrorDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/demo/MulticasterErrorDemo.java`:

```java
package demo;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.context.event.SimpleApplicationEventMulticaster;
import org.springframework.context.support.AbstractApplicationContext;
import org.springframework.core.annotation.Order;

public class MulticasterErrorDemo {

    public record ReportReady(String reportId) {}

    @Configuration(proxyBeanMethods = false)
    public static class ListenerConfig {
        @Bean
        public Handlers handlers() {
            return new Handlers();
        }
    }

    public static class Handlers {

        @EventListener
        @Order(1)
        public void writeAudit(ReportReady event) {
            System.out.println("FIRST " + event.reportId());
            throw new IllegalStateException("audit unavailable");
        }

        @EventListener
        @Order(2)
        public void updateMetrics(ReportReady event) {
            System.out.println("SECOND " + event.reportId());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class SuppressingMulticasterConfig {

        @Bean(name =
                AbstractApplicationContext.APPLICATION_EVENT_MULTICASTER_BEAN_NAME)
        public SimpleApplicationEventMulticaster applicationEventMulticaster() {
            var multicaster = new SimpleApplicationEventMulticaster();
            multicaster.setErrorHandler(error ->
                    System.out.println("HANDLED " + error.getMessage()));
            return multicaster;
        }
    }

    private static void execute(String label, boolean enableHandler) {
        System.out.println("=== " + label + " ===");

        try (var context = new AnnotationConfigApplicationContext()) {
            context.register(ListenerConfig.class);
            if (enableHandler) {
                context.register(SuppressingMulticasterConfig.class);
            }
            context.refresh();

            try {
                context.publishEvent(new ReportReady("R-42"));
            } catch (IllegalStateException error) {
                System.out.println("PUBLISH_FAILED " + error.getMessage());
            }
        }
    }

    public static void main(String[] args) {
        execute("DEFAULT", false);
        execute("WITH_HANDLER", true);
    }
}
```

Run in the directory containing `pom.xml`:

```bash
mvn -q compile exec:java
```

Lines explicitly printed by the program via `System.out.println`:

```text
=== DEFAULT ===
FIRST R-42
PUBLISH_FAILED audit unavailable
=== WITH_HANDLER ===
FIRST R-42
HANDLED audit unavailable
SECOND R-42
```

Explanation:

1. Both contexts register `Handlers`. Spring converts the two `@EventListener` methods into listeners for `ReportReady`.
2. In the `DEFAULT` case without an `ErrorHandler`, `writeAudit` throws an exception and the `context.publishEvent(...)` call throws. `updateMetrics` is not invoked because the error interrupted the synchronous dispatch loop.
3. In the `WITH_HANDLER` case using the multicaster bean with the standard name, the callback is invoked after `writeAudit` fails.
4. The callback prints `HANDLED ...` and **returns normally**. The multicaster continues to `updateMetrics`, so `SECOND R-42` appears.
5. `publishEvent(...)` itself does not know that audit logging failed in the suppress scenario; the event publisher only sees the call return normally.

The example avoids transactions or executors so the output order is easy to observe. Console printing is only for learning; in production, proper logging and metrics are required.

## 6. What If ErrorHandler Rethrows the Exception?

`ErrorHandler` is not required to swallow errors:

```java
multicaster.setErrorHandler(error -> {
    // Diagnose, then force the calling thread to know processing failed.
    System.err.println("Listener failed: " + error.getMessage());

    if (error instanceof Error fatal) {
        throw fatal;
    }
    if (error instanceof RuntimeException runtime) {
        throw runtime;
    }
    throw new IllegalStateException("Listener failed", error);
});
```

This is an **illustrative configuration snippet** replacing the lambda in the example above. When the handler throws an exception in synchronous dispatch mode, the exception exits the listener invocation, the loop of subsequent listeners is interrupted, and the publisher can catch it. If throwing a new exception wrapping `cause`, preserve the root cause for traceability.

Conversely, a handler that only logs and returns can make an HTTP request or business transaction **appear to have succeeded**, even though a listener's side effect did not complete. This is not necessarily a bug: independent audit/analytics should usually not block payment; however, for a mandatory check before completing payment, suppressing is a dangerous policy.

Spring provides helpers named `LOG_AND_SUPPRESS_ERROR_HANDLER` and `LOG_AND_PROPAGATE_ERROR_HANDLER` in `org.springframework.scheduling.support.TaskUtils`. You can refer to them when a standard policy is needed, though custom handlers often require richer contextual logging. Do not confuse logging helpers with retries or circuit breakers.

## 7. ErrorHandler with Asynchronous TaskExecutor

`SimpleApplicationEventMulticaster` allows configuring `setTaskExecutor(...)`. When an executor is present, listeners supporting async execution can be handed off to another task, while certain special listeners require running on the original thread.

**Illustrative configuration example** (not a standalone program):

```java
@Bean(name = AbstractApplicationContext.APPLICATION_EVENT_MULTICASTER_BEAN_NAME)
SimpleApplicationEventMulticaster applicationEventMulticaster(
        TaskExecutor eventExecutor) {

    var multicaster = new SimpleApplicationEventMulticaster();
    multicaster.setTaskExecutor(eventExecutor);
    multicaster.setErrorHandler(error ->
            log.error("Application event listener failed", error));

    return multicaster;
}
```

This snippet assumes the application has already declared `TaskExecutor eventExecutor` and a `log` field. You should not set an executor arbitrarily in a library or create unbounded threads for production loads; configure pool size, queue, rejection policy, and shutdown.

For listeners actually executed by the executor:

- The listener body may run **after** `publishEvent(...)` returns.
- The `ErrorHandler` attached to the multicaster can still catch errors thrown by the listener **inside the task created by the multicaster**, but that handler runs on the **executor thread**.
- If the handler rethrows the error, the error continues on the **task thread**; the caller of `publishEvent(...)` normally does not directly receive that execution exception.
- There is no guarantee that listeners execute or complete in `@Order` sequence as in the synchronous case; `@Order` does not create synchronization across tasks.
- If the executor rejects the task, an error raised **at task submission** can propagate back to the publisher; this differs from an error thrown inside the listener after the task starts.
- The publisher's thread-local state, security context, and transaction context are **not automatically copied** to the listener's thread.

Distinguish **the multicaster's executor** from `@Async` placed directly on a listener method. With `@Async`, the proxy can return before the method body runs; errors occurring afterward are handled by `@Async`'s mechanism (such as `AsyncUncaughtExceptionHandler` for `void` methods), so you cannot expect the multicaster's `ErrorHandler` to always catch errors inside an async method body. For a consistent policy, clearly define which async mechanism the application uses.

**Log-reading rule:** "the handler handled it" does not mean the publisher knows about the error. Correlation IDs, task monitoring, and separate retry mechanisms are needed when reliability is required.

## 8. Relationship with Transactions and @TransactionalEventListener

This is a frequent source of confusion.

### 8.1. Synchronous Listeners Inside a Transaction

Suppose a `@Transactional` method publishes an event and a synchronous listener throws `RuntimeException`:

- If there is no `ErrorHandler` or the handler rethrows, the exception can exit the transactional method, causing the transaction interceptor to mark a rollback according to active rollback rules.
- If the handler suppresses and no other error occurs, the business method can continue and the transaction **can commit** even though the listener failed.
- Whether the transaction rolls back still depends on the exception type, where the exception is caught, rollback configuration, and the actual transaction state. Do not naively deduce that "having an ErrorHandler always commits".

If a listener's side effect is a mandatory condition for the business operation to be valid, consider placing it directly in the application service or designing the transaction explicitly, rather than treating an easily suppressed listener as a mandatory validation step.

### 8.2. @TransactionalEventListener Has a Different Lifecycle

`@TransactionalEventListener` can run at `BEFORE_COMMIT`, `AFTER_COMMIT`, `AFTER_ROLLBACK`, or `AFTER_COMPLETION`. With default settings, it does not process events if there is no active transaction, unless `fallbackExecution = true`.

Illustrative example:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onOrderCommitted(OrderPlaced event) {
    sendNotification(event);
}
```

This is a method snippet inside a Spring bean; `OrderPlaced` and `sendNotification` are illustrative application components.

In the post-commit phase, the actual callback is typically executed **later by the transaction synchronization mechanism**, not within the immediate call of `SimpleApplicationEventMulticaster.invokeListener`. Therefore, **the multicaster's `ErrorHandler` is not a general-purpose mechanism for catching all errors arising from the deferred logic of `@TransactionalEventListener`**. Errors must be monitored and handled at the appropriate callback/transaction layer.

In modern Spring versions, transactional listeners by default do not support offloading listener invocation to the multicaster's executor because they must preserve transaction context; that **does not turn** an after-commit callback into a durable retried operation.

If an outbound message must be guaranteed to be sent **after commit** while also not being lost on process crash, consider a transactional outbox and durable messaging system. Setting `AFTER_COMMIT` and an `ErrorHandler` alone does not create that guarantee.

## 9. Choosing an Error Policy by Listener Criticality

An application typically has multiple kinds of listeners:

| Processing type | Example | Error-handling approach to consider |
| --- | --- | --- |
| Mandatory to complete business operation | Validating conditions before accepting an operation | Do not silently suppress; consider calling directly in the service |
| Independent, prioritized not to block the request | Collecting metrics, writing secondary traces | Suppress with logging/metrics and appropriate alerting |
| Important but retryable | Sending email after an order is paid | Extract to durable job/message, bounded retries, idempotency |
| Transaction-mandatory | Writing related data in the same transaction | Design explicitly in the same transaction, monitor rollbacks |
| Serving multiple independent consumers | Audit, metrics, notification | Define failure policy per consumer; consider separate multicaster/executor or dedicated protocols |

**One `ErrorHandler` on a multicaster applies globally to the listeners invoked by that multicaster.** If some listeners need fail-fast while others need best-effort, a "log and ignore all errors" lambda is too broad a policy.

Clearer alternatives are usually:

1. Separate mandatory work in the business flow from optional side effects.
2. Let optional listeners handle their own expected errors and report proper metrics/traces.
3. Use a message queue/outbox for work that cannot be lost and requires retries.
4. Use a global `ErrorHandler` only when a single common policy genuinely fits the listeners in that context.

## 10. Logging Useful Information in ErrorHandler

Logging only `error.getMessage()` is usually not enough. An error report should include:

- **Exception type** and stack trace, including `cause`.
- **Event type and business ID** if context has been put into the log.
- **Name of the running listener/task**; `ErrorHandler.handleError(Throwable)` only receives `Throwable`, so instrumentation, wrappers, or logging at the listener are needed if this information is required.
- **Request ID/correlation ID** to link with the trace of the originating operation. When processing asynchronously, intentionally propagate context.
- **Error count, frequency, and trend**, along with alerts so you know a listener is failing even when requests succeed.
- **Policy decision**: whether it was suppressed, propagated, or will be retried by a separate mechanism.

Sample error handling with SLF4J (**illustrative snippet, assuming a `log` logger exists**):

```java
multicaster.setErrorHandler(error -> {
    if (error instanceof Error fatal) {
        throw fatal;
    }
    log.error("Spring application event listener failed", error);
    // Returning normally means suppressing this listener failure.
});
```

If each listener needs a different policy, add logging directly inside the listener and suppress only exceptions identified as recoverable. Globally suppressing every `RuntimeException` can hide data corruption and violate business invariants.

## 11. Testing ErrorHandler: Beyond Checking Logs

In the example scenario, verify at minimum:

| Case | Setup | Expected outcome |
| --- | --- | --- |
| Listeners succeed | Both listener A and B succeed | Both are invoked, no `ErrorHandler` called |
| Listener fails, no handler | A fails before B, synchronous | `publishEvent` throws, B does not run |
| Listener fails, suppress handler | A fails before B, synchronous | Handler records error; B still runs; publisher does not throw due to A |
| Listener fails, rethrow handler | A fails before B, synchronous | Handler records then rethrows; B does not run |
| Two listeners both fail | Suppress handler | Handler is called for each error; not "merged" into one exception |
| Async listener fails in executor | With `TaskExecutor` | Properly recorded on task; publisher does not wait for task completion |
| `@Async` listener fails after proxy returns | `@EnableAsync` configured | Test the async proxy's error path, do not assume it routes to multicaster handler |
| Transactional listener fails after commit | `@TransactionalEventListener` | Test at the phase callback, not just watching the multicaster handler |
| Executor rejects task | Pool/queue full | Verify rejection policy and exception raised at task submission |

When writing tests, use a thread-safe recorder or `CountDownLatch`/`CompletableFuture` for async scenarios; **do not** use `Thread.sleep(...)` and infer that the listener has definitely finished. For synchronous examples, you can assert invocation order alongside the number of times `ErrorHandler` was triggered.

Add tests on the business transaction itself: **is** the suppress handler allowed to let the request succeed when a listener fails? Testing that policy is more important than asserting a specific log string.

## 12. Common Misconceptions

1. **Misnaming the multicaster bean**: the bean exists, but the context continues using the default multicaster.
2. **Assuming `ErrorHandler` always runs**: by default no handler may be configured; if a listener catches and swallows exceptions internally, the multicaster never sees that exception.
3. **Thinking suppress equals error recovery**: the handler returning does not mean the listener task completed or was retried.
4. **Thinking every listener continues after an error**: with a rethrow handler or no handler in synchronous mode, the dispatch loop is interrupted.
5. **Confusing `@Order` with async completion order**: a `TaskExecutor` can run multiple tasks concurrently.
6. **Expecting async exceptions to propagate to the publisher**: they are different execution threads; an error-collection mechanism for the executor/task is required.
7. **Confusing `ErrorHandler` with `AsyncUncaughtExceptionHandler`**: `@Async` has its own exception-handling path for errors occurring after the proxy returns.
8. **Confusing `ErrorHandler` with transaction phases**: `@TransactionalEventListener` can run in a deferred transaction callback; you cannot rely solely on the multicast-time handler.
9. **Suppressing mandatory errors**: requests/transactions can continue even though critical conditions were not met.
10. **Unconditionally swallowing `Throwable`**: hides fatal JVM errors; always consider propagating `Error`.
11. **Lack of observability**: a suppress policy without logs/metrics lets listener outages persist unnoticed.
12. **Assuming retries, exactly-once, persistence**: internal Spring Application Events do not provide these properties on their own.

## 13. Checklist Before Enabling ErrorHandler on the Multicaster

- Which listeners are allowed to fail without affecting the business outcome?
- Which listeners must report errors back to the caller to roll back or fix data?
- Have you identified whether execution is synchronous, on the multicaster executor, or `@Async` on the method?
- Have you verified the multicaster bean has the exact name `applicationEventMulticaster`?
- Will the handler **suppress** or **propagate**? Does that policy apply to all relevant listeners?
- Are fatal `Error`s protected, and are stack traces, correlation IDs, and error metrics logged?
- Is there any work requiring retries or durable delivery that needs an outbox/queue?
- Are there `@TransactionalEventListener` methods running later where the multicaster's `ErrorHandler` is no longer on the main execution call path?
- Have you written tests verifying the behavior of subsequent listeners, the publisher, and transactions?

**Key takeaway:** `SimpleApplicationEventMulticaster`'s `ErrorHandler` is where you decide whether a listener exception is **recorded to allow dispatching to continue** or **rethrown** within the call path controlled by the multicaster. Choose the policy based on the listener's business responsibility and synchronous/asynchronous context; do not treat error suppression as a guarantee that the event was successfully processed.

**References:**

- [Spring Framework Reference — Standard and Custom Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [SimpleApplicationEventMulticaster API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [ErrorHandler API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/util/ErrorHandler.html)
- [Transactional Application Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
