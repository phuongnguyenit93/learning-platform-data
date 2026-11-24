# ContextPropagatingTaskDecorator in Spring Application Events

## 1. Objectives

`ContextPropagatingTaskDecorator` is a class in Spring Framework (since **Spring 6.1**) that wraps tasks before they run on another thread, preserving context values supported by Micrometer Context Propagation. It is especially useful when `@EventListener` or `@Async @EventListener` hands off work from the event-publishing thread to a `TaskExecutor`.

In a real application, a request may carry a trace ID, correlation ID, logging MDC, observation context, or custom `ThreadLocal` values. With a default synchronous listener, the callback usually runs directly on the publisher thread and sees that thread-bound context. When a listener runs asynchronously, the worker thread **does not automatically have** those values.

The decorator **captures context at task submission time** and **restores it within the worker's execution scope**, but it does not automatically copy every `ThreadLocal`; you need a corresponding accessor. It also **does not** automatically propagate JDBC/JPA transactions, guarantee successful event delivery, or turn async into sync.

After this lesson, you will:

- Distinguish `ThreadLocal`, `TaskDecorator`, `ContextRegistry`, `ThreadLocalAccessor`, `ContextSnapshot`, and `ContextSnapshotFactory`.
- Attach `ContextPropagatingTaskDecorator` to the right executor used for application events.
- Write a Java 17+ Spring Framework demo with two executors, clearly demonstrating behavior with and without context propagation.
- Understand snapshotting, restoration, isolation, MDC/observation, security/transactions, and Reactor Context.
- Know common pitfalls and how to test thread-pool reuse, context leaks, and overhead.

## 2. Why Do Async Listeners Lose ThreadLocal?

`ThreadLocal<T>` variables bind **one value per thread**:

~~~java
// Illustrated inside a Java class.
private static final ThreadLocal<String> TRACE_ID = new ThreadLocal<>();

public static void handleRequest() {
    TRACE_ID.set("trace-17");
    try {
        System.out.println(TRACE_ID.get()); // trace-17
    } finally {
        TRACE_ID.remove();
    }
}
~~~

On another thread, `TRACE_ID.get()` normally returns `null` unless that thread already has a value of its own or some mechanism transfers it across.

Spring Application Events uses `ApplicationEventMulticaster`. With the default `SimpleApplicationEventMulticaster`, synchronous listeners run on the same thread as `publishEvent(...)`:

~~~text
request-handler thread
    |
    +-- TRACE_ID = trace-17
    +-- publisher.publishEvent(OrderCreated)
            |
            +-- synchronous @EventListener
            |       TRACE_ID = trace-17
            |
            +-- @Async @EventListener
                    |
                    +-- executor queue
                    +-- worker thread
                            TRACE_ID = null if not propagated
~~~

Therefore, **a synchronous listener seeing `ThreadLocal` does not mean the event payload contains `ThreadLocal`**. It simply runs on the same thread holding that value. If the application configures an `applicationEventMulticaster` backed by an executor, even a listener without `@Async` may run on a worker.

`InheritableThreadLocal` is not a suitable solution for thread pools: it inherits at child-thread creation time, whereas workers usually already exist and are reused across many requests. You need **per-task** capture and restoration.

## 3. Key Components

| Component | Responsibility |
| --- | --- |
| `TaskDecorator` | Spring interface taking a `Runnable` and returning a wrapped `Runnable` |
| `ContextPropagatingTaskDecorator` | Uses a Micrometer factory to capture and restore context on the worker |
| `ContextRegistry` | Holds the list of accessors that know how to read/write context types |
| `ThreadLocalAccessor<V>` | Reads, sets, and clears a specific `ThreadLocal` |
| `ContextAccessor` | Accesses map-like structured contexts, such as Reactor Context |
| `ContextSnapshot` | A snapshot of selected context values |
| `ContextSnapshotFactory` | Creates snapshots according to the registry and capture policy |
| `ThreadPoolTaskExecutor` | Spring executor supporting `setTaskDecorator(...)` |

