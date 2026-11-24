# Impact of Event Multicaster on Threads in Spring Framework

## 1. Where Does the Event Multicaster Sit in the Event-Publishing Flow?

In Spring Framework, `ApplicationEventPublisher.publishEvent(event)` publishes an event so that matching `ApplicationListener` beans or `@EventListener` methods receive it. `ApplicationEventMulticaster` is responsible for finding listeners and **invoking or scheduling execution** of those listeners. The commonly used implementation in `ApplicationContext` is `SimpleApplicationEventMulticaster`.

Basic relationship:

```text
Publisher (running thread)
    |
    | publishEvent(event)
    v
ApplicationEventMulticaster
    |
    +-- identify matching listeners
    +-- choose how to execute listeners
          |
          +-- synchronous: invoke listener directly on publisher thread
          |
          +-- asynchronous: submit listener to Executor, if listener supports it
```

The key point is that **publishing an event does not create a new thread by default**. Which thread a listener uses depends on how the multicaster is configured, whether the listener supports asynchronous execution, and sometimes `@Async` on the listener method.

Terms to keep distinct:

- **Publisher thread**: the thread calling `publishEvent(...)` (for example, an HTTP request-handling thread, a scheduler worker, or a task thread).
- **Listener thread**: the thread actually executing the listener body.
- **Executor/TaskExecutor**: the component that accepts tasks and decides whether they run immediately or are handed off to a worker thread. There are synchronous executors and thread-pool executors.
- **Thread context**: data bound to a thread via `ThreadLocal` or similar mechanisms, such as the thread-bound transaction, logging MDC, security context, or request attributes.
- **Completion**: the moment the listener finishes processing; distinct from when the task is successfully submitted to the executor.

## 2. Default Configuration: Listeners Run on the Publisher's Thread

With the default `SimpleApplicationEventMulticaster` and no asynchronous executor configured, Spring invokes listeners directly on the event-publishing thread. This behaves equivalently to using `SyncTaskExecutor`.

```text
publisher-thread
    |-- executes business code
    |-- publishEvent(E)
    |     |-- listener A runs and finishes
    |     |-- listener B runs and finishes
    |     +-- returns
    +-- continues after publishEvent(E)
```

Consequences:

1. **No thread switch by the multicaster**: `Thread.currentThread()` inside the listener is the exact same `Thread` object as the publisher, when the listener actually runs synchronously.
2. **Publisher waits for listeners**: if one listener takes 500 ms and the next takes 300 ms, the publish call waits for both on the normal synchronous path. Latency adds onto the request/job publishing the event.
3. **Can access active thread context**: if the publisher is inside a thread-bound transaction, synchronous listeners normally run in the same transaction context. Do not mistake this for a guarantee that data has already committed.
4. **Exceptions can propagate back**: if a synchronous listener throws an unhandled error and the multicaster has no suitable `ErrorHandler`, the exception propagates to the publisher and interrupts the current listener loop.
5. **No global ordering across multiple publishers**: two threads publishing events concurrently can run two listener chains in parallel. "Synchronous" only describes the relationship between each event publication and the listeners of that publication.

For example, if an HTTP request calls `publishEvent` on thread `http-nio-...`, a synchronous listener also runs directly on that request thread. A listener calling a slow external API increases HTTP response time accordingly.

## 3. Configuring the Multicaster with TaskExecutor: Listeners Can Move to Worker Threads

`SimpleApplicationEventMulticaster.setTaskExecutor(Executor)` lets you change how listeners execute. If an asynchronous executor is configured (such as `ThreadPoolTaskExecutor` or a thread-pool `ExecutorService`), the multicaster normally **submits the task** and continues. A worker thread then executes the listener logic afterward.

```text
publisher-thread                          event-worker-1
    |                                          |
    |-- publishEvent(E)                        |
    |     |-- executor.execute(listener A) ----+----> listener A
    |     |-- executor.execute(listener B) -----|----> ...
    |     +-- returns                           |
    +-- continues business work                 +-- listener completes later
```

Because a thread pool depends on CPU scheduling and actual load, a listener may start **before or after** `publishEvent` returns. What the scheduling mechanism guarantees is that the multicaster does not actively wait for all async tasks to complete; do not assume a fixed log order without additional synchronization.

A very important point in Spring Framework 6.1 and later: the multicaster checks `ApplicationListener.supportsAsyncExecution()`. If a listener returns `false`, Spring **invokes that listener directly on the publisher thread**, even when the multicaster has an executor. A prime example is `TransactionalApplicationListener`, which must register transaction synchronization on the appropriate thread. Therefore, the statement "configuring an executor means every listener runs on the thread pool" is false.

