# Inspecting Thread Names When Diagnosing Spring Application Events

## 1. Why Does the Thread Name Matter?

When an application uses Spring Application Events, the same `publishEvent(...)` call can cause a listener to run **directly on the publisher thread** or be handed to an executor and run **on a different thread**. Looking only at business outcomes without knowing where the listener ran leads engineers to misdiagnose issues:

- Why is the HTTP request slow even though the service only called `publishEvent(...)`?
- Why is the listener annotated with `@Async` yet logs still appear on the request thread?
- Why did `MDC`, `SecurityContext`, the transaction, or a `ThreadLocal` value disappear when entering the listener?
- Why did the event publish succeed while the listener failed at a different time?
- Why do multiple listeners appear to run "in parallel" when in reality they share a single worker, causing queue bottlenecks?

**The thread name**, obtained via `Thread.currentThread().getName()`, is a very useful diagnostic signal. It helps identify *the likely execution path*, especially when custom prefixes are configured on executors. However, **a thread name is only a mutable label**: it does not prove a listener has a transaction, does not guarantee an event finished, does not uniquely identify a thread, and is not enough to conclude that context data was propagated properly.

This lesson focuses on how to observe and interpret thread names when publishing/handling **Spring Application Events**, how to configure clear names, and how to combine logs and metrics to verify hypotheses.

## 2. The Default Model: Synchronous Publisher and Listener

Under Spring's default mechanism, `ApplicationEventPublisher` passes the event to a multicaster (typically `SimpleApplicationEventMulticaster`). If no task executor is configured on the multicaster and the listener does not use `@Async`, the callback is invoked **synchronously on the publisher's thread**.

```text
HTTP thread: http-nio-8080-exec-3
    |
    v
OrderService.placeOrder()
    |
    v
publisher.publishEvent(new OrderPlaced(...))
    |
    v
@EventListener onOrderPlaced(...)  <--- same HTTP thread
    |
    v
callback completes
    |
    v
publishEvent(...) returns
    |
    v
HTTP response
```

Example of a request handled by a thread named `http-nio-8080-exec-3`:

```text
2026-11-11 12:00:00.000 [http-nio-8080-exec-3] INFO  OrderService - Publishing order=ORD-9
2026-11-11 12:00:00.003 [http-nio-8080-exec-3] INFO  OrderListener - Handling order=ORD-9
2026-11-11 12:00:00.040 [http-nio-8080-exec-3] INFO  OrderService - Publish returned
```

These are **illustrative logs**, not output from the section 5 program. Matching thread names and execution ordering suggest a synchronous listener; combine that with executor configuration and runtime evidence before concluding. When a listener performs slow work, that duration may be included in the response latency.

**Do not jump to wrong conclusions:** Seeing the thread name `main` during application startup only indicates code was running on the startup thread when logged. In a web application, the publisher is often a request-handling thread, though it can also be a scheduler, worker, messaging thread, or custom thread.

## 3. When Will the Thread Name Change?

There are several independent ways a listener can be invoked on a different thread from the publisher:

### 3.1. `@Async` on the Listener Itself

With `@EnableAsync` and a matching executor:

```java
@Async("eventExecutor")
@EventListener
public void on(OrderPlaced event) {
    System.out.println(Thread.currentThread().getName());
}
```

This is an **illustrative code snippet**. The listener executes via Spring's `@Async` mechanism through a Spring proxy; the call is routed to the executor bean named `eventExecutor`. Not every call switches threads under every possible configuration: a synchronous executor, `CallerRunsPolicy` under overload, misconfigured proxying, or self-invocation can cause behavior that differs from expectations.

### 3.2. `ApplicationEventMulticaster`'s Executor

Another way is configuring `SimpleApplicationEventMulticaster.setTaskExecutor(...)` so the multicaster can submit callbacks of listeners that **support asynchronous execution** via the executor. This differs from placing `@Async` on a single method.

Since Spring Framework 6.1, some listeners do not support async execution at the multicaster level—particularly transaction-bound synchronous listeners such as `@TransactionalEventListener`, which must be invoked in the originating context to register transaction synchronization. Therefore, do not assume "setting an executor on the multicaster = every listener runs on the pool".

