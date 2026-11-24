# Measuring Event Publish and Process Latency in Spring Framework

## 1. Goal and observability context

In Spring Framework Application Events, a service can call `ApplicationEventPublisher.publishEvent(...)` to signal a business state change. Many applications measure only the duration of `publishEvent` and conclude that **the event was processed quickly**. That conclusion can be partially true when all listeners run synchronously, but it is clearly wrong when using an executor, `@Async`, transaction-bound listeners, or a decoupled processing flow.

To observe accurately, independent time intervals must be defined:

- **Publish latency:** the time `publishEvent(...)` takes to **hand off** the event to the dispatch mechanism and return/throw.
- **Processing latency:** the time **a specific handler** actually spends executing its work; measured inside the handler.
- **Start delay:** the interval from when the event is created/marked as emitted until the handler starts; this can include dispatch overhead and executor queue wait time.
- **End-to-end latency:** from a chosen business milestone until **all required outcomes** complete or a specific outcome is confirmed. This cannot be inferred by default from a publish timer.

This article explains these definitions, how to measure them with Micrometer `Timer`, how sync/async and transactions differ, how to design safe metric tags, how to write a runnable Java 17+ example, and how to test to avoid inaccurate measurements.

**Core rule:** `publishEvent(...)` is a **handoff** to the event multicaster; by Spring's contract, it **does not guarantee** synchronous execution, asynchronous execution, or processing completion at the moment the method returns.

## 2. The ApplicationEventPublisher contract and where to measure

Spring Framework provides these components:

- `ApplicationEventPublisher`: the API to publish an `ApplicationEvent` or a plain payload object.
- `ApplicationEventMulticaster`: decides how to dispatch an event to matching `ApplicationListener`s.
- `SimpleApplicationEventMulticaster`: the default implementation when the context does not declare a custom multicaster bean.
- `ApplicationListener<E>` and `@EventListener`: mechanisms for receiving events.
- `@TransactionalEventListener`: a callback bound to a transaction phase, not necessarily executed during `publishEvent`.

When passing a record/POJO:

~~~java
publisher.publishEvent(new OrderSubmitted("order-101", 100L));
~~~

Spring may wrap it in a `PayloadApplicationEvent` before the multicaster dispatches it. The snippet above is **illustrative**, requiring `publisher` and the `OrderSubmitted` record to be defined.

In the **default** configuration, `SimpleApplicationEventMulticaster` typically invokes listeners immediately on the publisher thread. However, `setTaskExecutor(...)` or `@Async` can change the execution path. Therefore:

~~~text
Publisher                          Multicaster               Listener
    |                                  |                        |
    |------ publishEvent(event) ----->|                        |
    |                                  |---- listener() ------->|
    |                                  |<--- listener done -----|
    |<----- publishEvent returns ------|                        |

             SYNCHRONOUS: the publish interval may include listener execution time.
~~~

~~~text
Publisher                          Multicaster/Executor       Listener
    |                                  |                        |
    |------ publishEvent(event) ----->|                        |
    |                                  |-- submit task -------->|
    |<----- publishEvent returns ------|                        |
    |                                  |    queue / scheduling  |
    |                                  |---- handler starts --->|
    |                                  |<--- handler ends ------|

             ASYNCHRONOUS: the publish interval usually measures handoff/submit only.
~~~

Point to observe: the diagram does not promise that every kind of listener will run asynchronously when the multicaster has an executor. Since Spring 6.1, `ApplicationListener.supportsAsyncExecution()` lets a listener decline async execution at the multicaster; for example, transaction-synchronized listeners need to register callbacks on the thread holding the transaction.

## 3. Defining exact timestamps

For one event and one handler, define:

~~~text
t0  business operation reaches chosen event-creation time
t1  just before publisher.publishEvent(event)
t2  publishEvent(event) returns or throws
t3  handler invocation begins
t4  handler finishes (success/failure)
t5  required downstream effect is durably confirmed, if applicable
~~~

Commonly used durations:

| Metric | Formula | Meaning |
| --- | --- | --- |
| `publish_duration` | `t2 - t1` | Execution time of the `publishEvent` call |
| `start_delay` | `t3 - t0` | From event creation time to when the handler starts |
| `process_duration` | `t4 - t3` | Time the handler spends running |
| `end_to_end_duration` | `t5 - t0` | Latency until the business outcome is confirmed per contract |
| `queue_wait` | `handler_start - enqueue_time` | Measures true queue time only if a timestamp is actually captured at enqueue |

**Do not call `start_delay` "exact queue wait"** if the start timestamp is taken at event creation. It also includes event preparation, dispatch overhead, scheduler handoff, and other work before the handler begins.

Likewise, do not assume:

~~~text
end_to_end = publish_duration + start_delay + process_duration
~~~

This formula **double-counts** some phases in synchronous execution, and can miss asynchronous downstream tasks. With sync, `t3` and `t4` lie inside `t1..t2`. With async, publish and handler can partially overlap. For `end_to_end`, choose a **separate end milestone** backed by completion proof.

### 3.1. Where to measure?

