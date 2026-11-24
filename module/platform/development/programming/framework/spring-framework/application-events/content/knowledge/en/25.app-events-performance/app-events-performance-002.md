# Slow Listeners Blocking the Publisher in Spring Application Events

## 1. Phenomenon and objectives

In Spring Framework Application Events, an `ApplicationEventPublisher` can dispatch events to multiple listeners within the same `ApplicationContext`. This approach reduces direct coupling between modules, but it easily runs into performance issues if **one listener performs slow work or blocks the thread**.

Example:

- A `placeOrder()` use case saves an order and then calls `publisher.publishEvent(new OrderPlaced(...))`.
- The first `@EventListener` only records an audit log in a few milliseconds.
- The second `@EventListener` calls a partner API or sends an email and has to wait several seconds.
- The HTTP request, message consumer, or publishing service **cannot proceed** until all synchronous listeners finish.

Notably: Spring Framework processes application events **synchronously on the event-publishing thread** by default. Therefore, `publishEvent()` is not always a “fire-and-forget” call. Under the default configuration, a slow listener itself can extend response latency or tie up the publisher's worker.

This lesson helps you:

1. Understand why `SimpleApplicationEventMulticaster` makes `publishEvent()` wait by default.
2. Identify slow listeners and the difference between **synchronous** handling, **`@Async`**, and a multicaster with an executor.
3. Offload slow tasks without mistaking async for durable delivery guarantees.
4. Configure `ThreadPoolTaskExecutor`, queue capacity, rejection, and backpressure properly.
5. Understand the impact on transactions, error propagation, context, and listener ordering.
6. Run a Java 17+ program with `CountDownLatch` proving the publisher is blocked before the listener finishes, then compare it with an `@Async` listener.
7. Design metrics, tests, and a checklist for troubleshooting bottlenecks in production.

## 2. Default mechanism: listeners run on the publisher thread

Spring provides `org.springframework.context.ApplicationEventPublisher`. A bean can inject this interface and publish events:

~~~java
// Illustration inside a Spring-managed service.
publisher.publishEvent(new OrderPlaced(orderId));
~~~

A corresponding listener method:

~~~java
// Illustration inside a Spring bean.
@EventListener
public void onOrderPlaced(OrderPlaced event) {
    paymentGateway.notifyPartner(event.orderId()); // May block.
}
~~~

When no executor is configured on the multicaster and `@Async` is not enabled on the listener, `SimpleApplicationEventMulticaster` invokes callbacks on **the publishing thread** by default. Diagram:

~~~text
HTTP request thread / consumer thread
   |
   +-- service.placeOrder()
         |
         +-- modify business data
         +-- publisher.publishEvent(OrderPlaced)
               |
               +-- Listener A: write log         [fast]
               +-- Listener B: call partner API  [waiting on I/O]
               +-- Listener C: update cache      [fast]
         |
         +-- publishEvent returns after synchronous listeners
         +-- service continues / returns response
~~~

In a single-threaded synchronous dispatch, subsequent listeners may also have to wait for previous listeners to finish. Default listener invocation order depends on configuration and annotations such as `@Order`; however, **changing the order does not eliminate total wait time** if a slow listener remains.

According to the Spring Framework 6.2 documentation, listeners receive events synchronously by default and `publishEvent()` may have to wait for all listeners to complete. Note that this is **the default configuration's behavior**, not a guarantee that every `ApplicationEventPublisher` is always synchronous: the `publishEvent` API itself describes handing off to a multicaster, and implementations may use different strategies.

### 2.1. Why does one slow listener affect many places?

If the publisher is an HTTP request thread, the time the handler holds the thread increases, lengthening response latency and potentially reducing the number of requests the server can process concurrently.

If the publisher runs inside a `@Transactional` service, synchronous listener execution time can keep the transaction open longer, holding connections, locks, and related resources; this increases the risk of contention and timeouts.

If the publisher is a message consumer with bounded concurrency, a slow listener can occupy the consumer thread, increasing topic/queue backlog.

If an event is published during the startup/shutdown lifecycle, a slow callback can also delay the application transitioning to the next phase. Long blocking I/O should be avoided in sensitive lifecycle listeners.

## 3. Latency and throughput analysis

Suppose a publisher thread executes sequentially:

~~~text
business work:  20 ms
listener A:      5 ms
listener B:    250 ms
listener C:     10 ms
-----------------------
approximate time: 285 ms
~~~

In a synchronous configuration without overlapping I/O, total duration for one request is roughly the business work duration plus the duration of the listeners. A single 250 ms callback already dominates latency.

If a single publisher thread can only handle one request at a time, that single thread's maximum serving capacity is roughly the inverse of a single request's processing time; however, **do not conclude that the entire system has only one thread or fixed throughput**, because web servers/consumers have multiple threads, contention, DB connections, and varying real-world workloads.

With N publisher threads, holding each thread for an extra few hundred milliseconds can still reduce effective concurrency. You should evaluate using throughput, percentile latencies (p95/p99), active threads, and backlog rather than looking solely at average CPU.

### 3.1. Slow listeners are not caused only by `Thread.sleep()`

Real-world causes:

- HTTP clients without connect/read timeouts or with overly large timeouts.
- Slow JDBC queries, lock waits, or exhausted connection pools.
- Unstable DNS resolution, SMTP, object storage, or external APIs.
- Listeners performing heavy CPU work on the publisher thread.
- Listeners calling `Future.get()`, `CountDownLatch.await()`, or waiting on a long-held lock.
- Listeners opening nested transactions or accessing a contended service.
- Oversized events where listeners perform complex deserialization/serialization.
- Listeners publishing new events and creating a deep callback chain or wide fan-out.

**`Thread.sleep()` should only appear in simulation demos**, never as a way to “fix” bottlenecks. In this article, the example uses latches to create controlled wait points independent of machine speed.

## 4. Options to avoid blocking the publisher

There are multiple approaches; not every case should be converted to async.

| Approach | Effect | Suitable when | Risks/limitations |
| --- | --- | --- | --- |
| Optimize synchronous listener | Reduces time spent in `publishEvent()` | Callback must remain inside the flow/transaction | Caller still waits |
| `@Async @EventListener` | Listener task runs on a separate executor | A few I/O-heavy listeners where caller does not need to wait for completion | Queueing, rejection, async errors, different thread context |
| Multicaster with `TaskExecutor` | Can move many listeners onto workers | Overall design calls for async dispatch | Affects the entire context, transaction/ordering semantics |
| Write job/outbox and process later | Persists processing intent durably | Critical side effects needing retry after crash | Requires workers, state tracking, idempotency |
| Direct service call | Preserves an explicit synchronous contract | Listener result determines response/rollback | Still incurs latency, though more transparent |
| Batch/coalesce/deduplicate | Reduces work per event | Repeated updates where individual small changes are unnecessary | Requires careful semantics and preventing lost updates |

**Rule of thumb:** if a task is a mandatory condition for the use case to succeed, moving it to `@Async` can break the business contract. You must decide first **whether the caller needs to know the processing outcome**, and only then choose the mechanism.

## 5. `@Async @EventListener`: offloading a slow listener

Example:

~~~java
// Illustration inside a Spring-managed bean.
@Async("notificationExecutor")
@EventListener
public void notifyPartner(OrderPlaced event) {
    partnerClient.notify(event.orderId());
}
~~~

The configuration requires `@EnableAsync` and an executor named `notificationExecutor`. With Spring AOP, `@Async` routes the method call through a proxy/async interceptor to schedule the task.

When properly configured:

1. The publisher still calls the multicaster, and the multicaster still determines which listeners receive the event.
2. Invocation of the async listener is scheduled onto the executor.
3. The publisher does not wait for the async listener's body to finish, but must still complete **the submit operation** to the executor; this operation can fail or experience pressure under overload.
4. A worker processes the event later, potentially after the HTTP request has already returned a response or the publisher's transaction has finished.

### 5.1. Do not equate `@Async` with never blocking

- An executor with a full queue will **reject tasks** or apply a fallback policy. If the policy is `CallerRunsPolicy`, a rejected task may run **directly on the submitting thread**, causing the publisher to block again.
- Scheduling has overhead, locks, context capture, and thread pool interaction; call duration is not always zero.
- If a listener runs asynchronously but other code calls `Future.get()` to wait inside the publisher, blocking can return.
- If another synchronous listener is still slow, `publishEvent()` still waits for that listener; adding `@Async` to one callback does not make all other callbacks async.

### 5.2. Exceptions and return values

