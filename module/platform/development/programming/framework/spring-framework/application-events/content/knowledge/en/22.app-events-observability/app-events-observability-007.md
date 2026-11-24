# Event Publication Count Metrics

## 1. What does counting "published events" actually count?

In Spring Framework Application Events, a service can call `ApplicationEventPublisher.publishEvent(...)` to signal a business occurrence: `OrderPlaced`, `PaymentCaptured`, `CustomerRegistered`. As a system grows, common operational questions are:

- How many events does the application publish per minute?
- Which event type suddenly spiked or stopped appearing?
- How many `publishEvent(...)` calls threw an exception?
- Were all events processed successfully by listeners?
- How do we count an event published inside a transaction that ultimately rolled back?

**The answer must begin with the metric definition.** "Called the publisher" differs from "publisher returned normally", "listener ran", and "occurrence committed". A single metric must not be interpreted as representing all four states.

Example:

~~~text
PlaceOrder command
      |
      v
Application service
      |
      +-- publishEvent(OrderPlaced #101)  <--- count publish attempt
                 |
                 +-- @EventListener A     <--- can count listener invocation
                 |
                 +-- @EventListener B     <--- second invocation
                 |
                 +-- @Async listener C    <--- processes later, may fail
      |
      v
Transaction commit / rollback   <--- independent business state
~~~

In this example, **a single publisher call can trigger multiple listeners**; conversely, a single publish does not necessarily execute listeners immediately (especially with transaction-bound listeners). If the total invocation count across three listeners is 3, that **does not mean** three events were published.

Lesson objective: use **Micrometer `Counter`** to measure event publication counts under clear definitions, categorize with low-cardinality tags, avoid double counting, and build dashboards that can be interpreted accurately.

## 2. Measurement levels that should have distinct names

| Logical metric | Counter increment point | Question answered |
| --- | --- | --- |
| `event.publish.attempts` | Right before calling `publishEvent` | How many times did the application attempt to publish an event through the instrumented entry point? |
| `event.publish.calls` + tag `outcome=returned` | After `publishEvent` returns normally | How many publisher calls **returned**, without asserting all listeners succeeded? |
| `event.publish.calls` + `outcome=threw` | When `publishEvent` throws an exception on the current thread | How many calls ended immediately with an exception? |
| `event.listener.invocations` | Right before starting a specific listener | How many times was that listener invoked? |
| `event.listener.results` + success/error | When listener processing **actually completes** | How many times did the listener finish/fail? |
| `event.transaction.committed` | When the business/transaction confirms a successful commit | How many occurrences were durably persisted per this contract? |
| `integration.event.sent` | After the transport confirms sending per contract | How many messages were accepted at the integration boundary? |

These are **application-defined suggested metric names**, not standard names automatically emitted by Spring Framework for every `ApplicationEventPublisher`.

In the main examples, we use two application-managed metrics:

1. **`demo.events.publish.attempts`**: incremented once before every call through the wrapper.
2. **`demo.events.publish.calls`**: incremented once when the call completes, tagged `outcome=returned` or `outcome=threw`.

Therefore:

~~~text
attempts ~= calls{returned} + calls{threw}
~~~

This equality holds only when all calls have **completed**, the process did not stop mid-call, and every publication path goes through the same wrapper. It is not an equality for committed business events.

**Do not add `attempts` to `calls` series** to infer "total events": those are two measurements of **the same calls** at two different points in time.

## 3. Micrometer Counter: the right tool for counting

Micrometer provides `MeterRegistry` and `Counter`. Each call to `increment()` increases the counter; counters suit monotonically increasing occurrence counts, such as how many times a service requested to publish an event. Counters are not for representing "how many tasks are currently running" (which would be a gauge) or latency.

Core API example:

~~~java
// Illustrative snippet requiring a configured MeterRegistry.
Counter published = Counter.builder("app.events.publish.attempts")
    .description("Attempts to publish application events")
    .tag("event_type", "order_placed")
    .register(meterRegistry);

published.increment();
~~~

A `MeterRegistry` stores meters by **name and tag set**. Re-registering the same name + tags typically retrieves the same meter rather than creating a new metric on every call. In high-throughput applications, you can cache references to `Counter`s with a bounded label set instead of rebuilding builders repeatedly; never create a new tag value per order ID.

**A Micrometer Counter does not mean "total system events since the beginning of time"**: local values reset on process restart and differ across instances. On backends such as Prometheus, prefer analyzing **rate/increase over a time window** and summing across instances when needed, rather than comparing raw counts of a long-lived process against a recently restarted one.

Micrometer recommends: if you already use a `Timer` or `DistributionSummary` for the same operation, they already track **count**. Do not create a redundant counter with the same meaning just to know completion counts, unless the definition intentionally differs (for example, `publish.attempts` measured before the call vs. a timer measuring duration of completed calls).

## 4. Where to count to avoid under-counting or double-counting?

There are three common locations:

### A. Instrument in the service calling the publisher

~~~java
// Illustrative; part of an application service, not a standalone file.
counter.increment();
eventPublisher.publishEvent(new OrderPlaced(orderId));
~~~

Pros: simple, aligns closely with business code. Cons: developers easily forget in other services, or multiple code paths may call the publisher without instrumentation.

### B. Create a wrapper/decorator for `ApplicationEventPublisher`

~~~text
OrderService
    -> MeteredPublisher.publish(event)
        -> increment attempts
        -> delegate.publishEvent(event)
        -> increment outcome=returned / threw
~~~

Pros: **a single entry point** for many domain event types. Limitations: every code path must go through this wrapper; events published internally by Spring Framework (such as lifecycle events) or code calling `ApplicationEventPublisher` directly will **bypass the wrapper** and **not be counted**.

This is the approach used in the section 6 demo because the definition and measurement point are explicit. Avoid exposing a new bean of type `ApplicationEventPublisher` that accidentally causes Spring to inject the wrapper into itself; use a **dedicated facade** (such as `MeteredPublisher`) receiving the underlying `ApplicationEventPublisher` via constructor.

### C. Instrument at `ApplicationEventMulticaster`

You can extend/customize the multicaster to observe dispatch or invocation calls. However, you must then distinguish:

- One publication can hit multiple listeners.
- The multicaster can dispatch synchronously or use an executor; callbacks can be rejected or run later.
- `ApplicationListener.supportsAsyncExecution()` can prevent some listeners (such as transaction-synchronized listeners) from moving to a shared executor.
- A custom multicaster can alter default behavior and easily affect Spring's internal events.

If the goal is solely to **count domain publish calls**, a wrapper at the application boundary is usually simpler and less risky.

## 5. Tag design: measure by event type, not per ID

Micrometer supports tags to group metrics. Choose **low cardinality**, meaning the number of values per tag is controlled and does not grow with every request/event.

| Tag | Should use? | Reason |
| --- | --- | --- |
| `event_type=order_placed / payment_captured` | **Yes** | Bounded, well-defined set of event types |
| `outcome=returned / threw` | **Yes** | Two discrete call outcomes |
| `service=checkout` | Yes, if needed and configured consistently | Value comes from a service catalog |
| `environment=prod / staging` | Yes, if the backend does not attach it already | Bounded environment catalog |
| `event_id=UUID` | **No** | A new value for every event, causing time-series explosion |
| `order_id=101 / 102 / ...` | **No** | Grows with every order |
| Arbitrary `customer_id / user_id / tenant_id` | **No** | High cardinality and potential exposure of sensitive data |
| `correlation_id / trace_id` | **No** | Unique ID per workflow/trace; belongs in logs/traces |
| `exception_message` | **No** | Free-form text, easy data leak, hard to bound |

If you want an `exception` tag, map it to **a bounded error category** such as `validation`, `downstream`, `unexpected`, rather than putting full messages or stack traces into tags.

Do not use `event.getClass().getName()` as a label without bounding the set of types: in systems with proxies, generated classes, or arbitrary payloads, that can increase cardinality. Better to maintain an explicit mapping for countable business events and bucket everything else under `other`.

The number of time series grows as the **Cartesian product** of tag groups. For example, 20 `event_type` × 3 `outcome` × 5 `service` × 3 `environment` already produces **900 combinations** (before multiplying by instances). Adding `order_id` turns that into a huge number with high storage/query costs.

## 6. Runnable example: Spring Framework + Micrometer

This example uses **Java 17+**, **Spring Framework 6.2.19**, and **Micrometer Core 1.15.12**. No Spring Boot or web server is required; metrics are kept in `SimpleMeterRegistry` for exact verification.

Demo flow:

1. Publish `OrderPlaced(101)`: synchronous listener succeeds normally.
2. Publish `OrderPlaced(102)`: listener intentionally throws; wrapper records `outcome=threw` and rethrows to caller.
3. Publish `PaymentCaptured(101)`: synchronous listener succeeds normally.
4. Print Counters proving **publish attempts**, **returned calls**, and **thrown calls** are distinct numbers.

### Structure

~~~text
spring-event-metrics/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/EventMetricsDemo.java
~~~

### settings.gradle

~~~groovy
rootProject.name = 'spring-event-metrics'
~~~

### build.gradle

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.19'
    implementation 'io.micrometer:micrometer-core:1.15.12'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.EventMetricsDemo'
}
~~~

