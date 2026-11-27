# Single-Item Suppliers and Flux-Returning Suppliers

In Spring Cloud Stream, a `Supplier` is a data producer for an output binding. There are two common ways to build this source: returning a single value per invocation with `Supplier<T>`, or returning a publisher that emits multiple values with `Supplier<Flux<T>>`. Both signatures create an output binding based on the bean name, but their trigger mechanisms and emission lifecycles differ.

`Supplier<T>` fits when the application can produce one event each time the poller invokes it. `Supplier<Flux<T>>` fits when the data source is naturally a reactive stream that can emit multiple items over time and supports asynchronous processing. Choosing the right type helps control emission cadence, resources, and error handling in production.

## 1. Supplier as the Source of an Output Binding

Spring Cloud Function recognizes functional beans based on standard Java functional types. With `Supplier<T>`, the function takes no input and produces an output value. Spring Cloud Stream connects that value to the application's output binding.

Example bean named `orderEventSupplier`:

```java
import java.time.Instant;
import java.util.UUID;
import java.util.function.Supplier;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public record OrderCreated(String orderId, Instant createdAt) {}

@Configuration
public class OrderEventSources {

    @Bean
    public Supplier<OrderCreated> orderEventSupplier() {
        return () -> new OrderCreated(
                "ORD-" + UUID.randomUUID(),
                Instant.now()
        );
    }
}
```

The default output binding name is:

```text
orderEventSupplier-out-0
```

The binding name is formed from the bean name and the `out` direction, with the first index `0`. The return type `OrderCreated` defines the payload produced by the function. The binding name does not depend on whether the payload is a record, a string, or another Java type.

## 2. Single-Item Supplier: Supplier<T>

With `Supplier<T>`, each call to `get()` produces a single value `T`. In Spring Cloud Stream's standard producer model, the framework uses a poller to invoke the supplier periodically. The returned value is converted into a message and sent through the output binding.

The processing flow can be visualized as follows:

```mermaid
flowchart LR
    A[Poller reaches interval] --> B[Calls Supplier.get()]
    B --> C[Creates one object T]
    C --> D[Converts to Message]
    D --> E[Binding out-0]
    E --> F[Binder]
    F --> G[Destination on broker]
```

The supplier does not create its own thread or scheduler in standard examples. The poller manages when it is called. The default poller configuration has a 1,000 ms interval between polls and a maximum of 1 message per poll. With a supplier returning a single object, each invocation creates one event.

### Configuring the Poll Interval

Example binding and poller configuration:

```yaml
spring:
  cloud:
    function:
      definition: orderEventSupplier
    stream:
      poller:
        initial-delay: 1000
        fixed-delay: 5000
        max-messages-per-poll: 1
      bindings:
        orderEventSupplier-out-0:
          destination: orders.created
          content-type: application/json
```

In this example:

- `initial-delay` sets the wait time before the first poll, in milliseconds.
- `fixed-delay` sets the pause between polls, in milliseconds.
- `max-messages-per-poll` limits how many messages are produced in a single poll.
- `destination` is the resource receiving events on the broker.
- `content-type` declares the output payload format; `application/json` lets the framework serialize the record into JSON when using standard message conversion.

The poller properties above apply to the shared application-wide poller. If multiple suppliers are activated together, consider the impact of shared settings and the emission cadence needed by each source. Do not set `fixed-delay` too low if creating or sending messages consumes more resources than the broker can handle.

### When Should You Use Supplier<T>?

This type suits producers with a steady cadence where each invocation can create an independent event, such as:

- Emitting service status snapshots periodically.
- Generating scheduled aggregated events.
- Reading one record from a data source per poll.
- Emitting health check signals or periodic metrics.

The supplier should create a fresh value or a value representing current state at the moment of invocation. Avoid returning the same mutable object and mutating it after emission, because the sent message may share references with application code.

## 3. Stream-Returning Supplier: Supplier<Flux<T>>

`Flux<T>` is a Project Reactor publisher that can emit zero, one, or many elements over time. When a bean declares `Supplier<Flux<T>>`, the supplier returns a publisher instead of a single object.

Example emitting a new event every two seconds:

```java
import java.time.Duration;
import java.time.Instant;
import java.util.function.Supplier;

import reactor.core.publisher.Flux;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public record MetricSample(long sequence, Instant capturedAt) {}

@Configuration
public class MetricEventSources {

    @Bean
    public Supplier<Flux<MetricSample>> metricStream() {
        return () -> Flux.interval(Duration.ofSeconds(2))
                .map(sequence -> new MetricSample(sequence, Instant.now()));
    }
}
```

