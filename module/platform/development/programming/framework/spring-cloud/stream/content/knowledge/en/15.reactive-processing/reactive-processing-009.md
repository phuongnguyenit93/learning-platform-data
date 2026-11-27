# Managing Buffers, Emission Rate, and Concurrency Limits

In event-processing systems, the incoming message rate can exceed the application's processing speed. If producers emit quickly, consumers process slowly, or an external service call stalls, messages accumulate in buffers. Unbounded buffers can cause memory to grow continuously; excessive concurrent tasks can exhaust connection pools, threads, or broker resources. Conversely, overly low limits can leave the system unable to clear its load.

Reactive Streams and Project Reactor provide demand/backpressure mechanisms to coordinate rates between publishers and subscribers. Spring Cloud Stream can connect reactive functions to destinations through binders, yet how far backpressure propagates to the broker depends on the binder, client, and configuration. Therefore, you must design buffering, emission rates, concurrency, and overload policies together.

This lesson focuses on managing those factors in a Spring Cloud Stream application: regulating demand, bounding buffers, batching messages, limiting parallel tasks, handling blocking calls, and observing the system under rising load.

## Learning Objectives

After this lesson, you will be able to:

- Explain demand and backpressure in Reactive Streams.
- Distinguish Reactor buffers, broker client buffers, and message backlogs on the broker.
- Use operators such as `limitRate`, `bufferTimeout`, `onBackpressureBuffer`, and `onBackpressureDrop` deliberately.
- Limit active tasks using `flatMap`, `concatMap`, and concurrency parameters.
- Pace emission rates and avoid producing messages faster than consumption capacity.
- Handle blocking tasks inside a reactive pipeline without blocking event-loop threads.
- Design behavior when buffers fill up, time out, or a processing step fails.
- Test backpressure and monitor queues, lag, latency, and throughput in production.

## 1. What Are Demand and Backpressure?

Reactive Streams defines a protocol between Publisher and Subscriber. A Subscriber receives a Subscription and signals how many elements it is ready to process via `request(n)`. The Publisher should emit at most the requested number of elements. When a subscriber processes slowly, it can slow its requests; a protocol-compliant publisher will not keep pushing unbounded elements downstream.

This is backpressure: demand signals from the consuming side propagate upstream to regulate data flow.

~~~mermaid
sequenceDiagram
    participant S as Subscriber
    participant P as Publisher
    S->>P: subscribe()
    S->>P: request(10)
    P-->>S: onNext(item 1..10)
    Note over S: Processing 10 elements
    S->>P: request(5)
    P-->>S: onNext(item 11..15)
    Note over S,P: Demand is regulated by processing capacity
~~~

In a reactive pipeline:

- The Publisher produces data.
- Intermediate operators transform, group, or regulate data.
- The Subscriber receives and processes data.
- Demand determines how many elements may be emitted next.
- The backpressure strategy determines behavior when a source cannot or will not honor demand.

Backpressure helps control how much work flows through the pipeline. It does not automatically guarantee that messages are never lost, never processed twice, or retained indefinitely. Those guarantees also depend on the broker, acknowledgements, offsets, retries, retention, and application design.

## 2. Distinguishing Buffer Layers

A Spring Cloud Stream system can contain multiple independent buffers. Identify which buffer is growing before tuning configuration.

| Layer | Location | Example | Overload signs |
|---|---|---|---|
| Reactor operator buffer | Inside the application pipeline | `buffer(100)`, `onBackpressureBuffer(500)` | Heap grows, operator queue grows |
| Scheduler queue | Inside Reactor thread pools | `publishOn`, `boundedElastic` | Long task waits, scheduler queue grows |
| Binder/client buffer | Inside the broker client library | Kafka producer buffer, client pending sends | Send latency rises, client queue fills |
| Broker backlog | On Kafka/RabbitMQ/Pulsar | Kafka consumer lag, RabbitMQ ready messages, Pulsar backlog | Accumulated messages grow |
| Business queue | Inside application or database | Job queue, outbox | Work waits a long time for processing |

