# ThreadLocal in Spring Application Events Listeners

## 1. Objectives

`ThreadLocal<T>` stores a **per-thread** value. In a Spring application, many types of context rely on thread-bound state: request information, logging MDC, security context in common configurations, locale, transaction resources, and certain tracing data.

When working with Spring Application Events, a common question is: **can a listener read the `ThreadLocal` of the caller that invoked `ApplicationEventPublisher.publishEvent(...)`?**

The answer depends on **which thread the listener is running on**:

- With the default `ApplicationEventMulticaster` and a synchronous listener: the callback usually runs **directly on the publishing thread**, so it sees the same active `ThreadLocal` values.
- If the listener has `@Async` or the multicaster delegates work to an `Executor`: the callback runs on a different thread, so it **does not automatically carry** the publisher's `ThreadLocal`, MDC, transaction, or request context.
- If context is passed manually, via a `TaskDecorator`, tracing/security adapters, or in the event payload itself: you must understand **which values are propagated, when to snapshot them, and when to clean them up**.

This lesson focuses on the actual mechanism, runnable Java 17+ examples, and safe design principles. Do not treat `ThreadLocal` as part of an event payload or as a global store.

## 2. The Nature of ThreadLocal

Pure Java example:

~~~java
// Illustrated inside a Java class:
private static final ThreadLocal<String> REQUEST_ID = new ThreadLocal<>();

public static void work() {
    REQUEST_ID.set("req-17");
    try {
        System.out.println(REQUEST_ID.get()); // req-17
    } finally {
        REQUEST_ID.remove();
    }
}
~~~

Key points:

1. `ThreadLocal` is **a key object**, while the corresponding value is attached to each `Thread`; two threads using the same `ThreadLocal` normally have two independent values.
2. `get()` returns `null` if no value has been set and no default value is configured via `withInitial(...)`.
3. `set(...)` assigns the value for the **current thread**, not for any other thread.
4. `remove()` deletes the entry for the current thread, which is especially important with thread pools because threads are reused.
5. A `ThreadLocal` is not automatically accessible across different processes/JVMs, nor is it a transaction/event store.

A thread pool can reuse the same worker for thousands of tasks. If a previous task sets `tenantId` or `userId` and forgets to clean up, the next task may see **stale data belonging to another request**. This is not only a memory issue, but can also become a data isolation or access control bug.

`InheritableThreadLocal` is a different mechanism that can pass values when creating **a new child thread**; it is **not a safe solution for thread pools** because workers may already be pre-created, reused, and carry outdated snapshots. Do not blindly enable context inheritance to fix async event issues.

## 3. Default: Synchronous Listeners See ThreadLocal

In Spring Framework, `ApplicationContext` uses an `ApplicationEventMulticaster`. By default, this is `SimpleApplicationEventMulticaster` calling listeners **synchronously in the publishing thread**.

~~~text
Thread: http-nio-8080-exec-1
    |
    +-- RequestContext.set("req-17")
    +-- OrderService.placeOrder()
            |
            +-- publisher.publishEvent(OrderPlaced)
                    |
                    +-- @EventListener.onOrderPlaced()
                    |        RequestContext.get() = "req-17"
                    |
                    +-- another listener (also synchronous)
    |
    +-- RequestContext.remove()
~~~

Because the callback runs on the same thread, it can access the same `ThreadLocal` if the value is still present when the callback is invoked. **Spring does not copy `ThreadLocal` into the event**; the listener simply uses **the same thread holding the value**.

Illustrative example:

~~~java
// Inside a Spring-managed bean, not a standalone program.
@EventListener
public void onOrderPlaced(OrderPlaced event) {
    String requestId = RequestContext.REQUEST_ID.get();
    logger.info("order={}, request={}", event.orderId(), requestId);
}
~~~

If `OrderPlaced` is published from a thread that never set `REQUEST_ID`, the callback will receive `null`. If `@EventListener` is changed to `@Async`, the same-thread assumption no longer holds.

### Important Conditions

- The synchronous default **does not guarantee that every application configuration is synchronous**; a project may declare an `applicationEventMulticaster` bean with a `TaskExecutor`.
- An `@EventListener` method annotated with `@Async` runs through Spring's async mechanism when `@EnableAsync` is enabled and interception applies.
- A custom `ApplicationListener` can invoke an executor itself or forward work to another thread even if the initial dispatch step is synchronous.
- If the callback spawns another task itself, the work inside that task **does not inherit** the `ThreadLocal` just because the initial callback saw it.