The default output binding is:

```text
metricStream-out-0
```

An important distinction: for a supplier returning a reactive type, Spring Cloud Function invokes the supplier to obtain the publisher and then subscribes to that publisher. A reactive supplier is not repeatedly invoked by the poller for each element the way `Supplier<T>` is. The publisher itself is responsible for emitting subsequent elements. Therefore, the poller's `fixed-delay` does not control the cadence of individual items emitted by `Flux`.

With `Flux.interval(Duration.ofSeconds(2))`, the publisher emits a sequential number every two seconds on its own. The `map` operator converts each number into a `MetricSample`. Each element passes through the output binding as a separate message.

### Configuring the Binding for Flux

```yaml
spring:
  cloud:
    function:
      definition: metricStream
    stream:
      bindings:
        metricStream-out-0:
          destination: metrics.samples
          content-type: application/json
```

No poller configuration is needed to create the two-second cadence in this example. The cadence is already expressed in `Flux.interval`. To change the emission timing, adjust the `Duration` or apply appropriate Reactor operators.

## 4. Comparing the Two Supplier Types

| Characteristic | `Supplier<T>` | `Supplier<Flux<T>>` |
| --- | --- | --- |
| Value returned by supplier | One object `T` per invocation | One publisher `Flux<T>` |
| Emission mechanism | Poller invokes supplier periodically | Supplier is invoked to obtain the publisher; subscription receives elements emitted by the publisher |
| Cadence control | `fixed-delay`, `initial-delay`, `max-messages-per-poll` | Reactor operators or sources, such as `interval`, `delayElements` |
| Item count | Typically one item per invocation | Zero, one, or many items within a subscription |
| Completion | Finishes after sending the value for that poll | Publisher may complete or continue running |
| Suitable for | Data sources polled periodically | Continuous or asynchronous data streams |

Both types share the `<function>-out-0` output binding convention. The difference lies in the return type and emission lifecycle, not in the binding name.

## 5. Finite Flux vs. Infinite Flux

A `Flux` can emit a finite number of items and then complete:

```java
@Bean
public Supplier<Flux<String>> startupEvents() {
    return () -> Flux.just(
            "SERVICE_STARTED",
            "CACHE_READY",
            "CONSUMER_READY"
    );
}
```

The `Flux.just` publisher emits three values and then sends a completion signal (`onComplete`). Once the publisher completes, that subscription ends. The framework does not automatically re-invoke the supplier on a poller schedule just because the `Flux` completed. If you need to replay a finite sequence, design repetition explicitly using Reactor operators like `repeat`, or create a new publisher via a mechanism suited to the application lifecycle.

An infinite `Flux` can continue emitting until the subscription is canceled or the publisher encounters an error:

```java
@Bean
public Supplier<Flux<Long>> heartbeat() {
    return () -> Flux.interval(Duration.ofSeconds(10));
}
```

This heartbeat source does not complete naturally. When the application shuts down, the subscription must be canceled so the publisher and related resources stop running. Source operators like `interval` manage Reactor schedulers; for sources that open external connections or resources, design explicit resource cleanup upon cancellation.

## 6. Cold Publisher vs. Hot Publisher

When building `Supplier<Flux<T>>`, understand whether the source is cold or hot:

- **Cold publishers** typically create dedicated data per subscription. `Flux.just`, `Flux.fromIterable`, and `Flux.interval` are common examples. When a new subscription arrives, the publisher starts emitting according to its definition.
- **Hot publishers** emit data independently of individual subscribers. A late subscriber may miss events emitted earlier. Callback sources, sensors, or event buses can exhibit hot behavior.

Spring Cloud Stream typically subscribes to the publisher returned by the supplier during the binding lifecycle. Therefore, choose a publisher matching how the application intends to manage subscribers. If using a hot source, account for when emission starts, buffering, policy when no subscriber is attached, and behavior when a subscriber cancels.

Do not create a global hot source in a static field and assume every application instance receives all events. When running multiple instances, each instance may have its own producer; if the external source is unshared or unpartitioned, the system may emit duplicates or lose data depending on the source design.

## 7. Combining Flux with Reactor Operators

