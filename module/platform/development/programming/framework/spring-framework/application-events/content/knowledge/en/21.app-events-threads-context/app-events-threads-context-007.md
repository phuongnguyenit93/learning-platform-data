# Context Propagation in Executors When Handling Spring Application Events

## 1. The Problem: When an Event Runs on Another Thread, Where Does Context Go?

In Spring Framework, an application commonly uses `ApplicationEventPublisher` to send events to listeners. By default, `SimpleApplicationEventMulticaster` calls listeners **synchronously on the event-publishing thread**. Consequently, values bound to the current thread—such as a request ID stored in `ThreadLocal`, logging MDC, or certain observation contexts—are normally visible inside synchronous listeners.

When `SimpleApplicationEventMulticaster` is replaced with a configuration using an asynchronous `TaskExecutor`, or when a listener is annotated with `@Async`, the listener may run on **another thread from the pool**. A plain `ThreadLocal` does not automatically follow the task. This leads to situations where:

- Logs in the listener no longer have `traceId` or `correlationId`, making it hard to correlate logs back to the original request.
- Observation/tracing context breaks between event publication and event processing.
- Information used for access control may be absent if the application inadvertently relies on thread-local security context.
- Trying to "copy everything" can cause thread pools to leak data from a previous task to the next, or misuse an already-ended transaction.

**Context propagation** is the practice of *capturing allowed context values at task submission time, restoring them when the task executes on the worker thread, and cleaning up/restoring the worker's original state in `finally`*.

It is a mechanism for **selectively transferring context data**, not an action that copies a live request, database connection, or Spring transaction onto another thread.

~~~text
Publisher / request thread                     Worker thread from pool
-------------------------------------------   ---------------------------------
ThreadLocal traceId = "t-42"
    |
    | publishEvent(OrderPlaced)
    |     +-- multicaster.execute(task)
    |             +-- TaskDecorator captures "t-42"
    |             +---------------------------------------------->
    |                                             restore traceId="t-42"
    |                                             @EventListener(...)
    |                                             log with traceId
    |                                             finally: restore/clear
    |                                                   |
    |<----------------------------------------------task completes
    |
    +-- publisher continues its work
~~~

Without a propagation mechanism, the task on the worker usually reads `ThreadLocal.get() == null`, even though the publisher called `set(...)` before publishing the event.

## 2. Distinguishing Four Types of Context

| Type | Example | Issue when switching threads | Appropriate handling |
| --- | --- | --- | --- |
| **Correlation/logging context** | `requestId`, `traceId`, MDC. | Downstream logs miss IDs or mix up IDs from previous tasks. | Pass a small, well-scoped snapshot; restore/clean up in `finally`. |
| **Tracing/observation context** | Current span, Micrometer Observation. | Span on the worker is no longer linked properly to the publisher. | Micrometer Context Propagation + properly registered accessors. |
| **Security context** | Spring Security `SecurityContextHolder`, principal. | Worker may not see authentication info. | Propagate intentionally with Spring Security tools or pass appropriate identity/authorization. |
| **Transaction/resource context** | JDBC Connection, JPA EntityManager, Spring transaction synchronization. | Worker does not automatically join the publisher's transaction. | **Never copy transactions via ThreadLocal**; define a new transaction boundary or use transaction-bound listeners properly. |

Not every `ThreadLocal` should be propagated. An immutable `requestId` may be safe for tracing, whereas a mutable request object, open resource, or expired authentication carries far greater risk.

For reactive applications, **Reactor Context** is a different mechanism: data travels with the pipeline's subscriber/subscription. Passing information between Reactor Context and a regular Java executor requires an intentional bridge; you cannot assume a `ThreadLocal` automatically receives all values from Reactor Context.

## 3. Two Different Async Mechanisms in Spring Application Events

There are two common ways an event listener ends up running asynchronously. They have different configuration points.

### 3.1. `TaskExecutor` on `ApplicationEventMulticaster`

~~~java
@Bean(name = "applicationEventMulticaster")
SimpleApplicationEventMulticaster applicationEventMulticaster(
        @Qualifier("eventExecutor") TaskExecutor executor) {

    var multicaster = new SimpleApplicationEventMulticaster();
    multicaster.setTaskExecutor(executor);
    return multicaster;
}
~~~