Calling `setTaskExecutor(...)` does not create concurrency by itself either: if a synchronous executor is passed, listeners still run on the calling thread. Inspect **the executor type and runtime execution behavior**, rather than merely checking whether an executor is configured.

## 4. Complete Java 17 Example: Comparing Same Thread vs. Worker Thread

This example uses Spring Framework 6.2.x in a plain Java application without Spring Boot. It creates two independent `ApplicationContext` instances:

- The first context uses the default multicaster: the listener runs on the same publisher thread.
- The second context declares a bean with the exact name `applicationEventMulticaster`, wired with a single-thread executor named `event-worker`: the listener moves to the worker thread.
- `CountDownLatch` is used **only to produce deterministic illustrative output**. The async listener waits for a signal from the publisher, proving that `publishEvent` returned before the listener printed its output. In real applications, you should not intentionally block a listener just to verify concurrency.

Structure:

```text
event-thread-demo/
├── pom.xml
└── src/main/java/demo/EventThreadDemo.java
```

File `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>event-thread-demo</artifactId>
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
                <version>3.3.0</version>
                <configuration>
                    <mainClass>demo.EventThreadDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/demo/EventThreadDemo.java`:

```java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.context.event.SimpleApplicationEventMulticaster;

public class EventThreadDemo {

    public record TicketCreated(String code) {}

    private static Thread publisherThread;

    public static class SyncListener {
        @EventListener
        public void onTicket(TicketCreated event) {
            boolean sameThread = Thread.currentThread() == publisherThread;
            System.out.println("sync listener, same publisher thread: " + sameThread);
            System.out.println("sync event: " + event.code());
        }
    }

    public static class AsyncListener {
        static final CountDownLatch release = new CountDownLatch(1);
        static final CountDownLatch finished = new CountDownLatch(1);

        @EventListener
        public void onTicket(TicketCreated event) {
            try {
                release.await();
                boolean sameThread = Thread.currentThread() == publisherThread;
                System.out.println("async listener, same publisher thread: " + sameThread);
                System.out.println("async worker: " + Thread.currentThread().getName());
                System.out.println("async event: " + event.code());
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            } finally {
                finished.countDown();
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class SyncConfiguration {
        @Bean
        SyncListener syncListener() {
            return new SyncListener();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AsyncConfiguration {
        @Bean
        AsyncListener asyncListener() {
            return new AsyncListener();
        }

        @Bean(destroyMethod = "shutdown")
        ExecutorService eventExecutor() {
            return Executors.newSingleThreadExecutor(
                    task -> new Thread(task, "event-worker"));
        }

        @Bean(name = "applicationEventMulticaster")
        SimpleApplicationEventMulticaster applicationEventMulticaster(
                ExecutorService eventExecutor) {
            var multicaster = new SimpleApplicationEventMulticaster();
            multicaster.setTaskExecutor(eventExecutor);
            return multicaster;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        publisherThread = Thread.currentThread();

        System.out.println("=== default ===");
        try (var sync = new AnnotationConfigApplicationContext(
                SyncConfiguration.class)) {
            System.out.println("publisher: before");
            sync.publishEvent(new TicketCreated("T-1"));
            System.out.println("publisher: after");
        }

        System.out.println("=== with executor ===");
        try (var async = new AnnotationConfigApplicationContext(
                AsyncConfiguration.class)) {
            System.out.println("publisher: before");
            async.publishEvent(new TicketCreated("T-2"));
            System.out.println("publisher: after");

            AsyncListener.release.countDown();
            if (!AsyncListener.finished.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Async listener timed out");
            }
        }
    }
}
```

Run from the `event-thread-demo` directory with JDK 17+ and Maven installed:

```bash
mvn -q clean compile exec:java
```

Output produced by the `System.out.println` statements:

```text
=== default ===
publisher: before
sync listener, same publisher thread: true
sync event: T-1
publisher: after
=== with executor ===
publisher: before
publisher: after
async listener, same publisher thread: false
async worker: event-worker
async event: T-2
```

Why is this result reliable?

1. The synchronous listener compares the `Thread` object directly with `publisherThread`, so it does not depend on thread names assigned by Maven or the launcher.
2. The custom executor creates a thread named `event-worker`. The async listener prints only after the publisher calls `release.countDown()`, which the publisher does only **after printing** `publisher: after`.
3. `finished.await(...)` makes the program wait for the result so it does not exit before the listener finishes processing. This waiting mechanism is **created by the example itself**, not default waiting behavior of an async multicaster.
4. `@Bean(destroyMethod = "shutdown")` tells Spring to shut down the executor when the context closes; the program waits for the listener to finish before exiting the `try` block.