### 3.3. Listener Delegates Work to Another Executor Itself

A listener may run synchronously yet call `CompletableFuture.runAsync(...)`, `TaskExecutor.execute(...)`, or send work to a broker. Logs at the start of the listener will retain the publisher's thread name, while logs from the spawned sub-work will carry a different name.

**Identify precisely which segment of code is being measured.** Logging the thread name only at the entry of the listener does not reveal the thread of work submitted internally.

## 4. Java APIs for Inspecting Threads

Java 17 supports:

```java
Thread current = Thread.currentThread();

String name = current.getName();
long id = current.getId();
boolean daemon = current.isDaemon();

System.out.printf(
        "thread=%s id=%d daemon=%s%n",
        name, id, daemon);
```

This is an **API-illustrative standalone Java snippet** that can be placed inside an executing method. Note:

- `getName()` reads the current thread's label. Default names depend on the container/framework and can be changed with `setName(...)`.
- `getId()` can be used on JDK 17 for correlation within the process; **never** use it as a request ID or event ID. Newer Java versions introduce updated thread-identifier APIs and deprecate/change usage guidance.
- `isDaemon()` indicates whether the thread is marked as a daemon; it does not prove a task will finish before shutdown.
- Thread names can collide or be reused; pools routinely reuse the same thread for many distinct events.

In production, include **thread name + event ID/correlation ID + listener name + status/latency** in logs. The thread name helps locate the execution path, while the event ID is what lets you correlate logs of the same event across different threads.

## 5. Runnable Java 17+ Example: Comparing Synchronous and `@Async` Listeners

This example uses Spring Boot 3.3.13, Java 17+, without starting a web server, creating a dedicated executor with the prefix `evt-worker-`. We publish two **distinct event types** to observe the synchronous and asynchronous paths cleanly without relying on dispatch ordering between multiple listeners for the same type.

### Directory Structure

```text
event-thread-demo/
├── pom.xml
└── src/main/java/example/events/EventThreadDemo.java
```

### `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>event-thread-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### `EventThreadDemo.java`

```java
package example.events;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.boot.Banner;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@SpringBootApplication
@EnableAsync
public class EventThreadDemo {

    public record SyncRequested(String id) {
    }

    public record AsyncRequested(String id) {
    }

    public static class EventHandlers {
        private final CountDownLatch asyncDone;

        public EventHandlers(CountDownLatch asyncDone) {
            this.asyncDone = asyncDone;
        }

        @EventListener
        public void onSync(SyncRequested event) {
            System.out.printf("SYNC id=%s thread=%s%n",
                    event.id(), Thread.currentThread().getName());
        }

        @Async("eventExecutor")
        @EventListener
        public void onAsync(AsyncRequested event) {
            try {
                System.out.printf("ASYNC id=%s thread=%s%n",
                        event.id(), Thread.currentThread().getName());
            } finally {
                // Used only to synchronize demo output.
                asyncDone.countDown();
            }
        }
    }

    @Bean
    CountDownLatch asyncDone() {
        return new CountDownLatch(1);
    }

    @Bean("eventExecutor")
    ThreadPoolTaskExecutor eventExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(1);
        executor.setQueueCapacity(10);
        executor.setThreadNamePrefix("evt-worker-");
        return executor;
    }

    @Bean
    EventHandlers eventHandlers(CountDownLatch asyncDone) {
        return new EventHandlers(asyncDone);
    }

    @Bean
    CommandLineRunner scenario(
            ApplicationEventPublisher publisher,
            CountDownLatch asyncDone) {
        return args -> {
            System.out.println(
                    "PUBLISHER thread=" + Thread.currentThread().getName());

            publisher.publishEvent(new SyncRequested("S1"));
            publisher.publishEvent(new AsyncRequested("A1"));

            if (!asyncDone.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Async event listener timed out");
            }

            System.out.println("RUNNER after async");
        };
    }

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(EventThreadDemo.class);
        application.setWebApplicationType(WebApplicationType.NONE);
        application.setBannerMode(Banner.Mode.OFF);

        try (ConfigurableApplicationContext context =
                     application.run(args)) {
            // Runner has finished; Spring manages the executor lifecycle.
        }
    }
}
```