*This is a Spring integration snippet; it requires importing `@Bean`, `@Qualifier`, `TaskExecutor`, and `SimpleApplicationEventMulticaster`. The bean must be named exactly `applicationEventMulticaster` for Spring to use the configured multicaster.*

In default mode, the multicaster uses behavior equivalent to `SyncTaskExecutor` and invokes listeners right on the publisher thread. When given an async executor, it can submit **each listener** to the executor.

Since Spring Framework 6.1, `ApplicationListener` provides `supportsAsyncExecution()`. Listeners reporting **that they do not support async execution at the multicaster level**—typically transaction-bound listeners—are still invoked on the event-publishing thread so they can register transaction synchronization. Therefore, do not conclude every listener moves onto the executor merely because the multicaster has `setTaskExecutor(...)`.

### 3.2. `@Async` on an `@EventListener` Method

~~~java
@Component
class NotificationListener {

    @Async("eventExecutor")
    @EventListener
    public void onOrderPlaced(OrderPlaced event) {
        // Method is routed by proxy onto the chosen executor.
    }
}
~~~

*Illustrative snippet; requires an `eventExecutor` bean, `@EnableAsync` enabled, and an `OrderPlaced` declaration. This is not a standalone program.*

`@Async` typically relies on a proxy and an executor chosen by name/qualifier. If you attach a decorator only to the **multicaster's** executor while `@Async("anotherExecutor")` runs on a **different** executor, context can still be lost at the second hop. Identify **which executor the task is actually submitted to** and configure propagation there.

**Key distinction:** multithreading in the multicaster and asynchronicity via `@Async` are two different dispatch layers. Do not combine both indiscriminately, as thread hops, error handling, and ordering can become unnecessarily complex.

## 4. ThreadLocal and the Thread Reuse Problem

`ThreadLocal<T>` gives each thread its own value:

~~~java
private static final ThreadLocal<String> TRACE_ID = new ThreadLocal<>();

TRACE_ID.set("trace-42");
try {
    // Only the current thread reads TRACE_ID.get() by default.
} finally {
    TRACE_ID.remove();
}
~~~

*Illustrative snippet placed inside a regular Java class/method.*

`ThreadPoolTaskExecutor` reuses worker threads. This creates two contrasting failures:

**Context loss:** the publisher on thread A calls `TRACE_ID.set("trace-42")`, but worker B was never assigned a value; the listener reads `null`.

**Context leak:** worker B was set to `trace-41` by an earlier task. If that task did not clear/restore in `finally`, the next task may mistakenly read `trace-41`. This is especially dangerous when context carries user or tenant identifiers.

`InheritableThreadLocal` is not a general solution: it only inherits conditionally when **creating a child thread**, whereas executors usually use pre-created threads. It can also cause context leaks across reused threads. Java virtual threads also do not automatically fix propagation across all asynchronous boundaries.

## 5. TaskDecorator: Capture at Submission Time, Restore at Execution Time

Spring provides the `org.springframework.core.task.TaskDecorator` interface:

~~~java
@FunctionalInterface
public interface TaskDecorator {
    Runnable decorate(Runnable runnable);
}
~~~

*Simplified signature to explain the API; do not redefine Spring's interface.*

Executors that support decorators, such as `ThreadPoolTaskExecutor`, call `decorate(...)` when preparing to execute a task. We can build a mechanism to propagate a custom `ThreadLocal`:

~~~java
static TaskDecorator captureTraceId() {
    return task -> {
        // Runs when the task is submitted, usually on the publisher's thread.
        String captured = TRACE_ID.get();

        return () -> {
            // Runs on the worker thread; save old state to avoid leaks.
            String previous = TRACE_ID.get();
            try {
                if (captured == null) {
                    TRACE_ID.remove();
                } else {
                    TRACE_ID.set(captured);
                }

                task.run();
            } finally {
                if (previous == null) {
                    TRACE_ID.remove();
                } else {
                    TRACE_ID.set(previous);
                }
            }
        };
    };
}
~~~

*Snippet placed in a class with `TRACE_ID` and `TaskDecorator` imported. Complete example below.*

Four details are decisive:

1. **Capture at submission time:** take the snapshot while the producer still holds the context, rather than reading late on the worker and picking up a mutated value.
2. **Restore before running the task:** the listener can access `TRACE_ID` during execution.
3. **Clean up in `finally`:** ensures that even if the listener throws an exception, the worker does not retain the value from the request just processed.
4. **Restore prior state:** if tasks run nested or the worker has valid outer context, do not wipe out the value used by the outer scope.