Do not blindly increase every buffer when throughput drops. Larger buffers only delay when overload becomes visible and can increase memory usage, latency, and recovery time. Measure where the bottleneck lies first: is the broker accumulating messages, is the binder falling behind on sends, is the pipeline unable to keep up, or is a dependent service slow?

## 3. Reactive Functions in Spring Cloud Stream

Spring Cloud Stream supports a reactive function model based on Reactor. A reactive function typically receives and returns publishers, for example:

~~~java
Function<Flux<OrderCreated>, Flux<EnrichedOrder>>
~~~

Unlike an imperative function that receives one object per invocation, a reactive function receives an entire stream. The function is constructed into a pipeline and elements flow through it according to demand. Do not assume a reactive function is invoked independently per message like `Function<OrderCreated, EnrichedOrder>`.

Example:

~~~java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import reactor.core.publisher.Flux;

@Configuration
public class ReactiveOrderFunctions {

    @Bean
    Function<Flux<OrderCreated>, Flux<EnrichedOrder>> enrichOrders() {
        return events -> events
            .filter(event -> event.total().signum() > 0)
            .map(event -> new EnrichedOrder(
                event.eventId(),
                event.orderId(),
                event.total(),
                "STANDARD"
            ));
    }
}
~~~

Bindings can be configured by function name:

~~~yaml
spring:
  cloud:
    function:
      definition: enrichOrders
    stream:
      bindings:
        enrichOrders-in-0:
          destination: orders
          group: order-enricher
          contentType: application/json
        enrichOrders-out-0:
          destination: enriched-orders
          contentType: application/json
~~~

This example illustrates the function and binding boundary. Reactive capabilities and how the binder manages subscriptions, acknowledgements, and demand depend on the binder and version. Confirm your binder supports reactive functions before relying on end-to-end backpressure.

### When to Use Imperative vs. Reactive?

| Scenario | Typically suitable choice |
|---|---|
| Independent per-message processing, simple logic | Imperative `Function<T, R>` or `Consumer<T>` |
| Composing multiple asynchronous steps in a stream | Reactive `Function<Flux<T>, Flux<R>>` |
| Need batching or time windowing | Reactive pipeline with `buffer` or `window` |
| Many asynchronous I/O calls | Reactive client with bounded concurrency |
| Blocking dependent libraries | Imperative or isolate blocking calls on an appropriate scheduler |

Reactive does not automatically turn a blocking operation into a non-blocking one. If the pipeline calls blocking JDBC, blocking file I/O, or a synchronous HTTP client, the execution thread remains held throughout the wait.

## 4. Throttling Demand with limitRate

`limitRate(n)` splits upstream requests into smaller batches instead of requesting the entire receivable count at once. It helps control the pace of demand the pipeline sends upstream.

~~~java
Flux<OrderCreated> controlled =
    incoming.limitRate(100);
~~~

With this configuration, the pipeline requests from upstream in bounded batches rather than issuing a huge request upfront. Reactor can prefetch and request more before the entire current batch finishes, so `limitRate` is not a strict cap on total messages sitting across all queues.

You can adjust the low tide to control when Reactor sends replenishment requests:

~~~java
Flux<OrderCreated> controlled =
    incoming.limitRate(100, 25);
~~~

Here, the high tide is 100 and the low tide is 25 per Reactor semantics. When remaining demand drops to the appropriate threshold, Reactor requests additional elements to keep the pipeline fed.

Use `limitRate` when you want to regulate how much demand the pipeline sends upstream. If you need to cap total in-flight work, combine it with concurrency limits and queue bounds at the right layers.

## 5. Managing Buffers When Downstream Processes Slowly

Some sources cannot or do not honor backpressure. When emission speed exceeds consumption capacity, the pipeline needs an explicit policy.

### Bounded Buffers

`onBackpressureBuffer(capacity)` holds elements while downstream has not requested more, up to a maximum capacity:

~~~java
Flux<OrderCreated> buffered =
    incoming.onBackpressureBuffer(
        500,
        item -> log.warn("Buffer overflow: {}", item.eventId())
    );
~~~

If the buffer fills up, Reactor invokes the overflow callback and emits an error signal according to the chosen overload. Handle that error at the appropriate layer; a callback that only logs does not mean the message was durably stored or processed successfully.

Do not use unbounded buffers in systems with uncontrolled ingress rates. When downstream stalls for a long time, memory can grow until the process is impacted.

### Choosing Behavior When the Buffer Is Full

Reactor provides several backpressure strategies:

| Operator | Behavior when downstream falls behind | When appropriate |
|---|---|---|
| `onBackpressureBuffer(capacity)` | Holds elements up to limit; overflow errors or handles per overload | Do not want to drop messages and memory is bounded |
| `onBackpressureDrop()` | Drops elements until downstream has demand | Droppable data such as high-frequency telemetry |
| `onBackpressureLatest()` | Keeps the latest element, dropping older ones as needed | Latest snapshot/state matters more than history |
| `onBackpressureError()` | Emits an error when demand cannot be met | Want fail-fast and outer-layer handling |

Drop/latest strategies lose some data. Never use them for business events such as payments, orders, or inventory changes unless another recovery mechanism exists.

Example using latest for device status data:

~~~java
Flux<DeviceSnapshot> latestSnapshots =
    snapshots.onBackpressureLatest();
~~~

If the goal is retaining all events, use backpressure-capable sources, durable queues, or broker backlogs; never rely on heap buffers as long-term storage.

### Buffering by Size and Time

`buffer(n)` collects `n` elements into a list before emitting a batch:

~~~java
Flux<List<OrderCreated>> batches =
    incoming.buffer(100);
~~~

If the stream has fewer than 100 elements, the last batch may wait a long time. Use `bufferTimeout(maxSize, maxTime)` to emit a batch when either the count or the timeout is reached:

~~~java
Flux<List<OrderCreated>> batches =
    incoming.bufferTimeout(100, Duration.ofSeconds(2));
~~~

This balances throughput and latency: larger batches can reduce database or external service call overhead, but increase wait time and memory usage. Choose `maxSize` and `maxTime` based on payload size, ingress rate, and SLAs.

`window(n)` creates inner `Flux` streams instead of collecting all elements into a `List`. Windows are useful when you want to process each window as an independent stream; ensure each window is properly subscribed to and consumed.

## 6. Limiting Concurrent Tasks

In a reactive pipeline, `flatMap` can run multiple inner publishers simultaneously. The concurrency parameter limits how many inner publishers are subscribed concurrently.

~~~java
Flux<EnrichedOrder> enriched =
    incoming.flatMap(
        this::enrichAsync,
        16,
        1
    );
~~~

In this example:

- Up to 16 calls to `enrichAsync` are processed concurrently.
- The last parameter is the prefetch per inner publisher.
- Results may be emitted in completion order, not necessarily input order.

If you must preserve output order while still allowing concurrent execution, use `flatMapSequential`. If sequential execution is needed, use `concatMap`:

~~~java
Flux<EnrichedOrder> ordered =
    incoming.concatMap(this::enrichAsync);
~~~

Comparison:

| Operator | Concurrency | Output order |
|---|---|---|
| `flatMap(mapper)` | Multiple inner publishers simultaneously | By completion time |
| `flatMap(mapper, concurrency)` | Bounded by concurrency | Input order not guaranteed |
| `flatMapSequential(mapper, concurrency)` | Concurrent execution | Emits results in source order |
| `concatMap(mapper)` | One inner publisher at a time | Preserves source order |

Preserving order can queue results if an early element is slower than later ones. Consequently, `flatMapSequential` may require extra memory when a task stalls. Choose operators by business ordering requirements, not solely by throughput.

### Calculating Overall Concurrency Limits