### Run Commands

Inside the directory containing `pom.xml`, using Java 17+ and Maven:

```bash
mvn -q package
java -jar target/event-thread-demo-1.0.0.jar
```

On a JVM launched via standard `java -jar`, the lines **printed by the application itself** appear in the following order, excluding Spring's own logs:

```text
PUBLISHER thread=main
SYNC id=S1 thread=main
ASYNC id=A1 thread=evt-worker-1
RUNNER after async
```

**Line-by-line analysis:**

1. `CommandLineRunner` executes during startup on the thread calling `SpringApplication.run(...)` (normally named `main` with the command above).
2. `SyncRequested` is dispatched to a listener without `@Async`, so the thread name remains `main`.
3. `AsyncRequested` is dispatched to a method with `@Async("eventExecutor")`; the method actually runs on a worker managed by `ThreadPoolTaskExecutor` with the configured `evt-worker-` prefix. With a single initial worker, the name is `evt-worker-1`.
4. `CountDownLatch` ensures the runner prints `RUNNER after async` **only after** the async listener has printed its line. No `Thread.sleep(...)` is used to gamble on ordering.
5. `@EnableAsync` and invocation via a Spring-managed event listener/proxy are required for `@Async` to take effect. If you instantiate `new EventHandlers(...)` yourself and call it directly, there is no Spring proxy for `@Async`.

**What this example does not prove:** there is no DB transaction, no MDC/security context propagation, no message broker, and no durable event guarantee. The thread name only confirms where a piece of code executed during this run.

**Reproducibility caveat:** the number after the prefix depends on tasks/workers already created. The demo creates only one async event in its own pool, so `evt-worker-1` is expected. In real systems with multiple workers and parallel tasks, never hardcode the suffix for application logic or long-term assertions.

## 6. Naming Executors for Readable Logs

When multiple executors coexist, names like `pool-8-thread-12` do not reveal which business domain a task belongs to. Set prefixes based on **workload purpose**, for example:

| Flow | Suggested prefix | Observable behavior |
| --- | --- | --- |
| Notification listener | `event-notify-` | Tasks handling notifications after events |
| Projection-updating listener | `event-projection-` | Processing read-model updates |
| Data sync job | `sync-job-` | Batch/scheduler execution |
| Tomcat HTTP server | `http-nio-...` (container-assigned name) | Requests handled on server workers |
| General async tasks | `application-task-` | Requires checking which bean actually uses it |

A prefix is not an isolation mechanism: two distinct executors can still be configured with the same name, or a task can hop threads. Pair it with **bean names**, thread dumps, and metrics when deep diagnosis is needed.

Basic configuration:

```java
@Bean("notificationExecutor")
ThreadPoolTaskExecutor notificationExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(8);
    executor.setQueueCapacity(100);
    executor.setThreadNamePrefix("event-notify-");
    return executor;
}
```

This is **a standalone configuration snippet**, not a complete file. The numbers 4/8/100 are illustrative only; in production, measure load, memory, downstream capacity, and rejection rates to size appropriately. Do not alter another module's executor/pool just to make log names prettier.

**Be careful with bean names:** `@Async("notificationExecutor")` requires Spring to resolve the matching executor/qualifier. If the annotation points to the wrong name, executor resolution may fail or fall back to another configuration depending on setup; when diagnosing, check both Spring configuration and runtime logs.

## 7. Printing Structured Thread Names in Logs

Although `System.out.println(...)` is handy for learning, use a logger in production. With SLF4J:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

private static final Logger log =
        LoggerFactory.getLogger(OrderEventListener.class);

