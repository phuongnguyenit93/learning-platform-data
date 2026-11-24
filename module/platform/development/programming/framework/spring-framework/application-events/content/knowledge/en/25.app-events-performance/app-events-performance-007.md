# Latency from Sequential Listeners in Spring Framework Application Events

## 1. Why can a single publishEvent call be slow?

A service may simply call `ApplicationEventPublisher.publishEvent(event)` to announce a newly created order, yet the request still takes hundreds of milliseconds or several seconds before returning. The cause is often **multiple listeners invoked sequentially on the publisher's own thread**.

Spring Framework uses `SimpleApplicationEventMulticaster` with synchronous execution by default if the application context is not customized. When an event matches multiple `@EventListener`s, the multicaster invokes each listener; the previous callback must return before the next callback is invoked in that synchronous dispatch pass. If three listeners take 60 ms, 90 ms, and 120 ms respectively, active waiting alone is 270 ms, excluding dispatch and other overhead.

This lesson helps you:

- Understand **how multiple listeners add up to increase latency** of a single event publish.
- Distinguish total publish duration, per-listener duration, queue delay, and business completion latency.
- Recognize that `@Order` only controls invocation order, without making listeners run in parallel.
- Grasp the impact of exceptions, nested events, transactions, and differences across publisher threads.
- Run a Java 17+ example with three synchronous listeners and measure duration.
- Write JUnit 5 tests verifying ordering, exception propagation, and async publishers returning before listeners complete.
- Choose latency-reduction strategies without silently trading away correctness and event durability.

**Key takeaway:** Reducing the measured duration of `publishEvent` does not necessarily reduce the time until the actual work completes. In particular, switching to async may only shift cost from the request thread to a worker/queue.

## 2. Default event dispatch mechanism

Involved components:

| Component | Role |
| --- | --- |
| `ApplicationEventPublisher` | API to publish an event to Spring's infrastructure |
| `ApplicationEventMulticaster` | Selects and dispatches to matching listeners |
| `SimpleApplicationEventMulticaster` | Simple multicaster; synchronous on caller thread by default |
| `ApplicationListener<T>` | Listener implemented as an interface |
| `@EventListener` | Declares a listener on a Spring bean method |
| `@Order` | Determines priority/order in which listeners are invoked |
| `TaskExecutor`, `@Async` | Can offload execution to another thread if configured |

A service method might publish an event via:

~~~java
publisher.publishEvent(new OrderSubmitted(orderId));
~~~

Three listeners:

~~~java
@EventListener
public void updateInventory(OrderSubmitted event) {
    inventoryService.update(event.orderId());
}

@EventListener
public void calculateBilling(OrderSubmitted event) {
    billingService.calculate(event.orderId());
}

@EventListener
public void notifyCustomer(OrderSubmitted event) {
    notificationService.send(event.orderId());
}
~~~

The snippets above are **illustrative only**; the event class, service beans, and corresponding imports are required. A complete runnable example is in section 8.

With a synchronous multicaster, the typical path is:

~~~text
request/service thread
     |
     +---> publishEvent(OrderSubmitted)
                |
                +---> updateInventory() -- return
                |
                +---> calculateBilling() -- return
                |
                +---> notifyCustomer() -- return
                |
                +---> publishEvent() returns
     |
     +---> service continues / HTTP response
~~~

Each callback here lies on the **critical path of the publish call**. If a listener runs slow I/O, the publisher waits for it.

Be precise: “sequential” only describes **listeners within a single synchronous dispatch pass**. It does **not** create a global lock across all events. Two separate HTTP request threads can still publish simultaneously and execute callbacks on their respective threads; shared underlying resources (DB, locks, services) may still contend with one another.

## 3. Cumulative latency model

In a simple case:

~~~text
T_publish ≈ T_dispatch + T_listener1 + T_listener2 + ... + T_listenerN
~~~

This model applies **when all listeners run synchronously, all are invoked, and no exception short-circuits the multicast**. `T_dispatch` can include event-type filtering overhead, adapter lookup, method invocation, and minor bookkeeping.

Example:

| Listener | Work | Hypothetical duration |
| --- | --- | --- |
| Inventory | Check inventory | 40 ms |
| Billing | Calculate and save invoice | 120 ms |
| Notification | Send notification | 250 ms |
| Total callback time | Three sequential tasks | 410 ms |