Do not write a decorator like this:

~~~java
task -> () -> {
    TRACE_ID.set(TRACE_ID.get()); // Wrong: reads worker, does not capture publisher!
    task.run();                   // Also wrong: no cleanup.
};
~~~

This is strictly an anti-pattern. It neither transfers anything from the publisher nor cleans up context.

## 6. Runnable Java 17+ Example: Listener Before and After Propagation

This example uses **Spring Framework 6.2.9**, Java 17+, and Maven. It creates two separate `ApplicationContext` instances, each with a `SimpleApplicationEventMulticaster` backed by a `ThreadPoolTaskExecutor`:

- First run **without** `TaskDecorator`: the worker does not see the publisher's `ThreadLocal`.
- Second run **with** the decorator: the worker receives the `trace-42` snapshot and restores state after running.

`CountDownLatch` makes the program wait for the listener to finish before reading the result, rather than guessing with `Thread.sleep(...)`. The `null` value in stdout is an intentional descriptive string, not a formatting bug.

### 6.1. Structure

~~~text
event-context-demo/
├── pom.xml
└── src/main/java/EventContextDemo.java
~~~

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>event-context-demo</artifactId>
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

`src/main/java/EventContextDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.context.event.SimpleApplicationEventMulticaster;
import org.springframework.core.task.TaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class EventContextDemo {

    private static final ThreadLocal<String> TRACE_ID = new ThreadLocal<>();

    public record WorkRequested(String jobId) {}

    @Configuration(proxyBeanMethods = false)
    public static class Config {

        @Bean
        public WorkListener workListener() {
            return new WorkListener();
        }
    }

    public static class WorkListener {

        private final CountDownLatch done = new CountDownLatch(1);
        private volatile String observedTraceId;

        @EventListener
        public void onWork(WorkRequested event) {
            String value = TRACE_ID.get();
            observedTraceId = (value == null ? "null" : value);
            done.countDown();
        }

        public String awaitObservation() throws InterruptedException {
            if (!done.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Event listener timed out");
            }
            return observedTraceId;
        }
    }

    private static TaskDecorator traceDecorator() {
        return task -> {
            String captured = TRACE_ID.get();

            return () -> {
                String oldValue = TRACE_ID.get();
                try {
                    if (captured == null) {
                        TRACE_ID.remove();
                    } else {
                        TRACE_ID.set(captured);
                    }

                    task.run();
                } finally {
                    if (oldValue == null) {
                        TRACE_ID.remove();
                    } else {
                        TRACE_ID.set(oldValue);
                    }
                }
            };
        };
    }

    private static void runCase(boolean enablePropagation)
            throws InterruptedException {

        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(1);
        executor.setQueueCapacity(16);
        executor.setThreadNamePrefix("event-worker-");

        if (enablePropagation) {
            executor.setTaskDecorator(traceDecorator());
        }
        executor.initialize();

        try {
            try (var context = new AnnotationConfigApplicationContext()) {
                context.register(Config.class);

                // Required bean name so Spring picks the custom multicaster.
                context.registerBean(
                    "applicationEventMulticaster",
                    SimpleApplicationEventMulticaster.class,
                    () -> {
                        var multicaster =
                            new SimpleApplicationEventMulticaster();
                        multicaster.setTaskExecutor(executor);
                        return multicaster;
                    });

                context.refresh();

                TRACE_ID.set("trace-42");
                try {
                    context.publishEvent(new WorkRequested("job-7"));

                    // Listener runs asynchronously: synchronize with latch.
                    String value = context.getBean(WorkListener.class)
                            .awaitObservation();

                    String mode = enablePropagation ? "WITH" : "WITHOUT";
                    System.out.println(mode + " decorator: " + value);
                } finally {
                    TRACE_ID.remove();
                }
            }
        } finally {
            executor.shutdown();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        runCase(false);
        runCase(true);
    }
}
~~~

Run command (in the directory containing `pom.xml`):

~~~bash
mvn -q compile exec:java -Dexec.mainClass=EventContextDemo
~~~

Stdout printed by the program, excluding Maven's own logs:

~~~text
WITHOUT decorator: null
WITH decorator: trace-42
~~~

### 6.2. Analyzing the Results

- `TRACE_ID.set("trace-42")` runs on the thread calling `publishEvent(...)`, not on an `event-worker-*` thread.
- The multicaster is configured with `setTaskExecutor(executor)`, so the `@EventListener` receiving `WorkRequested` is submitted as an asynchronous task.
- **Without decorator:** the worker does not automatically have the publisher's `ThreadLocal`; `TRACE_ID.get()` returns `null`.
- **With decorator:** at submission time, `traceDecorator()` captures `trace-42`. When the task runs, the decorator installs that value into the worker's `ThreadLocal`; the listener reads `trace-42`.
- The listener signals completion via `CountDownLatch`, so `main` does not depend on thread pool speed.
- The `finally` block in the decorator clears/restores context. `try-with-resources` closes `AnnotationConfigApplicationContext`, and `executor.shutdown()` releases the worker thread.

The program intentionally processes **only one application event per run** so ordering among multiple async listeners does not need to be enforced. It also uses neither transactions nor Spring Security, avoiding confusion between trace ID propagation and propagation of other resources.

## 7. Spring `ContextPropagatingTaskDecorator` and Micrometer

Since Spring Framework **6.1**, Spring includes `org.springframework.core.task.support.ContextPropagatingTaskDecorator`. It uses **Micrometer Context Propagation**, which is helpful for transferring values such as logging/observation context when tasks run on another thread.

In Spring Framework 6.2, the integration configuration snippet can be written as:

~~~java
@Configuration
class EventExecutorConfiguration {

    @Bean("eventExecutor")
    ThreadPoolTaskExecutor eventExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("events-");
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        return executor;
    }

    @Bean(name = "applicationEventMulticaster")
    SimpleApplicationEventMulticaster applicationEventMulticaster(
            @Qualifier("eventExecutor") ThreadPoolTaskExecutor executor) {

        var multicaster = new SimpleApplicationEventMulticaster();
        multicaster.setTaskExecutor(executor);
        return multicaster;
    }
}
~~~

*This is an **integration configuration** snippet, not a standalone Maven example: it requires importing `@Configuration`, `@Bean`, `@Qualifier`, `ThreadPoolTaskExecutor`, `ContextPropagatingTaskDecorator`, and `SimpleApplicationEventMulticaster`. A compatible `io.micrometer:context-propagation` library is needed on the classpath; with Spring Boot, prefer Boot's dependency management.*

**This does not mean it automatically copies every `ThreadLocal`.** Micrometer transfers contexts that the library recognizes through registered `ThreadLocalAccessor`/`ContextAccessor` implementations. For custom application `ThreadLocal` values, you must provide an appropriate accessor if you want to use the standard decorator rather than writing one manually. Whether MDC is fully transferred also depends on the logging stack and actual accessors.

Conceptual mechanism:

~~~text
Publisher thread                           Worker thread
Micrometer ContextSnapshot                ContextSnapshot.Scope
  | capture registered contexts               | restore registered values
  +------------------------------------------>| task.run()
                                              | finally: close Scope
                                              | restore previous worker context
~~~

Advantages:

- Can manage multiple context types through a single snapshot mechanism.
- Integrates cleanly with Micrometer Observation/tracing when properly configured.
- Reduces the risk of writing buggy `try/finally` logic for every custom `ThreadLocal`.

Limitations:

- Only data with matching accessors/infrastructure is transferred.
- Capture/restore incurs CPU and memory cost; do not attach a large snapshot pipeline to millions of tiny tasks without benchmarking.
- Does not make unsafe mutable data thread-safe.
- Does not automatically transfer `EntityManager`, JDBC connections, or active transactions.

Spring supports `CompositeTaskDecorator` when multiple decorators must be combined; you still need to define set/clear ordering and avoid stacking multiple solutions that copy the same context and overwrite each other.

## 8. Logging MDC: A Dedicated Solution for SLF4J Systems

Some applications use `org.slf4j.MDC` to inject `traceId` and `requestId` into log formatting:

~~~text
2026-11-11 14:00:00 INFO [trace-42] OrderPlaced received
2026-11-11 14:00:01 INFO [trace-42] Order email scheduled
~~~

*Timestamps are illustrative examples, not stdout from the program in section 6.*

If you do not yet use Micrometer propagation or want direct control over MDC, you can build a `TaskDecorator` using an MDC snapshot:

~~~java
TaskDecorator mdcDecorator = task -> {
    Map<String, String> captured = MDC.getCopyOfContextMap();

    return () -> {
        Map<String, String> previous = MDC.getCopyOfContextMap();

        try {
            if (captured == null) {
                MDC.clear();
            } else {
                MDC.setContextMap(captured);
            }

            task.run();
        } finally {
            if (previous == null) {
                MDC.clear();
            } else {
                MDC.setContextMap(previous);
            }
        }
    };
};
~~~

*This is an illustrative snippet requiring `java.util.Map`, `org.slf4j.MDC`, and `org.springframework.core.task.TaskDecorator`; an appropriate SLF4J/logging implementation must be present. It is not standalone runnable code.*

Why use `getCopyOfContextMap()`? Because we want to capture **a copy of the current logging data** at submission time, rather than sharing a live mutable map between publisher and worker.

**Note:** MDC is not secure storage. Never place access tokens, passwords, or sensitive data into MDC just to "pass context", as logs may inadvertently record or export that data.

## 9. SecurityContext: Propagation Is Not Equivalent to Delegation/Authorization

Spring Security normally stores the thread's `SecurityContext` in `SecurityContextHolder`. For a task pushed to an executor, the worker may not receive the publisher's authentication.

Spring Security provides wrappers such as `DelegatingSecurityContextExecutor` or `DelegatingSecurityContextAsyncTaskExecutor` to transfer security context in appropriate situations. When using them:

1. Choose the right security context to transfer (a fixed context vs. the context at submission time).
2. Verify the task actually uses the wrapped executor; `@Async` might pick a different bean.
3. Limit privileges and context lifetime; do not accidentally turn a long-running task into a job holding the original user's permissions permanently.
4. Restore/clean up state after the task finishes to prevent leaking the principal to other tasks.
5. If work runs long after the request or after user permissions have changed, consider using a service account/separate authorization rather than keeping the old authentication object alive.

**Do not copy `SecurityContextHolder` using a custom `ThreadLocal` and assume it is a complete security mechanism.** Authorization, session invalidation, and timeout implications must be explicitly designed according to business requirements.

## 10. Why Not Propagate Spring Transactions by Copying ThreadLocal?

This is the most important warning when discussing context propagation in Spring events.

For imperative transactions (JDBC/JPA), Spring uses `org.springframework.transaction.support.TransactionSynchronizationManager` to bind resources and transaction synchronization to **the current thread**. If a service inside `@Transactional` publishes an event, a synchronous listener can run while that transaction is active. When a listener moves onto another thread:

- The worker does not automatically participate in the publisher's transaction.
- Grabbing a `ThreadLocal` pointing to transaction state or a JDBC connection and binding it to a worker is unsafe: transactions and resources have their own lifecycle, thread-safety constraints, and commit/rollback rules.
- The publisher thread may commit or roll back the transaction before the worker finishes processing.
- Code running outside the transaction may encounter `LazyInitializationException` or observe unexpected data.

**Never build a "transaction decorator" by copying `TransactionSynchronizationManager` from A to B.** Spring is not designed to share JDBC/JPA transactions concurrently across threads.

If an async listener needs to write data to the DB, explicitly start **a new transaction on the worker**, for example by delegating to a `@Transactional` Spring service invoked through the proper proxy. If the requirement is only to react when the original transaction commits successfully, use `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` with proper post-commit handling and, when durability is required, a transactional outbox.

An important nuance from Spring Framework 6.1: transaction-synchronized listeners declare that they do not support the **multicaster** arbitrarily offloading the callback to another thread (`supportsAsyncExecution() == false`). However, a handler method with `@Async` or a task it submits itself can still switch to an executor; never conclude the old transaction travels with the task because of that.

For **reactive transactions** using `ReactiveTransactionManager`, context mainly follows the Reactor subscriber context rather than JDBC thread-locals. When reactive transaction events must be handled, the proper mechanism is the pipeline/`TransactionalEventPublisher`, not copying Java `ThreadLocal` values with a decorator.

## 11. Capture Lifecycle, Cleanup, and Sensitive Information

A good decorator does more than "set the propagated value"—it manages data lifecycle:

| Moment | Proper practice |
| --- | --- |
| Before submission | Capture a small, immutable, or defensively copied snapshot. |
| When worker starts | Save the worker's old state, then restore the needed snapshot. |
| While listener runs | Use only values needed for logging/tracing or designed checks. |
| When listener succeeds | Complete and return the worker's state to what it was before. |
| When listener fails | Still clean up in `finally`, while reporting/recording the error per policy. |
| When task is canceled before running | Avoid holding references to large payloads/contexts or secrets in the queue for too long. |
| When application shuts down | Shut down the executor per lifecycle, awaiting needed tasks or setting a clear cancellation policy. |

Never place an entire `HttpServletRequest` in a `ThreadLocal` to pass to a worker: requests/responses have a lifecycle tied to the HTTP flow; a delayed task may access an invalidated object or retain resources unintentionally. When data is needed, **extract the required fields**, such as correlation ID, validated tenant code, and immutable business data.

If context is written to logs or telemetry, follow privacy and access-control policies. Tracing metadata must not contain card numbers, passwords, or raw tokens.

## 12. Testing Context Propagation and Concurrency

A minimal test suite should prove both **correct context** and **zero context leakage**:

1. A synchronous listener reads the request ID when publisher and listener run on the same thread.
2. An async listener on an undecorated executor **does not** implicitly receive the publisher's custom `ThreadLocal`.
3. An executor with the right decorator captures the request ID at submission time and restores it at execution time.
4. Two events from two different requests have different IDs; the worker does not mistakenly reuse the previous request's ID.
5. After a listener throws an exception, the worker cleans up so the next task does not see stale context.
6. When the publisher has no context, the decorator handles `null`/absent properly instead of "retaining" old worker data.
7. When tasks run nested, the pre-task state is restored accurately.
8. If Spring Security is used, test the right principal/authorities per expected semantics and ensure no tenant leakage.
9. If using Micrometer, verify accessors/Observation are actually registered; having the dependency without the matching accessor can still lose custom `ThreadLocal` values.
10. Ensure transactions are not improperly shared across threads; async listeners open their own transactions when business logic requires it.

In async tests, use `CountDownLatch`, `CompletableFuture`, `Awaitility`, or synchronized conditions with timeouts. Never use `Thread.sleep(100)` and assume the executor has finished, as that makes CI tests flaky.

Regarding ordering: even when context propagation works, **it does not guarantee event processing order** across multiple workers. If business rules require ordering, configure a queue/partition/serial executor or coordinate at the business level. Propagation only solves **task context**; it does not change scheduling semantics.

## 13. Error Handling and System Observability

When a listener runs asynchronously, exceptions occur on the worker rather than propagating directly back to the caller of `publishEvent(...)`. This affects error reporting:

- With an async multicaster, consider `SimpleApplicationEventMulticaster.setErrorHandler(...)` to observe errors in listeners dispatched through the multicaster; never swallow errors without metrics or logs.
- With `@Async`, manage exceptions via `AsyncUncaughtExceptionHandler` for `void` methods, or via `Future`/`CompletableFuture` when the signature returns one.
- `TaskDecorator` is primarily designed to wrap tasks and context; do not assume it always sees exceptions from every `FutureTask`, since the wrapper may store exceptions inside the future.
- If retries after failure are required, Spring Application Events are not a durable queue on their own; you need explicit retry/idempotency mechanisms and, if events must not be lost, an outbox/broker.
- When logging, record correlation ID, event name, handler, timestamp, outcome, and exception type; avoid logging full sensitive payloads.

A diagnostic workflow when listener logs are missing a trace:

~~~text
Do publisher logs have traceId?
  |
  +-- No -> trace source is already missing; check request/filter/tracing first.
  |
  +-- Yes
       |
       +-- Sync listener on the same thread?
       |       |
       |       +-- Yes -> check ThreadLocal set/remove lifecycle.
       |       +-- No -> identify which executor runs the listener.
       |
       +-- Is the decorator attached to the actual executor?
       |       |
       |       +-- No -> configure the right bean.
       |       +-- Yes
       |             |
       |             +-- Does the accessor/snapshot capture that value?
       |             +-- Does the decorator restore and clean up?
       |             +-- Is there another @Async hop or scheduler?
       |
       +-- Is it accessing a resource/transaction from the publisher?
               |
               +-- Yes -> redesign transaction boundaries; DO NOT copy connections.
~~~

## 14. Common Mistakes

1. **Assuming `@Async` automatically carries all `ThreadLocal` values to the worker.** It only changes execution threading; context propagation needs explicit configuration.
2. **Decorating the wrong executor.** Multicaster uses `eventExecutor` while `@Async` uses another executor; context is still lost.
3. **Capturing on the worker instead of the publisher.** The worker only sees its own value; capture must happen before the task runs.
4. **Failing to restore/clean up in `finally`.** The thread pool retains data from the prior task, risking user or tenant leakage.
5. **Using `InheritableThreadLocal` as a pool solution.** It is unreliable with reused threads.
6. **Assuming `ContextPropagatingTaskDecorator` transfers everything automatically.** Only contexts with matching accessors/infrastructure are supported.
7. **Copying `TransactionSynchronizationManager` or a JDBC Connection to another thread.** Cannot replace proper transaction management and can cause severe corruption.
8. **Sharing mutable requests/entities across workers.** Context metadata does not make those objects thread-safe.
9. **Lacking timeouts and error handling.** Callers may have already returned while async listeners fail silently.
10. **Assuming having a trace ID guarantees delivery.** Tracing does not provide queues, retries, exactly-once semantics, or rollbacks.
11. **Logging sensitive credentials in MDC.** Propagation increases the places sensitive data appears; record minimal metadata only.
12. **Assuming a transaction-bound listener will always be moved to a pool by the multicaster.** Spring intentionally disables multicaster-level async execution for transaction-synchronized listeners.

## 15. Self-Check Exercises

**Question 1.** Why doesn't `ThreadLocal.set("trace-42")` in a controller guarantee that an `@EventListener` running in a thread pool reads that value?

**Answer:** `ThreadLocal` is per-thread and is not automatically copied from the publisher to an executor worker. Intentional propagation is required.

**Question 2.** When should `TaskDecorator.decorate(...)` capture the value?

**Answer:** When the task is prepared/submitted on the thread holding the original context. The returned `Runnable` restores that value when the worker actually runs.

**Question 3.** Why is `finally` needed even if the listener succeeds on almost every invocation?

**Answer:** Worker threads are reused. If a listener fails or a task terminates abnormally without cleanup, old context can leak into subsequent tasks.

**Question 4.** Can `ContextPropagatingTaskDecorator` be used to pass the controller's JDBC transaction to a listener running on another thread?

**Answer:** No. Propagation is for contexts with accessors such as logging/tracing; it is unsafe to copy thread-bound transactions/resources managed by a transaction manager.

**Question 5.** The multicaster uses `eventExecutor`, while the listener specifies `@Async("mailExecutor")`. Which executor gets the decorator?

**Answer:** You must examine the actual thread hops; decorating only `eventExecutor` may not be enough. Tasks dispatched by `@Async` to `mailExecutor` also need appropriate propagation.

**Question 6.** If a custom `ThreadLocal` does not have a registered `ThreadLocalAccessor`, does adding the Micrometer Context Propagation library guarantee it will be propagated?

**Answer:** No. There must be an accessor or an explicit capture/restore mechanism for that value.

**Question 7.** What does propagation guarantee, and what does it not guarantee?

**Answer:** It helps tasks receive the selected context values and clean up safely. It does **not** guarantee event ordering, transaction commits, retries, durable delivery, or security if authority/identity is designed incorrectly.

## References

- [Spring Framework Reference — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html): default synchronous listeners, `SimpleApplicationEventMulticaster` configuration, `@Async`, and context.
- [Spring Framework Reference — Observability: Application Events](https://docs.spring.io/spring-framework/reference/integration/observability.html): propagating observation/log context across executors via `ContextPropagatingTaskDecorator`.
- [Spring Framework Reference — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `TaskExecutor`, `ThreadPoolTaskExecutor`, `TaskDecorator`, and `@Async`.
- [Spring Framework 6.2.9 Javadoc — SimpleApplicationEventMulticaster](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html): executor, synchronous default, and `supportsAsyncExecution` exception.
- [Spring Framework 6.2 Javadoc — ContextPropagatingTaskDecorator](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html): capturing/restoring context for workers, execution cost.
- [Spring Framework 6.2 Javadoc — TaskDecorator](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/task/TaskDecorator.html): wrapping `Runnable` and notes on exceptions in `Future`.
- [Micrometer Context Propagation](https://micrometer.io/docs/contextPropagation): `ContextSnapshot`, `ThreadLocalAccessor`, and registering context accessors.