### src/main/java/demo/EventMetricsDemo.java

~~~java
package demo;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

import java.util.Objects;

@Configuration
public class EventMetricsDemo {

    public record OrderPlaced(long orderId) {}
    public record PaymentCaptured(long orderId) {}

    @Bean
    MeterRegistry meterRegistry() {
        return new SimpleMeterRegistry();
    }

    @Bean
    MeteredPublisher meteredPublisher(
            ApplicationEventPublisher publisher,
            MeterRegistry registry) {
        return new MeteredPublisher(publisher, registry);
    }

    @Bean
    DomainListeners domainListeners() {
        return new DomainListeners();
    }

    public static class DomainListeners {
        @EventListener
        public void onOrderPlaced(OrderPlaced event) {
            if (event.orderId() == 102L) {
                throw new IllegalStateException(
                    "simulated listener failure");
            }
            System.out.println("handled order " + event.orderId());
        }

        @EventListener
        public void onPaymentCaptured(PaymentCaptured event) {
            System.out.println("handled payment " + event.orderId());
        }
    }

    public static class MeteredPublisher {
        private final ApplicationEventPublisher delegate;
        private final MeterRegistry registry;

        public MeteredPublisher(ApplicationEventPublisher delegate,
                                MeterRegistry registry) {
            this.delegate = delegate;
            this.registry = registry;
        }