- **Publish timer:** directly around the `publishEvent` call, at the application's publisher/gateway boundary.
- **Process timer:** around the body of **each listener or clearly named processing step**. Each handler needs a sensible identifying tag/metric.
- **Start delay:** measured at the start of the listener using a monotonic timestamp created at the publisher, suitable only for events **within the same JVM**.
- **Result:** attach `success`/`error` based on the handler's outcome; do not treat `publishEvent returned` as proof of async success.

If an event has 3 listeners, a single publish can yield **1 publish measurement and 3 process measurements**. Therefore, the counts of the two timer types do not have to be equal.

## 4. How sync, async, and transactional Spring events affect measurements

| Mechanism | What does the publish timer actually measure? | Where should the process timer go? | Things to note |
| --- | --- | --- | --- |
| Default synchronous `SimpleApplicationEventMulticaster` | Handoff + time of listeners invoked on the same stack | Start/end of each handler | The publish timer can be high because of one slow listener |
| Multicaster with `TaskExecutor` | Usually scheduling/task submission; may include fallback or task rejection | Inside the handler executing on the worker | Do not treat publish returning as listener completion |
| `@Async` on listener | Usually reflects the proxy/submit call step | Inside the actual async code | Exceptions and context must be tracked separately |
| `@TransactionalEventListener(AFTER_COMMIT)` | Callback registration if a suitable transaction exists | Inside the callback running after commit | Callback cannot be measured using `publishEvent` alone |
| `@TransactionalEventListener(BEFORE_COMMIT)` | Callback registration when publishing the event | Inside the pre-commit callback | Callback can affect rollback; not async by default |
| Reactive event with `TransactionalEventPublisher` | Emitting the event per subscription and Reactor Context | Inside the listener for the right phase; if the handler returns a publisher, measure until terminal signal | Do not treat `Mono` assembly time as execution time |

**Important example:** a service calls `publishEvent` inside a transaction, and an `AFTER_COMMIT` listener sends an HTTP request after commit. The publish timer may be only a few microseconds/milliseconds, while the handler takes 500 ms after commit. The `publish_duration` figure says nothing about the HTTP delivery SLA.

## 5. Micrometer Timer is the right tool

Micrometer provides `Timer`, `Counter`, `DistributionSummary`, `Observation`, and integrates with many metrics registries. Measure durations with **`Timer`** because it carries time-unit semantics and supports count, total time, max, and histograms/percentiles depending on configuration.

A short snippet:

~~~java
Timer publishTimer = Timer.builder("app.event.publish")
        .description("Time spent in publishEvent hand-off")
        .tag("event", "order_submitted")
        .register(registry);

publishTimer.record(() -> publisher.publishEvent(event));
~~~

This is an **illustrative snippet**, requiring `registry`, `publisher`, and `event` to be declared. `record(Runnable)` measures the block; when an exception is thrown, the timer still records the duration when using `record` properly. If you want to attach an outcome tag **after knowing success/error**, use `Timer.Sample`.

~~~java
Timer.Sample sample = Timer.start(registry);
String outcome = "success";

try {
    doWork();
} catch (RuntimeException ex) {
    outcome = "error";
    throw ex;
} finally {
    sample.stop(Timer.builder("app.event.process")
            .tag("handler", "notify_customer")
            .tag("outcome", outcome)
            .register(registry));
}
~~~

This is also an **illustrative snippet**, requiring `doWork` and `MeterRegistry`. Place `sample.stop(...)` inside `finally` so error paths are measured as well. Never catch and swallow an exception just to record a metric: that alters the error-handling/rollback contract.

### 5.1. Count, total time, and max

A `Timer` can report:

- `count()`: the number of measurements recorded in the corresponding window/registry instance.
- `totalTime(TimeUnit.MILLISECONDS)`: total recorded duration, converted to the requested unit.
- `max(TimeUnit.MILLISECONDS)`: maximum within the corresponding statistics window; max can reset depending on time-window configuration.

A simple mean within the statistics window is `totalTime / count` when `count > 0`, but **mean does not replace p95/p99**. Observing latency under load requires histograms or appropriate percentiles, and you must distinguish a local registry's metric snapshot from numbers aggregated by a monitoring backend.

### 5.2. Clocks for measuring duration

For code within the same process, use `System.nanoTime()` or `Timer.Sample`'s monotonic clock to measure **interval lengths**. Do not use `Instant.now()` / `System.currentTimeMillis()` and claim high precision, because wall clocks can be adjusted.

`System.nanoTime()` is meaningful only for comparing timestamps within the same JVM runtime, **not as a timestamp to send across Kafka, databases, or different machines**. For cross-process events, use tracing and timestamps with different semantics while accounting for clock skew.

## 6. Long-term metric and tag naming conventions

A suggested set of names:

| Meter name | Type | Suggested low-cardinality tags | Measurement boundary |
| --- | --- | --- | --- |
| `app.event.publish` | Timer | `event`, `result` | Around the publish call |
| `app.event.process` | Timer | `event`, `handler`, `outcome` | Inside the listener |
| `app.event.start.delay` | Timer | `event`, `handler` | From event creation to handler start |
| `app.event.inflight` | Gauge | `handler` | Number of handlers currently running |
| `app.event.failures` | Counter | `handler`, `error_kind` | When a handler fails |
| `app.event.executor.queue.depth` | Gauge | `executor` | Number of tasks waiting in the actual queue |
| `app.event.executor.rejected` | Counter | `executor`, `reason` | When the executor rejects work |