Basic workflow:

~~~text
publisher thread
  ThreadLocal traceId=A
       |
       +-- execute(task)
               |
               +-- decorator.decorate(task)
               |       ContextSnapshot capture=A
               |
             task queue
               |
             worker thread
               +-- open snapshot scope -> traceId=A
               +-- run listener/task
               +-- close scope -> restore worker state
~~~

The snapshot is captured at **submission time**, not when the worker begins running. For instance, if the publisher changes `traceId` from A to B after submitting task 1, task 1 still uses snapshot A; task 2 submitted when the value is B uses snapshot B.

### Constructors and Dependency

Spring Framework 6.2 API:

~~~java
// Uses the default ContextSnapshotFactory.
new ContextPropagatingTaskDecorator();

// Explicitly specifies a ContextSnapshotFactory.
new ContextPropagatingTaskDecorator(snapshotFactory);
~~~

The `io.micrometer:context-propagation` library must be on the classpath. Simply adding the decorator does not automatically recognize custom `ThreadLocal` variables. A `ThreadLocalAccessor` must be registered with the right `ContextRegistry`.

According to the Spring Javadoc, capturing and restoring introduces **overhead** and should not be enabled unconditionally for very large volumes of tiny tasks.

## 4. Configuring an Executor with the Decorator

Configuration example in Spring:

~~~java
// Illustration: @Bean in @Configuration, not a standalone file.
@Bean("propagatingExecutor")
ThreadPoolTaskExecutor propagatingExecutor(ContextRegistry registry) {
    ContextSnapshotFactory factory = ContextSnapshotFactory.builder()
            .contextRegistry(registry)
            .build();

    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(2);
    executor.setQueueCapacity(64);
    executor.setThreadNamePrefix("event-");
    executor.setTaskDecorator(new ContextPropagatingTaskDecorator(factory));
    return executor;
}
~~~

The Spring container initializes the executor bean according to its lifecycle. If you construct `ThreadPoolTaskExecutor` outside the container, call `initialize()` before using it and `shutdown()` after finishing.

Listener method intending to use this executor:

~~~java
// Spring bean illustration; requires @EnableAsync in configuration.
@Async("propagatingExecutor")
@EventListener
public void onOrderCreated(OrderCreated event) {
    // Can read ThreadLocal values captured by accessors.
}
~~~

**You must attach the decorator to the exact executor selected by `@Async("...")`.** Another executor in the application will not gain propagation merely because a decorator bean exists somewhere in the container.

## 5. Complete Java 17+ Example

We build a Spring Framework 6.2.12 application without a web server. Two async listeners both receive `ProbeEvent`, but use two different executors:

- `plainExecutor` with no decorator: the worker does not receive the custom `ThreadLocal`.
- `propagatingExecutor` configured with `ContextPropagatingTaskDecorator` and a `ContextSnapshotFactory` pointing to the registry containing the custom accessor.

The publisher emits two events with different `TRACE_ID` values (`trace-one` and `trace-two`). `CountDownLatch` awaits all four callbacks before printing. Each executor has a single worker thread so we can verify thread reuse does not retain the previous event's value.

Structure:

~~~text
context-propagation-events/
├── pom.xml
└── src/main/java/demo/ContextPropagationEventsDemo.java
~~~

### 5.1. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>context-propagation-events</artifactId>
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
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>context-propagation</artifactId>
            <version>1.1.3</version>
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

### 5.2. `src/main/java/demo/ContextPropagationEventsDemo.java`