        public void publish(Object event) {
            Objects.requireNonNull(event, "event");
            String type = eventType(event);

            // Increment before the call, even if the listener throws.
            Counter.builder("demo.events.publish.attempts")
                .description("Publication attempts through this facade")
                .tag("event_type", type)
                .register(registry)
                .increment();

            try {
                delegate.publishEvent(event);

                // Only means: publishEvent returned normally.
                outcome(type, "returned");
            } catch (RuntimeException | Error ex) {
                // Synchronous failure surfaces right at the publisher call.
                outcome(type, "threw");
                throw ex;
            }
        }

        private void outcome(String type, String value) {
            Counter.builder("demo.events.publish.calls")
                .description("Completed publish calls by exit outcome")
                .tags("event_type", type, "outcome", value)
                .register(registry)
                .increment();
        }

        // Allow only an application-defined bounded tag set.
        private static String eventType(Object event) {
            if (event instanceof OrderPlaced) {
                return "order_placed";
            }
            if (event instanceof PaymentCaptured) {
                return "payment_captured";
            }
            return "other";
        }
    }

    private static long attempts(
            MeterRegistry registry, String type) {
        return Math.round(registry
            .get("demo.events.publish.attempts")
            .tag("event_type", type)
            .counter()
            .count());
    }

    private static long calls(
            MeterRegistry registry, String type, String outcome) {
        return Math.round(registry
            .get("demo.events.publish.calls")
            .tags("event_type", type, "outcome", outcome)
            .counter()
            .count());
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(
                EventMetricsDemo.class)) {

            var publisher = context.getBean(MeteredPublisher.class);
            var registry = context.getBean(MeterRegistry.class);

            publisher.publish(new OrderPlaced(101L));

            try {
                publisher.publish(new OrderPlaced(102L));
            } catch (RuntimeException ex) {
                System.out.println("caught publish 102");
            }

            publisher.publish(new PaymentCaptured(101L));

            System.out.println(
                "order attempts=" + attempts(registry, "order_placed"));
            System.out.println(
                "order returned=" + calls(
                    registry, "order_placed", "returned"));
            System.out.println(
                "order threw=" + calls(
                    registry, "order_placed", "threw"));
            System.out.println(
                "payment attempts=" + attempts(
                    registry, "payment_captured"));
            System.out.println(
                "payment returned=" + calls(
                    registry, "payment_captured", "returned"));
        }
    }
}
~~~