If dispatch overhead is small, time measured around `publishEvent` is close to 410 ms. These are **arithmetic examples**, not performance benchmarks established by Spring.

Timeline:

~~~text
Time →
Publish starts
|--- Inventory 40ms ---|
                       |------- Billing 120ms -------|
                                                  |---------- Notification 250ms ----------|
                                                                                             |
                                                                                      Publish returns
~~~

The last listener **cannot start** until the preceding callback returns in synchronous mode. If notification times out after 5 seconds, even a tiny event can make the publish call take 5 seconds.

### 3.1. How does this add to request latency?

Suppose the service takes 10 ms for validation, 30 ms for SQL, 410 ms for publish, and 5 ms for response mapping. The request takes roughly **455 ms**, even though SQL itself is quite fast.

~~~text
validate:         10 ms
database:         30 ms
publish:         410 ms  (includes listener execution)
serialize:         5 ms
-----------------------
request:         455 ms
~~~

This is not a real system measurement. In real traces, callbacks may nest other events, DB queries may contend on locks, or the active transaction may cause timings far from the simple model.

### 3.2. Tail latency matters more than the average

If two listeners are consistently fast while one HTTP listener occasionally takes several seconds, **p95/p99 of publish** and of requests can spike sharply. Average measurements from local dev cannot prove production SLOs are met.

Collect throughput, duration distributions, active request threads, DB pool waits, downstream timeouts, and queue depth if async is used.

## 4. @Order controls sequence, not parallelism

Spring supports:

~~~java
@EventListener
@Order(10)
public void inventory(OrderSubmitted event) {
    // ...
}

@EventListener
@Order(20)
public void billing(OrderSubmitted event) {
    // ...
}

@EventListener
@Order(30)
public void notification(OrderSubmitted event) {
    // ...
}
~~~

This is illustrative; the methods must belong to Spring beans.

In a synchronous setup, invocation order is inventory, billing, notification. Changing `@Order(30)` to `@Order(-100)` can cause notification to be called first, **but does not make the callbacks run concurrently**. Total processing cost generally remains if all execute.

In an async setup, `@Order` can govern **dispatch** order, whereas **completion** order depends on thread scheduling, each handler's duration, and the executor. Do not rely on annotation order to guarantee an email finishes after billing commits when execution is asynchronous.

If one listener genuinely depends on data produced by another listener, consider an explicit service workflow or contract-based result coordination rather than relying on implicit event-bus ordering.

## 5. Exceptions can cause the publisher to return early for the wrong reason

In the default synchronous multicaster, if a listener throws an unhandled `RuntimeException`, the exception can halt the multicasting pass and propagate back to the publisher.

~~~text
L1 -> success
L2 -> throws RuntimeException
L3 -> never invoked
publisher -> receives exception
~~~

This leads to a misleading outcome: publish duration **drops** because L3 never got a chance to run, yet that is **not a successful optimization**.

Consequences:

- L1 may have already performed side effects, L2 failed, and L3 never ran.
- If the publisher retries the whole event, L1 may run again.
- Inside an active transaction, the exception can cause the transaction to roll back per applicable rules.
- If L1 already sent an email before rollback, the email cannot be recalled automatically.
- If a configured `ErrorHandler` swallows the error, multicasting can continue, but you must explicitly accept the error-logging/retry policy.

`SimpleApplicationEventMulticaster#setErrorHandler(...)` is an exception-handling extension point; **it does not automatically provide a dead-letter queue, durable retries, or exactly-once delivery**. Never swallow errors just to report a “fast publisher”.

## 6. Difference between multiple listeners and multiple publishers

Three listeners in **one synchronous publish pass** run sequentially on thread A. Meanwhile, thread B can still publish another event and invoke those very same listener methods concurrently.

~~~text
Thread A:  publish(E1) -> L1(E1) -> L2(E1) -> L3(E1)
Thread B:      publish(E2) -> L1(E2) -> L2(E2) -> L3(E2)
~~~

In practice:

- A Spring singleton listener can be called by multiple threads simultaneously. It must be **thread-safe** or avoid mutable shared state.
- Database locks, thread pools, HTTP connection pools, and rate limits can cause two publish calls to interfere with each other.
- `@Order` does not apply a **system-wide** mutex enforcing order between E1 and E2.
- If listeners write to a shared resource, contention increases duration even if each method looks simple on its own.