These are **application-defined names**, not automatic metrics always emitted by Spring Framework. You can replace `app` with a project-agreed namespace; keep names and tags stable across deployments.

### Tags you must never include

- `eventId`, `orderId`, `userId`, `requestId`, `traceId`.
- Raw exception messages, full stack traces, URLs with personal query parameters, emails, JSON payloads.
- Dynamic class names derived from user data or any unbounded state values.

Because each tag combination creates a separate meter/time series, tags with unique per-event values cause **high cardinality**, consuming memory and driving up metrics backend costs. Use `event="order_submitted"`, `handler="billing"`, `outcome="success|error"`, and a bounded set of `error_kind` values instead of specific IDs.

**Distinguish roles:** metric tags are for aggregation; trace/span attributes can carry correlation IDs subject to security and sampling policies. Do not turn metrics into a detailed per-event log store.

## 7. Runnable example with Java 17+, Spring Framework, and Micrometer

This example builds a plain Spring application context and configures `SimpleApplicationEventMulticaster` to use **a single worker thread**. The program publishes three events, measures `publishEvent` duration, handler duration, and the interval from event creation until the handler starts. It uses `CountDownLatch` instead of `Thread.sleep` to wait for completion, and prints **measurement counts** (deterministic), not actual durations (machine-dependent).

Goal: demonstrate precisely why **publish returned** is insufficient to conclude **process done** when listeners run asynchronously.

### 7.1. Structure

~~~text
event-timing-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   └── java/
    │       └── demo/
    │           └── EventTimingDemo.java
    └── test/
        └── java/
            └── demo/
                └── EventTimingDemoTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'event-timing-demo'
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
    implementation 'io.micrometer:micrometer-core:1.14.14'

    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}

application {
    mainClass = 'demo.EventTimingDemo'
}

test {
    useJUnitPlatform()
}
~~~

Spring 6.2.15 and Micrometer 1.14.14 are both released artifacts; Spring Context 6.2.15 depends on `micrometer-observation` 1.14.14. Using the same Micrometer line avoids dependency skew. When working with Spring Boot, prefer the Boot BOM rather than pinning these versions individually.

### 7.2. Complete source code

Create `src/main/java/demo/EventTimingDemo.java`:

~~~java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.ApplicationEventMulticaster;
import org.springframework.context.event.EventListener;
import org.springframework.context.event.SimpleApplicationEventMulticaster;

public class EventTimingDemo {

    // createdAtNanos is used only for measuring duration within the same JVM.
    public record OrderSubmitted(
            String orderId,
            long amountCents,
            long createdAtNanos) {}

    // Measure the exact duration of the publishEvent(...) call.
    public static final class MeasuredPublisher {
        private final ApplicationEventPublisher publisher;
        private final MeterRegistry registry;

        public MeasuredPublisher(
                ApplicationEventPublisher publisher,
                MeterRegistry registry) {
            this.publisher = publisher;
            this.registry = registry;
        }

        public void submit(String id, long amountCents) {
            OrderSubmitted event =
                    new OrderSubmitted(id, amountCents, System.nanoTime());

            Timer.Sample sample = Timer.start(registry);
            String result = "returned";

            try {
                publisher.publishEvent(event);
            } catch (RuntimeException ex) {
                result = "exception";
                throw ex;
            } finally {
                sample.stop(Timer.builder("demo.event.publish")
                        .tag("event", "order_submitted")
                        .tag("result", result)
                        .register(registry));
            }
        }
    }

    // Listener executes on the event executor.
    public static final class AccountingListener {
        private final MeterRegistry registry;
        private final CountDownLatch finished;
        private final AtomicLong totalCents = new AtomicLong();

        public AccountingListener(
                MeterRegistry registry,
                CountDownLatch finished) {
            this.registry = registry;
            this.finished = finished;
        }

        @EventListener
        public void onOrderSubmitted(OrderSubmitted event) {
            long elapsedNanos =
                    System.nanoTime() - event.createdAtNanos();

            Timer.builder("demo.event.start.delay")
                    .tag("event", "order_submitted")
                    .tag("handler", "accounting")
                    .register(registry)
                    .record(Math.max(0L, elapsedNanos),
                            TimeUnit.NANOSECONDS);

            Timer.Sample processing = Timer.start(registry);
            String outcome = "success";

            try {
                // Represents business processing work.
                totalCents.addAndGet(event.amountCents());
            } catch (RuntimeException ex) {
                outcome = "error";
                throw ex;
            } finally {
                processing.stop(Timer.builder("demo.event.process")
                        .tag("event", "order_submitted")
                        .tag("handler", "accounting")
                        .tag("outcome", outcome)
                        .register(registry));
                finished.countDown();
            }
        }