With default synchronous listeners, an exception can propagate back to `publishEvent()` (unless handled by an error handler), failing the use case/transaction.

With `@Async @EventListener`, exceptions inside the body do not automatically return to the publisher thread. For `void` methods, configure an `AsyncUncaughtExceptionHandler`, logging, metrics, and an appropriate retry mechanism. If you want a task to expose completion status for coordination, use an abstraction with proper acknowledgment; do not treat a `void` publisher as a business-completion `Future`.

A synchronous `@EventListener` is allowed to produce subsequent events via its **return value**. An `@Async` listener does not support publishing subsequent events via return values under Spring's contract; if a worker needs to emit a new event, inject `ApplicationEventPublisher` and call `publishEvent` explicitly.

## 6. Runnable example: proving sync blocks while async does not wait for the listener

The project uses **Java 17+**, Maven, and **Spring Framework 6.2.12**; no Spring Boot, HTTP server, or database is required.

Two distinct event types keep them independent:

- `SyncWork` has a **synchronous** listener held at `syncRelease`.
- `AsyncWork` has an `@Async("eventExecutor")` listener held at `asyncRelease`.

Main uses a separate thread to call `context.publishEvent(...)`, allowing us to inspect whether the publisher thread has finished. `CountDownLatch` lets us observe wait points without measuring time via `System.currentTimeMillis` or `Thread.sleep()`.

### 6.1. Structure

~~~text
slow-listener-demo/
├── pom.xml
└── src/main/java/demo/SlowListenerDemo.java
~~~

### 6.2. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>slow-listener-demo</artifactId>
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

### 6.3. `src/main/java/demo/SlowListenerDemo.java`

