# TaskDecorator for Logging Context in Spring Framework Application Events

## 1. The Problem to Solve

An HTTP request handling an order typically attaches fields such as `traceId`, `requestId`, or `correlationId` to the **Mapped Diagnostic Context (MDC)** so every log line can be linked to the same request. When a service publishes `OrderPlaced` via `ApplicationEventPublisher.publishEvent(...)`, a synchronous `@EventListener` running on the same thread usually reads that MDC.

However, an asynchronous listener using `@Async` or an executor configured on `ApplicationEventMulticaster` runs on a **different worker thread**. Because MDC is usually stored via `ThreadLocal`, the publisher's context map **does not automatically transfer** to the worker. A listener may process the business data properly yet emit logs missing `traceId`.

```text
Request thread "http-1"
    MDC.traceId = trace-A
        |
        | publishEvent(OrderPlaced)
        v
Spring Event Multicaster
        |
        | invoke @Async("eventExecutor") on listener
        v
ThreadPoolTaskExecutor
        |
        | submit task
        v
Worker thread "events-1"
    MDC.traceId = ?         <-- not automatically copied
        |
        v
log.info("Order event processed")
```

If a worker retains MDC from a previous task because code lacked cleanup, logs for `OrderPlaced("ORD-B")` might even get tagged with `trace-A` by mistake. This is dangerous in multi-user/multi-tenant systems, as logs become not only hard to investigate but can also mislead about the origin of data.

**`TaskDecorator` is Spring's extension point for wrapping tasks executed by an executor.** We use it to capture MDC when submitting a task, install it on the worker while executing, and **restore the old context in `finally`**.

Lesson goals: understand the MDC lifecycle between publisher and listener, write a safe decorator, configure `ThreadPoolTaskExecutor` properly, verify with a runnable Java 17 program, and distinguish logging context from transactions/security/tracing.

## 2. Terminology and Boundaries

| Concept | Role | Key takeaway |
| --- | --- | --- |
| `SLF4J MDC` | Key-value map for the currently running thread's logs | Not a business data store |
| `ThreadLocal` | Per-thread data storage | Pooled workers usually lack the submitting thread's MDC |
| `TaskDecorator` | Wraps a `Runnable` before the executor runs it | Capture, install, restore execution context |
| `ThreadPoolTaskExecutor` | Spring-managed pool | Supports `setTaskDecorator(...)` |
| `@Async` | Routes method calls through Spring async infrastructure | Requires `@EnableAsync` and proxy invocation |
| `@EventListener` | Registers a typed event callback | May run synchronously or be dispatched to an executor |
| `ApplicationEventPublisher` | Publishes events inside the context | Does not persist events durably on its own |

Note: `TaskDecorator` **does not sit on the event class**, does not alter the payload, and does not "register" listeners. It is attached **to the executor**. If the application has multiple executors, you must choose the exact one where MDC propagation is desired.

### Contract of TaskDecorator

The `org.springframework.core.task.TaskDecorator` interface has one method:

```java
Runnable decorate(Runnable runnable);
```

This is the simplified API signature. Spring invokes the decorator when preparing to execute a task and uses the returned `Runnable` as the wrapper. According to the Javadoc, the input object **may already be an infrastructure-wrapped callback**, not necessarily the raw original `Runnable` submitted by the application.

The decorator is well suited for establishing an execution context scope around `runnable.run()`. It is not the sole place to handle every task exception, especially when the task is wrapped in a `FutureTask`.

## 3. The Capture – Install – Run – Restore Principle

A task typically passes through two distinct moments:

- **Submission time:** the publisher thread calls `publishEvent(...)`; `@Async` infrastructure submits the task to the executor.
- **Execution time:** a worker pulls the task from the queue and runs the listener body.

If MDC changes **after submission but before execution**, the listener still needs to see the snapshot **from submission time**. For example, if the publisher sends A under `trace-A`, changes MDC to `trace-B` to send B, and then clears MDC, task A may only start running afterward. Task A must still see `trace-A`.

Safe flow:

```text
Publisher thread                       Worker thread
--------------------------------      -------------------------
MDC = {traceId: trace-A}
        |
        | executor receives task
        v
decorate(delegate)
captured = copy(MDC)
        |
        +-----------------------------> Runnable.run()
                                          previous = copy(MDC)
                                          install(captured)
                                          try {
                                              delegate.run()
                                          } finally {
                                              restore(previous)
                                          }
```

There are **four important rules**:

1. Capture on the **submitting thread**, not the worker: the worker does not yet have the publisher's info.
2. Copy MDC as a **snapshot** rather than keeping mutable data that the publisher could alter externally.
3. If the caller **has no MDC**, the worker must run with an empty context for that task instead of retaining an old context.
4. Restore the worker's context in `finally`, even if the listener throws an exception.

## 4. Writing Your Own MDC TaskDecorator

A clean and correct implementation:

```java
package example;

import java.util.Map;
import org.slf4j.MDC;
import org.springframework.core.task.TaskDecorator;

public final class MdcTaskDecorator implements TaskDecorator {

    @Override
    public Runnable decorate(Runnable delegate) {
        // Executes when the task is submitted from the publisher.
        Map<String, String> captured =
                MDC.getCopyOfContextMap();

        return () -> {
            // Executes on the worker when the task starts.
            Map<String, String> previous =
                    MDC.getCopyOfContextMap();

            try {
                if (captured == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(captured);
                }

                delegate.run();
            } finally {
                if (previous == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(previous);
                }
            }
        };
    }
}
```

This is a class usable in a Spring project, though verifying it requires an executor, a logging backend supporting MDC, and a task actually dispatched through the pool. The complete example is in section 6.

### 4.1. Taking a Copy

`MDC.getCopyOfContextMap()` returns a `Map<String,String>` that is **a copy of the current context map**, or `null` when no map exists. Never call this method **only inside the worker lambda** expecting to read the publisher's MDC: by then you are on a different thread.

### 4.2. Installing Context or Clearing

If `captured` is non-null, `MDC.setContextMap(captured)` replaces the worker's existing MDC. If `captured` is `null`, you must call `MDC.clear()`. The null branch is especially critical in thread pools that reuse workers to avoid logs from a request without a `traceId` mistakenly picking up an ID from the previous request.

### 4.3. Restoring Previous

You should not blindly call `clear()` unconditionally after execution. The worker might already be inside another wrapper that installed a valid context, or an executor might execute inline under a certain policy. The **save → replace → restore** pattern lets the decorator compose cleanly with outer contexts.

### 4.4. Using `finally`

If `delegate.run()` fails, `finally` still executes and restores MDC. An asynchronous listener must never leave a `traceId` behind on a thread returned to the pool.

**Counter-example:**

```java
return () -> {
    MDC.setContextMap(captured);
    delegate.run();
    // Wrong: does not restore upon completion or exception.
};
```

This snippet is intentionally broken and **must not be used in production**. It neither protects the worker when a task fails nor preserves/cleans up prior context.

## 5. Configuring the Decorator on the Right Executor

Inside a `@Configuration` class:

```java
@Bean("eventExecutor")
public ThreadPoolTaskExecutor eventExecutor() {
    ThreadPoolTaskExecutor executor =
            new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(50);
    executor.setThreadNamePrefix("events-");
    executor.setTaskDecorator(new MdcTaskDecorator());
    return executor;
}
```

Then the listener:

```java
@Async("eventExecutor")
@EventListener
public void onOrder(OrderPlaced event) {
    log.info("Handle orderId={}", event.orderId());
}
```

`@EnableAsync` must be enabled. The listener must be a Spring bean eligible for proxying—for example, a `public` method in a non-`final` class invoked through Spring's event infrastructure, not via internal self-invocation `this.onOrder(...)`.

When `@Async("eventExecutor")` specifies an executor name, Spring looks up the matching executor bean by bean name/qualifier. If you use `@Async` without specifying a name, it goes through the default executor selection mechanism; it **does not automatically know** that the application wants to use the decorated pool.

With a Spring `ThreadPoolTaskExecutor` bean, the container manages executor initialization and shutdown. Do not instantiate `new ThreadPoolTaskExecutor()` per event or submit tasks to an unmanaged executor expecting a decorator on another bean to take effect.