The example uses `newSingleThreadExecutor` to make **different threads** clear, not to represent an ideal performance configuration. With a multi-thread pool, listeners can run in parallel; with one worker, they are queued in the executor while the publisher can still continue.

## 5. Comparing Configurations and Their Impact on Threads

| Listener registration / configuration | Listener execution thread | Does `publishEvent` wait for listener? | Notes |
| --- | --- | --- | --- |
| Default multicaster + regular `@EventListener` | Same thread as publisher | Yes, on the normal path | Does not require `@EnableAsync` |
| Multicaster with synchronous executor such as `SyncTaskExecutor` | Same thread as publisher | Yes | `setTaskExecutor` is set yet does not switch threads |
| Multicaster with `ThreadPoolTaskExecutor` + async-capable listener | Worker thread in the pool | Does not wait for completion | Submitting/scheduling still has cost and can be rejected |
| Default multicaster + `@Async` on `@EventListener`, async enabled | Thread of the executor serving `@Async` | Does not wait for listener body | Only the annotated listener is affected |
| Async multicaster + `@Async` on listener method | Can have two layers of async scheduling | Should not expect synchronous behavior | Hard to reason about ordering and context; combine only with a clear reason |
| Async multicaster + listener with `supportsAsyncExecution() == false` | Invokes listener on publisher thread | Waits for that synchronous invocation | Example: transaction-synchronized listeners |

The table describes **typical behavior** when the executor accepts work. Certain paths such as executor task rejection, listeners spawning their own threads, or custom framework extensions can make actual behavior differ; when investigating, inspect the running implementation and configuration.

### How Does `@Async` Differ from the Multicaster's Executor?

- `setTaskExecutor` is an **event-dispatching policy at the multicaster level**, typically affecting async-capable listeners across the application.
- `@Async` is a mechanism marking **a single method** to run asynchronously via Spring's async support, usually requiring `@EnableAsync` and a corresponding executor. An `@EventListener` method with `@Async` can move to a worker thread even if the multicaster still invokes the listener's adapter method synchronously.
- For listeners running via `@Async`, exceptions do not propagate back to the event publisher automatically; they must be handled through an appropriate exception-handling policy, such as `AsyncUncaughtExceptionHandler` for `void` async methods.
- If you only need one lightweight listener running in the background, `@Async` may suffice. If you want a consistent policy across many listeners, consider the multicaster's executor and identify exceptions / listeners that must stay on the original thread.

The illustrative snippet below is **not a standalone program**, because it still requires Spring bean configuration and a suitable executor:

```java
@EnableAsync
@Configuration
class AsyncSupport {
}

@Component
class MailEventListener {
    @Async
    @EventListener
    public void onMailQueued(MailQueued event) {
        // Work can run on @Async's executor.
    }
}
```

Imports, the `MailQueued` bean, and application configuration are omitted to focus on the interaction between `@Async` and the multicaster; use the complete example in section 4 to run on your own.

## 6. ThreadLocal, Transactions, SecurityContext, and Logging Context

When a listener switches to another thread, **data bound to the publisher thread does not automatically follow**. This directly affects application correctness and observability:

| Context type | Synchronous on same thread | Async on another thread |
| --- | --- | --- |
| Thread-bound transaction | Regular listener can participate in the open transaction context | Does not automatically inherit thread-bound transaction |
| MDC / trace logging stored via `ThreadLocal` | Usually sees the same correlation ID | Can lose correlation ID if context is not propagated |
| Spring Security `SecurityContextHolder` in default mode | Sees the current thread's security context | Should not assume the worker has the same authentication |
| `RequestContextHolder` | Can see bound request attributes | Not automatically guaranteed to exist on the worker |
| Application-defined `ThreadLocal` | Same object stored on that thread | Worker has its own value or no value |

**Do not share a transaction directly across two threads merely by copying `ThreadLocal`.** Transactions also involve resources and management boundaries; for async work, explicitly define a new transaction on the worker if needed, while considering post-commit consistency. `ContextPropagatingTaskDecorator` and context-propagation mechanisms are useful for tracing/MDC but do not replace transaction management.

For example, an application sending an email after saving a record: if an async listener starts immediately before the record commits, the worker might read data that has not yet appeared in its separate transaction or send an email before the publisher's transaction rolls back. To start only after commit, look into `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` or a durable outbox mechanism if reliable delivery is required. **Using an async multicaster does not provide an after-commit guarantee**.

### Important Exception: TransactionalApplicationListener

Transaction-synchronized listeners typically declare `supportsAsyncExecution() == false`. Therefore, the multicaster must invoke the transaction-synchronization registration part on the publisher thread. If a listener uses `@TransactionalEventListener` with phase `AFTER_COMMIT`, the business callback runs after commit (normally on the thread executing the transaction), rather than being automatically pushed wholesale to the executor by the multicaster.