Reactor provides operators to shape data before messages enter the output binding.

### Transforming Each Element

```java
@Bean
public Supplier<Flux<String>> normalizedCodes() {
    return () -> Flux.just(" ab-01 ", "cd-02 ", " ef-03 ")
            .map(String::trim)
            .map(String::toUpperCase);
}
```

`map` transforms each element synchronously. Each transformed string is emitted as an element of the `Flux`.

### Filtering Elements

```java
@Bean
public Supplier<Flux<Integer>> validMeasurements() {
    return () -> Flux.range(1, 20)
            .filter(value -> value % 2 == 0);
}
```

`filter` retains only elements satisfying the predicate. Filtered-out values are not sent to the binding.

### Limiting and Grouping

```java
import java.util.List;

@Bean
public Supplier<Flux<List<Integer>>> measurementBatches() {
    return () -> Flux.range(1, 100)
            .buffer(10);
}
```

`buffer(10)` groups elements into lists of at most ten values. At that point, each output message's payload is a list rather than an individual integer. Consumers must understand the new schema.

### Calling Asynchronous Services

```java
@Bean
public Supplier<Flux<OrderSummary>> orderSummaries() {
    return () -> Flux.fromIterable(loadPendingOrderIds())
            .flatMap(this::loadSummaryAsync, 8);
}
```

This example illustrates `flatMap` with a concurrency limit of eight simultaneous tasks. In a real application, `loadPendingOrderIds` and `loadSummaryAsync` must be provided by appropriate beans. Limiting concurrency helps control simultaneous requests and pressure on dependent services.

## 8. Backpressure and Emission Rate

Reactive Streams includes a backpressure mechanism allowing subscribers to request data according to their processing capacity. However, not every source can pause. For example, `Flux.interval` follows its own clock; if downstream cannot keep up, Reactor may raise an overflow error according to the source's policy rather than buffering infinitely.

When designing a `Flux` source:

- Choose an emission rate aligned with the binder's and broker's write capacity.
- Use bounded buffers if short-term spikes must be absorbed; define clear behavior when the buffer fills.
- Limit concurrency when calling external services with `flatMap`.
- Avoid calling `block()` inside reactive chains because it can block processing threads.
- Monitor latency, emission rate, error counts, and buffered or dropped item counts.

Reactor backpressure does not mean the broker buffers messages infinitely. How the binder requests and forwards data down to the producer depends on the implementation, configuration, and broker. Run load tests against the actual binder to determine throughput limits and behavior when the broker slows down.

## 9. Error Handling in Supplier and Flux

With `Supplier<T>`, errors can occur when the poller invokes the supplier—for instance, when the data source is unreachable or a computation throws an exception. With `Supplier<Flux<T>>`, errors can occur while constructing the publisher or while the publisher is emitting items.

Several Reactor operators assist with error handling:

```java
import java.time.Duration;

@Bean
public Supplier<Flux<String>> resilientSource() {
    return () -> readEvents()
            .retryWhen(reactor.util.retry.Retry.backoff(3, Duration.ofSeconds(1)))
            .onErrorResume(error -> {
                log.error("Event source stopped", error);
                return Flux.empty();
            });
}
```

This snippet illustrates retrying up to three times with backoff before falling back to an empty `Flux`. `readEvents()` and `log` represent application components that must be supplied. If you use `onErrorResume` to return `Flux.empty()`, the publisher completes after handling the error; the source does not resume indefinitely on its own. Choose fallback behavior based on business requirements and avoid silently dropping events.

Publisher-level retries, Spring Cloud Stream retries, and broker retries or redeliveries are distinct mechanisms. Configuring consumer retries does not automatically ensure a `Supplier` source will re-emit data that failed to send. For critical data sources, explicitly design state persistence, acknowledgments, replay, and idempotency.

## 10. Controlling Duplicates and Delivery Guarantees

A `Supplier` can re-emit the same data upon application restart, retry, or multi-instance deployment. Therefore, do not assume each event is emitted strictly once.

Practical measures:

1. Generate a stable event ID from the business source so consumers can detect duplicate messages.
2. Use an outbox or a checkpointed data source if you must ensure events are not lost between updating data and emitting messages.
3. Design idempotent consumers to safely handle redelivered events.
4. Choose an appropriate partition key if ordering per business entity matters.
5. Monitor send errors, retries, broker acknowledgments, and unprocessed message counts.