        public long totalCents() {
            return totalCents.get();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {

        @Bean
        public MeterRegistry meterRegistry() {
            return new SimpleMeterRegistry();
        }

        @Bean(destroyMethod = "shutdown")
        public ExecutorService eventExecutor() {
            return Executors.newSingleThreadExecutor();
        }

        // This is the bean name that Spring ApplicationContext looks up.
        @Bean(name = "applicationEventMulticaster")
        public ApplicationEventMulticaster applicationEventMulticaster(
                ExecutorService eventExecutor) {
            SimpleApplicationEventMulticaster multicaster =
                    new SimpleApplicationEventMulticaster();

            multicaster.setTaskExecutor(eventExecutor);
            return multicaster;
        }

        @Bean
        public CountDownLatch finished() {
            return new CountDownLatch(3);
        }

        @Bean
        public AccountingListener accountingListener(
                MeterRegistry registry,
                CountDownLatch finished) {
            return new AccountingListener(registry, finished);
        }

        @Bean
        public MeasuredPublisher measuredPublisher(
                ApplicationEventPublisher publisher,
                MeterRegistry registry) {
            return new MeasuredPublisher(publisher, registry);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            MeasuredPublisher measuredPublisher =
                    context.getBean(MeasuredPublisher.class);
            MeterRegistry registry = context.getBean(MeterRegistry.class);
            CountDownLatch finished = context.getBean(CountDownLatch.class);
            AccountingListener accounting =
                    context.getBean(AccountingListener.class);

            measuredPublisher.submit("A", 100L);
            measuredPublisher.submit("B", 200L);
            measuredPublisher.submit("C", 300L);

            if (!finished.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Timed out waiting for 3 event handlers");
            }

            System.out.println("publish.count=" +
                    registry.get("demo.event.publish")
                            .tag("result", "returned").timer().count());

            System.out.println("process.count=" +
                    registry.get("demo.event.process")
                            .tag("outcome", "success").timer().count());

            System.out.println("start.delay.count=" +
                    registry.get("demo.event.start.delay").timer().count());

            System.out.println("total.cents=" + accounting.totalCents());
        }
    }
}
~~~

**Why the code works by this design:**

1. `MeasuredPublisher.submit(...)` creates the record first, then starts `Timer.Sample` **right before** `publisher.publishEvent(event)`. It records `result=returned` if the call returns without throwing an exception, **not `result=processed`**.
2. `SimpleApplicationEventMulticaster` has the bean name `applicationEventMulticaster` and uses `ExecutorService`. For a regular `@EventListener` listener, work is handed off to the worker.
3. `AccountingListener` receives the event, uses the `createdAtNanos` timestamp to measure **start delay**, and then uses a separate `Timer.Sample` for **process duration**. The two intervals have distinct meanings.
4. `finished.countDown()` in `finally` ensures completion signaling for the three handler invocations even if business logic throws a runtime exception. Counting down does not mean the side effect succeeded; it signals "the handler has exited its body".
5. `CountDownLatch.await(...)` sets a real timeout instead of guessing that 100 ms is enough for all callbacks to finish.
6. `AtomicLong` guarantees safe accumulation if the executor is later expanded to multiple workers. `CountDownLatch` gives the main thread a happens-before relationship with the handler's prior work.
7. `SimpleMeterRegistry` stores metrics in memory for the demo; it **does not automatically export metrics to Prometheus**. Exporting metrics in a real application requires configuring the appropriate registry/exporter.

### 7.3. Running and expected output

Inside the `event-timing-demo` directory, with JDK 17+ and Gradle:

~~~bash
gradle -q run
~~~

Or use the Gradle Wrapper if configured: `./gradlew -q run` (Linux/macOS) or `gradlew.bat -q run` (Windows).

Lines explicitly printed by the program when all three handlers complete successfully:

~~~text
publish.count=3
process.count=3
start.delay.count=3
total.cents=600
~~~

This is the **expected logical output**, not the log of a build executed in this environment. Gradle or library logging may add other output.

**Fixed durations are not printed** because nanosecond/millisecond timings depend on CPU, scheduler, JVM warmup, and system load. Counts and the total cents are the deterministic values from the demo.

Here, `publish.count=3` and `process.count=3` are equal only because each event in the demo has **exactly one handler** and `main` waits for all three callbacks. That is not a general rule for Spring Application Events.

## 8. Testing instrumentation with JUnit 5

The test example below also uses a real Spring context, publishes three events, waits for the handlers to finish, and checks the timers. It **does not assert an absolute time threshold**, because unit/integration latency tests using the system clock are very prone to flakiness.

Create `src/test/java/demo/EventTimingDemoTest.java`:

~~~java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.MeterRegistry;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class EventTimingDemoTest {

    @Test
    @Timeout(15)
    void publishAndProcessAreMeasuredSeparately() throws Exception {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             EventTimingDemo.Config.class)) {

            EventTimingDemo.MeasuredPublisher publisher =
                    context.getBean(EventTimingDemo.MeasuredPublisher.class);
            EventTimingDemo.AccountingListener listener =
                    context.getBean(EventTimingDemo.AccountingListener.class);
            MeterRegistry registry = context.getBean(MeterRegistry.class);
            CountDownLatch finished = context.getBean(CountDownLatch.class);

            publisher.submit("A", 100L);
            publisher.submit("B", 200L);
            publisher.submit("C", 300L);

            assertTrue(finished.await(10, TimeUnit.SECONDS));

            assertEquals(3L,
                    registry.get("demo.event.publish")
                            .tag("result", "returned").timer().count());
            assertEquals(3L,
                    registry.get("demo.event.process")
                            .tag("outcome", "success").timer().count());
            assertEquals(3L,
                    registry.get("demo.event.start.delay").timer().count());
            assertEquals(600L, listener.totalCents());
        }
    }
}
~~~