If each instance runs up to 16 parallel calls and there are 5 instances, the system can generate roughly 80 concurrent calls at that step. If each call holds a database connection, the connection pool must accommodate that or concurrency must be lowered accordingly.

Calculate concurrency across the whole system, not a single pipeline:

- Number of application replicas.
- Concurrency per replica.
- Number of assigned partitions or consumers.
- Connection pools and dependent service limits.
- Thread pools and schedulers.
- Retries that can generate extra calls on errors.

Even small per-instance concurrency can exceed an external service's capacity as replica count scales.

## 7. Pacing Emission Rate

Backpressure regulates demand, whereas rate limiting enforces a time-based rate cap. The two concepts are related but distinct.

- **Demand control:** how many elements a subscriber requests from upstream.
- **Concurrency control:** how many tasks execute at the same time.
- **Rate control:** how many messages or requests are allowed to emit within a time window.
- **Buffer control:** how many elements are held when ingress exceeds egress.

You can slow a source down with `delayElements`:

~~~java
Flux<OrderCreated> paced =
    incoming.delayElements(Duration.ofMillis(20));
~~~

The example enforces a minimum spacing between elements emitted downstream. This is a simple way to illustrate pacing; it does not replace a token bucket or accurate rate limiter across multiple subscribers, replicas, or per-tenant quotas.

To cap requests to external services, use an explicitly configured rate limiter, potentially paired with a concurrency limit. For broker producers, evaluate client and broker limits such as batch size, linger, buffer memory, request quotas, or corresponding flow control.

Do not rely solely on `delayElements` to enforce production quotas. It provides no cluster-wide quota distribution policy and can add significant latency.

## 8. Handling Blocking I/O in a Reactive Pipeline

A reactive pipeline should keep processing threads from being blocked by synchronous calls. If you must call a blocking library, isolate that operation on an appropriate scheduler.

Example:

~~~java
import reactor.core.scheduler.Schedulers;

Mono<CustomerProfile> profile =
    Mono.fromCallable(() -> blockingCustomerClient.load(customerId))
        .subscribeOn(Schedulers.boundedElastic());
~~~

`boundedElastic` fits blocking tasks that wait, with thread count and queue bounded per Reactor configuration. Do not use `Schedulers.parallel()` for blocking I/O; that scheduler is intended for short, CPU-bound computations.

Key operators:

- `subscribeOn` affects the scheduler executing subscription and the upstream source.
- `publishOn` shifts execution of subsequent operators to the selected scheduler.
- `parallel` and `runOn` can split CPU-bound tasks across multiple rails, though rail count and resources must be controlled.

Do not create a new scheduler per message. Reuse appropriate schedulers, configure bounds, and close resources properly with the application lifecycle.

## 9. Combining Buffers, Concurrency, and Rate Control

All three mechanisms should be designed together. For example, a pipeline receiving orders, calling a customer service asynchronously, collecting results, and writing batches:

~~~java
@Bean
Function<Flux<OrderCreated>, Flux<EnrichedOrder>> enrichOrders(
        CustomerClient customerClient) {

    return events -> events
        .limitRate(100, 25)
        .flatMap(event ->
            customerClient.findProfile(event.orderId())
                .map(profile -> new EnrichedOrder(
                    event.eventId(),
                    event.orderId(),
                    event.total(),
                    profile.tier()
                )),
            16,
            1
        )
        .onBackpressureBuffer(
            500,
            item -> log.warn("Overflow for {}", item.orderId())
        );
}
~~~

This snippet illustrates coordinating demand, concurrency, and buffering, though operator order matters greatly. `onBackpressureBuffer` placed after `flatMap` only observes that step's output stream; it does not bound internal queues inside `flatMap`, clients, or the binder. In real designs, place bounds at the exact boundaries where data can accumulate and test overflow behavior.

To write batches, you can chain:

~~~java
events
    .bufferTimeout(100, Duration.ofSeconds(2))
    .concatMap(batch -> repository.saveAll(batch));
~~~