@EventListener
public void on(OrderPlaced event) {
    log.info("Handling eventId={} orderId={} thread={}",
            event.eventId(),
            event.orderId(),
            Thread.currentThread().getName());
}
```

This is an **illustrative snippet** requiring `OrderEventListener`, `OrderPlaced`, and event methods in an existing Spring application. If the logging pattern already includes the thread name, there is no need to repeat it in the message except for specific investigations.

In Spring Boot using Logback, you can set the pattern in `application.properties`:

```properties
logging.pattern.console=%d{HH:mm:ss.SSS} [%thread] %-5level %logger{36} - %msg%n
```

This is an **illustrative configuration**, not needed in the section 5 demo. `%thread` or `%t` in Logback captures the thread name at the moment the log event is created. Sample log:

```text
12:00:01.050 [http-nio-8080-exec-3] INFO  OrderService - Publishing order=ORD-9
12:00:01.053 [event-notify-2] INFO  NotificationListener - Sending order=ORD-9
```

Logs do not prove the HTTP request finished before the listener ran; they only show they occurred on differently labeled threads. If logs are processed asynchronously by a logging backend, **display order in centralized log viewers** may also shift. Rely on timestamps, event IDs, and trace/span IDs.

### Use Both Correlation ID and Event ID

At a minimum, log:

- `eventId`: identifies the event record.
- `eventType`: business type, e.g. `OrderPlaced`.
- `listener`: handler name.
- `threadName`: where the handler is running.
- `traceId`/`correlationId`: links steps within one request/flow.
- `status`, `durationMs`, `attempt`: shows whether the handler actually succeeded or failed.

If you rely solely on the thread name, two different requests/aggregates running consecutively on the same worker will be mistakenly grouped as the same action.

## 8. ThreadLocal, MDC, and Contexts That Do Not Automatically Follow Threads

One of the most common reasons async listeners "lose data" is misunderstanding the relationship between threads and context.

| Context | Nature | When switching threads |
| --- | --- | --- |
| Java `ThreadLocal` | Value bound to the current thread | Does not appear on another worker by default |
| SLF4J `MDC` | Logging diagnostic context usually stored per thread | Not automatically copied accurately across every executor |
| Spring Security `SecurityContextHolder` | Defaults to a thread-bound context strategy | Do not assume a principal exists on async workers |
| Spring transaction | For imperative transactions, state is usually thread-bound | Does not automatically pull the source transaction onto an async worker |
| Request context | Servlet info bound to the request thread | Should not be used after the request or without propagation |
| Reactor Context | Subscriber-scoped context, not equivalent to `ThreadLocal` | Requires observability/propagation mechanisms suited for reactive flows |

Example where the publisher writes to MDC:

```java
MDC.put("traceId", "t-123");
publisher.publishEvent(new OrderPlaced(...));
```

This is an **illustrative snippet**. Synchronous listeners on the same thread usually read MDC at that moment; listeners running on a separate pool may **not see** `traceId` without context propagation. The issue is not that the event "lacks the thread name", but that MDC is not part of the event payload and does not cross threads automatically.

**Never blindly copy transaction `ThreadLocal` values** to fake cross-thread transactions. A Spring imperative transaction, entity manager/connection, or request-scoped resource cannot be treated as safe to use from another worker. For business logic needing its own transaction, open a fresh transaction properly inside the listener's service.

## 9. Controlled Logging Context Propagation with TaskDecorator

When you need to preserve MDC across a `ThreadPoolTaskExecutor`, attach a `TaskDecorator` to capture logging context at submission time and restore it on the executing thread.

Example with SLF4J MDC, placed **inside the executor configuration method** (an add-on snippet, not a standalone project):

```java
executor.setTaskDecorator(task -> {
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
});
```

Assumes `java.util.Map` and `org.slf4j.MDC` are imported and a suitable logging dependency is present. Capture context on submit, apply it on the worker before running, and **restore the previous state in `finally`** to avoid leaking data across tasks sharing the pool. Properly copying MDC in an executor does not automatically propagate `SecurityContext`, request scope, or transactions.

In Spring Framework 6.1+, `ContextPropagatingTaskDecorator` integrates with Micrometer Context Propagation when compatible dependencies/accessors are configured; it can replace manual MDC copying in supported observability architectures. Test what context actually propagates, because not every custom context is propagated automatically.

**Security warning:** if a task is delayed significantly, context holding sensitive data may no longer be valid when the task actually executes. Prefer passing minimal business values (such as a verified `userId`) in the payload and re-authorizing when needed instead of copying raw request/security contexts.

## 10. Distinguishing `@Async` from the Multicaster's Executor

These are two distinct ways to move work onto another thread; applications sometimes use both, causing confusion.

### A. `@Async` on the Listener Method

```java
@Async("eventExecutor")
@EventListener
public void handle(MyEvent event) {
    // This method is submitted to eventExecutor by the async proxy.
}
```

Requirements: `@EnableAsync` annotation processing is active, the bean is Spring-managed, proxies are not bypassed, and the executor name is right. By default the multicaster **calls the listener on the publisher thread**, while the async proxy shifts method execution onto the worker.

### B. The Multicaster's Executor

```java
@Bean(name = "applicationEventMulticaster")
SimpleApplicationEventMulticaster eventMulticaster(
        @Qualifier("eventExecutor") TaskExecutor executor) {

    SimpleApplicationEventMulticaster multicaster =
            new SimpleApplicationEventMulticaster();

    multicaster.setTaskExecutor(executor);
    return multicaster;
}
```

This is an **illustrative configuration** requiring Spring imports and an `eventExecutor` bean in the application. When the multicaster has an executor, listeners **supporting asynchronous execution** can be invoked on workers. Some listeners, such as transaction-synchronized listeners, are not arbitrarily moved to another thread by the multicaster. Each strategy submits tasks at a different layer; choosing one clear approach is best unless complexity is justified.

### C. Why See the Publisher's Thread Name When You Expected Async?

- The listener lacks `@Async` and the multicaster has no executor configured.
- `@EnableAsync` is missing or the bean is not Spring-managed.
- The `@Async` method call is a self-invocation (calling `this.method()`), bypassing the proxy.
- A synchronous executor is used, such as `SyncTaskExecutor`.
- The pool uses `CallerRunsPolicy` when saturated: the submitting thread may execute the task itself for backpressure.
- The log was emitted **before submission** rather than inside the executing callback.
- The code creates another task inside the listener and logs from both parts are mixed up.

Merely seeing the same thread name **is not enough** to conclude `@Async` is definitely broken. Add logs at the publish point, callback entry, and actual completion point, and inspect executor/runtime configuration.

## 11. Diagnostic Flowchart When a Listener "Runs on the Wrong Thread"

```text
1. Log publisher thread right before publishEvent()
                      |
                      v