Run:

~~~bash
gradle test
~~~

This is an **integration-style unit test** with a real context and executor, requiring no web server or database. It verifies that instrumentation triggers at the right points and that metrics are not read before the listeners finish.

If you add a failure simulation test, assert the `outcome=error` timer and exception path separately. With async execution, handler exceptions can occur on the worker thread instead of returning to the publisher; the test must have a mechanism to observe errors in the listener/worker rather than only `assertThrows(() -> publishEvent(...))`.

## 9. Switching the example to synchronous mode for comparison

Simply change the multicaster configuration: omit `setTaskExecutor(eventExecutor)` (or do not declare a custom multicaster). Then `SimpleApplicationEventMulticaster` invokes matching listeners synchronously by default:

~~~java
@Bean(name = "applicationEventMulticaster")
public ApplicationEventMulticaster applicationEventMulticaster() {
    return new SimpleApplicationEventMulticaster();
}
~~~

This is a **configuration bean variant** and must not be used simultaneously with the `applicationEventMulticaster` bean in the main example. There should be only one bean with that exact name in the same context.

If the listener is synchronous:

~~~text
t1 start publish
   |
   +-- t3 handler starts
   |       |
   |       +-- processing
   |       |
   |   t4 handler ends
   |
t2 publish returns
~~~

In that case, `publish_duration` can be larger than `process_duration` because it includes multicaster overhead and possibly multiple handlers. Do not infer from "slow publisher" that the `publishEvent` method itself has heavy logic independent of listeners: **a slow synchronous listener slows down the publisher**.

If there are **multiple listeners**, the publisher can end up measuring the combined duration of multiple synchronous callbacks. A `process` timer for handler A cannot represent handler B's duration.

## 10. Measuring multiple listeners: metric cardinality and choosing attachment points

In a real application, a single `OrderSubmitted` event can trigger:

~~~text
OrderSubmitted
  |
  +--> InventoryListener
  +--> BillingListener
  +--> NotificationListener
  +--> AnalyticsListener
~~~

If you need to know which listener is slow, you must measure **each handler**:

~~~java
@EventListener
public void onOrderSubmitted(OrderSubmitted event) {
    Timer.Sample sample = Timer.start(registry);
    String outcome = "success";

    try {
        handleInventory(event);
    } catch (RuntimeException ex) {
        outcome = "error";
        throw ex;
    } finally {
        sample.stop(registry.timer(
                "app.event.process",
                "event", "order_submitted",
                "handler", "inventory",
                "outcome", outcome));
    }
}
~~~

This is an **illustrative snippet** requiring `registry` and `handleInventory`; it is not part of the demo class in section 7. Set the `handler` tag to a fixed logical name rather than using dynamic proxy object names or bean instance IDs.

You can write a wrapper/decorator to reduce boilerplate, but ensure it instruments **the actual processing time**. If a decorator only wraps a method returning `CompletableFuture` or `Mono`, the timer may stop as soon as the future/publisher is created without measuring until work completes.

### Timer counts differ from event counts

With 1 event and 4 listeners:

- `app.event.publish{event="order_submitted"}` may have `count=1`.
- `app.event.process{handler="inventory"}` has `count=1`.
- `app.event.process{handler="billing"}` has `count=1`.
- The total count across **all handlers** can be 4 if all four process the event, or lower when a listener is filtered, skipped, unregistered, or not yet finished.

When building dashboards, do not divide total `process.count` directly by `publish.count` and assume that is the delivery success rate. Define success per handler and expected subscribers.

## 11. Measuring errors: publish errors differ from processing errors

The publisher can throw an exception in synchronous mode or immediately when the multicaster/executor fails, whereas in async mode:

~~~text
publishEvent returned normally
               |
               v
task runs later -> handler throws exception
~~~

In that case, `publish.result=returned` is still valid even though `process.outcome=error`. Both metrics are accurate, reflecting two different boundaries.

A handling pattern inside a listener:

~~~java
Timer.Sample sample = Timer.start(registry);
String outcome = "success";

try {
    processBusinessEvent(event);
} catch (ExpectedTemporaryException ex) {
    outcome = "error";
    registry.counter(
            "app.event.failures",
            "handler", "notification",
            "error_kind", "temporary").increment();
    throw ex;
} catch (RuntimeException ex) {
    outcome = "error";
    registry.counter(
            "app.event.failures",
            "handler", "notification",
            "error_kind", "runtime").increment();
    throw ex;
} finally {
    sample.stop(registry.timer(
            "app.event.process",
            "event", "order_submitted",
            "handler", "notification",
            "outcome", outcome));
}
~~~

**This snippet is illustrative only**: `processBusinessEvent`, `ExpectedTemporaryException`, `event`, and `registry` must be defined in the application. Do not alter business behavior by swallowing errors; exceptions are rethrown as before.

For each handler, standardize on one place to measure errors; if a `Timer` already has `outcome=error`, the error count can be derived from the timer without creating a separate `Counter` just to double-count. Use a separate counter when you genuinely need an additional error classification or a distinct occurrence rate separate from duration.

**Never put exception messages into tags**. Use a bounded set of values such as `timeout`, `validation`, `dependency_unavailable`, `unknown`. Exception details and event IDs belong in structured logs/traces with redaction and restricted access.