When there is no active transaction, `@TransactionalEventListener` by default does not execute the listener; `fallbackExecution = true` can be configured when business logic requires it. This is a transaction rule, independent of whether the multicaster has a pool.

## 7. Ordering, Errors, and Performance with a Thread Pool

### Ordering and Completion Timing

With a synchronous multicaster, each matching listener is invoked sequentially within the same event publication. `@Order` can arrange invocation order. When using an asynchronous pool, the multicaster submitting listeners in priority order **does not mean** listeners start or finish in that order: worker A can take longer than worker B; the scheduler and queue length also have an effect.

Even with a single worker, two publishers publishing events concurrently can interleave submissions. If business logic genuinely requires a step sequence A → B → C and unified rollback, calling directly through an orchestrating service is usually clearer and easier to control.

### Errors Differ Between the Two Modes

- **Default synchronous**: unhandled exceptions in a listener can propagate to the publisher, causing the `publishEvent` call to fail.
- **Async via executor**: errors occurring on a worker usually cannot be caught by the publisher with a `try/catch` around `publishEvent` after submission succeeds. Logging, `ErrorHandler`, retries, and result monitoring are needed where async processing happens.
- **Executor rejects task**: Spring 6.2's `SimpleApplicationEventMulticaster` implementation has a branch that handles `RejectedExecutionException` by invoking the listener locally. Consequently, a task expected to run in the background **can execute on the publisher thread** in an executor-rejection scenario. Do not build business-safety logic assuming a fixed thread name.

### Performance, Load, and Resources

Moving heavy listeners to an executor reduces how long the publisher is held by listeners, but it does not make the work disappear. If events arrive faster than they are consumed, the queue can fill up, listener latency can rise, or tasks can be rejected. Choose bounded pools/queues, monitor active tasks, queue latency, errors, retries, and shutdown policies. Running asynchronously only means "processing at a different time and in a different context"; **it is not a durable guarantee that events will still be processed if the process dies**. For guaranteed delivery across crashes, consider a transactional outbox and message broker instead of pure in-process events.

## 8. Practical Troubleshooting

When investigating which thread a listener runs on or why responses are slow, check in order:

1. Log in both publisher and listener: `Thread.currentThread().getName()`, event ID, timestamp, and trace ID. If you need to prove **the exact same thread object**, compare `Thread.currentThread() == publishingThread` directly in a controlled example.
2. Confirm the active `applicationEventMulticaster` bean. Spring uses this exact bean name to replace the context's multicaster. Check whether `setTaskExecutor` was called and whether the actual executor is synchronous or pooled.
3. Distinguish whether the listener is invoked via `@EventListener`, `ApplicationListener`, `@Async`, or `@TransactionalEventListener`. With Spring 6.1+, note `supportsAsyncExecution()`.
4. Check `ThreadLocal`/MDC/SecurityContext/transaction where they are used. If running on another thread, propagate only safe, necessary context through official mechanisms.
5. Do not infer from a single log run that `publishEvent` always returns before the listener: two threads run concurrently and log timing depends on the scheduler.
6. When the publisher is blocked for a long time, measure synchronous listener duration; when listeners are delayed despite a fast publisher, measure queue/pool saturation and pending job counts.
7. Separate retry policies and async error handling from `try/catch` around the publisher. Set timeouts and idempotency for tasks with side effects.

### Self-Check Questions

1. **Which thread does `@EventListener` run on by default?** — On the thread calling `publishEvent`, unless another mechanism such as `@Async` intervenes.
2. **Does merely adding `setTaskExecutor` make every listener run in the background?** — No. The executor might be synchronous, and `supportsAsyncExecution() == false` keeps certain listeners on the event-publishing thread.
3. **Does the publisher wait for listeners submitted to a thread pool to finish?** — Not by default; submission can finish before processing. Waiting requires an explicit mechanism.
4. **Can a publisher's thread-bound transaction be used immediately inside a worker?** — No; you need separate transaction design, post-commit timing, and appropriate context propagation.
5. **With `@Order`, will async listeners always finish in order?** — No.
6. **Is a multicaster thread pool enough if events must still be processed even when the process crashes?** — No; it is still an in-process mechanism, requiring durable storage and delivery mechanisms if business rules demand it.

## References

- [Spring Framework — Application Events / Asynchronous Listeners](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework 6.2 — `SimpleApplicationEventMulticaster` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring Framework 6.2 — Observability, Application Events and Thread Context](https://docs.spring.io/spring-framework/reference/6.2/integration/observability.html)