Do not slap `synchronized` indiscriminately onto entire listeners to “guarantee order”, as that can serialize many request threads and bottleneck throughput.

## 7. Common reasons listeners become slow

| Cause | Symptom | Investigation hint |
| --- | --- | --- |
| N+1 JPA queries | Handler fast on small data, slows down with order size | SQL logs, query counts, projections |
| Slow HTTP dependency | Request/publish p99 rises with timeouts | HTTP client timers, tracing, timeouts |
| DB locks / deadlock retries | Requests wait despite low CPU | Lock metrics, transaction duration |
| Large serialization graph | Allocation, CPU, and GC rise | JFR/heap profiler |
| Synchronous I/O | Many request threads in WAITING | Thread dumps, wall-clock profiler |
| Excessive logging | Hot path slows under sync logging or disk contention | Logging profiler, sampling |
| Listener publishes nested events | Unpredictable latency, deep call stacks | Trace nested publishes |
| Unbounded inline retries | Requests hang when dependencies fail | Retry policy, attempt counts |
| Missing caches or batching | Too many DB/network round trips | Query planner, batching |
| Exhausted resource pools | Threads wait on connections despite short handler logic | Pool usage and wait times |

What needs optimization is not necessarily the number of listeners: keeping three callbacks is fine if each does tiny work. Conversely, a single listener hitting a 30-second HTTP timeout is enough to drag down publish.

## 8. Runnable Java 17+ example: three sequential listeners

The example uses plain Spring Framework 6.2.15 and JUnit 5. No web server, database, or Spring Boot is needed. To simulate observable latency, the three listeners use short `Thread.sleep` calls totaling 270 ms; **never use sleep as a production event-handling technique**.

### 8.1. Directory structure

~~~text
sequential-event-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   └── java/
    │       └── demo/
    │           └── SequentialEventDemo.java
    └── test/
        └── java/
            └── demo/
                └── SequentialEventDemoTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'sequential-event-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.15'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}

application {
    mainClass = 'demo.SequentialEventDemo'
}

test {
    useJUnitPlatform()
}
~~~

### 8.2. Complete Java code

Create `src/main/java/demo/SequentialEventDemo.java`:

~~~java
package demo;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;

public class SequentialEventDemo {

    public record OrderSubmitted(String orderId) {}

    public static final class Trace {
        private final CopyOnWriteArrayList<String> stages =
                new CopyOnWriteArrayList<>();

        public void add(String stage) {
            stages.add(stage);
        }

        public List<String> snapshot() {
            return List.copyOf(stages);
        }
    }

    public static final class Handlers {
        private final Trace trace;

        public Handlers(Trace trace) {
            this.trace = trace;
        }

        @EventListener
        @Order(10)
        public void inventory(OrderSubmitted event) {
            simulate("inventory", 60);
        }

        @EventListener
        @Order(20)
        public void billing(OrderSubmitted event) {
            simulate("billing", 90);
        }

        @EventListener
        @Order(30)
        public void notification(OrderSubmitted event) {
            simulate("notification", 120);
        }