## 12. Transaction-bound events: measuring when the callback actually runs

A listener:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterCommit(OrderSubmitted event) {
    sendNotification(event);
}
~~~

This is an illustrative method, not a complete file; it requires a Spring bean, transaction annotation imports, the event class, and the notification-sending implementation.

If `publishEvent` is called inside `@Transactional`, the listener may only **register a synchronization** at publish time; processing will occur **after commit**. Therefore:

- Publish timer: measures the call inside the transactional service, not the wait time until commit.
- Process timer: measures inside `afterCommit(...)` when the callback actually executes.
- Start delay: from when the event was created until the callback runs, **which can include uncommitted transaction time**, not just executor queuing.
- End-to-end: must be defined post-commit plus whether the side effect was confirmed.

If the transaction rolls back, an `AFTER_COMMIT` listener will **not run**. With the default `fallbackExecution=false` and no active transaction, the listener is also skipped. Therefore, `process.count < publish.count` is **not automatically** a delivery error in this case.

You can additionally measure:

- `transaction.duration` if appropriate instrumentation exists at the service/transaction boundary.
- `event.pending.commit.duration` if storing a timestamp from when the event occurred until the `AFTER_COMMIT` callback begins.
- `event.process.duration` for the actual handler.
- `event.outcome` with commit/rollback labels if the business requires observing outcomes, rather than guessing from publish counts.

**Note:** Writing to the DB inside `AFTER_COMMIT` does not by default create a new transaction that commits independently. If additional data needs to be written, define a new transaction explicitly; instrumentation does not alter transaction semantics.

## 13. Distinguishing @Async, executor queues, and context propagation

### 13.1. Measuring true queue wait

If you want pure **queue wait**, you must instrument right at the executor layer when a task is enqueued and when the task starts running:

~~~text
enqueue_time = clock.monotonicTime() immediately before/after queue offer per contract
start_time   = clock.monotonicTime() right when the worker starts the task
queue_wait   = start_time - enqueue_time
~~~

Do not equate the time from event creation to handler start with queue wait. An executor running a task via `CallerRunsPolicy` may execute immediately on the publisher thread; in that case, the publish timer **includes the handler**, even though the configuration is called async. Evidence must come from how the executor actually runs.

### 13.2. Observing backlog and thread pool health

For a `ThreadPoolTaskExecutor` or `ThreadPoolExecutor` where applicable, collect:

- Active workers, pool size, and maximum size.
- Queue depth, queue capacity, task submissions/rejections.
- Completed task count and long-running tasks.
- Event handler p95/p99 duration compared against producer rate.

If the producer emits 1,000 events/s while workers process only 600 events/s, queue latency grows over time even while `publish_duration` stays low. This is why you must observe **throughput + backlog + start delay**, not publish latency alone.

### 13.3. Tracing and MDC across thread boundaries

On a synchronous path, the publisher's logging context/ThreadLocal usually remains present when the listener runs on the same thread. When the multicaster picks a different executor or `@Async`, context does not automatically transfer to the worker thread. If trace correlation is needed, use **Micrometer Context Propagation** and an appropriate task decorator, such as `ContextPropagatingTaskDecorator` on the `TaskExecutor`.

Illustrative configuration with Spring Framework 6.2:

~~~java
@Bean(name = "applicationEventMulticaster")
public SimpleApplicationEventMulticaster eventMulticaster() {
    SimpleApplicationEventMulticaster multicaster =
            new SimpleApplicationEventMulticaster();

    SimpleAsyncTaskExecutor executor = new SimpleAsyncTaskExecutor();
    executor.setTaskDecorator(new ContextPropagatingTaskDecorator());

    multicaster.setTaskExecutor(executor);
    return multicaster;
}
~~~

This is an **alternative configuration**, requiring Spring imports, `io.micrometer:context-propagation` on the classpath, and an executor management policy. Do not use it alongside the demo's multicaster. The decorator helps propagate supported context; it **does not turn a Java ThreadLocal transaction into a valid transaction on the worker**. Data needed for processing still requires an explicit contract.

## 14. Micrometer Observation and Spring Boot Actuator

Micrometer provides the `ObservationRegistry` API to describe observable operations, combining metrics and tracing when matching handlers/registries are configured. However, **Spring Framework does not automatically create an Observation for every `@EventListener` invocation**; the Spring documentation explicitly notes that because of sync/async dispatch semantics, the framework does not enforce a single instrumentation model.

If an Observation is needed for a specific handler, wrap the **actual** work:

~~~java
Observation.createNotStarted("app.event.process", observationRegistry)
        .lowCardinalityKeyValue("event", "order_submitted")
        .lowCardinalityKeyValue("handler", "notification")
        .observe(() -> handle(event));
~~~

This is an illustrative snippet: it requires `Observation`, `ObservationRegistry`, and `handle` in context; depending on setup, handlers are required to emit metrics/spans. **Do not assume merely declaring `@EventListener` or `@Timed` automatically creates dashboards** without configuring the corresponding instrumentation/AOP.

With Spring Boot Actuator, if the project already has `spring-boot-starter-actuator` and a registry exporter such as `micrometer-registry-prometheus`, you can configure metric exposure per security policy. Reference configuration example:

~~~properties
management.endpoints.web.exposure.include=health,info,prometheus
management.metrics.distribution.percentiles-histogram.app.event.process=true
management.metrics.distribution.percentiles-histogram.app.event.publish=true
~~~

This is a **reference configuration**, requiring Actuator, Prometheus registry, the matching Boot version, and endpoint access control settings. Do not expose metrics endpoints publicly by default when they contain infrastructure details. Verify the actual metric names via the exporter because naming conventions and versions affect how `app.event.process` is converted into time series.

### 14.1. Prometheus and percentiles

If the timer has histograms enabled, Prometheus can expose `*_bucket`, `*_count`, and `*_sum` series per the naming convention. A sample query for p95 by handler:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, handler) (
    rate(app_event_process_seconds_bucket[5m])
  )
)
~~~

Expressions must be **verified against the real metric names and labels** in your system. Do not use `histogram_quantile` if the registry does not export histogram buckets with an appropriate `le` label. With systems exporting only count/sum, you can calculate mean rates, not accurate percentiles.

For SLOs, choose thresholds from business requirements, such as "p95 notification handler under 250 ms during steady state". That number is an example of how to state an SLO, not a standard mandated by Spring.

## 15. Measuring with traces: connecting publish and process spans

A flow can look like:

~~~text
HTTP request span
    |
    +--> event.publish span
              |
              +--> handler.inventory span
              +--> handler.billing span
              +--> handler.notification span
~~~

This is a **conceptual diagram**, not a span structure Spring provides automatically for `@EventListener`. With async, handler spans can be children/links or separate traces depending on context propagation and instrumentation rules. Tracing provides per-event evidence when sampled, but does not replace aggregate latency metrics for all events.

When an event passes through a message broker or transactional outbox:

- Use `eventId`/`correlationId` in logs/traces per policy.
- Use trace context propagation per the standard supported by your stack.
- Separate `enqueue`, `broker lag`, `consumer start`, and `consumer finish`.
- Do not pass the producer's `System.nanoTime()` across machines to compute delivery time.
- If using wall-clock timestamps for cross-machine end-to-end timing, account for clock skew or use tracing/server-side metrics with clear semantics.

## 16. Designing dashboards and alerts

An event dashboard can be organized into four groups:

| Group | Charts / questions |
| --- | --- |
| Producer | Publish rate, `publish_duration` p95/p99, exception count |
| Dispatch | Queue depth, rejected tasks, publish-to-start delay |
| Handler | `process_duration` p50/p95/p99 by handler, success/error count, inflight |
| Business completion | Time to confirmed outcome, retry/dead-letter backlog, outcome |

Charts must have **clear name definitions and time units**. Do not label both `publish_duration` and `process_duration` as "event latency" without distinguishing the stage. For timer metrics, choose appropriate aggregations: rate/count for throughput, histogram percentiles for tail latency, and total duration to track time consumption.

Alerting suggestions:

1. **Sustained increase in handler p95** while publish latency stays flat → check slow dependencies, workers, or databases.
2. **Continuously growing queue depth** → producer outpaces consumer; apply backpressure/concurrency/rate limiting.
3. **Rising handler errors** → categorize errors and inspect failed events.
4. **No process measurements while publishes occur** → listeners may be skipped, transactions rolled back, event types misconfigured, or instrumentation miswired; investigate before concluding events were lost.
5. **Publish latency rises alongside process latency in synchronous mode** → a listener may be stalling the publish call.
6. **Process duration is stable while business E2E increases** → check queue lag, retries, commit delays, or downstream side effects.

Do not fire alerts on a single data point during low traffic. Use an appropriate evaluation window and minimum sample count before acting on percentiles.

## 17. Common measurement mistakes

| Mistake / misconception | Why it is wrong | How to fix |
| --- | --- | --- |
| `publishEvent` returned fast, so the event processed fast | Async returns right after handoff without waiting for handlers | Measure a timer inside the listener and await true completion |
| Wrapping `publishEvent` and calling it "handler latency" | May cover 0, 1, or many listeners depending on configuration | Attach timers to individual handlers |
| Using `System.currentTimeMillis()` to measure microseconds | Wall clock can jump and resolution is unsuitable | Use `Timer.Sample`/`System.nanoTime` within the same JVM |
| Using `System.nanoTime` across multiple processes | Monotonic clocks are unsynchronized between JVMs | Use tracing/timestamps and account for clock skew |
| Stopping the timer only on the success path | Errors are unmeasured → skewed statistics | Use `try/finally` and an outcome tag |
| Using `eventId`/`userId` as metric tags | High cardinality, memory/TSDB cost | Use bounded tags; put IDs in traces/logs |
| Timing a newly created `Mono` without subscribing | Measures pipeline assembly, not execution | Instrument around subscription/terminal signals |
| Enabling an executor while expecting ThreadLocal transactions to follow | Async breaks thread-bound boundaries | Design transactions and context propagation properly |
| Multiple listeners per event yet expecting process count = publish count | One event triggers multiple handler executions | Inspect counts by handler/event/outcome |
| Measuring start delay and calling it exact queue wait | Start delay also includes dispatch/commit time | Measure enqueue and dequeue if queue wait is needed |
| Using averages to hide tail latency | Mean does not show p95/p99 | Use histograms/percentiles |
| Assuming `@Timed` auto-instruments every `@EventListener` | Spring Framework has no default Observation for event listeners | Add explicit timers/Observations in handlers or valid AOP config |
| Not awaiting async callbacks before assertions | Reading counts too early → flaky tests | Use latches/futures/StepVerifier with appropriate timeouts |
| Assuming `finally` countDown means business success | It only indicates the handler exited its body | Check outcome and side-effect state |
| Recording nanosecond durations into `Timer` while labeling milliseconds | Wrong units and dashboards | Specify `TimeUnit` explicitly and check the exporter base unit |
| Metrics only, no traces or error logs | Cannot tell which specific event failed | Pair aggregated metrics with correlated logs/traces |
| Benchmarking 3 events in a demo and setting production SLOs | Demos do not reflect load, GC, or network | Load test, observe long-term trends, set SLOs from requirements |