## 6. Java 17 + Maven Example: Three Events Through the Same Worker

The following example demonstrates **per-task MDC snapshotting** and **zero context leakage** when a worker thread is reused. No web server or database is needed.

Three events:

- `ORD-A` is published under `traceId=trace-A`.
- `ORD-B` is published under `traceId=trace-B`.
- `ORD-C` is published when the publisher **has no traceId**.

The executor has `corePoolSize=1`, `maxPoolSize=1`, so all three tasks run on the same worker. The listener is annotated with `@Async("eventExecutor")` and `@EventListener`. Results are recorded into a `ConcurrentHashMap`; `CountDownLatch` waits for all three callbacks before inspecting.

### Directory Structure

```text
mdc-event-context/
├── pom.xml
└── src/main/
    ├── java/example/MdcEventDemo.java
    └── resources/logback.xml
```

### File `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>mdc-event-context</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
        </dependency>
        <dependency>
            <groupId>ch.qos.logback</groupId>
            <artifactId>logback-classic</artifactId>
            <version>1.5.12</version>
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
                <version>3.5.0</version>
                <configuration>
                    <mainClass>example.MdcEventDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### File `src/main/resources/logback.xml`

```xml
<configuration>
    <appender name="STDOUT"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>trace=%X{traceId:-none} thread=%thread %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="demo.events" level="INFO" additivity="false">
        <appender-ref ref="STDOUT"/>
    </logger>

    <root level="ERROR">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
```

`%X{traceId:-none}` is Logback's pattern to print MDC key `traceId`, defaulting to `none` when absent. `%thread` lets you verify which thread the logger ran on. Here Logback acts as an SLF4J backend that genuinely supports MDC; swapping in a backend without MDC support will yield different results.

### File `src/main/java/example/MdcEventDemo.java`

```java
package example;

import java.util.HashSet;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.task.TaskDecorator;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class MdcEventDemo {

    public record OrderPlaced(String orderId) {}

    public static final class MdcTaskDecorator implements TaskDecorator {
        @Override
        public Runnable decorate(Runnable task) {
            Map<String, String> captured =
                    MDC.getCopyOfContextMap();

            return () -> {
                Map<String, String> previous =
                        MDC.getCopyOfContextMap();
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
        }
    }

    public static final class Evidence {
        private final CountDownLatch done =
                new CountDownLatch(3);
        private final Map<String, String> traces =
                new ConcurrentHashMap<>();
        private final Map<String, String> threads =
                new ConcurrentHashMap<>();

        public void record(String orderId, String traceId,
                           String workerThread) {
            traces.put(orderId,
                    traceId == null ? "<none>" : traceId);
            threads.put(orderId, workerThread);
            done.countDown();
        }

        public void awaitAll() throws InterruptedException {
            if (!done.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Async listeners timed out");
            }
        }

        public String traceOf(String orderId) {
            return traces.get(orderId);
        }

        public boolean sameWorkerForAll() {
            return threads.size() == 3
                    && new HashSet<>(threads.values()).size() == 1;
        }
    }

    // Class is non-final so Spring can create an @Async proxy.
    public static class OrderListener {
        private static final Logger log =
                LoggerFactory.getLogger("demo.events");
        private final Evidence evidence;

        public OrderListener(Evidence evidence) {
            this.evidence = evidence;
        }

        @Async("eventExecutor")
        @EventListener
        public void handle(OrderPlaced event) {
            String trace = MDC.get("traceId");
            log.info("order={}", event.orderId());
            evidence.record(
                    event.orderId(),
                    trace,
                    Thread.currentThread().getName());
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    public static class Config {
        @Bean
        public Evidence evidence() {
            return new Evidence();
        }

        @Bean
        public OrderListener orderListener(Evidence evidence) {
            return new OrderListener(evidence);
        }

        @Bean("eventExecutor")
        public ThreadPoolTaskExecutor eventExecutor() {
            ThreadPoolTaskExecutor executor =
                    new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(10);
            executor.setThreadNamePrefix("events-");
            executor.setTaskDecorator(new MdcTaskDecorator());
            return executor;
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {
            Evidence evidence = context.getBean(Evidence.class);

            try {
                MDC.put("traceId", "trace-A");
                context.publishEvent(new OrderPlaced("ORD-A"));

                MDC.put("traceId", "trace-B");
                context.publishEvent(new OrderPlaced("ORD-B"));

                MDC.clear();
                context.publishEvent(new OrderPlaced("ORD-C"));
            } finally {
                // Also clean up the publisher thread on exit.
                MDC.clear();
            }

            evidence.awaitAll();

            System.out.println(
                    "A trace=" + evidence.traceOf("ORD-A"));
            System.out.println(
                    "B trace=" + evidence.traceOf("ORD-B"));
            System.out.println(
                    "C trace=" + evidence.traceOf("ORD-C"));
            System.out.println(
                    "Worker reused=" + evidence.sameWorkerForAll());
            System.out.println(
                    "Publisher MDC cleared="
                            + (MDC.get("traceId") == null));
        }
    }
}
```