~~~java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class SlowListenerDemo {

    // Java 17 records: event payload is a POJO without needing to extend ApplicationEvent.
    public record SyncWork(String id) {}
    public record AsyncWork(String id) {}

    public static final class Gates {
        final CountDownLatch syncEntered = new CountDownLatch(1);
        final CountDownLatch syncRelease = new CountDownLatch(1);
        final CountDownLatch asyncEntered = new CountDownLatch(1);
        final CountDownLatch asyncRelease = new CountDownLatch(1);
        final CountDownLatch asyncFinished = new CountDownLatch(1);
    }

    private static void awaitRelease(CountDownLatch release) {
        try {
            release.await();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Listener was interrupted", e);
        }
    }

    private static void awaitWithTimeout(
            CountDownLatch latch, String name) throws InterruptedException {
        if (!latch.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Timed out: " + name);
        }
    }

    public static final class SlowSyncListener {
        private final Gates gates;

        public SlowSyncListener(Gates gates) {
            this.gates = gates;
        }

        @EventListener
        public void onSync(SyncWork event) {
            gates.syncEntered.countDown();
            awaitRelease(gates.syncRelease);
        }
    }

    public static class SlowAsyncListener {
        private final Gates gates;

        public SlowAsyncListener(Gates gates) {
            this.gates = gates;
        }

        @Async("eventExecutor")
        @EventListener
        public void onAsync(AsyncWork event) {
            try {
                gates.asyncEntered.countDown();
                awaitRelease(gates.asyncRelease);
            } finally {
                gates.asyncFinished.countDown();
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync(proxyTargetClass = true)
    public static class Config {
        @Bean
        public Gates gates() {
            return new Gates();
        }

        @Bean
        public SlowSyncListener slowSyncListener(Gates gates) {
            return new SlowSyncListener(gates);
        }

        @Bean
        public SlowAsyncListener slowAsyncListener(Gates gates) {
            return new SlowAsyncListener(gates);
        }

        @Bean("eventExecutor")
        public ThreadPoolTaskExecutor eventExecutor() {
            ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(8);
            executor.setThreadNamePrefix("event-worker-");
            executor.setWaitForTasksToCompleteOnShutdown(true);
            return executor;
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService publisherThread =
                Executors.newSingleThreadExecutor();

        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {
            Gates gates = context.getBean(Gates.class);

            try {
                Future<?> syncPublish = publisherThread.submit(
                    () -> context.publishEvent(new SyncWork("s1")));

                awaitWithTimeout(gates.syncEntered, "sync listener start");

                // Listener has entered, but has not received the release signal yet.
                if (syncPublish.isDone()) {
                    throw new AssertionError(
                        "Synchronous publisher returned too early");
                }
                System.out.println("sync-publisher-blocked=true");

                gates.syncRelease.countDown();
                syncPublish.get(5, TimeUnit.SECONDS);
                System.out.println(
                    "sync-publisher-returned-after-release=true");

                Future<?> asyncPublish = publisherThread.submit(
                    () -> context.publishEvent(new AsyncWork("a1")));

                // Worker is inside the listener and waiting for release.
                awaitWithTimeout(gates.asyncEntered, "async listener start");

                // Publisher future completes once the task has been scheduled,
                // WITHOUT needing the async listener to be released.
                asyncPublish.get(5, TimeUnit.SECONDS);
                System.out.println(
                    "async-publisher-returned-before-release=true");

                boolean finishedEarly =
                        gates.asyncFinished.getCount() == 0L;
                if (finishedEarly) {
                    throw new AssertionError(
                        "Async listener finished before release");
                }
                System.out.println(
                    "async-listener-finished-before-release=false");

                gates.asyncRelease.countDown();
                awaitWithTimeout(
                        gates.asyncFinished, "async listener finish");
                System.out.println(
                    "async-listener-finished-after-release=true");
            } finally {
                // Ensure workers are not left hanging if a test assertion fails.
                gates.syncRelease.countDown();
                gates.asyncRelease.countDown();
            }
        } finally {
            publisherThread.shutdownNow();
        }
    }
}
~~~

Run from the directory containing `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.SlowListenerDemo
~~~

Five lines printed by **the program itself** when the conditions are verified:

~~~text
sync-publisher-blocked=true
sync-publisher-returned-after-release=true
async-publisher-returned-before-release=true
async-listener-finished-before-release=false
async-listener-finished-after-release=true
~~~

Maven/Spring may print other logs; the output above consists of the five `System.out.println` lines from the example. There are no timing assertions like “must run under 10 ms”. The `await(..., 5, TimeUnit.SECONDS)` calls act as **timeouts so the test does not hang forever**, not as a production latency metric.

### 6.4. Exact stage-by-stage breakdown

**Synchronous path:**

1. Main submits the `publishEvent(SyncWork)` call to `publisherThread`.
2. `SlowSyncListener` runs **directly on the publishing thread**, signals `syncEntered`, and waits on `syncRelease`.
3. After receiving `syncEntered`, main verifies `syncPublish.isDone() == false`. This proves the publisher **is blocked by the listener**.
4. Main calls `syncRelease.countDown()`; the listener finishes; only then does the `publishEvent` call complete.
5. `Future.get(...)` returns, and main prints `sync-publisher-returned-after-release=true`.

**Asynchronous path:**

1. Main submits `publishEvent(AsyncWork)` to the same `publisherThread`.
2. `@Async` transfers the body of `SlowAsyncListener` to `eventExecutor`.
3. The worker signals `asyncEntered` and waits on `asyncRelease`.
4. Main calls `asyncPublish.get(...)` **while the worker is still being held**, and the publisher call still completes: proving the publisher does not wait for the listener body.
5. Before release, `asyncFinished` has not been counted down; main prints `async-listener-finished-before-release=false`.
6. After release, the worker finishes and counts down the latch in `finally`; main waits and prints `async-listener-finished-after-release=true`.

Two separate event types prevent another synchronous listener from mixing up the `AsyncWork` outcome. The executor is managed and shut down by Spring within the context lifecycle; `finally` opens the latches if an assertion fails.

**Testing limitations:** the example uses a small executor and purposeful events to demonstrate semantics; it does not simulate saturation or benchmark throughput. The code has been reviewed against the Spring 6.2.12 API, though the output shown here is expected from logic rather than from an executed Maven run.

## 7. Alternative: attaching an executor to `applicationEventMulticaster`

You can configure a bean with the special name `applicationEventMulticaster` so the multicaster dispatches listeners supporting async via a `TaskExecutor`:

~~~java
// Illustrative snippet inside @Configuration, not a standalone file.
@Bean(name = "applicationEventMulticaster")
SimpleApplicationEventMulticaster applicationEventMulticaster(
        ThreadPoolTaskExecutor eventExecutor) {

    SimpleApplicationEventMulticaster multicaster =
            new SimpleApplicationEventMulticaster();
    multicaster.setTaskExecutor(eventExecutor);
    return multicaster;
}
~~~

Advantage: many regular listeners can be scheduled asynchronously without adding `@Async` to each method. However, it changes **application-wide `ApplicationContext` behavior**: previously synchronous listeners may now run on different threads, ordering and exception propagation change, and thread-bound contexts are not propagated automatically.

**A very important exception:** `ApplicationListener.supportsAsyncExecution() == false` forces a listener to run on the publisher thread even when the multicaster has an executor. Transaction-synchronized listeners, such as those created by `@TransactionalEventListener`, need to register synchronization on the thread holding the transaction; you cannot assume all listeners are sent to the pool.

If only a few business listeners are slow, `@Async("namedExecutor")` usually provides a narrower, easier-to-test change. Do not turn on global async to mask all performance issues without evaluating the impact on correctness.

## 8. Designing `ThreadPoolTaskExecutor` and backpressure

Moving slow work off the publisher thread to another pool reduces publisher thread hold time **when capacity is sufficient**, but the task still consumes CPU, network, DB, and memory.

Illustrative configuration example:

~~~java
@Bean("notificationExecutor")
ThreadPoolTaskExecutor notificationExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(8);
    executor.setQueueCapacity(100);
    executor.setThreadNamePrefix("notification-");

    // The executor will reject tasks when saturated instead of accepting infinitely.
    // Do not pick CallerRunsPolicy unless you intentionally want backpressure on the caller.
    executor.setRejectedExecutionHandler(
        new ThreadPoolExecutor.AbortPolicy());
    return executor;
}
~~~

The snippet above is a **snippet** inside Spring configuration, requiring imports for `ThreadPoolTaskExecutor` and `java.util.concurrent.ThreadPoolExecutor`. The numbers are examples, **not an optimal configuration for every application**.

### 8.1. Core pool, max pool, and queue

- `corePoolSize`: number of core workers.
- `maxPoolSize`: upper bound to which workers can grow when the queue policy allows.
- `queueCapacity`: number of waiting tasks allowed; should be **bounded** when memory/backpressure control is needed.
- `threadNamePrefix`: aids debugging and metrics.
- Rejection policy: decides what happens when the pool and queue cannot accept more tasks.

With `ThreadPoolTaskExecutor` and a positive queue capacity, the executor normally uses core threads first, then enqueues; **only when the queue is full will it scale threads beyond core** (up to max). Therefore, setting an overly large queue can mean max pool is rarely used, leaving tasks waiting a long time while CPU sits idle on unopened threads.

### 8.2. Rejection is not an error you can ignore

If the queue is full, submission can throw `TaskRejectedException` (or be wrapped/translated from `RejectedExecutionException`). An event that was “published” while its async callback **was never scheduled** is a scenario that requires an explicit policy.

Options:

- **Fail fast:** the publisher receives the submit error and the caller chooses an appropriate retry/rollback/response.
- **CallerRunsPolicy:** the task executes on the submitting thread when the executor is saturated; causes **synchronous backpressure** — whether intentional or not, it makes the publisher wait again.
- **Bounded retry/durable queue:** if the side effect is important, write the processing intent to storage/outbox and let a durable worker retry.
- **Drop/coalesce** only for data that is contractually acceptable to lose (such as certain metrics), while measuring the loss.
- **Throttle the producer** with rate limits or concurrency limits rather than merely increasing the queue.

**Do not use an unbounded queue as a “throughput fix”**: it simply trades latency for memory and backlog until resources run out.

### 8.3. Estimating capacity

Suppose a listener takes an average of 200 ms per task and has 4 continuously busy workers. Under simplified conditions with zero overhead/contention, the pool serves roughly `4 / 0.2 = 20 tasks/second`. If the producer emits 50 events/second over a sustained period, the backlog grows by roughly 30 tasks/second. A bounded queue will eventually fill up.

These numbers only explain the mechanism; actual capacity depends on processing time distribution, I/O concurrency, retries, fan-out, locks, and infrastructure. Measure p95/p99 instead of relying only on the mean.

## 9. Transactions, consistency, and durability

### 9.1. Synchronous listeners run inside the publisher's transaction

Application service example:

~~~java
// Illustration inside a Spring-managed bean.
@Transactional
public void submitOrder(long orderId) {
    repository.insertOrder(orderId);
    publisher.publishEvent(new OrderSubmitted(orderId));
}
~~~

With the default synchronous multicaster, regular listeners run immediately inside `publishEvent` and **can participate in the publisher's thread-bound transaction**. If a listener calls a slow API, the transaction may be prolonged. If a synchronous callback throws a RuntimeException, the exception can cause the transaction to roll back according to active rules.

Do not “fix” this by moving a critical business invariant to async and returning a success response even though the business step has not completed.

### 9.2. Async listeners do not automatically inherit the old transaction

With `@Async`, the body runs on a different thread and thus does not automatically participate in the publisher's thread-bound transaction. When the worker starts, the main transaction might still be open or already finished. A worker reading the database from another connection might **not see uncommitted data yet**.

If work should only start after commit, `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` is the right fit; for work that needs to be offloaded after commit, it can be combined with `@Async` by design, with proper verification of transaction semantics. An async callback that needs to write to the DB typically has to open its **own** transaction, e.g., via another service annotated with `@Transactional` through a proxy.

By default, `@TransactionalEventListener` ignores events published outside a transaction when `fallbackExecution=false`. It also does not solve durability or retries if the JVM crashes after commit.

### 9.3. `AFTER_COMMIT` is not a reliable queue

An in-JVM post-commit callback may not get to run if the process crashes. If a business side effect must execute reliably, use a **transactional outbox**: write the outbox record **in the same transaction as the business state**, commit atomically, and have a worker/relay send messages and retry on failures.

~~~text
BEGIN TRANSACTION
    INSERT order state
    INSERT outbox event
COMMIT
    |
    +-- relay reads outbox
          +-- sends message, retries, observability
          +-- idempotent consumer
~~~

An outbox durably persists the **intent to send**, without automatically guaranteeing end-to-end exactly-once delivery. Duplicates can occur when the relay sends successfully before updating the status; consumers need `eventId` and idempotency.

## 10. Error handling and isolation between listeners

In a synchronous multicaster, an exception from a listener can **halt dispatch** and propagate to the publisher if there is no custom error handler. This can be desirable if the listener is a mandatory step of the use case; however, if the listener only records metrics, a metrics error should not necessarily roll back an order.

Spring's `SimpleApplicationEventMulticaster` supports `setErrorHandler(...)`. Be careful not to swallow errors blindly:

~~~java
// Illustration: should only be used for side effects that do not determine use-case outcome.
multicaster.setErrorHandler(error ->
        logger.error("Application event listener failed", error));
~~~

If you choose a handler that does not rethrow, callback errors may no longer propagate to the publisher. This **changes the error policy**, not just performance. For important side effects, you need retries/queues or explicit orchestration responsible for handling failures.

With an `@Async @EventListener` returning `void`, exceptions are handled by Spring's async mechanism and do not automatically propagate back to the publisher thread. Configure `AsyncUncaughtExceptionHandler`, log event IDs and correlation IDs, and set up dashboards for failed task counts. With a global multicaster executor, the error handler and `TaskExecutor` play different roles; test the exact boundary where errors are caught.

## 11. ThreadLocal, MDC, and security when switching threads

Moving listeners to an executor also alters context:

- Custom `ThreadLocal` values usually do not carry over to the worker.
- MDC/tracing/observation context can be lost without propagation.
- ThreadLocal-based `SecurityContextHolder` needs a security-aware executor mechanism when the principal genuinely must be propagated.
- `TransactionSynchronizationManager` **does not copy raw transaction resources** over to the worker.
- The HTTP request may have already ended when the worker runs; do not pass a live `HttpServletRequest` as payload.

You can pass `traceId`, `orderId`, `tenantId`, and necessary data explicitly in the event payload. For logging/observation, Spring provides `ContextPropagatingTaskDecorator` combined with Micrometer Context Propagation when appropriate accessors are configured.

**Security note:** a correlation/tenant ID in an event or MDC does not authenticate access rights on its own. Listeners must enforce authorization/tenant boundaries according to system rules.

## 12. `@Order` and fan-out do not solve bottlenecks

Spring supports `@Order` to adjust listener invocation priority:

~~~java
// Illustration inside a Spring bean.
@Order(10)
@EventListener
public void first(OrderPlaced event) { /* ... */ }

@Order(20)
@EventListener
public void second(OrderPlaced event) { /* ... */ }
~~~

When both are synchronous, the publisher still has to wait for the callbacks; changing the order only changes which callback is called first. When listeners are async, `@Order` **does not guarantee task completion order**. If step B truly depends on step A's result, use a workflow/orchestrator or pipeline with acknowledgments, rather than relying solely on event subscriber ordering.

Fan-out also needs control. One event triggering ten synchronous callbacks can hold the publisher longer than one callback, especially if each listener makes external I/O calls. Avoid emitting arbitrary child events without termination conditions, hop limits, or a state machine; an event storm can cause bottlenecks even if each individual callback is fairly fast.

## 13. When should a listener stay synchronous?

Async is not the default answer. Some tasks should remain synchronous:

- Mandatory invariant checks before the use case returns.
- State updates in the same transaction when results must be atomic with the business operation.
- Very fast, deterministic processing requiring no external I/O and adding negligible latency.
- Work whose errors the caller must know immediately to return a valid response.

However, if it is genuinely business logic determining the success of the use case, an **explicit service call** can provide a clearer contract than a hidden event listener. Events are usually well-suited when downstream reactions can be decoupled from the primary decision.

Conversely, emails, analytics, cache refreshes, or external API calls can be decoupled if business rules allow; however, you must decide how to handle retries, idempotency, and real failures rather than just “marking async”.

## 14. Diagnosing bottlenecks in production

### 14.1. Symptoms

- p95/p99 HTTP latency rises precisely when event traffic increases.
- Request worker threads are occupied and many stack frames appear in `@EventListener`, HTTP clients, or JDBC.
- Thread dumps show publisher threads waiting on I/O inside listeners.
- Transaction duration, DB lock waits, and connection utilization increase.
- Consumer lag/backlog grows even without direct failures visible on the publisher.
- With async, executor `activeCount` is high, `queueSize` climbs, and rejected tasks and timeouts increase.

### 14.2. Gathering evidence

1. Identify the event type and all registered listeners.
2. Measure **the time from before to after `publishEvent`** at the caller using an appropriate timer/observation.
3. Measure the slow listener's own execution time; separate I/O, DB, CPU, queueing, and retry time.
4. Capture thread dumps during slowdowns to inspect publisher and worker stacks.
5. Check whether the multicaster has a custom `applicationEventMulticaster` bean and which executor is actually used.
6. Verify whether `@Async` works through a Spring proxy; if a method calls `this.method()` within the same bean, async advice is usually not applied.
7. Cross-check executor metrics: `activeCount`, `poolSize`, queue depth, rejections, task latency.
8. Classify the issue: “publisher is blocked” vs. “publisher returns fast but the async queue is backing up”.

A common observability mistake is measuring only the callback body while ignoring **the time tasks wait in the queue**. A listener might run in 30 ms yet start after 30 seconds, meaning end-to-end latency is still terrible.

Spring does not automatically generate complete observations for every `@EventListener` invocation with your expected semantics; if you need reliable metrics, explicitly instrument **publish**, **queue wait**, **callback execution**, and **business completion** boundaries.

### 14.3. Minimum recommended metrics

| Metric | Meaning |
| --- | --- |
| `publisher.duration` | Time `publishEvent` holds the caller thread |
| `listener.execution.duration` | Execution time of the listener body |
| `listener.queue.delay` | From submission until the worker starts |
| `listener.errors` | Errors by event type/listener |
| `executor.active`, `executor.queued` | Pool saturation |
| `executor.rejected` | Events/tasks that could not be scheduled |
| `outbox.backlog`, `outbox.oldest_age` | Ability to complete post-processing durably |
| `business.callback.completed` | Business side effect reached the desired state |

Metric names are **application naming suggestions**, not a claim that Spring provides all these metrics out of the box. Avoid putting raw `eventId` or `userId` into high-cardinality metric tags; put them in logs/traces instead of series labels.

## 15. Testing accurately without relying on `Thread.sleep()`

### 15.1. Proving blocking behavior

The example above does not assert latency below a millisecond threshold, which is prone to flaking on slow CI. Instead, it tests synchronization conditions:

- The sync listener **has entered the method** and **has not been released**.
- The sync publish call **has not finished yet**.
- Once released, only then does the publisher finish.
- With async, the worker **has entered the method** and **is not released yet**, while the publisher's Future has already completed.
- After release, the async listener completes.

This anchors the test to dispatcher semantics rather than whether the scheduler happens to be faster than 5 ms. The 5-second timeout is simply a guard to detect failures/deadlocks in the demo environment and can be tuned for real CI.

### 15.2. Separate saturation tests

Do not use the demo above to conclude the system is safe under heavy load. A separate test is needed for:

1. Fixed worker count and small queue capacity.
2. Submitting more events than capacity while workers are intentionally blocked.
3. Verifying the rejection/backpressure policy **matches the contract**.
4. Verifying the publisher is notified of submit errors if required by policy.
5. Verifying no critical events are lost when using outbox/durable messaging.
6. Verifying executor state after errors or shutdown.

### 15.3. Transaction and error tests

- If the publisher is inside `@Transactional`, verify the sync listener sees an active transaction and whether a slow callback prolongs the transaction.
- If using `@TransactionalEventListener(AFTER_COMMIT)`, test both commit and rollback; the event may have been published, yet AFTER_COMMIT does not run on rollback.
- If using `@Async`, test that side effects are only observed after the worker completes and that exceptions do not propagate back to the publisher.
- If the publisher needs the callback's outcome to determine success, do not replace a synchronous callback with async while omitting business-outcome verification.

## 16. Common mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Calling slow REST/SMTP from a default `@EventListener` | Holds publisher thread and transaction for a long time | Optimize I/O, add timeouts; consider async or outbox |
| Moving all listeners to async to “fix” latency | Loses sequencing/transaction/error semantics | Offload only tasks that can be processed independently |
| Increasing the queue without managing throughput | Backlog/memory grow | Bounded queue, concurrency limits, measure arrival/service rates |
| Using `CallerRunsPolicy` while expecting publish never to wait | Saturated workers make callers run tasks themselves | Choose an appropriate policy, accept backpressure deliberately |
| Choosing too few workers for long I/O | Queue delay increases | Measure duration/concurrency and set sensible I/O limits |
| Choosing too many workers | Saturates DB, network, memory | Measure load and cap downstream resources |
| Assuming async listeners receive transaction/MDC | Lost context, uncommitted data | Event payload, selective context propagation, new transaction |
| Assuming `@Async` has built-in retries | Tasks fail/are lost when the JVM crashes | Error handling, retries/durable queue/outbox |
| Using `@Order` to make async tasks finish sequentially | Race condition | Orchestrator/acknowledgment when ordering is required |
| Ignoring submit rejections | Business events lose reactions | Enforce failure policy, monitoring, and durable storage |
| Using `Thread.sleep()` to “wait” for listeners in tests | Flaky tests | Latch/Future with timeouts |
| Assuming `publishEvent` returning means all subscribers succeeded | Async callbacks may not have run yet | Assert business completion separately |

## 17. Implementation checklist

1. Do you know which listeners consume time and which threads they run on?
2. Are you measuring **publisher wait time**, queue delay, and listener processing time separately?
3. Is the slow listener a core invariant or just a secondary side effect?
4. If moving to async, does the application have `@EnableAsync` and the correctly named executor?
5. Are pool/queue bounded with an explicit rejection policy?
6. Under overload, does the publisher fail, run the task itself, or drop it? Does that outcome match business requirements?
7. Does the listener need committed data or a new transaction?
8. Have you addressed `AsyncUncaughtExceptionHandler`, retries, idempotency, and crash recovery?
9. Are correlation IDs/trace context propagated appropriately without copying transaction resources?
10. Do tests prove sync callbacks block, async callbacks switch threads, and saturation behaves as designed?

**Conclusion:** Slow listeners block the publisher because **Spring's default multicaster invokes listeners synchronously right on the event-publishing thread**. Optimizing callbacks is the first step; use `@Async` or a custom executor if the work can be deferred, while governing **queues, rejections, error handling, context, and transactions**. For critical work that must survive crashes, use an outbox/durable queue rather than relying on an in-memory executor.

## Official documentation

- Spring Framework 6.2 — ApplicationContext events and `@Async`: https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html
- Spring Framework 6.2 — `SimpleApplicationEventMulticaster`: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html
- Spring Framework 6.2 — `ApplicationEventPublisher`: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/ApplicationEventPublisher.html
- Spring Framework 6.2 — Scheduling and `@Async`: https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html
- Spring Framework 6.2 — Transaction-bound events: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html
- Spring Framework 6.2 — Observability and context propagation: https://docs.spring.io/spring-framework/reference/6.2/integration/observability.html