        private void simulate(String name, long durationMillis) {
            System.out.println("begin:" + name);

            try {
                Thread.sleep(durationMillis);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(
                        "Interrupted in " + name, ex);
            }

            trace.add(name);
            System.out.println("end:" + name);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {

        @Bean
        public Trace trace() {
            return new Trace();
        }

        @Bean
        public Handlers handlers(Trace trace) {
            return new Handlers(trace);
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            Trace trace = context.getBean(Trace.class);

            System.out.println("publisher:begin");
            long start = System.nanoTime();

            context.publishEvent(new OrderSubmitted("ORD-7"));

            long duration = System.nanoTime() - start;
            System.out.println("publisher:return");
            System.out.println(
                    "trace=" + String.join(",", trace.snapshot()));
            System.out.printf(
                    "publish.duration.ms=%.1f%n",
                    duration / 1_000_000.0);
        }
    }
}
~~~

### 8.3. Running the demo and reading stdout

In the project directory, with JDK 17+ and Gradle:

~~~bash
gradle -q run
~~~

If using the Gradle Wrapper, replace with `./gradlew -q run` on Linux/macOS or `gradlew.bat -q run` on Windows.

Lines with deterministic content and order:

~~~text
publisher:begin
begin:inventory
end:inventory
begin:billing
end:billing
begin:notification
end:notification
publisher:return
trace=inventory,billing,notification
publish.duration.ms=<varying value>
~~~

**The last line is an explanatory placeholder**, not a literal printed by `printf`. In an actual run, it is a decimal number, roughly around or above 270 ms. The exact figure depends on the scheduler, CPU, GC, logging, and machine load; no fixed number is promised. Stdout may also include Gradle/framework logs.

The output proves: `publisher:return` appears only **after** all three `end:...` lines; the callbacks are invoked sequentially and all three finish before `publishEvent` returns.

Note: `@Order` makes the sequence predictable in the demo, while the publisher waiting until the end is due to **the synchronous multicaster**. Do not conflate these two roles.

## 9. JUnit 5: testing synchronous, exception, and asynchronous cases

Create `src/test/java/demo/SequentialEventDemoTest.java`. Do not use Mockito to mock the event bus: the tests build a real `AnnotationConfigApplicationContext` and publish events through Spring.

The third test uses an executor and `CountDownLatch` to prove that in an async setup, the publisher can return while the handler is still waiting. Do not use `Thread.sleep` to guess when the worker finishes.

~~~java
package demo;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.ApplicationEventMulticaster;
import org.springframework.context.event.EventListener;
import org.springframework.context.event.SimpleApplicationEventMulticaster;
import org.springframework.core.annotation.Order;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SequentialEventDemoTest {

    @Test
    void syncPublishWaitsForAllThreeHandlers() {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             SequentialEventDemo.Config.class)) {

            SequentialEventDemo.Trace trace =
                    context.getBean(SequentialEventDemo.Trace.class);

            assertTrue(trace.snapshot().isEmpty());

            context.publishEvent(
                    new SequentialEventDemo.OrderSubmitted("A"));

            // No sleep needed after publish: all 3 listeners have completed.
            assertEquals(
                    List.of("inventory", "billing", "notification"),
                    trace.snapshot());
        }
    }

    public record FailureRequested() {}

    public static final class FailureHandlers {
        private final CopyOnWriteArrayList<String> calls =
                new CopyOnWriteArrayList<>();

        @EventListener
        @Order(10)
        public void first(FailureRequested event) {
            calls.add("first");
            throw new IllegalStateException("listener failed");
        }

        @EventListener
        @Order(20)
        public void second(FailureRequested event) {
            calls.add("second");
        }

        public List<String> snapshot() {
            return List.copyOf(calls);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class FailureConfig {

        @Bean
        public FailureHandlers failureHandlers() {
            return new FailureHandlers();
        }
    }

    @Test
    void exceptionStopsLaterListenerInSyncMode() {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             FailureConfig.class)) {

            FailureHandlers handlers =
                    context.getBean(FailureHandlers.class);

            assertThrows(
                    IllegalStateException.class,
                    () -> context.publishEvent(new FailureRequested()));

            assertEquals(List.of("first"), handlers.snapshot());
        }
    }

    public record HoldRequested() {}

    public static final class BlockingListener {
        final CountDownLatch started = new CountDownLatch(1);
        final CountDownLatch release = new CountDownLatch(1);
        final CountDownLatch finished = new CountDownLatch(1);