### Run Command

In the directory containing `pom.xml`, using JDK 17+ and Maven:

```bash
mvn -q compile exec:java
```

**Log lines from logger `demo.events` in the demo configuration** (single-worker pool):

```text
trace=trace-A thread=events-1 order=ORD-A
trace=trace-B thread=events-1 order=ORD-B
trace=none thread=events-1 order=ORD-C
```

**`System.out` lines after all three listeners complete:**

```text
A trace=trace-A
B trace=trace-B
C trace=<none>
Worker reused=true
Publisher MDC cleared=true
```

The number after the `events-` prefix may differ if more tasks/threads are created or configuration changes; what matters is that the same worker is used and each event's MDC is accurate. Auxiliary logs from Maven, Logback, or the framework (if any) are outside these business result lines.

### Explaining the Results

1. When `ORD-A` is published, MDC on the publisher thread is `trace-A`. The decorator captures a copy when task A is submitted.
2. The publisher changes MDC to `trace-B` and submits B. Even if the worker has not yet processed A, A's captured value **does not change**.
3. Before C, the publisher calls `MDC.clear()`. The decorator captures `null` or an empty map and installs the corresponding empty context so the worker **does not inherit `trace-B`**.
4. Because the pool has one thread, all three tasks run on the same worker, demonstrating that inter-task cleanup has real effect.
5. `CountDownLatch` awaits all three callbacks before `main` reads `ConcurrentHashMap`. No arbitrary `Thread.sleep` is needed.
6. The `record` calls happen before `countDown`; once `awaitAll` succeeds, the program has complete data to print.
7. `try-with-resources` closes the Spring context after the test tasks have completed.

If the executor fails to process all three tasks within 10 seconds, the program throws a timeout exception instead of falsely reporting success.

## 7. What If TaskDecorator Is Omitted?

Keep the `@Async` listener as is, but remove:

```java
executor.setTaskDecorator(new MdcTaskDecorator());
```

With a fresh worker and no other propagation mechanism, logs typically do not see the publisher's MDC:

```text
trace=none thread=events-1 order=ORD-A
trace=none thread=events-1 order=ORD-B
trace=none thread=events-1 order=ORD-C
```

This is an **illustrative result when no other context propagation mechanism exists**. If the application already uses Micrometer context propagation, an instrumented executor, or another decorator, inspect the actual configuration.

Conversely, when `@EventListener` runs synchronously on the publisher's own thread with the default multicaster, MDC can be read directly without a decorator. A test using only synchronous listeners **does not prove** propagation across a thread pool.

## 8. Where to Attach the Decorator in Application Events?

There are two common ways listeners are moved onto an executor.

### 8.1. @Async on the Listener Method

```java
@Async("eventExecutor")
@EventListener
public void onOrder(OrderPlaced event) {
    // Runs on the executor selected by @Async.
}
```

MDC must be propagated through **the async method's executor**. If `eventExecutor` has the decorator, the task receives the context. If `@Async("emailExecutor")` selects another bean without a decorator, configuration on `eventExecutor` **does not affect** that other bean.