### Running

With JDK 17+ and Gradle:

~~~bash
gradle run --quiet
# If using Gradle Wrapper: ./gradlew run --quiet
# On Windows with wrapper: gradlew.bat run --quiet
~~~

Lines printed by `System.out` in the demo (excluding external logs):

~~~text
handled order 101
caught publish 102
handled payment 101
order attempts=2
order returned=1
order threw=1
payment attempts=1
payment returned=1
~~~

### Why are these numbers accurate?

- `OrderPlaced(101)`: wrapper increments **attempts by 1**, listener completes, `publishEvent` returns, wrapper increments **returned by 1**.
- `OrderPlaced(102)`: wrapper increments **attempts by 1**, synchronous listener throws `IllegalStateException`; default `SimpleApplicationEventMulticaster` has no error handler and no executor, so the error propagates to the publish call. Wrapper increments **threw by 1**, caller catches the error.
- `PaymentCaptured(101)`: wrapper increments **payment attempts by 1** and **payment returned by 1** after the listener finishes.
- Counters by `event_type` only have `order_placed` and `payment_captured` groups for the demo calls. There is no `order_id` tag, so there is no per-order time series.
- Failure of listener 102 **does not prove the event was not delivered**: the listener began executing and threw an error. The `outcome=threw` metric only describes the outcome of the publisher call from the caller's perspective.

**Example limitations:** the demo uses synchronous in-process events only, with no database, transaction, or broker. Never interpret the `returned` metric as "the order was committed" or "all async processing succeeded".

## 7. When a listener uses `@Async`, what does the publish metric measure?

With regular synchronous listeners, `SimpleApplicationEventMulticaster` invokes listeners on the publisher's thread by default. Listener errors can propagate back to the publisher, as in the demo above.

With `@Async @EventListener` or a multicaster using an executor, the publisher typically **returns before the listener finishes**. At that point:

~~~text
publishEvent(OrderPlaced)
    |
    +-- executor receives task
    |     |
    |     +------ @Async listener runs later
    |                       |
    |                       +-- success / failure
    |
    +-- publishEvent may return before the step above
          |
          +-- metric outcome=returned increments
~~~

If the listener fails later, **you cannot use the wrapper's `outcome=threw` to infer processing error counts**. Exceptions occurring in async tasks must be observed at the listener, executor, `AsyncUncaughtExceptionHandler`, or appropriate result-handling mechanism.

To observe the listener, instrument at the **actual processing boundary**:

~~~java
// Illustrative snippet inside a bean, not a standalone file.
@Async
@EventListener
public void onOrderPlaced(OrderPlaced event) {
    Counter.builder("app.event.listener.invocations")
        .tags("listener", "order_notification",
              "event_type", "order_placed")
        .register(registry)
        .increment();

    try {
        notificationGateway.enqueue(event.orderId());

        Counter.builder("app.event.listener.results")
            .tags("listener", "order_notification",
                  "outcome", "success")
            .register(registry)
            .increment();
    } catch (RuntimeException ex) {
        Counter.builder("app.event.listener.results")
            .tags("listener", "order_notification",
                  "outcome", "error")
            .register(registry)
            .increment();
        throw ex;
    }
}
~~~

This snippet assumes the bean has `MeterRegistry registry`, `NotificationGateway notificationGateway`, and matching imports/event types. **It is not a standalone compilable program**. For handlers returning `Mono`/`Flux`, place instrumentation on the completion/error signals of the reactive pipeline, not when creating the publisher; `Mono` may not yet be subscribed.

Counting listeners per handler also means **one event can produce multiple invocations**. Never sum listener invocations across handlers and call that "number of published events".

## 8. When `@TransactionalEventListener` is involved, distinguish publication from commit

`@TransactionalEventListener` registers handling for a transaction phase, such as `AFTER_COMMIT`. A `publishEvent(...)` call can occur **before the transaction commits**:

~~~text
BEGIN T1
  save(order)
  publishEvent(OrderPlaced)   -> attempt +1
  ...
ROLLBACK T1                  -> AFTER_COMMIT listener does not run
~~~

Therefore:

- `publish.attempts` incremented by 1; it counts **calls**, not commits.
- `outcome=returned` may also increment: the publisher call returned normally after registering synchronization.
- The `AFTER_COMMIT` listener **does not run** because T1 rolled back.
- Never treat normal publish return metrics as proof that an order record exists in the database.

If you want to count **events whose post-commit processing started**, instrument directly inside the listener:

~~~java
// Illustrative snippet, not a standalone program.
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onCommitted(OrderPlaced event) {
    registry.counter("app.events.after_commit.invocations",
        "event_type", "order_placed").increment();
    // Invoke post-commit processing...
}
~~~

Maintain a distinction: the metric above counts **AFTER_COMMIT callbacks invoked**, does not guarantee a secondary task completed, and is not the count of committed transactions (one transaction may publish multiple events, zero events, or multiple events of the same type).

Additional notes:

- `@TransactionalEventListener` by default ignores events **outside a transaction** when `fallbackExecution=false`. Enabling fallback changes semantics: running outside a transaction is no longer after-commit.
- Post-commit callbacks occur after the original transaction has committed; listener errors cannot automatically roll back T1. Writing to the DB from the callback may require an explicit independent transaction.
- For reactive transactions since Spring Framework 6.1+, transaction context lives in **Reactor Context**. `TransactionalEventPublisher` helps attach `TransactionContext` to the event source; counting at a synchronous wrapper does not prove a reactive chain was subscribed or a transaction committed.
- When you must guarantee no events are lost after a crash, use a **transactional outbox**: write to the outbox in the same business transaction, then count separately as workers send/ACK events. In-memory counters do not replace a durable event log.

## 9. Spring Boot Actuator and monitoring backend integration

In Spring Boot, Actuator can auto-configure a `MeterRegistry` for Micrometer. Once `MeterRegistry` is injected, you can use the same wrapper technique or record counters in application services.

Commonly needed Maven dependencies:

~~~xml
<!-- Illustrative when using Spring Boot with BOM managing versions -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>

<!-- Add only when Prometheus scrape format is needed -->
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
</dependency>
~~~

Optional configuration example:

~~~properties
management.endpoints.web.exposure.include=health,info,metrics,prometheus
~~~

At runtime, you can inspect the metric at `/actuator/metrics/demo.events.publish.attempts` (using the **Micrometer name** in code), filtered by query parameter `tag=event_type:order_placed`. With a Prometheus registry and enabled endpoint, `/actuator/prometheus` exposes time series per the backend's naming conventions.

**Do not expect Actuator to auto-create `demo.events.publish.attempts`:** that name appears only when instrumented by the application. The plain Spring Framework demo does not use Actuator, so it prints from `SimpleMeterRegistry`.

**Security:** expose only the endpoints needed per environment and apply appropriate auth/network policies; metrics can reveal operational information even without personal IDs.

### PromQL suggestions for publish rate

With Prometheus, a Micrometer `Counter` named `demo.events.publish.attempts` typically appears under a name like `demo_events_publish_attempts_total` (exact name depends on registry, naming convention, and version). After verifying the actual name at the scrape endpoint, you can use:

~~~promql
sum by (event_type) (
  rate(demo_events_publish_attempts_total[5m])
)
~~~

The result is **average attempts per second over 5 minutes**, not an absolute total since system startup. For total attempts in 5 minutes, consider `increase(...[5m])`. Across multiple instances, `sum` aggregates time series, though you should still verify labels and scrape behavior.

To track the error ratio of **publisher calls** (not async listener failures), you can analyze:

~~~promql
sum(rate(demo_events_publish_calls_total{outcome="threw"}[5m]))
/
clamp_min(
  sum(rate(demo_events_publish_calls_total[5m])),
  1e-9
)
~~~

This is only the **ratio of publisher calls that threw over completed calls**; it does not measure domain processing failure rates. Do not use it in place of handler error reporting or dead-letter queues.

## 10. Common measurement mistakes

### Mistake 1 — Incrementing a counter in every listener and calling it "published events"

One event received by three listeners can increment the counter three times. Better to place the publication counter at **one entry point** and keep separate listener metrics with clear names/scopes.

### Mistake 2 — Counting `returned` as all listeners succeeding

With `@Async`, transaction-bound listeners, or custom multicasters, `publishEvent` returning does not mean handlers finished. Use dedicated handler completion metrics.

### Mistake 3 — Creating a metric per unique event ID