        @EventListener
        public void onHold(HoldRequested event) {
            started.countDown();

            try {
                if (!release.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "Listener was not released");
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(
                        "Interrupted while waiting", ex);
            } finally {
                finished.countDown();
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AsyncConfig {

        @Bean
        public ThreadPoolTaskExecutor eventExecutor() {
            ThreadPoolTaskExecutor executor =
                    new ThreadPoolTaskExecutor();

            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(8);
            executor.setThreadNamePrefix("event-demo-");
            return executor;
        }

        @Bean(name = "applicationEventMulticaster")
        public ApplicationEventMulticaster applicationEventMulticaster(
                ThreadPoolTaskExecutor eventExecutor) {

            SimpleApplicationEventMulticaster multicaster =
                    new SimpleApplicationEventMulticaster();

            multicaster.setTaskExecutor(eventExecutor);
            return multicaster;
        }

        @Bean
        public BlockingListener blockingListener() {
            return new BlockingListener();
        }
    }

    @Test
    void asyncPublisherReturnsBeforeHandlerIsReleased()
            throws InterruptedException {

        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             AsyncConfig.class)) {

            BlockingListener listener =
                    context.getBean(BlockingListener.class);

            context.publishEvent(new HoldRequested());

            try {
                assertTrue(listener.started.await(5, TimeUnit.SECONDS));

                // Handler is waiting for release; publish has already returned.
                assertEquals(1L, listener.finished.getCount());
            } finally {
                listener.release.countDown();
            }

            assertTrue(listener.finished.await(5, TimeUnit.SECONDS));
        }
    }
}
~~~

### 9.1. Running the tests

~~~bash
gradle test
~~~

**3 JUnit 5 tests** are expected to pass if dependencies resolve and wait timeouts are not disrupted by the CI environment. Gradle typically generates a report at `build/reports/tests/test/index.html`. This is **logical expectation**, not the output of a test run executed here.

### 9.2. Meaning of each test

- `syncPublishWaitsForAllThreeHandlers`: immediately after `publishEvent` returns, the trace already holds all three stages in `@Order`. Verifies **Spring wiring** and true synchronous execution.
- `exceptionStopsLaterListenerInSyncMode`: the first listener's runtime error propagates to the publisher; the second listener is not invoked under default configuration.
- `asyncPublisherReturnsBeforeHandlerIsReleased`: the listener starts on the executor and awaits the latch. The publisher has already returned while `finished` has not counted down; after release, the handler exits.

The async test deliberately isolates `AsyncConfig` rather than applying an executor to the sync tests. The executor has one worker with a bounded queue; it **does not prove parallel execution of multiple listeners**, only the difference in when the publisher returns.

## 10. Switching to async: reduces publish wait, not necessarily completion time

You can provide a multicaster bean with the special name `applicationEventMulticaster`:

~~~java
@Bean(name = "applicationEventMulticaster")
ApplicationEventMulticaster eventMulticaster(
        ThreadPoolTaskExecutor executor) {

    SimpleApplicationEventMulticaster multicaster =
            new SimpleApplicationEventMulticaster();

    multicaster.setTaskExecutor(executor);
    return multicaster;
}
~~~

This is an illustrative configuration snippet; the test file already contains the full `AsyncConfig`. For regular async-capable listeners, the multicaster submits work to the executor instead of invoking every callback directly on the publisher thread.

Idealized model comparison:

~~~text
SYNCHRONOUS:
    L1: 60 ms
           L2: 90 ms
                     L3: 120 ms
    Publisher wait ≈ 270 ms + overhead

ASYNCHRONOUS with enough workers and independence:
    L1: 60 ms
    L2: 90 ms
    L3: 120 ms
    All done ≈ 120 ms + queue/dispatch/overhead
    Publish may return shortly after submission
~~~

The models above are **ideal load assumptions**, not executor guarantees. If the pool has only one worker, the three handlers still execute sequentially in the queue. The publisher returns sooner, yet the time until all callbacks complete may stay close to the old total—or longer if there is a backlog.

**Measure two things separately:** `publish latency` and `business completion latency`. An async change can sharply drop the first while leaving the second unimproved.

## 11. Side effects of async: queues, ordering, errors, and transactions

| Issue | What to understand |
| --- | --- |
| Wait queue | If publishing outpaces processing, queue depth and start delay grow |
| Memory retention | Events/payloads stay retained by queued tasks |
| Rejection | A full queue can trigger submit errors or policy fallbacks |
| `CallerRunsPolicy` | Under saturation, tasks may run on the publisher thread and slow publish back down |
| Order | `@Order` does not guarantee **completion** order across multiple threads |
| Exceptions | Worker errors do not propagate back to the publisher like sync callbacks |
| Transaction context | JDBC/JPA ThreadLocal transactions do not automatically follow to workers |
| Security/MDC/tracing | Explicit context propagation is needed if required |
| Crashes | In-memory queues lose tasks if the process dies |
| Shared resources | Multiple workers can contend on DB pools/rate limits |

Since Spring 6.1, `ApplicationListener.supportsAsyncExecution()` lets certain listeners **opt out of async execution at the multicaster**. For example, transaction-synchronized listeners must register callbacks on the thread bound to the transaction. Never assume configuring an executor moves every callback off the thread.

With `@Async` on an individual listener, you also need `@EnableAsync`, an executor, an async error-handling mechanism, and a clear side-effect contract. `@Async` can be less invasive than altering the entire multicaster, but still does not provide durable delivery.

## 12. @TransactionalEventListener does not automatically eliminate request latency

A service:

~~~java
@Transactional
public void placeOrder(String id) {
    repository.save(new Order(id));
    publisher.publishEvent(new OrderPlaced(id));
}
~~~

With a regular synchronous `@EventListener`, the callback runs **inside the active transaction**, potentially extending connection/lock hold times and causing rollback if an unchecked exception crosses the transaction boundary.

Changing it to:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void sendReceipt(OrderPlaced event) {
    notificationService.send(event.id());
}
~~~

only defers execution until after a successful commit; the callback can still run **on the thread completing the transaction** and prolong the time before the service returns. It does not mean “already in the background” or “non-blocking for the request”.

After commit, a side-effect failure cannot undo the committed record. If a post-commit callback needs to write to the DB, you must establish an appropriate new transaction; do not assume the old resources will commit new changes.

To ensure email work survives crashes, use a persisted job or transactional outbox written in the same business transaction, processed by a worker after commit. Internal Spring application events do not inherently offer durable queues, replay, or exactly-once delivery.

## 13. Nested events make latency harder to spot

If a synchronous listener itself publishes another event:

~~~java
@EventListener
public void onOrderPlaced(OrderPlaced event) {
    publisher.publishEvent(new InvoiceRequested(event.id()));
}
~~~

then that callback may **not return** until all synchronous listeners of `InvoiceRequested` finish. This is illustrative code requiring the publisher and records.

~~~text
publish(OrderPlaced)
   |
   +--> inventory()
   |
   +--> billing()
           |
           +--> publish(InvoiceRequested)
                      |
                      +--> generateInvoice()
                      +--> auditInvoice()
           |
           +--> return
   |
   +--> notification()
   |
   +--> publish returns
~~~

Therefore, the root event's latency can include **the entire tree of nested events**. With recursive publishes lacking a termination condition, there is also a risk of stack overflow or duplicate processing. When tracing, tag each event type and parent-child relationship per contract rather than lumping everything into one “publisher slow” figure.

## 14. Measuring publish and processing latency accurately

### 14.1. Publisher timer

~~~java
long started = System.nanoTime();

try {
    publisher.publishEvent(event);
} finally {
    long elapsedNanos = System.nanoTime() - started;
    metrics.recordPublish(elapsedNanos);
}
~~~

This is an illustrative snippet requiring a `metrics` implementation. `finally` measures error cases too. `System.nanoTime()` is a monotonic duration clock within the same JVM; never subtract two `nanoTime` values from different processes to compute transit latency.

### 14.2. Per-listener timer

~~~java
@EventListener
public void onOrderPlaced(OrderPlaced event) {
    long started = System.nanoTime();
    String outcome = "success";

    try {
        inventoryService.reserve(event.id());
    } catch (RuntimeException ex) {
        outcome = "error";
        throw ex;
    } finally {
        metrics.recordHandler(
                "inventory", outcome, System.nanoTime() - started);
    }
}
~~~

The snippet above is illustrative, requiring a `metrics` bean and inventory service. It preserves exception-throwing semantics without hiding errors just to record duration.

### 14.3. Micrometer Timer.Sample

If a `MeterRegistry` is available:

~~~java
Timer.Sample sample = Timer.start(registry);
String outcome = "success";

try {
    inventoryService.reserve(event.id());
} catch (RuntimeException ex) {
    outcome = "error";
    throw ex;
} finally {
    sample.stop(Timer.builder("app.event.process")
            .tag("event", "order_placed")
            .tag("listener", "inventory")
            .tag("outcome", outcome)
            .register(registry));
}
~~~

This is an **illustrative snippet** requiring the Micrometer dependency, imports, and beans; it is not part of the section 8 Gradle demo. Spring Framework does not automatically generate an Observation for every `@EventListener` just because you use the annotation. If instrumentation is needed, configure/place timers in the right places.

### 14.4. Metrics to separate

| Metric | What does it measure? |
| --- | --- |
| Publish Timer | Duration of `publishEvent`, not necessarily async completion |
| Handler Timer | Duration inside each listener |
| Publish-to-start delay | From event creation until handler begins |
| Queue wait | From task enqueue until worker starts, if executor is instrumented |
| Inflight Gauge | How many callbacks are currently executing |
| Error Counter | How many callbacks failed by bounded category |
| Queue depth / rejected | Executor saturation |
| Business completion Timer | Until side effects are confirmed per contract |

Do not put `eventId`, `userId`, email, exception messages, raw URLs, or payloads into metric tags: they create high cardinality and increase TSDB costs. Use bounded tags such as event type, handler name, and outcome/error kind. Correlation IDs belong in structured logs/traces with appropriate data protection.

## 15. When to optimize synchronously vs. change architecture

Before moving to async, identify the **critical path** and business needs:

1. **Is the listener mandatory before returning success?** If it is a validation/invariant that must be guaranteed, do not move it to the background just to cut latency.
2. **Does the listener only perform a secondary side effect?** Email/analytics can be processed after commit.
3. **Can queries or I/O be optimized?** Projections, batching, sensible caching, and eliminating N+1 queries often reduce total work.
4. **Can duplicate processing be eliminated?** Two listeners querying the same object graph or serializing the same payload can be redesigned.
5. **Are there ordering dependencies?** If so, do not run concurrently without coordination.
6. **Is retry/replay after a crash required?** If so, a persisted job/outbox/broker is better than an in-JVM queue.
7. **Are there downstream rate limits?** Increasing concurrency can worsen p99 and error rates.

A decision matrix:

| Need | Approach |
| --- | --- |
| All three listeners are light and mandatory | Keep sync, optimize code |
| One I/O listener is slow and response need not wait | `@Async` or worker, with proper error handling and transactions |
| Many independent listeners with sufficient resources | Multicaster executor, bounded pool, measure completion |
| Critical work must not be lost on restart | Persisted job/outbox + worker |
| Multiple services need durable events | Broker + schema + retry/DLQ/idempotency |
| Steps with business dependencies | Explicit workflow/service orchestration instead of relying on `@Order` |

Using an executor with an unbounded queue can seem fast at low load and trigger OOM during bursts. Bounded concurrency/backpressure, timeouts, saturation metrics, and load testing must be designed alongside async changes.

## 16. Practical performance testing strategy

The JUnit suite in section 9 verifies **wiring and execution contracts**, not a substitute for benchmarking.

A good benchmark/load test should:

- Warm up the JVM and downstream dependencies.
- Publish enough events for p50/p95/p99 distributions, not a single run.
- Measure per-listener duration, publisher duration, and business completion.
- Monitor DB pools, HTTP connection pools, CPU, GC, queue depth, and rejected tasks.
- Test failure modes: listener throws, HTTP timeouts, executor overload, process shutdown.
- Keep workloads equivalent when comparing sync vs. async.
- Verify correctness and final side-effect counts, not just latency.
- Set SLOs from business requirements; Spring has no universal “publishEvent must be under 10ms” rule.

Depending on the project, you can use JFR, async-profiler, Micrometer + Actuator/Prometheus, and OpenTelemetry/tracing. A CPU profiler does not necessarily reveal full **wall-clock wait** on network I/O; inspect thread states or dependency timers.

### An important test when multiple listeners exist

Suppose an event has three listeners, yet one is skipped by a `condition` or an error stops the multicast. Total `process.count` will not necessarily equal three times `publish.count`. Track statistics **per listener/event/outcome** instead of dividing blindly without context to claim delivery succeeded.

## 17. Common mistakes and misconceptions

| Misconception | Reality |
| --- | --- |
| `publishEvent` is always fast because it just notifies | By default, the multicaster invokes listeners synchronously on the caller thread |
| Multiple `@EventListener`s mean multiple threads | No; callbacks run sequentially by default within one publish pass |
| `@Order` makes listeners run in parallel | No; it controls invocation order |
| Total latency is always max(listener durations) | Only approximately true in a well-resourced parallel design; sync is near the sum |
| The third listener always runs even if the second throws | Not with default sync and no error-swallowing ErrorHandler |
| Enabling async means business work is done when publish returns | Returning usually only confirms handoff/task submission |
| A single-worker executor makes all listeners faster | They may still run sequentially in the queue |
| Async has no cost | Queues, memory, scheduling, context propagation, and retries all have cost |
| `@Order` guarantees async completion order | No general guarantee |
| `@TransactionalEventListener(AFTER_COMMIT)` never blocks requests | Callbacks can still run on the transaction completion thread |
| Executors automatically propagate JDBC ThreadLocal transactions | Never assume this |
| `@Async` is a durable queue | No; tasks can be lost if the process dies |
| Publisher throwing means all side effects rolled back | Previously executed side effects may not be reversible |
| Two requests cannot publish concurrently | “Sequential” only applies to listeners within a single publish pass |
| A single demo run's duration is the production SLO | Histograms/load tests measuring p95/p99 are needed |
| Bigger pools are always better | Can overload DB pools or external rate limits |
| `Thread.sleep` is a performance solution | Only for simulating latency in demos |
| Spring provides a built-in Timer for every `@EventListener` | Requires instrumentation matching sync/async semantics |

## 18. Adoption checklist and self-check questions

**Checklist:**

- [ ] Confirmed whether default multicaster or custom executor is used.
- [ ] Publish duration and per-listener timers are in place.
- [ ] Slow synchronous listeners are identified via profiling.
- [ ] `@Order` is not treated as a way to reduce total work.
- [ ] Exception paths and partially completed side effects are tested.
- [ ] Transaction duration, locks, and connection usage have been reviewed.
- [ ] Critical listeners that must remain sync are identified.
- [ ] When switching to async, bounded queues, error policies, and saturation monitoring exist.
- [ ] Async callbacks are not assumed to carry the request's transaction/security context.
- [ ] When durable delivery is required, an outbox/job/broker and idempotency are in place.
- [ ] Sync/async tests are explicit, awaiting async completion with latches/futures instead of risky sleeps.
- [ ] Both request latency **and** side-effect completion time are measured under load.
- [ ] High-cardinality IDs/event payloads are not used as metric tags.
- [ ] A rollout/rollback plan and pre/post-optimization failure rate comparisons exist.

**Question 1.** Three synchronous listeners take 40, 70, and 100 ms. Assuming small dispatch overhead, roughly what is the publish duration?

**Answer:** Around 210 ms, not 100 ms, because the callbacks execute sequentially.

**Question 2.** Does changing `@Order` automatically reduce the duration of the three listeners?

**Answer:** No. It changes invocation order; the total work still has to be performed.

**Question 3.** An async publisher returns in 2 ms, while the HTTP-sending listener takes 600 ms. Can you claim the email completed in 2 ms?

**Answer:** No. 2 ms is only the handoff; handler completion and side effects must be measured.

**Question 4.** Why does the synchronous JUnit test not need `Thread.sleep` after `publishEvent`?

**Answer:** In the synchronous multicaster, the method returns after the listeners finish if no exception occurs. You can assert the trace immediately after the call.

**Question 5.** When can adding workers make things slower?

**Answer:** When DB/CPU/lock contention, pool limits, or downstream rate limits push p99 higher.

**Question 6.** Does `AFTER_COMMIT` always run off the request thread?

**Answer:** No. Transaction synchronization callbacks can run on the thread completing the commit; it only selects the phase, without spawning a worker.

**Question 7.** A synchronous listener throws, causing later listeners to be skipped; publish finishes faster—is that a successful performance improvement?

**Answer:** No. That may be a functional failure; inspect the exception and any partially executed side effects.

## 19. References

- Spring Framework — Standard and Custom Events, `@EventListener`, `@Order`, asynchronous listeners: https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html
- Spring Framework 6.2 — `SimpleApplicationEventMulticaster`, default synchronous behavior and task executor: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html
- Spring Framework 6.2 — `ApplicationEventPublisher` and handoff contract: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/context/ApplicationEventPublisher.html
- Spring Framework 6.2 — `ApplicationListener.supportsAsyncExecution()`: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/context/ApplicationListener.html
- Spring Framework 6.2 — `ThreadPoolTaskExecutor`: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html
- Spring Framework Reference — Observability for Application Events: https://docs.spring.io/spring-framework/reference/integration/observability.html
- Spring Framework Reference — Transaction-bound Events: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html
- Micrometer — Timers: https://docs.micrometer.io/micrometer/reference/concepts/timers.html
- Micrometer — Histograms and Percentiles: https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html
- Java 17 — `System.nanoTime()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime()
- JUnit 5 User Guide: https://junit.org/junit5/docs/current/user-guide/