`Supplier<Flux<T>>` does not create an exactly-once guarantee by itself. It only provides a reactive emission model. Delivery guarantees depend on the binder, broker, producer and consumer settings, transactions, source state persistence, and application idempotency logic.

## 11. Testing Single-Item Suppliers

For `Supplier<T>`, you can test the returned value and verify that each invocation creates an event as expected:

```java
import static org.junit.jupiter.api.Assertions.assertNotNull;

import org.junit.jupiter.api.Test;

class OrderEventSourcesTest {

    @Test
    void createsAnOrderEvent() {
        OrderEventSources sources = new OrderEventSources();
        OrderCreated event = sources.orderEventSupplier().get();

        assertNotNull(event.orderId());
        assertNotNull(event.createdAt());
    }
}
```

If the supplier needs to call a repository or external service, inject dependencies via constructor or bean method parameters and mock them in unit tests. Testing event-creation logic in isolation helps pinpoint producer bugs without starting a broker.

## 12. Testing Flux-Returning Suppliers

For finite publishers, Reactor Test provides `StepVerifier` to verify the sequence of elements and completion signal:

```java
import java.time.Duration;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class MetricEventSourcesTest {

    @Test
    void emitsThreeValuesAndCompletes() {
        StepVerifier.create(Flux.just(1L, 2L, 3L))
                .expectNext(1L, 2L, 3L)
                .verifyComplete();
    }

    @Test
    void emitsPeriodicValues() {
        StepVerifier.withVirtualTime(() -> Flux.interval(Duration.ofSeconds(2)))
                .thenAwait(Duration.ofSeconds(6))
                .expectNext(0L, 1L, 2L)
                .thenCancel()
                .verify();
    }
}
```

The second example uses virtual time to test a time-based publisher without waiting six real seconds. In complete test code, import `Flux` and the corresponding Reactor Test types. For infinite sources, always cancel the subscription in tests to avoid leaking schedulers or resources.

Spring Cloud Stream's Test Binder can verify output messages emitted through bindings. Integration tests with Kafka, RabbitMQ, or Pulsar remain essential to validate serialization, producer throughput, behavior under slow brokers, and error recovery.

## 13. Choosing the Supplier Type for Real-World Problems

| Need | Suitable Type | Reason |
| --- | --- | --- |
| Read one status record per minute from a repository | `Supplier<StatusSnapshot>` | Poller controls the invocation interval and produces one object per call. |
| Emit data continuously from a timer | `Supplier<Flux<MetricSample>>` | `Flux.interval` manages the publisher's emission cadence. |
| Emit a known list of events and finish | `Supplier<Flux<Event>>` | `Flux.fromIterable` emits multiple items and completes. |
| Receive callbacks from an async API | `Supplier<Flux<Event>>` or an appropriate reactive adapter | Can bridge callback sources into a publisher, though buffering and lifecycle must be defined. |
| Read one record per poll to limit source load | `Supplier<Record>` | Each call can read a single unit of data and update checkpoints accordingly. |

Do not choose `Flux` simply because it looks more modern. If the data source is essentially a synchronous operation returning one object periodically, `Supplier<T>` is simpler and easier to control. Conversely, if the source is naturally an asynchronous event stream, `Supplier<Flux<T>>` models emission directly.

## 14. Production Deployment Checklist

Before taking a `Supplier` to production, verify:

- Which bean is selected via `spring.cloud.function.definition`.
- That the output binding `<function>-out-0` has the exact destination and content type.
- If using `Supplier<T>`, that the poller has an appropriate cadence and message limit.
- If using `Supplier<Flux<T>>`, whether the publisher is cold or hot, finite or infinite, and what manages subscription lifecycle.
- That emission rate, concurrency, and buffers are bounded.
- That source errors, conversion errors, and send errors are observed and handled under a clear policy.
- That events have stable IDs or appropriate deduplication mechanisms.
- That unit tests, Test Binder tests, and integration tests cover critical behavior.

## Conclusion

`Supplier<T>` produces one value per poller invocation; its emission cadence is controlled by poller configuration. `Supplier<Flux<T>>` returns a publisher and Spring subscribes to receive multiple elements; its emission cadence lives in the Reactor source and operators rather than the poller. Both create the `<function>-out-0` output binding. When choosing between them, base your decision on the nature of the data source, publisher lifecycle, backpressure, error handling, and system delivery requirements.