With multiple pools, establish a factory or consistent decorator configuration convention, or configure each bean explicitly. Never assume that having one `TaskDecorator` bean in the context makes every executor use it automatically.

### 8.2. SimpleApplicationEventMulticaster's Executor

An application may configure:

```java
SimpleApplicationEventMulticaster multicaster =
        new SimpleApplicationEventMulticaster();

multicaster.setTaskExecutor(sharedTaskExecutor);
```

This is an integration snippet requiring `sharedTaskExecutor` and proper multicaster wiring; it is not part of the section 6 program. In this case, eligible listeners are multicast asynchronously via **the multicaster's executor**. If that executor is a decorated `ThreadPoolTaskExecutor`, MDC is captured where the multicaster submits the task.

If you configure an executor on the multicaster **and** also put `@Async` on the listener, **two thread hops** can occur. Each thread-switching layer must be examined separately for propagation. Do not use both just to "make doubly sure it's async".

### 8.3. Listener Publishing Another Event

If a listener already running on a worker with MDC installed by a decorator calls `publisher.publishEvent(new ChildEvent(...))`, then with a synchronous multicaster, listeners for the derived event can run on **that same worker** and see the current MDC.

If the child event's listener also uses `@Async("otherExecutor")`, a second thread boundary appears. To preserve `traceId`, the decorator must be configured on `otherExecutor` as well, or an equivalent context propagation mechanism must be used.

## 9. Spring 6.1+ ContextPropagatingTaskDecorator

Spring Framework 6.1 introduced `org.springframework.core.task.support.ContextPropagatingTaskDecorator`, which uses **Micrometer Context Propagation** to capture and restore contexts that have matching integrations. It is useful for logging/tracing/observation when an application uses Micrometer and a context registry.

Illustrative configuration:

```java
@Bean("observedExecutor")
public ThreadPoolTaskExecutor observedExecutor() {
    ThreadPoolTaskExecutor executor =
            new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(50);
    executor.setThreadNamePrefix("observed-");
    executor.setTaskDecorator(
            new ContextPropagatingTaskDecorator());
    return executor;
}
```

This snippet requires importing `ContextPropagatingTaskDecorator`, `ThreadPoolTaskExecutor`, and `@Bean`, as well as having `micrometer-context-propagation` and appropriate integrations/accessors on the classpath/configuration. This is an API example, not a standalone runnable program.

**Do not assume:** calling `new ContextPropagatingTaskDecorator()` automatically copies **every arbitrary MDC key** across every logging backend. `ThreadLocal` types needing propagation must have an appropriate `ThreadLocalAccessor`/registration and actual integration. Propagating Micrometer Observation context does not mean every arbitrary library's logging context is covered.

How to choose:

| Need | Solution |
| --- | --- |
| Only need to copy the entire SLF4J MDC map across an executor | `MdcTaskDecorator` is simple and easy to test |
| Need to coordinate multiple observation contexts in a Micrometer system | Evaluate `ContextPropagatingTaskDecorator` and accessors |
| Combining multiple decorators | Verify wrapper order, scope, and cleanup |
| Extremely small/high-volume tasks | Measure capture/restore cost and prefer minimal metadata |

Do not stack two decorators that both manage MDC without understanding their installation and restoration order.

## 10. MDC Is Not a Transaction, SecurityContext, or HttpServletRequest

| Context | Meaning | Does MDC TaskDecorator propagate it automatically? |
| --- | --- | --- |
| SLF4J MDC | Metadata to enrich logs | **Yes**, via a map copy |
| Spring transaction | Connection/resource binding and synchronization | **No** |
| Spring `SecurityContext` | Authentication/authorization | **No** |
| `RequestContextHolder` | Thread-bound request attributes | **No** |
| Micrometer Observation | Metrics/tracing context | Not automatically if only copying MDC |
| Application custom `ThreadLocal` | Project-defined state | No, unless a dedicated mechanism exists |
| Event payload | Business data snapshot | Not a `ThreadLocal` |

**Do not manually copy transaction context like MDC.** A transaction bound to a connection/resource on the original thread has commit/rollback contracts; copying `ThreadLocal` references to a worker can corrupt semantics. An `@Async` listener needs its own transaction if it performs transactional database operations.