## 18. Project adoption checklist

- [ ] Document clearly which metrics measure **publication handoff** and which measure **handler processing**.
- [ ] Start the `publish` timer right before the call so it does not accidentally include heavy payload construction.
- [ ] Place the `process` timer inside the actual handler; measure both success and error in `finally`.
- [ ] For async, have a mechanism to know processing **finished**; never treat publisher return as completion.
- [ ] For transaction-bound listeners, understand phase, commit/rollback, and non-transactional cases.
- [ ] Keep `start_delay`, `queue_wait`, and `end_to_end` distinctly defined.
- [ ] Use monotonic clocks for in-process durations; never compare `nanoTime` across JVMs.
- [ ] Keep metric tags low-cardinality; exclude event IDs, user IDs, payloads, and exception messages.
- [ ] If using an executor, monitor queue depth, active workers, rejections, and saturation.
- [ ] If tracing async, configure proper context propagation and verify span linkage.
- [ ] Do not label an event "succeeded" solely from `publish.count`; inspect per-handler outcomes.
- [ ] Distinguish rate, duration, count, percentiles, and error rate on dashboards/alerts.
- [ ] Test sync, async, handler exceptions, ignored listeners, rollbacks, and unsubscribed cases if using reactive.
- [ ] Do not rely on absolute duration assertions in unit tests using wall/real timing; verify counts/tags and semantics first.

## 19. Self-check questions

**Question 1.** A listener runs via an executor and makes an HTTP call taking 400 ms. `publishEvent` returns in 2 ms. What is `publish_duration` and does it prove the listener is fast?

**Answer:** `publish_duration` is around 2 ms, measuring the handoff. It does not reflect the 400 ms processing; `process_duration` inside the listener is required.

**Question 2.** 100 events of the same type, each with 3 listeners. Must the total process timer count equal 100?

**Answer:** No; there can be up to 300 successful handler invocations if all three listeners run each time, depending on event type filtering, phases, errors, and completion state.

**Question 3.** Why might `@TransactionalEventListener(AFTER_COMMIT)` show a low publish timer while the process timer appears much later?

**Answer:** Because publishing only registers the callback. The listener runs after the actual commit; start delay also includes the uncommitted transaction time.

**Question 4.** Should `eventId` be a tag on a Micrometer `Timer`?

**Answer:** No. It creates nearly unique time series, causing high cardinality; use bounded event type/handler/outcome tags and put correlation IDs in traces/logs.

**Question 5.** If `@EventListener` is used, does Spring Framework automatically create an Observation for every listener?

**Answer:** No. You must instrument with explicit Timers/Observations or properly configured AOP infrastructure, respecting sync/async contracts.

**Question 6.** What does `CountDownLatch` guarantee in the example?

**Answer:** It lets `main` wait until all three handler bodies have exited and finished recording metrics; it does not guarantee an out-of-process side effect was committed or durably delivered.

**Question 7.** To measure pure queue wait, where must timestamps be captured?

**Answer:** Around when the task is enqueued and when the worker starts executing it. Measuring from event creation to listener start is only a composite start delay.

**Question 8.** What unit handling is required for `Timer.record`?

**Answer:** Use an explicit `TimeUnit` for numeric durations or duration-recording Timer APIs; never assume a passed integer means milliseconds or nanoseconds without specifying it.

## 20. References

- Spring Framework 6.2 — `ApplicationEventPublisher` and handoff contract: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/context/ApplicationEventPublisher.html
- Spring Framework 6.2 — `SimpleApplicationEventMulticaster`, executor, and exception handling: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html
- Spring Framework Reference 6.2 — Observability Support; Application Events / `@EventListener` section: https://docs.spring.io/spring-framework/reference/6.2/integration/observability.html
- Spring Framework Reference 6.2 — Standard and Custom Events: https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html
- Spring Framework Reference 6.2 — Transaction-bound Events: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html
- Micrometer Reference — Timers and `Timer.Sample`: https://docs.micrometer.io/micrometer/reference/concepts/timers.html
- Micrometer Reference — Choosing Meter Types: https://docs.micrometer.io/micrometer/reference/concepts/meters.html
- Micrometer Reference — Histograms and Percentiles: https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html
- Spring Boot Reference — Metrics: https://docs.spring.io/spring-boot/reference/actuator/metrics.html
- Micrometer Context Propagation: https://docs.micrometer.io/context-propagation/reference/