~~~java
package demo;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import io.micrometer.context.ContextRegistry;
import io.micrometer.context.ContextSnapshotFactory;
import io.micrometer.context.ThreadLocalAccessor;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class ContextPropagationEventsDemo {

    private static final ThreadLocal<String> TRACE_ID = new ThreadLocal<>();

    public record ProbeEvent(String name) {}

    public static final class Results {
        final Map<String, String> seen = new ConcurrentHashMap<>();
        final CountDownLatch done = new CountDownLatch(4);

        public void record(String listener, ProbeEvent event, String value) {
            seen.put(listener + "-" + event.name(), String.valueOf(value));
            done.countDown();
        }

        public String value(String key) {
            return seen.get(key);
        }
    }

    public static class PlainListener {
        private final Results results;

        public PlainListener(Results results) {
            this.results = results;
        }

        @Async("plainExecutor")
        @EventListener
        public void on(ProbeEvent event) {
            results.record("plain", event, TRACE_ID.get());
        }
    }

    public static class PropagatingListener {
        private final Results results;

        public PropagatingListener(Results results) {
            this.results = results;
        }

        @Async("propagatingExecutor")
        @EventListener
        public void on(ProbeEvent event) {
            results.record("propagated", event, TRACE_ID.get());
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync(proxyTargetClass = true)
    public static class Config {
        @Bean
        public Results results() {
            return new Results();
        }

        @Bean
        public ContextRegistry contextRegistry() {
            ContextRegistry registry = new ContextRegistry();

            registry.registerThreadLocalAccessor(
                new ThreadLocalAccessor<String>() {
                    @Override
                    public Object key() {
                        return "demo.trace-id";
                    }

                    @Override
                    public String getValue() {
                        return TRACE_ID.get();
                    }

                    @Override
                    public void setValue(String value) {
                        TRACE_ID.set(value);
                    }

                    @Override
                    public void setValue() {
                        TRACE_ID.remove();
                    }
                });
            return registry;
        }

        @Bean("plainExecutor")
        public ThreadPoolTaskExecutor plainExecutor() {
            ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(16);
            executor.setThreadNamePrefix("plain-");
            executor.setWaitForTasksToCompleteOnShutdown(true);
            return executor;
        }

        @Bean("propagatingExecutor")
        public ThreadPoolTaskExecutor propagatingExecutor(
                ContextRegistry registry) {
            ContextSnapshotFactory factory =
                    ContextSnapshotFactory.builder()
                            .contextRegistry(registry)
                            .build();

            ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(16);
            executor.setThreadNamePrefix("propagating-");
            executor.setTaskDecorator(
                    new ContextPropagatingTaskDecorator(factory));
            executor.setWaitForTasksToCompleteOnShutdown(true);
            return executor;
        }

        @Bean
        public PlainListener plainListener(Results results) {
            return new PlainListener(results);
        }

        @Bean
        public PropagatingListener propagatingListener(Results results) {
            return new PropagatingListener(results);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {
            Results results = context.getBean(Results.class);

            try {
                TRACE_ID.set("trace-one");
                context.publishEvent(new ProbeEvent("one"));

                TRACE_ID.set("trace-two");
                context.publishEvent(new ProbeEvent("two"));
            } finally {
                TRACE_ID.remove();
            }

            if (!results.done.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Async listeners timed out");
            }

            System.out.println("plain-one=" + results.value("plain-one"));
            System.out.println("propagated-one="
                    + results.value("propagated-one"));
            System.out.println("plain-two=" + results.value("plain-two"));
            System.out.println("propagated-two="
                    + results.value("propagated-two"));
            System.out.println("publisher-after=" + TRACE_ID.get());
        }
    }
}
~~~

Run from the directory containing `pom.xml` with JDK 17+ and Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.ContextPropagationEventsDemo
~~~

The five lines printed by the program itself (excluding any Spring/Maven logs):

~~~text
plain-one=null
propagated-one=trace-one
plain-two=null
propagated-two=trace-two
publisher-after=null
~~~

### 5.3. Why Is the Result Deterministic?

1. The publisher sets `TRACE_ID="trace-one"` and publishes event `one`.
2. The plain executor runs the callback on another worker thread where the custom `ThreadLocal` is unset, so `plain-one=null`.
3. The propagating executor captures `trace-one` via `ThreadLocalAccessor` at task submission. Inside the worker's scope, the listener reads `trace-one`.
4. The publisher updates `TRACE_ID` to `trace-two` and publishes event `two`. A new snapshot captures the new value; thus `propagated-two=trace-two` even if the worker executes after the publisher has cleared its `ThreadLocal`.
5. `ContextPropagatingTaskDecorator` restores the worker's context when the task finishes; the worker thread can be reused safely.
6. `main` calls `TRACE_ID.remove()` in `finally` to clean up **the publisher thread**.
7. `CountDownLatch` waits for all four callbacks; `ConcurrentHashMap` provides thread-safe result storage. `main` prints in a fixed order without guessing executor scheduling.

**Note:** the program does not measure exact timestamps/latency and does not require the worker to start before the publisher switches context. What is verified is **per-submission** snapshotting rather than a live reference to `main`'s `ThreadLocal`.

## 6. Using the Decorator with a Custom ApplicationEventMulticaster

Besides `@Async`, you can configure a bean named `applicationEventMulticaster` to offload listeners that support async execution onto an executor:

~~~java
// Illustration in Spring @Configuration, not a standalone program.
@Bean(name = "applicationEventMulticaster")
public SimpleApplicationEventMulticaster multicaster(
        ThreadPoolTaskExecutor propagatingExecutor) {
    SimpleApplicationEventMulticaster m =
            new SimpleApplicationEventMulticaster();
    m.setTaskExecutor(propagatingExecutor);
    return m;
}
~~~

The executor must have the decorator configured. With this setup, an `@EventListener` **without `@Async`** can still run on a worker, depending on the listener's `supportsAsyncExecution()`. Therefore, you must never deduce the callback thread solely from annotations on the method.

**Special case:** listeners that must run on the publisher thread (`ApplicationListener.supportsAsyncExecution()==false`), such as listeners registering transaction synchronization, are not moved to async solely by the multicaster executor. Do not use a global async configuration to try to "copy a transaction" to a worker; transactions must be handled according to their own lifecycle.

Moving all events to async also changes listener completion ordering, exception propagation paths, and startup/shutdown timing. When only one handler needs async, `@Async("propagatingExecutor")` is usually easier to isolate.

## 7. Registry, Snapshot, and Restore in Detail

### 7.1. Registering a Custom ThreadLocal

Micrometer needs to know the **key**, how to read, how to set, and how to clear a `ThreadLocal`. The accessor in the example:

~~~java
// Illustration of the ThreadLocalAccessor<String> methods.
@Override
public Object key() {
    return "demo.trace-id";
}

@Override
public String getValue() {
    return TRACE_ID.get();
}

@Override
public void setValue(String value) {
    TRACE_ID.set(value);
}

@Override
public void setValue() {
    TRACE_ID.remove();
}
~~~

If you forget to register the accessor or the factory uses **a different registry**, the custom `ThreadLocal` will not be captured. When using `ContextSnapshotFactory.builder().contextRegistry(registry).build()`, ensure this `registry` actually holds the accessors for the desired contexts.

For framework-integrated observation/MDC, accessors may be registered automatically or through the corresponding integration, but **do not assume by default that every logging backend and every custom key has an accessor**.

### 7.2. A Snapshot Is Not a Live Link

~~~text
t0: Thread A TRACE_ID = trace-one
t1: submit(task-one) => snapshot(trace-one)
t2: Thread A TRACE_ID = trace-two
t3: submit(task-two) => snapshot(trace-two)
t4: Thread A remove()
t5: Thread B run(task-one) => sees trace-one
t6: Thread B run(task-two) => sees trace-two
~~~

This is a **snapshot of the value at capture time**. If a context holds a reference to a mutable object, that does not mean the decorator automatically deep-copies that object. Avoid passing large mutable objects, HTTP requests/sessions, or live database resources across thread boundaries.

### 7.3. Restore and Thread-Pool Reuse

After the task runs, the propagation scope must **restore the worker's previous state**. If the worker originally had no value, the bound value is removed; if the worker previously held its own value, the scope must restore the appropriate value.

This is crucial for thread pools: forgetting cleanup can cause a task for tenant A to make a task for tenant B mistakenly read A's correlation/security context. When writing a custom `TaskDecorator`, always use `try/finally` to restore; with Micrometer, `ContextSnapshot.Scope` manages the bind/restore lifecycle.

Pay attention to the **missing key / clearMissing** policy in `ContextSnapshotFactory`. Do not assume a context missing a value on the publisher will automatically clear every pre-existing `ThreadLocal` on the worker in every configuration; test both the "present value" and "absent value" directions.

## 8. MDC, Observation, Security, and Transactions

### Logging MDC / Micrometer Observation

MDC and tracing/observation often store correlation info in thread-bound state. `ContextPropagatingTaskDecorator` is primarily useful here: trace/span/MDC are transferred to the worker when the corresponding accessor and integration are present.

However, a log line showing `tenantId=tenant-7` in MDC **does not prove authorization** for that tenant. MDC serves observability; security/tenant authorization must still be verified via trusted sources.

### Spring Security

`SecurityContextHolder` normally uses `ThreadLocal` under its default strategy. For an async task to use a principal's identity under an explicit policy, Spring Security provides mechanisms such as `DelegatingSecurityContextAsyncTaskExecutor`. Do not assume `ContextPropagatingTaskDecorator` copies the entire `SecurityContext` automatically; sensitive contexts require explicit decisions on how they are propagated, their lifecycle, and permission expiration.

### Transaction Synchronization

`TransactionSynchronizationManager` can hold a JDBC `Connection`, `EntityManager`, and transaction state on the publisher thread. **Never register an accessor to copy those raw transaction resources to a worker**. A transaction does not become thread-safe merely by copying `ThreadLocal` entries.

If an async listener must write to the DB, start **a separate transaction on the worker**, such as calling a `@Transactional(propagation = Propagation.REQUIRES_NEW)` Spring service through a proxy when appropriate. If you only want to react after commit, use `@TransactionalEventListener(phase = AFTER_COMMIT)`, which is a **transaction-bound event** mechanism, not decorator propagation.

`@TransactionalEventListener` ignores events published outside a transaction by default when `fallbackExecution=false`; a decorator cannot compensate for the absence of a transaction on the event-publishing thread.

### HTTP Request / Locale

`RequestContextHolder` and `LocaleContextHolder` can hold request/thread-bound context. Never pass a raw `HttpServletRequest` or session into a task running long after the request ends; request-scoped beans may no longer be valid. Pass IDs, locale, correlation, or verified data in the event when needed.

### Reactive

With `ReactiveTransactionManager` and Reactor pipelines, context typically lives in the **Reactor Context**, not solely in `ThreadLocal`. Micrometer Context Propagation has mechanisms to bridge between context types when properly configured. Never use `ThreadLocal` copying as a substitute for Reactor's transaction context.

## 9. When to Use It, and When Not To?

| Need | Typically appropriate approach |
| --- | --- |
| Propagating trace/observation/MDC across an `@Async` executor | `ContextPropagatingTaskDecorator` with proper accessors |
| Passing business IDs, aggregate IDs, validated tenant IDs | Explicit fields in the event payload |
| Writing data in an async listener | Open a separate transaction matching business semantics |
| Passing security context to a worker | Spring Security's dedicated propagation mechanisms |
| Reactive flows | Reactor Context and appropriate adapters |
| Emitting durable integration events across crashes | Outbox, broker, retries, idempotency; a decorator does not solve this |
| Millions of very short tasks per second | Benchmark overhead before enabling the decorator broadly |

Spring's Javadoc warns that context capture/restore overhead may be unsuitable for very large numbers of tiny tasks. Balance correlation needs against throughput, latency, thread allocation, and the number of registered accessors.

Do not assume the decorator guarantees task execution, event redelivery, or listener completion. Tasks may be rejected if the executor is saturated, may fail, or may be interrupted during shutdown before running; appropriate error handling and monitoring are still required.

## 10. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Forgetting the Micrometer `context-propagation` dependency | Missing `ContextSnapshot` API | Add a compatible dependency |
| Creating the decorator but forgetting a custom `ThreadLocalAccessor` | Worker still reads `null` | Register the accessor in the right `ContextRegistry` |
| Attaching the decorator to a different executor than `@Async` uses | Context is still lost | Check executor qualifier names and multicaster |
| Using `InheritableThreadLocal` for thread pools | Stale values or wrong submission context | Capture per task and restore properly |
| Thinking the decorator automatically copies `SecurityContext`/transactions | Lost context or invalid resource access | Choose proper propagation; never copy transactions |
| Treating MDC as an authorization source | Risk of cross-tenant data exposure | Authorize using an independent trusted source |
| Keeping a mutable request/session inside a context snapshot | Expired object or concurrent mutation | Use explicit IDs/data snapshots |
| Skipping cleanup when the task completes | `ThreadLocal` leaks between requests | Micrometer scope or `try/finally` |
| Relying on `@Order` for async completion ordering | Race conditions | Latch, `Future`, or explicit workflow |
| Ignoring rejected or timed-out tasks | Unprocessed events | Bounded queue, logging, and error handling |
| Treating the decorator as a retrying message queue | Events can be lost if the process crashes | Outbox / durable messaging when required |

## 11. Testing and Operations

### Proper Cross-Thread Testing

1. Use a real executor with worker threads; do not substitute `SyncTaskExecutor` when testing context loss.
2. Publish two events with two different `TRACE_ID` values; verify the decorated worker receives the right snapshot per submission.
3. Wait using `CountDownLatch` or `Future` with a timeout; do not rely on `Thread.sleep`.
4. Test a second task on **the same worker** to catch stale context and restoration bugs.
5. Test when the publisher **has no** `ThreadLocal` and verify the appropriate `clearMissing` policy.
6. Simulate an exception in the task, confirming worker context is restored and the error is recorded.
7. Test both `@Async` and multicaster executors depending on the actual design.
8. If propagating security context, test multiple principals/tenants and revoked permissions.

### Metrics to Observe

Track pending task count, executor rejections, callback failure rate, queue time, logs missing correlation IDs, shutdown behavior, and latency before/after enabling the decorator. Avoid "fixing" missing values by setting a shared default trace ID for all tasks; that obscures real causal relationships.

## 12. Final Checklist

1. Does the listener run on a different thread from the publisher? Via `@Async` or a multicaster executor?
2. Is the decorator attached to **the exact right executor**?
3. Are the `context-propagation` dependency and required accessors present?
4. Does the factory use **the exact `ContextRegistry`** where the accessors are registered?
5. Is the context snapshot captured at task submission time?
6. Does the scope restore/clear worker context, even when the callback throws?
7. Are explicit payloads used for business data instead of relying on `ThreadLocal`?
8. Are live transaction resources and active requests/sessions kept off other threads?
9. Have two consecutive requests/tenants on the same thread pool been tested?
10. Has capture/restore overhead been measured under realistic task volume?

**Conclusion:** `ContextPropagatingTaskDecorator` is a tool for propagating **contexts that have registered accessors** across thread boundaries using Micrometer. To use it properly in Spring Application Events, attach it to the executor that actually runs the listeners, capture per submission, and ensure restoration after the task. Keep business data in the event, keep transactions and authorization within their proper boundaries, and never use a decorator as a substitute for durable messaging.

## Official Documentation

- Spring Framework 6.2 — ContextPropagatingTaskDecorator Javadoc: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html
- Spring Framework 6.2 — Observability and Application Events: https://docs.spring.io/spring-framework/reference/6.2/integration/observability.html
- Spring Framework — ThreadPoolTaskExecutor: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html
- Micrometer Context Propagation — Purpose: https://docs.micrometer.io/context-propagation/reference/purpose.html
- Micrometer Context Propagation — Usage: https://docs.micrometer.io/context-propagation/reference/usage.html