**Do not use MDC for authorization.** A log containing `userId=alice` is not proof that the worker is authorized to access Alice's data. If authentication must be propagated, use the mechanisms provided by Spring Security with proper limits and security policies.

**Do not hold request objects for long.** In event payloads or long async tasks, avoid holding `HttpServletRequest`, persistence contexts, connections, or mutable request-flow objects. Pass only required business IDs and minimal logging metadata.

## 11. MDC and `correlationId` in the Payload Are Two Different Layers

An event record can define:

```java
public record OrderPlaced(
        String eventId,
        String orderId,
        String correlationId
) {}
```

`correlationId` in the payload is **business/tracing data durable across processing**. Meanwhile, `MDC.get("correlationId")` exists only on a thread where context has been installed. If an event is stored in an outbox and reprocessed minutes later or in another process, the original request's MDC is long gone.

A listener can set MDC from the payload:

```java
@EventListener
public void onOrder(OrderPlaced event) {
    try (MDC.MDCCloseable ignored =
                 MDC.putCloseable(
                         "correlationId",
                         event.correlationId())) {
        log.info("order={}", event.orderId());
    }
}
```

This is an integration pattern. `MDC.putCloseable` removes the key when the scope ends; it **does not automatically restore an earlier value** for that same key. If nested context preservation is needed, save/restore the previous value or previous map yourself using `finally`.

IDs usually serve distinct roles:

- `eventId` identifies **one occurrence of an event**, remaining stable across retries of that same occurrence.
- `correlationId` groups events belonging to **the same workflow**.
- `traceId` from distributed tracing describes a technical trace, which may be shorter than a business workflow.
- `causationId` (if present) describes the direct parent event that led to the new event.

Do not use a transient MDC `traceId` as the sole idempotency key for emails, invoices, or payment updates.

### If the Publisher Lacks MDC, the Decorator Cannot Know Payload Data

A generic `TaskDecorator` receives a `Runnable` and has no knowledge of which event type a listener handles. It has no contract for extracting `correlationId` from arbitrary records. If you want IDs logged when publishing from a scheduler/outbox task without MDC, install context from metadata before submission or inside the listener with an explicit scope.

## 12. MDC Leaks and Thread Reuse

Thread pools reuse workers repeatedly:

```text
Task A: set traceId=trace-A
Task A: finishes without clearing
           |
           v
Task B on the same thread:
  publisher has no traceId
  log still shows trace-A  <-- wrong
```

Another common bug:

```java
if (captured != null) {
    MDC.setContextMap(captured);
}
// Fails to clear when captured == null.
```

This is a **counter-example**. If the worker already had old MDC or an outer wrapper, the new task may see data that does not belong to it. The right pattern must **clear when `captured` is null** and **restore `previous` in `finally`**.

For logs containing `tenantId` or `userId`, context leakage can produce log entries under the wrong user/tenant, creating operational and investigative risks. Ensure MDC holds only minimized logging data—never passwords, tokens, or unnecessary PII.

### InheritableThreadLocal Is Not the Answer for Thread Pools

`InheritableThreadLocal` has inheritance semantics at **thread creation time**, not when **submitting a new task to a pre-created thread**. A long-lived worker may carry old state or lack state for new requests. Thus, using `InheritableThreadLocal` to pass per-event MDC through a pool is generally incorrect. Per-task capture/restore is the cleaner choice.

## 13. TaskDecorator Is Not the Only Error-Catching Mechanism

Spring's documentation notes that a decorator may receive a `FutureTask`-style callback rather than the original runnable. `FutureTask.run()` typically stores exceptions inside the `Future`, so a `catch` outside `delegate.run()` **is not guaranteed** to see business exceptions.

Counter-example:

```java
return () -> {
    try {
        delegate.run();
    } catch (RuntimeException ex) {
        log.error("All async errors are here", ex);
    }
};
```

Do not rely on this logic as the sole way to catch all `@Async` errors.

Separate responsibilities:

- **TaskDecorator:** propagate and clean up context via `try/finally`; do not swallow exceptions.
- **`@Async void`:** monitor exceptions via `AsyncUncaughtExceptionHandler` or handle them in the service.
- **Future/CompletableFuture:** handle results or exceptions via the Future API or appropriate callbacks.
- **Task rejection:** track task submission failures when the executor is full or shutting down.
- **Event workflow:** maintain its own business status, retries, and idempotency.

If a callback is never admitted to the pool because it was rejected, `run()` never executes. A decorator cannot turn an unexecuted event into a completed one.

## 14. Overload, Shutdown, and Durability

`ThreadPoolTaskExecutor` has `corePoolSize`, `maxPoolSize`, and `queueCapacity`. When all workers and the queue are full, the executor may reject additional tasks. In that case:

1. `@Async` does not mean the event is guaranteed to be processed.
2. The task may never execute; there will be no callback log even though `publishEvent` was called.
3. A captured MDC snapshot does not guarantee the work is persisted.
4. Forceful JVM shutdown can lose tasks waiting in RAM.
5. If processing must be guaranteed, use an outbox, broker, or job store with retries and idempotency.

MDC also increases the memory retained per queued task. Never put large payloads or secrets into MDC; keep only short, necessary IDs allowed by logging policy.

Choosing a large `queueCapacity` is not a delivery guarantee. With a small executor and a large queue, wait times can grow; when the worker eventually runs, MDC still holds the submission-time snapshot—which is accurate for tracing semantics, though latency should be kept in mind.

## 15. @TransactionalEventListener and MDC

A post-commit listener may be declared as:

```java
@Async("eventExecutor")
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterCommit(OrderPlaced event) {
    log.info("After commit: {}", event.orderId());
}
```

This is an integration example: it requires `@EnableAsync`, an executor, and a real transaction manager. `@TransactionalEventListener` binds to `AFTER_COMMIT` by default; if an event is published outside a transaction with `fallbackExecution=false`, the callback normally does not run.

Understand each boundary:

- The post-commit callback is registered against the source transaction.
- When Spring submits the `@Async` method to the executor, the decorator captures the MDC of **the thread submitting the task at that moment**.
- If MDC was already cleared before that moment, the decorator cannot resurrect a `traceId` no longer on the thread.
- The original transaction **is not** copied to the worker alongside MDC; if the listener writes new data, open an appropriate transaction.
- Post-commit events can still be lost on a crash between the business commit and follow-up work. If loss is unacceptable, a transactional outbox is the data-layer solution, not `TaskDecorator`.

This explains why the event payload should carry stable `eventId`/`correlationId` fields so logging context can be re-established in deferred or replayed tasks.

## 16. Proper Testing

### Unit Testing Save/Restore

Wrapper logic can be tested on the same thread:

```java
MdcTaskDecorator decorator = new MdcTaskDecorator();

MDC.put("traceId", "publisher-A");
Runnable wrapped = decorator.decorate(() -> {
    if (!"publisher-A".equals(MDC.get("traceId"))) {
        throw new AssertionError("MDC was not installed");
    }
});

MDC.put("traceId", "worker-old");
wrapped.run();

if (!"worker-old".equals(MDC.get("traceId"))) {
    throw new AssertionError("MDC was not restored");
}
MDC.clear();
```

This snippet requires an `MdcTaskDecorator` implementation and an MDC provider as in section 6. It proves save/restore behavior, but **does not replace an integration test through a Spring executor**.

### Integration Tests Must Exercise Thread Switching

| Scenario | Expectation |
| --- | --- |
| Task A submitted with `trace-A` | Worker A reads `trace-A` |
| Publisher switches to `trace-B` while A is still queued | A still sees `trace-A` |
| Task B submitted with `trace-B` | Worker B reads `trace-B` |
| Task C submitted without MDC | Worker C does not see B's trace |
| Same thread pool processing multiple tasks | Context does not leak between tasks |
| Listener throws an exception | `finally` still restores MDC |
| Executor without a decorator | Must not infer propagation succeeded |
| Executor rejects a task | Rejection is observed with an appropriate policy |
| Two executor hops | Verify propagation across both thread switches |
| Logger omits `traceId` while MDC has a value | Check logging pattern configuration instead of only blaming `TaskDecorator` |