When the repository returns a Publisher, `concatMap` waits for the current batch to finish before sending the next batch. This caps concurrent batch writes and preserves batch order. If the database supports parallel writes and higher throughput is required, you can increase concurrency with a bound.

## 10. End-to-End Backpressure and Binder Limitations

Reactive Streams regulates demand inside the Reactor pipeline, but brokers do not always share the same demand model. Some binders use clients capable of pause/resume or tuning message fetch amounts; others use listener containers, prefetch, acknowledgements, or their own buffers.

Therefore, distinguish:

1. Backpressure between Reactor operators.
2. Binder/client message intake mechanics.
3. Broker flow control.
4. Durable backlog on the broker.

Do not assume downstream pausing requests will cause every broker to stop sending immediately. Clients may have already prefetched messages, listener containers may hold internal queues, and brokers can continue accumulating backlog.

### Kafka

A Kafka consumer reads via polling and manages offsets. The binder may leverage poll, batching, and consumer concurrency of the Kafka client/container. When the application processes slowly, monitor consumer lag, poll interval, partition counts, and consumer counts. Depending on the binder and function model, Reactor backpressure may not translate directly into broker-level demand.

### RabbitMQ

RabbitMQ has prefetch/QoS to bound how many unacknowledged messages a consumer receives at once. Excessively large prefetch increases messages held in the client; too small a value can reduce throughput. Acknowledgements and queue backlog are key metrics when throttling consumers.

### Pulsar

A Pulsar client has its own receiver queue size, subscription type, and flow-control mechanics. Excessively large receiver queues raise consumer-side memory; too small a size can hurt throughput. Check your binder version and client properties to understand how the reactive pipeline relates to messages already pre-received by the client.

In deployment, configure bounds at both the pipeline and binder/client where needed. A Reactor-level limit cannot substitute for broker prefetch, pause/resume, or quotas.

## 11. Error Handling, Retries, and Overflow

When an element errors inside a pipeline, Reactor can terminate the entire stream if the error goes unhandled. Decide which errors can be retried, which must route to another branch, and which should stop the pipeline.

Example of bounded retry:

~~~java
Flux<EnrichedOrder> result =
    incoming.flatMap(
        event -> enrichAsync(event)
            .retryWhen(
                Retry.backoff(3, Duration.ofMillis(200))
                    .maxBackoff(Duration.ofSeconds(2))
            ),
        16
    );
~~~

Retries can cause duplicate side effects if the previous call succeeded on an external service but the response was lost. Data writes or payments require idempotency keys and deduplication safeguards.

For business messages that cannot be lost, overflow should not be handled by dropping. Emit an observable error so the binder/broker applies the configured retry or dead-letter policy. How acknowledgements, retries, and DLQs work in reactive functions depends on the binder and version; test against a real broker before relying on those semantics.

For telemetry that can tolerate loss, `onBackpressureDrop` or `onBackpressureLatest` can fit, provided you count dropped elements and expose metrics. Never silently drop messages without observability.

## 12. Observing and Operating Under Load

To know whether configured limits are right, monitor both throughput and wait times.

| Metric | What to observe |
|---|---|
| Input rate | Incoming messages per second |
| Output rate | Processed messages per second |
| Processing latency | Time from receipt to completion |
| Buffer occupancy | Number of elements currently in buffers |
| Overflow/drop count | Times buffers filled or messages were dropped |
| In-flight tasks | Number of tasks executing concurrently |
| Scheduler queue | Tasks waiting for an execution thread |
| Broker backlog/lag | Messages queued on the broker |
| Error/retry rate | Failure rates and retry counts |
| Heap/GC | Memory pressure from payloads and queues |

If input rate exceeds output rate for an extended period, backlog will grow. Identify whether the system is bottlenecked by CPU, database, external services, partition count, connection pools, or the binder. Raising concurrency helps only when downstream resources still have headroom.