2. Log thread on the first line of the listener
                      |
            +---------+----------+
            |                    |
       same name            different name
            |                    |
            v                    v
3a. Check @Async,          3b. Identify executor,
    multicaster config         prefix, and task
    and proxy                  execution path
            |                    |
            +---------+----------+
                      |
                      v
4. Log eventId/traceId on both sides
                      |
                      v
5. Inspect queue, active threads, rejections,
   exceptions, and elapsed time
                      |
                      v
6. Verify business outcome and
   MDC/transaction/security context if applicable
```

Questions to answer in order:

**(1) Which thread published this event?** Log in the controller/service before and after `publishEvent(...)`; do not guess from method names.

**(2) Which listener was actually invoked?** Identify by event type, listener class, method, and an `eventId`. If no callback logs appear, the listener may be unregistered, skipped by a filter/condition, failed during task submission, or still queued; thread names alone cannot diagnose that.

**(3) Did any executor actually accept the task?** Check `@Async("...")` config, executor beans or multicaster, thread prefixes, and rejection handlers. If the task was rejected, the callback may never have run at all.

**(4) Which context did the callback lose?** Distinguish MDC (logging only), security principal, transaction, and request attributes. Choose the right propagation mechanism instead of lumping everything together as "thread context".

**(5) Did the callback succeed, or only reach its first log line?** Log completion status, exceptions, duration, attempt count, and track idempotency. If the listener is `void @Async`, runtime exceptions normally do not return to the caller; configure `AsyncUncaughtExceptionHandler` or handle errors in the listener.

## 12. Thread Dumps: When Logs Alone Cannot Explain the Issue

If a listener is suspected of hanging, deadlocking, or exhausting workers, inspect thread states and stack traces at the time of the incident. On a machine/container running a JDK JVM, you can use:

```bash
jcmd <PID> Thread.print
```

Or on a suitable environment/JDK:

```bash
jstack <PID>
```

These are **administrative tool commands**—replace `<PID>` with the real process ID; they typically require the same OS user or appropriate privileges. Do not run them indiscriminately on unauthorized processes, and consider operational impact when taking dumps on very large systems.

In the output, look for:

- Thread names matching configured prefixes, such as `evt-worker-1`.
- States `RUNNABLE`, `WAITING`, `TIMED_WAITING`, or `BLOCKED`—interpret **together with the stack trace**, never from the state name alone.
- Multiple workers stuck on the same HTTP client/DB call, lock, or `CountDownLatch.await()`.
- Threads waiting on the executor queue: normal when the pool is idle, not proof of a deadlock.
- Java lock deadlock indicators; distinguish them from downstream timeouts or connection pool exhaustion.

**Illustrative example:** a task named `event-notify-3` in `TIMED_WAITING` inside an HTTP client may be awaiting a timeout; if many tasks are stuck like this and the queue grows, investigate downstream health, timeouts, retries, and concurrency limits rather than blindly enlarging the pool.

With **virtual threads** (Java 21+), naming/display and thread dumps differ; newer tooling/formats may be more appropriate. On Java 17 in the demo, we use platform threads from `ThreadPoolTaskExecutor`.

## 13. Do Not Confuse Thread Name with Transactions, Correctness, or Ordering

Common hasty conclusions:

| Hasty conclusion | Why it is wrong | Additional evidence needed |
| --- | --- | --- |
| "Same thread means same transaction" | Transaction may not be open yet, may have ended, or propagation differs | Actual transaction status and transaction boundary |
| "Different thread means data runs in parallel" | Pool may have only 1 worker or a long queue | Pool size, active count, queue depth, timestamps |
| "Name says async so it won't block publisher" | Executor may use `CallerRunsPolicy`, another rejection policy, or blocking submit | `publishEvent` duration, policy, stack trace |
| "START log means event succeeded" | Task may throw an error after START | END/FAILED logs, metrics, business outcome |
| "Different thread carries the transaction along" | Imperative transactions are typically thread-bound | New transaction configuration on the worker |
| "Same thread name means same request" | Workers are reused and names may not be unique | `eventId`, `traceId`, `requestId` |
| "Adjacent logs mean business ordering" | Async scheduling/log ingestion can reorder entries | Sequence/aggregate version, timestamps, contract |
| "Good thread naming is enough observability" | Lacks error, latency, and retry visibility | Tracing, queue/executor metrics, IDs |

If you need to check whether an imperative transaction is active when a listener runs, you can use `TransactionSynchronizationManager.isActualTransactionActive()` **for diagnostic purposes**, though that only reflects the thread-bound transaction at call time; it does not prove a later commit will succeed and cannot substitute for verifying DB state.

If you need to verify the security principal, use the appropriate Spring Security API and ensure proper propagation; never log access tokens or secrets.

## 14. Testing Thread Names and Sync/Async Behavior

### Unit Tests / Integration Tests

| Scenario | What to verify |
| --- | --- |
| Regular listener and default multicaster | Callback runs on the publishing thread (within the same synchronous call) |
| `@Async("eventExecutor")` with `@EnableAsync` | Callback is submitted to the specified executor |
| Executor with custom prefix | Callback thread name starts with the matching prefix |
| Multiple async tasks | Do not assert completion order without synchronization |
| Rejected task | Rejection log/metric recorded; do not infer listener ran |
| `CallerRunsPolicy` when pool saturates | Caller may execute the task; detect via thread name and latency |
| MDC propagation with `TaskDecorator` | Value is present inside the task and cleared/restored afterward |
| Async listener throws an exception | Error is observed on the async error path; do not assume publisher receives it |
| Transaction around publisher | Do not assume async workers inherit the transaction |

In asynchronous tests, use `CountDownLatch`, `Awaitility`, or a waiting mechanism with a **timeout**. Avoid `Thread.sleep(100)` and guessing the task ran; slow CI machines easily cause flaky tests.

An appropriate assertion:

```java
assertTrue(observedThreadName.startsWith("evt-worker-"));
```

This is an **illustrative test snippet**, assuming `observedThreadName` was safely collected via a synchronization mechanism. Do not assert an exact `-1` suffix if the system may scale workers up/down or run other tasks before the test.

### Testing Context Propagation

Tests should set `MDC.put("traceId", "test-123")` before submission, verify the decorated worker sees that value, and then **clear MDC on the publisher in `finally`** and verify an independent task does not accidentally receive the stale value. The goal is not just "prettier logs", but preventing data leaks between requests sharing a pool.

## 15. Common Mistakes When Diagnosing by Thread Name

**Mistake 1 — Logging the thread name only in the publisher.** That does not identify which thread executed the listener. Log at publish, listener START, and listener END/FAILED.

**Mistake 2 — Using thread name as a request identifier.** Pools reuse threads and two requests can run sequentially on the same worker. Use `eventId`/`correlationId` instead.

**Mistake 3 — Seeing a different thread and assuming `@Async` is working.** The task might have been moved by the multicaster or by `CompletableFuture` inside the listener. Check the call path.

**Mistake 4 — Seeing the same thread and assuming `@Async` is broken.** It might be a synchronous executor or `CallerRunsPolicy` under overload; inspect pool policy and saturation.

**Mistake 5 — Leaving executors unnamed.** Multiple `pool-N-thread-M` names make ownership hard to trace. Set purpose-specific prefixes via explicit bean configuration.

**Mistake 6 — Believing MDC/transactions/security automatically cross threads.** Each context has its own mechanism; propagate only what is truly needed, and never copy transaction `ThreadLocal` values.

**Mistake 7 — Failing to clear MDC in thread pools.** Data from an earlier event can leak into the next event; use `try/finally` or a proper context propagation solution.

**Mistake 8 — Ignoring async failures because the publisher succeeded.** Exceptions in `void @Async` do not automatically propagate to the publisher. Record failure metrics and handle explicitly.

**Mistake 9 — Concluding deadlock solely from thread names.** You need stack traces, lock/resource state, pool/queue metrics, and wait durations.

**Mistake 10 — Hardcoding container thread names.** Tomcat/Jetty or executor prefixes can change across configurations and versions. Rely on labels your application controls and measure at runtime.

## 16. Operations Checklist

When investigating a slow event or one "running on the wrong thread", check:

1. Are `eventType` and `eventId` logged on both publisher and listener?
2. Is `Thread.currentThread().getName()` logged **inside the callback itself**, not only before submission?
3. Is the application using a synchronous multicaster, `@Async`, a multicaster executor, or multiple executor layers?
4. Are `@EnableAsync`, executor bean names, and proxies configured properly?
5. Do thread prefixes clearly distinguish each workload group?
6. Did the callback lose MDC, security principal, request context, or transaction across the thread hop?
7. Are there signs of pool saturation, queue growth, task rejections, or `CallerRunsPolicy`?
8. Are START→END durations, failure counts, retries, and side-effect states measured?
9. If hung, have thread dumps/stack traces and downstream status been inspected?
10. Do async tests wait with timeouts and avoid asserting unstable exact thread names?

**Remember:** The thread name is **a trace of where code executed**, not proof of business success. With Spring Application Events, log thread names at both publisher and listener, use meaningful executor prefixes, link logs with `eventId`/`traceId`, and verify dispatch mode, context propagation, transactions, error handling, and thread pool health.

## References

- [Spring Framework — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html): default synchronous listeners and `@Async`, exception/context limits.
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `TaskExecutor`, `ThreadPoolTaskExecutor`, `TaskDecorator`, and `@Async`.
- [Spring Framework — Observability Support](https://docs.spring.io/spring-framework/reference/integration/observability.html): event observability and thread-bound context propagation.
- [Spring Framework — SimpleApplicationEventMulticaster API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html): executor configuration and error handler.
- [Spring Boot — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html): logging patterns and configuration for diagnostics.