**Do not test with `Thread.sleep(50)` and then assert.** Execution timing depends on machine load and queueing, making tests flaky. Use `CountDownLatch` or a future with a timeout as shown in the example.

Logging tests should also record `MDC.get("traceId")` on the worker into a thread-safe verification structure rather than only eyeing log strings—because loggers may be filtered or patterns misconfigured.

## 17. Common Mistakes

1. **Attaching `TaskDecorator` to the wrong executor.** `@Async("mailExecutor")` does not use the decorator on `eventExecutor`.
2. **Forgetting `@EnableAsync`.** Listeners may still run synchronously, giving a false pass when verifying propagation.
3. **Capturing MDC on the worker.** Too late to get the publisher's snapshot.
4. **Failing to handle `captured == null`.** A new event without MDC can still see an old `traceId`.
5. **Failing to restore `previous`.** An outer wrapper may lose the worker's initial context.
6. **Omitting `finally`.** Exceptions leave the worker carrying context into the next task.
7. **Relying solely on `InheritableThreadLocal`.** Thread pools reuse threads and do not inherit context per task.
8. **Using MDC as a business data source.** Logging context can be lost across processes or replays.
9. **Assuming copying MDC also copies transactions.** These are completely different contexts.
10. **Assuming copying MDC enforces authorization.** Authentication/authorization must rely on proper security mechanisms.
11. **Configuring a multicaster executor while forgetting `@Async`'s executor.** Two thread hops can occur.
12. **Relying on the decorator to catch all exceptions.** `FutureTask` may store errors inside the `Future`.
13. **Lacking an SLF4J backend with MDC support.** Calling the MDC API alone does not ensure log patterns print values.
14. **Putting large or sensitive data into MDC.** Each queued task may retain a snapshot.
15. **Letting listeners process tiny tasks without measuring overhead.** Capturing and restoring maps has a cost.
16. **Assuming `ContextPropagatingTaskDecorator` copies all MDC keys by default.** Integrations/accessors must be verified.
17. **Treating a `traceId` in logs as proof of successful processing.** Tasks can fail, retry, or log before side effects.
18. **Believing an in-RAM executor is a durable queue.** `TaskDecorator` provides neither persistence nor exactly-once delivery.

## 18. Application Adoption Checklist

- [ ] Identified clearly whether event listeners switch threads via `@Async` or a multicaster executor.
- [ ] Configured the decorator on **the exact executor** being used.
- [ ] Captured the MDC map at task submission time, not when the worker runs.
- [ ] Saved the worker's previous context and restored it in `finally`.
- [ ] A null captured map clears MDC for that task.
- [ ] A logging backend supporting MDC is present and the pattern prints the right key.
- [ ] `@EnableAsync` and proxy invocation behave as designed.
- [ ] Tested two distinct `traceId` values and a task without MDC on the same worker.
- [ ] Used latches/futures to await completion rather than guessing timing/order.
- [ ] With multiple executors or multiple thread hops, each layer has the needed propagation.
- [ ] Event payloads include a business correlation ID for replay/outbox use.
- [ ] MDC is not confused with transactions, `SecurityContext`, request context, or tracing state.
- [ ] Separate policies exist for exceptions, rejections, shutdown, retries, and idempotency.
- [ ] Unnecessary secrets/PII are kept out of MDC and logs.
- [ ] Propagation overhead has been measured for small, high-frequency tasks.

**Remember:** `TaskDecorator` lets logging context "travel with the work" across thread boundaries via **capture at publisher → install on worker → run task → restore worker in `finally`**. Configuring the right pool and cleaning up context are what keep logs from missing or leaking `traceId` values across Spring Application Events.

## Official Documentation

- [Spring Framework — TaskDecorator Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/core/task/TaskDecorator.html)
- [Spring Framework — ThreadPoolTaskExecutor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Spring Framework — ContextPropagatingTaskDecorator Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html)
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [SLF4J MDC API](https://www.slf4j.org/apidocs/org/slf4j/MDC.html)
- [Logback Manual — MDC](https://logback.qos.ch/manual/mdc.html)