~~~java
// Illustrative anti-pattern (not a standalone program).
Counter.builder("app.events.publish.attempts")
    .tag("event_id", event.id().toString())
    .register(registry)
    .increment();
~~~

Every new event ID creates a new time series. Put `eventId` and `correlationId` in **structured logs or tracing spans**, never in metric labels.

### Mistake 4 — Counting publishes as committed occurrences

If an event is published inside a transaction and T1 rolls back, the counter still increments. Use post-commit metrics or durable domain counts (database/outbox) when business logic requires persisted events.

### Mistake 5 — Incrementing the counter in both the wrapper and the service, then summing them

When a service calls a wrapper, one event can be counted twice if both places increment `app.events.publish.attempts`. Choose **one point of ownership** and avoid two metrics with the same name but different definitions.

### Mistake 6 — Using a Counter for pending work counts

Counters only increase. For queue depth, active jobs, or pending events, choose a gauge, long-task timer, or appropriate state metric instead of trying to decrement a counter or misnaming it.

### Mistake 7 — Forgetting retries and duplicate deliveries

`publish.attempts` increments on every **attempt**. If retries send the same event three times, attempts can be 3 even for one business event ID. If the goal is unique business events, durable ID tracking/deduplication is required and cannot be inferred from a simple Counter.

### Mistake 8 — Monitoring Counters without monitoring processing errors

A service can publish steadily while every async handler fails. Combine publish rate, listener success/error, latency, backlog/outbox age, and health per system needs.

## 11. Testing whether metrics match their definitions

A test matrix should include:

| Test | Publish attempts | Publish returned | Publish threw | Notes |
| --- | ---: | ---: | ---: | --- |
| One synchronous listener succeeds | +1 | +1 | +0 | Does not mean commit |
| Synchronous listener throws exception to publisher | +1 | +0 | +1 | Some earlier listeners may already have run |
| Async listener scheduled, then fails later | +1 | usually +1 | usually +0 | Handler errors must be measured separately |
| Event published in T1, then rollback | +1 | usually +1 | usually +0 | `AFTER_COMMIT` listener does not run |
| One event goes to 3 listeners | +1 | 1 call outcome | 0 or 1 | Listener invocations may be 3 |
| Same event retried twice | +2 | depends on each call | depends on each call | Unique event ID may be only 1 |

"Usually" cases depend on executor, transaction, listener, and error-path configuration, not a guarantee of the `ApplicationEventPublisher` API.

### Operational checklist

1. Define precisely what is counted: attempt, returned, handler success, after-commit, or broker ACK.
2. Identify the right entry point so the metric is not bypassed.
3. Use `Counter` with bounded tags; exclude IDs/request/correlation from labels.
4. Write tests asserting counter increments on synchronous errors and no double counting.
5. Add `@Async` and `@TransactionalEventListener` tests to avoid interpreting `returned` as handler success.
6. Consider `Timer` when latency is needed; avoid redundant count metrics.
7. Use `rate`/`increase` on dashboards and account for resets on instance restarts.
8. Verify actual metric names at actuator/scrape endpoints before writing PromQL.
9. Monitor backlog, retries, handler errors, or outboxes if business logic requires delivery guarantees.
10. Re-evaluate overhead/cardinality as event types or labels change over time.

### Takeaway

~~~text
Counter before publishEvent()
    -> Number of publication attempts through the instrumented entry point.

Counter after publishEvent() returns
    -> Number of publisher calls that returned normally.

Counter inside listener
    -> Number of listener invocations / completions (per measurement point).

Counter in AFTER_COMMIT
    -> Number of post-commit callbacks invoked, not all published events.

Outbox/broker metric
    -> Different guarantee level; requires its own contract and retry/idempotency.
~~~

**Event publication count metrics are valuable only when the metric name and counting point match.** In Spring, instrument at a clear publication boundary using Micrometer `Counter`; never treat a `publishEvent` call as a guarantee of commit, delivery, or successful processing.

## References

- [Micrometer — Counters](https://docs.micrometer.io/micrometer/reference/concepts/counters.html)
- [Micrometer — Meters and MeterRegistry](https://docs.micrometer.io/micrometer/reference/concepts/registry.html)
- [Spring Framework — ApplicationEventPublisher Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Spring Framework — SimpleApplicationEventMulticaster Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [Spring Boot — Metrics / Actuator](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