Set alerts for nearly full buffers, steadily rising consumer lag, rising ready queues, backlog above thresholds, latency breaching SLAs, or elevated retry rates. When needed, throttle sources, pause intake, or scale consumers within broker and dependency limits.

## 13. Testing Backpressure and Concurrency

Tests must verify behavior when downstream is slow, not just the happy path.

### StepVerifier

Reactor Test provides StepVerifier to drive demand:

~~~java
@Test
void emitsOnlyRequestedElements() {
    Flux<Integer> source = Flux.range(1, 5);

    StepVerifier.create(source, 0)
        .thenRequest(2)
        .expectNext(1, 2)
        .thenRequest(1)
        .expectNext(3)
        .thenCancel()
        .verify();
}
~~~

This test starts with zero demand, requests two elements, then requests one more. It verifies the publisher honors demand within the pipeline.

### Testing Buffers and Overflow

Create a source faster than downstream, use a bounded buffer, and confirm overflow is observed. For drop/latest, count discarded elements and verify the retained or latest elements match expected semantics.

### Testing Concurrency

Use a counter incremented when a task starts and decremented when it completes. Record the peak value to confirm concurrency never exceeds the configured bound. Avoid relying on overly short fixed timers; use latches or controllable publishers for deterministic results.

### Broker Integration Tests

Use a real broker or Testcontainers to verify:
- Prefetch/receiver queue/consumer polling behave as configured.
- Broker backlog grows when the consumer processes slowly.
- Consumers resume from the proper position after scaling or restarts.
- Retries, acknowledgements, and DLQs neither lose nor duplicate business side effects unexpectedly.
- Increasing load does not push heap or internal queues past limits.

The Test Binder is useful for checking functions and bindings, but it does not replace testing flow control on Kafka, RabbitMQ, or Pulsar.

## 14. Hands-On Workflow

Build a reactive pipeline processing `OrderCreated` events:

1. Declare `Function<Flux<OrderCreated>, Flux<EnrichedOrder>>`.
2. Configure the input binding to read from destination `orders` with a stable group.
3. Use `limitRate` to regulate demand from the pipeline.
4. Use `flatMap` with bounded concurrency when calling the customer service.
5. If batch writes are needed, use `bufferTimeout` with both count and time limits.
6. Bound queues at every boundary where data can accumulate.
7. Choose overflow behavior aligned with data criticality; never drop critical business events.
8. Isolate blocking calls on an appropriate scheduler or replace them with a reactive client.
9. Run StepVerifier to verify demand and overflow.
10. Run broker integration tests, observing backlog, latency, and active task counts.
11. Ramp up input rate in a controlled way to find the saturation point.
12. Tune concurrency, batch size, prefetch, and instance counts based on measured metrics.

Acceptance checklist:

| Item | Result to confirm |
|---|---|
| Reactive function | Accepts/returns publishers with the right signature |
| Demand | Pipeline does not emit beyond demand within Reactive Streams scope |
| Buffer | Explicit capacity limits and overflow behavior defined |
| Batch | Bounded size and wait time configured |
| Concurrency | Never exceeds chosen parallel task limit |
| Rate | Emission rate fits dependent service limits |
| Blocking I/O | Does not block event-loop threads |
| Binder | Prefetch/flow control understood and configured appropriately |
| Recovery | Retries, acknowledgements, and DLQs tested |
| Observability | Metrics exist for lag, buffers, latency, errors, and drops |

## Conclusion

Managing buffers, emission rates, and concurrency limits are three interconnected parts of reactive processing design. Demand/backpressure coordinates speeds between publishers and subscribers; buffers temporarily hold data when downstream slows down; concurrency caps active work; and rate control enforces time-based rate caps.

In Spring Cloud Stream, combine Reactor operators with binder configuration and broker flow control. Place explicit limits on every queue, pick overflow policies based on message criticality, avoid blocking on event loops, and test under load exceeding processing capacity. Backpressure inside the pipeline does not automatically become a broker delivery guarantee; measure backlog, acknowledgements, retries, and DLQs in realistic environments.