### ThreadLocal and Synchronous Transactions

A thread-bound transaction managed by `PlatformTransactionManager` typically has resources/state attached to the thread, for example via `TransactionSynchronizationManager`. A synchronous listener is called **within the publisher's transaction** if the event is published from a flow with an active transaction.

This does not mean a synchronous listener runs after commit. A normal `@EventListener` runs **immediately at publish time**; if the listener produces an external side effect such as sending an email, that side effect may already have occurred even if the transaction later rolls back. To react based on transaction outcome, use `@TransactionalEventListener` with the appropriate phase.

## 4. When a Listener Runs Asynchronously, What Changes?

There are two common mechanisms that should be distinguished.

### 4.1. Only One Method Uses @Async

~~~java
// Illustrative snippet: requires @EnableAsync, an executor, and a real Spring bean.
@Async("eventExecutor")
@EventListener
public void handle(OrderPlaced event) {
    // Runs on an eventExecutor thread, not the publisher's thread.
}
~~~

When `@Async` is applied, Spring schedules the method via the executor. `publishEvent` **does not wait for the asynchronous logic to finish**. The publisher's `ThreadLocal` values **are not automatically transferred to the worker**.

If an async listener throws an exception, it does not automatically propagate back to the caller of `publishEvent`; for async `void` methods, errors must be observed through `AsyncUncaughtExceptionHandler` or an appropriate monitoring mechanism. Do not assume that changes inside an async listener are still within the publisher's transaction.

### 4.2. Replacing ApplicationEventMulticaster with an Executor

An application can configure a bean with the special name `applicationEventMulticaster`:

~~~java
// Configuration example; requires a corresponding Executor eventExecutor bean.
@Bean(name = "applicationEventMulticaster")
ApplicationEventMulticaster applicationEventMulticaster(
        Executor eventExecutor) {
    SimpleApplicationEventMulticaster multicaster =
            new SimpleApplicationEventMulticaster();
    multicaster.setTaskExecutor(eventExecutor);
    return multicaster;
}
~~~

In that case, the multicaster can schedule listeners that support asynchronous execution onto the executor. An `@EventListener` without `@Async` can still run on a worker thread, so **you must not infer same-thread execution merely by seeing that a method lacks `@Async`**.

**Important exception:** not every listener can be offloaded to another thread. `ApplicationListener` implementations that report `supportsAsyncExecution() == false` are still processed on the event-publishing thread; transaction-synchronized listeners are the classic case. You should not configure a global async multicaster and then assume every transaction-bound event listener is scheduled the same way.

### 4.3. Consequences of Switching Threads

| Context type | Same thread by default | Across executor/worker |
| --- | --- | --- |
| Custom `ThreadLocal<String>` | Can read current value | Not automatically copied |
| SLF4J MDC | Usually shares the thread's context map | Not automatically copied in general configurations |
| `SecurityContextHolder` (`MODE_THREADLOCAL`) | Can read security context | Requires a designed context propagation mechanism |
| `RequestContextHolder` | Can see request attributes | Not automatically carried to worker; request must also still be valid |
| `LocaleContextHolder` | Can see thread-bound locale | Must capture/restore if truly needed |
| `TransactionSynchronizationManager` | Can see current transaction resources | **Thread-bound transaction is not copied** |
| Reactor Context in reactive flows | Not equivalent to ThreadLocal | Requires Reactor context propagation mechanisms |

These behaviors can vary depending on the application's configuration. Especially with Spring Security, how `SecurityContext` is stored can be configured differently from the default thread-local mode; use official mechanisms rather than assuming a global configuration.

## 5. Runnable Java 17+ Example: Sync Sees ThreadLocal, Async Does Not

This example uses Spring Framework 6.2.12 with `@EnableAsync` and a `ThreadPoolTaskExecutor`. No web server, database, or Spring Boot is needed.

Scenario:

1. The publisher sets `ThreadLocal` to `"request-7"`.
2. The publisher creates an event containing an **explicit** `traceId="trace-7"` and calls `publishEvent`.
3. The synchronous listener reads the publisher's `ThreadLocal`.
4. The async listener runs on a worker; before binding manually, `ThreadLocal.get()` returns `null`.
5. The async listener takes `traceId` from the event and binds the context itself inside `try/finally`, then calls `remove()`.
6. The publisher also cleans up in `finally`. The program waits using a `CountDownLatch` so stdout has a deterministic order regardless of worker timing.

Structure:

~~~text
threadlocal-listener-demo/
├── pom.xml
└── src/main/java/demo/ThreadLocalListenerDemo.java
~~~

### 5.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>threadlocal-listener-demo</artifactId>
    <version>1.0.0</version>

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
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 5.2. src/main/java/demo/ThreadLocalListenerDemo.java

~~~java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class ThreadLocalListenerDemo {

    // Thread-bound data scoped only to the current thread.
    private static final ThreadLocal<String> REQUEST_ID = new ThreadLocal<>();

    // Event carries an explicit correlation/trace value, independent of thread.
    public record JobRequested(String eventId, String traceId) {}

    public static final class State {
        final AtomicReference<String> syncSeen = new AtomicReference<>();
        final AtomicReference<String> asyncBefore = new AtomicReference<>();
        final AtomicReference<String> asyncBound = new AtomicReference<>();
        final CountDownLatch asyncDone = new CountDownLatch(1);
    }

    public static final class SyncListener {
        private final State state;

        public SyncListener(State state) {
            this.state = state;
        }

        @EventListener
        public void handle(JobRequested event) {
            state.syncSeen.set(
                    "local=" + REQUEST_ID.get()
                    + ", payload=" + event.traceId());
        }
    }

    public static final class AsyncListener {
        private final State state;

        public AsyncListener(State state) {
            this.state = state;
        }

        @Async("listenerExecutor")
        @EventListener
        public void handle(JobRequested event) {
            try {
                // Different thread, so it does not receive the publisher's ThreadLocal.
                state.asyncBefore.set(String.valueOf(REQUEST_ID.get()));

                // Explicitly bind data from the event for the processing block needing context.
                REQUEST_ID.set(event.traceId());
                state.asyncBound.set(REQUEST_ID.get());
            } finally {
                // Thread pool reuses workers, so cleanup is mandatory.
                REQUEST_ID.remove();
                state.asyncDone.countDown();
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync(proxyTargetClass = true)
    public static class Config {
        @Bean
        public State state() {
            return new State();
        }

        @Bean
        public SyncListener syncListener(State state) {
            return new SyncListener(state);
        }

        @Bean
        public AsyncListener asyncListener(State state) {
            return new AsyncListener(state);
        }

        @Bean
        public ThreadPoolTaskExecutor listenerExecutor() {
            ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(16);
            executor.setThreadNamePrefix("event-worker-");
            executor.setWaitForTasksToCompleteOnShutdown(true);
            return executor;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {

            State state = context.getBean(State.class);
            REQUEST_ID.set("request-7");
            try {
                context.publishEvent(new JobRequested("event-1", "trace-7"));

                if (!state.asyncDone.await(10, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "Async listener did not finish");
                }

                // Print only after both listeners have completed:
                // independent of executor scheduling order.
                System.out.println("sync: " + state.syncSeen.get());
                System.out.println(
                        "async-before: local=" + state.asyncBefore.get());
                System.out.println(
                        "async-bound: local=" + state.asyncBound.get());
            } finally {
                REQUEST_ID.remove();
            }

            System.out.println(
                    "publisher-cleanup: local=" + REQUEST_ID.get());
        }
    }
}
~~~

Run in the directory containing `pom.xml` with JDK 17+ and Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.ThreadLocalListenerDemo
~~~

The four lines printed by the program itself:

~~~text
sync: local=request-7, payload=trace-7
async-before: local=null
async-bound: local=trace-7
publisher-cleanup: local=null
~~~

Spring/Maven may print additional logs depending on the environment; the four lines above are the deterministic output produced in `main`.

### 5.3. Why Is the Output Correct?

- `REQUEST_ID.set("request-7")` runs on the main thread.
- `SyncListener` does not have `@Async`, and the default multicaster runs synchronously, so `REQUEST_ID.get()` is `request-7`.
- `AsyncListener` is scheduled onto a worker. `ThreadLocal` normally does not transfer between two threads, so before binding, `get()` returns `null`.
- `trace-7` is **in the event payload**, independent of thread. The listener uses it to bind context locally for its processing scope and clears it in `finally`.
- `CountDownLatch` ensures main waits for the async listener to finish. Main prints the results after `publishEvent` and after the latch, so the output does not depend on whether the async listener runs before or after the sync listener.
- After `finally` in the publisher, the `ThreadLocal` value on main is also cleared; the value on the worker was already cleared separately. No step assumes that calling `remove()` on main clears the value on the worker.

This example defines one async listener and one synchronous listener without replacing the global multicaster. If an application replaces the multicaster with an executor, both dispatch structure and waiting semantics may differ, so you should test the actual configuration.

## 6. Approach 1 — Pass Required Data Directly in the Event

For data such as `traceId`, `correlationId`, identifier-level `tenantId`, `locale`, or aggregate keys, the cleanest solution is usually to **put the needed values into the event envelope**:

~~~java
// Payload illustration; do not carry an HTTP session or mutable entity directly.
public record OrderSubmitted(
        String eventId,
        String correlationId,
        String tenantId,
        long orderId
) {}
~~~

Listeners can read those values regardless of which thread they run on:

~~~java
// Illustration inside a Spring bean.
@Async("eventExecutor")
@EventListener
public void onOrderSubmitted(OrderSubmitted event) {
    auditService.record(
            event.tenantId(), event.orderId(), event.correlationId());
}
~~~

Advantages: explicit contract, easy to test, can be forwarded through a broker if needed, and does not rely on an invisible `ThreadLocal`. However, there is also a risk: **do not assume `tenantId` in an event automatically grants access**. The listener must enforce authorization/tenant boundaries according to the application design, especially for events coming from untrusted sources.

Do not stuff an entire `SecurityContext`, `HttpServletRequest`, session, `EntityManager`, JDBC `Connection`, or live `RequestAttributes` into an event. They usually have their own lifecycle/thread semantics, hold sensitive data, or are unsafe to pass across threads.

## 7. Approach 2 — Capture and Restore a ThreadLocal with TaskDecorator

If underlying libraries genuinely require a `ThreadLocal` (for example, a legacy logger that implicitly expects a requestId), you can use `TaskDecorator` to **take a snapshot at submission time** and re-bind it in the worker for the duration of the task.

The snippet below illustrates a custom `ThreadLocal<String>`, not a general-purpose solution for copying transactions:

~~~java
// Illustration in a configuration that already defines ThreadLocal<String> REQUEST_ID.
// Requires importing org.springframework.core.task.TaskDecorator.

TaskDecorator requestIdDecorator() {
    return task -> {
        // Capture the value on the thread submitting the task.
        String captured = REQUEST_ID.get();

        return () -> {
            String previous = REQUEST_ID.get();
            try {
                if (captured == null) {
                    REQUEST_ID.remove();
                } else {
                    REQUEST_ID.set(captured);
                }
                task.run();
            } finally {
                // Restore in case the executor reuses the thread.
                if (previous == null) {
                    REQUEST_ID.remove();
                } else {
                    REQUEST_ID.set(previous);
                }
            }
        };
    };
}
~~~

Attach the decorator to the `ThreadPoolTaskExecutor` of **the exact executor used by the listener**:

~~~java
// Illustration where the executor is constructed:
ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
executor.setCorePoolSize(2);
executor.setMaxPoolSize(2);
executor.setQueueCapacity(32);
executor.setTaskDecorator(requestIdDecorator());
return executor;
~~~

When running in Spring, the executor bean is initialized according to the container lifecycle. The snapshot must be taken before the task switches threads; restore/remove logic in `finally` prevents an old task's context from leaking into the next task.

**Limitations:** `TaskDecorator` may wrap an execution callback rather than necessarily the user's original `Runnable`. Error handling needs to be designed separately, especially with `FutureTask`. Do not use a decorator to "copy an entire transaction" or bypass security checks; a transaction on one connection/thread cannot become a valid transaction on another thread merely by copying a few `ThreadLocal` values.

### Built-in Context Propagation

Spring Framework supports integration with **Micrometer Context Propagation** and `ContextPropagatingTaskDecorator` when dependencies/context accessors are properly configured. This is worth considering when you need to systematically propagate observability/MDC context across an executor. It adds capture/restore overhead, so choose where to apply it judiciously. Do not assume every custom `ThreadLocal` is automatically carried: a corresponding mechanism/accessor must exist.

With Spring Security, use official wrappers such as `DelegatingSecurityContextAsyncTaskExecutor` or a propagation mechanism compatible with the application's security setup. Avoid passing a mutable `SecurityContext` across multiple tasks yourself or relying on `InheritableThreadLocal` in a thread pool.

## 8. ThreadLocal in Transaction-Bound Listeners

Distinguish three cases (and their async combination):

| Listener | Execution timing | Thread/transaction to note |
| --- | --- | --- |
| Synchronous `@EventListener` | Immediately at publish time | Usually on the publisher thread; can see the active transaction |
| `@TransactionalEventListener(AFTER_COMMIT)` | Callback on transaction completion | Bound to the transaction at publish time; runs after successful commit |
| `@Async @EventListener` | Task on an executor | Does not automatically join the publisher's transaction or `ThreadLocal` |
| `@Async @TransactionalEventListener(AFTER_COMMIT)` | After the commit point, the listener body may be scheduled asynchronously | The publisher's transaction context can no longer be assumed on the worker |

Example:

~~~java
// Illustration inside a Spring-managed bean.
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterCommit(OrderSubmitted event) {
    // Work runs only after a successful commit.
    // Do not assume the old transaction can be committed again.
}
~~~

Important:

- `@TransactionalEventListener` registers synchronization when the event is published **inside a transaction**; by default, events outside a transaction are not processed (`fallbackExecution=false`).
- After commit, some old resources may still remain bound during the completion callback phase; if the callback needs to perform new DB writes, use an independent transaction (for example, `REQUIRES_NEW` via a proxy) or include those writes in the original transaction if atomicity is required.
- Combining `@TransactionalEventListener` and `@Async` does not pass the committed transaction to the worker. Pass only the required business data in the event and open a separate transaction if the async task must write to the DB.
- When using `SimpleApplicationEventMulticaster` with a global executor, listeners reporting `supportsAsyncExecution()==false` (including those registering transaction synchronization) must still be registered on the event-publishing thread to see the right transaction. Subsequent callback/work delegation is a separate concern.

**Warning:** copying `TransactionSynchronizationManager` resources from an old thread to a new thread is dangerous. It can cause the same JDBC `Connection`/`EntityManager` to be used concurrently, break isolation, and violate transaction semantics. Never propagate thread-bound transactions through a decorator.

### Reactive Differs from ThreadLocal

With `ReactiveTransactionManager`, transaction context typically lives in the **Reactor Context**, not in a conventional thread-bound `ThreadLocal` transaction. Spring Framework 6.1+ supports transactional event listeners for reactive transactions when the event carries the proper transaction context, for example via `TransactionalEventPublisher`. Do not apply blocking-application `ThreadLocal` copying solutions to reactive pipelines.

## 9. MDC, SecurityContext, RequestContext, and Lifecycle

### MDC and Tracing

SLF4J MDC is a common case of thread-scoped logging context. When a listener runs synchronously, logs typically share the publisher's `requestId`/`traceId`. When a listener runs asynchronously, MDC may be empty or contain leftover data from a previous task if cleanup was mishandled.

Options:

1. Include `traceId` in the event and bind MDC locally inside the listener using `try/finally`.
2. Use a properly configured `TaskDecorator`/context propagation on the executor.
3. In distributed systems, use your tracing library's standard trace context instead of manually stitching `ThreadLocal` strings across services.

MDC is not a trusted source of truth for authenticating user identity or choosing a tenant for data writes. It serves only for observability/logging as configured.

### SecurityContext

`SecurityContextHolder` has different context-storage strategies; in typical Spring Security setups, the default strategy uses `ThreadLocal`. When switching threads, the security context can be lost. If a task needs to act with the principal's permissions, use Spring Security's controlled propagation mechanisms and determine **how long those permissions remain valid**. Do not put sensitive authentication objects/tokens into a domain event just so a listener can receive them.

### RequestContextHolder and Request Attributes

An HTTP request has a bounded lifecycle. Even if `RequestAttributes` can be copied to a worker, the request may already have ended when the task executes; accessing request-scoped beans at that point may fail or be unsafe. Extract the required data (ID, locale, already-validated information) at publish time rather than keeping a reference to a live request.

### Cleanup When Using a Thread Pool

Every `set(...)` block should have a `try/finally` with `remove()` or restoration of the previous value:

~~~java
String previous = REQUEST_ID.get();
try {
    REQUEST_ID.set(event.traceId());
    process(event);
} finally {
    if (previous == null) {
        REQUEST_ID.remove();
    } else {
        REQUEST_ID.set(previous);
    }
}
~~~

If code modifies a `ThreadLocal` inside a synchronous listener **without restoring it**, it can affect the remainder of the request on **the same publisher thread**, not just the next task in a thread pool. Therefore, cleanup/restoration matters in both synchronous and asynchronous modes.

## 10. Common Mistakes

| Misconception | Consequence | Correct approach |
| --- | --- | --- |
| "Events automatically carry the publisher's ThreadLocal" | Async listeners receive null or different data | Explicit payload or controlled propagation |
| "No @Async means always on the same thread" | Multicaster may be configured with an executor | Check `applicationEventMulticaster` configuration |
| "With @Async it is still in the original transaction" | Data access lacks a transaction or sees stale data | Open a separate transaction, or use a transaction-bound event phase |
| "Using InheritableThreadLocal is enough for thread pools" | Workers inherit old snapshots or do not inherit at all | Do not use it as a propagation mechanism for pools |
| "Copy the entire TransactionSynchronizationManager to the worker" | Resource contention and broken transactions | Do not copy transactions; pass data and open a new transaction |
| "MDC is a security identity" | Trusting data meant only for logging | Validate security/tenant boundaries independently |
| "No need to call remove after setting ThreadLocal" | Data leaks across tasks/requests | `try/finally`, remove or restore |
| "ThreadLocal in a request lasts forever" | Async runs after the request has expired | Snapshot needed values into the event |
| "@Order guarantees async listeners finish in order" | Race conditions when the executor schedules tasks | Synchronize workflow using `Future`/latch or orchestration mechanisms |
| "TaskDecorator automatically copies every kind of context" | Missing accessors or copying wrong data | Choose the right decorator/accessor; verify with real tests |

## 11. Testing Key Scenarios

### Testing Synchronous Listeners

1. Set `ThreadLocal` on the test thread and publish the event.
2. Verify the synchronous listener read the expected value.
3. Call `remove()`, publish another event, and confirm the listener reads `null`.
4. Verify the listener does not overwrite the caller's context or has full restoration logic.

### Testing Asynchronous Listeners

1. Enable `@EnableAsync` and a real executor; do not substitute `SyncTaskExecutor` if the goal is to test context loss.
2. Publish an event with an explicit `correlationId`.
3. Use `CountDownLatch` or `CompletableFuture` to await task completion with a timeout; **do not rely on `Thread.sleep`**.
4. Assert that the worker does not have the publisher's `ThreadLocal` when propagation is not configured.
5. Enable the decorator and assert that only the captured values actually appear in the worker.
6. Have the worker process two tasks with different contexts on **the same pool thread**, and verify the second task does not see the first task's data.
7. Simulate the listener throwing an exception, and verify logging/metrics/handler behavior and that cleanup still executes.

### Testing Transactions and Security

- Publish an event inside `@Transactional` and compare a synchronous callback with `@TransactionalEventListener(AFTER_COMMIT)` on both commit and rollback paths.
- For async listeners, verify they are not reading the old transaction via `TransactionSynchronizationManager.isActualTransactionActive()` on the worker (do not confuse active transaction with whether bound resources exist).
- If security context is required, test missing-context paths, revoked permissions, and multiple users/tenants sharing the same executor.
- For reactive pipelines, test Reactor Context instead of relying on `ThreadLocal` tied to thread names.

## 12. Design Checklist

1. Does the listener actually run on the publisher thread? Is there `@Async` or a multicaster executor?
2. Is the data in `ThreadLocal` needed for business logic or only for logging?
3. Which values should be placed directly in the **event payload** to avoid implicit dependencies?
4. If propagation is required, is the snapshot captured **before switching threads**?
5. Is there a `finally` block to restore/remove on both worker and publisher?
6. Are MDC/request/security `ThreadLocal` values being confused with transaction context?
7. Does a new transaction need to be opened, or should the callback run on the `AFTER_COMMIT` phase?
8. Does the executor/thread pool have queue bounds, timeouts, an error handler, and monitoring?
9. Do tests prove there is no data leakage across tasks sharing the same thread?
10. Do reactive pipelines use context propagation following the Reactor model?

**Conclusion:** With Spring Application Events, `ThreadLocal` inside a listener depends on **the executing thread**, not on the event name. Synchronous listeners see the publisher's thread-bound values by default; asynchronous listeners do not automatically receive them. Prefer passing **necessary data explicitly in the event**; use `TaskDecorator`/dedicated propagation mechanisms only for appropriate contexts, never copy live transactions across threads, and always clean up to avoid context leaks.

## Official Documentation

- Spring Framework 6.2 — Application Events and asynchronous listeners: https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html
- Spring Framework 6.2 — Observability for Application Events, ThreadLocal, and context propagation: https://docs.spring.io/spring-framework/reference/6.2/integration/observability.html
- Spring Framework 6.2 — SimpleApplicationEventMulticaster Javadoc: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html
- Spring Framework 6.2 — TaskDecorator Javadoc: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/core/task/TaskDecorator.html
- Spring Framework 6.2 — Async execution: https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html
- Spring Framework 6.2 — Transaction-bound Events: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html
