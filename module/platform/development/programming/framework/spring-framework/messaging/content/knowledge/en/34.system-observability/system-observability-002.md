# Distinguishing Broker, Queue, and Business Processing Latency

> Scope: accurately measuring each stage in the message lifecycle, distinguishing send time to the broker, queue wait time, and consumer business processing time; applicable to Spring Framework, Spring Integration, JMS, Spring AMQP, and RSocket architectures.

## 1. Objectives

After this lesson, you can:

- Define the start and end boundaries of each type of latency.
- Distinguish broker publish latency, broker queue residence, local queue wait, consumer processing, and end-to-end latency.
- Read queue depth, oldest message age, consumer lag, throughput, and in-flight messages together.
- Use Micrometer Observation, metrics, and distributed tracing in Spring.
- Understand built-in observations in Spring JMS, Spring AMQP, and Spring Integration.
- Instrument business processing yourself without accidentally including queue wait time in business duration.
- Isolate bottlenecks using p50/p95/p99, arrival/completion rates, and per-message traces.

## 2. What Stages Does a Message Pass Through?

In an asynchronous messaging system, a message typically goes through these steps:

1. Producer creates the message and calls the send API.
2. Client library serializes the message and sends it to the broker.
3. Broker confirms or rejects the publish according to protocol semantics and configuration.
4. Broker routes and stores the message in a queue or log.
5. Consumer receives the message when capacity and delivery conditions allow.
6. The message may sit in an internal application queue or executor before the handler starts.
7. Handler runs business logic, potentially calling databases or other services.
8. Consumer ACKs/commits or returns a result; broker updates delivery state.

Each step can have its own latency. A chart showing only `message duration = 2 seconds` is not enough to tell whether those two seconds were spent in the producer, broker, queue, consumer, or database.

### 2.1. Durations to separate

| Metric | Start point | End point | What does it tell you? |
| --- | --- | --- | --- |
| Producer send duration | Application calls send/publish | Send API completes or publisher confirm is received | How long the client and publish path to the broker take per API semantics |
| Broker queue residence | Broker receives/enqueues message | Broker delivers message to consumer | How long the message stays in the broker before delivery |
| Local queue wait | Application enqueues into channel/executor | Worker dequeues message | Wait time in the service's internal queue |
| Consumer delivery-to-handler delay | Client receives delivery | Handler begins processing | Dispatch, decode, scheduling, and pre-handler steps |
| Business processing duration | Handler starts business logic | Business logic succeeds or fails | Actual processing time inside the application |
| ACK/commit duration | Handler finishes | ACK/commit is sent and completes per API | Time to finalize delivery after processing |
| End-to-end age | Producer creates message | Business outcome completes | Overall age of the message or command |

Terminology may differ across brokers and libraries. Document boundaries clearly in dashboards and metric documentation. `send()` completing does not necessarily mean the consumer has processed the message; publisher confirm, transaction commit, and consumer ACK are distinct events.

### 2.2. Decomposition formula

For a simple sequential flow, you can model it as:

```text
End-to-end latency
  = producer preparation and publish
  + broker residence and delivery
  + consumer-side queue/scheduling
  + business processing
  + acknowledgement or result propagation
```

This is a mental model, not a formula you can always sum directly from histograms. Retries, batching, prefetch, concurrency, and parallel operations can cause intervals to overlap. Accurate decomposition requires measuring spans or timestamps at each boundary.

## 3. Distinguishing Broker Latency and Queue Wait

### 3.1. Producer-to-broker publish duration

This is the time for the producer to send a message to the broker according to client API semantics. This interval may include serialization, network, broker receipt and publish handling, routing, persistence, or waiting for publisher confirms depending on configuration.

A publish timer does not automatically measure how long the message sits in a queue. If the producer API only confirms that bytes were written to a socket or client buffer, that timer does not even prove the broker received the message. Be explicit about whether the application is measuring API return, broker ACK, publisher confirm, or transaction commit.

### 3.2. Broker queue residence / queue wait

Queue residence is the time from when the broker places the message into a queue until the broker delivers it to a consumer. It increases when consumers lack capacity, consumers are stopped, prefetch/in-flight limits are hit, routing sends messages to a queue with no consumers, or the publish rate exceeds the processing rate.

To measure queue residence separately, you need a broker-provided enqueue timestamp or an equivalent broker observability mechanism. A timestamp written into the message by the producer only measures producer-created-to-consumer-received; that interval also includes publish network and delivery network time, so it cannot accurately be called queue wait.

If the broker does not provide reliable enqueue timestamps, track approximations such as oldest ready message age, queue depth, consumer lag, and publish/deliver rates. These metrics help diagnose backlog, though they do not replace a direct latency measurement.

### 3.3. Local queue wait

Many applications have a second queue after the broker delivers a message: a `QueueChannel`, executor, worker pool, scheduler, or internal pipeline queue. This is the time a message waits inside the process.

For example, the broker delivers messages quickly, but the listener hands work to an executor with a long queue. The broker queue may be near zero while local queue wait climbs sharply. If you only look at the broker dashboard, the system looks healthy even though users are waiting a long time.

For an in-process internal queue, you can record `System.nanoTime()` at enqueue and at dequeue to compute duration. Do not use `System.currentTimeMillis()` to measure local duration because the wall-clock can be adjusted.

### 3.4. Business processing duration

Business duration begins when the handler/service actually starts processing the message and ends when business work succeeds or fails. Depending on your definition, decide whether to include database commits, downstream API calls, and result persistence.

Measure critical dependencies separately, such as database queries, downstream HTTP/RPC calls, lock waits, and transaction commits. When business duration is high, child spans in a trace help determine whether the time is spent in CPU code, connection pools, the database, or another service.

## 4. Queue Depth, Queue Age, and Throughput

Do not use queue depth alone as a latency metric. A queue with 10,000 messages where consumers process 20,000 messages/second may drain quickly; a queue with 10 messages where the oldest message has been waiting 20 minutes is a serious sign of trouble.

Track at a minimum:

| Metric | Interpretation | When it spikes abnormally |
| --- | --- | --- |
| Queue depth / messages ready | Messages waiting for delivery | Slow consumers, too few consumers, burst traffic, or misrouting |
| Oldest message age | Age of the message waiting the longest | Starved messages, unprocessed backlog, or stalled consumers |
| In-flight / unacked | Delivered messages not yet ACKed/committed | Slow handlers, large prefetch, hung consumers, or delayed ACKs |
| Publish rate | Messages sent per second | Higher input load or producer retries |
| Delivery/consume rate | Messages delivered or received by consumers per second | Consumer capacity and broker dispatch rate |
| Completion rate | Messages completing business processing per second | Actual effective processing capacity |
| Redelivery/retry rate | Messages redelivered or retried | Processing errors, timeouts, incorrect ACKs, or poison messages |
| Dead-letter rate | Messages moved to DLQ | Unprocessable messages or exhausted retry policy |
| Queue capacity remaining | Remaining queue capacity | Near 0 risks backpressure or rejecting/blocking producers |

### 4.1. Arrival rate and service rate

Let `λ` be the rate of messages arriving at the queue and `μ` be the rate at which consumers complete processing. If `λ` consistently exceeds `μ`, backlog grows. Increasing the number of consumers only helps if the bottleneck is consumer capacity and downstream dependencies still have headroom.

Little's Law for a stable system:

```text
L = λ × W
```

Where `L` is the average number of items in the system, `λ` is the average throughput, and `W` is the average time an item spends in the system. It can be used as a sanity check for queue/latency figures in steady state. Do not apply it mechanically while backlog is growing, workloads are bursting heavily, or figures come from mismatched boundaries.

### 4.2. Reading metrics together

- Queue depth rising, oldest age rising, consumer completion rate dropping: suspect slow consumers or downstream dependencies.
- Queue depth rising while handler duration is steady: check consumer count, prefetch, scheduler, consumer capacity, and when messages are dispatched.
- Broker queue low while local queue depth rises: the bottleneck is inside the process after message receipt.
- Publish duration rising while queue remains low: check network, broker overload, disk I/O, confirm latency, or routing.
- Handler duration rising alongside database spans: check queries, locks, connection pools, and transactions.
- Unacked surging while ready queue drops: messages have been delivered, but consumers have not ACKed; check the handler or ACK path.
- Redeliveries and DLQ rising: investigate processing errors, poison messages, retry policies, and idempotency.

## 5. Micrometer Observation in Spring

### 5.1. Observation, metrics, and traces

Spring Boot uses Micrometer Observation to bridge metrics and tracing. An `Observation` describes an operation with start/end boundaries and metadata. `ObservationHandler` implementations can turn it into timers, counters, or spans depending on configuration.

The three pillars complement one another:

- **Metrics:** show trends, percentiles, throughput, error rates, and backlog across the system.
- **Traces:** show the path of a specific message through producer, broker, consumer, and dependencies.
- **Logs:** provide event and error details; they should include trace ID/message ID to correlate the same flow.

Spring Boot auto-configures the Observation infrastructure when suitable observability dependencies are present. You can inject `ObservationRegistry` to instrument custom business logic.

### 5.2. Instrumenting business processing

Example measuring a synchronous processing block:

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
class OrderProcessor {

    private final ObservationRegistry registry;

    OrderProcessor(ObservationRegistry registry) {
        this.registry = registry;
    }

    OrderResult process(OrderMessage message) {
        return Observation.createNotStarted(
                        "orders.business.process", registry)
                .lowCardinalityKeyValue("messaging.destination.name", "orders")
                .lowCardinalityKeyValue("operation", "process")
                .observe(() -> performBusinessWork(message));
    }

    private OrderResult performBusinessWork(OrderMessage message) {
        // Validate, update domain state and commit the business operation.
        return new OrderResult(message.orderId(), "processed");
    }
}
```

The Observation starts right before `performBusinessWork` and ends when that method returns or throws an exception. If the handler includes decoding, queue wait, ACK, and business logic, place the Observation at the exact service boundary so the timer only measures the intended part.

For reactive methods returning `Mono` or `Flux`, do not blindly use `observe(() -> publisher)`: the supplier may return the publisher immediately while actual work only runs on subscription. Use Reactor/Micrometer Observation-compatible instrumentation to preserve context and end the observation when the publisher completes, errors, or is cancelled. Explicitly test cancellation so timers are not left dangling.

### 5.3. Tag cardinality

Use low-cardinality tags for dimensions with small, stable value sets such as operation, result, component, queue group, or message type. Avoid putting `messageId`, `correlationId`, user ID, order ID, or raw exception messages into metric tags because each value can create a new time series.

Unique identifiers belong in traces or logs under appropriate data protection policies. Metrics must be kept at a manageable cardinality.

## 6. Built-in Instrumentation in the Spring Ecosystem

### 6.1. Spring Framework and JMS

Spring Framework uses Micrometer's Jakarta JMS instrumentation when the `io.micrometer:micrometer-jakarta9` dependency is on the classpath. The main observations include:

| Observation | What interval does it measure? |
| --- | --- |
| `jms.message.publish` | Time to send a JMS message to a destination/broker, typically via `JmsTemplate` |
| `jms.message.process` | Time for the application to process a received message, typically via `MessageListener` or `@JmsListener` |

Spring Framework does not currently create a `jms.message.receive` observation for message receive wait time. Therefore, `jms.message.process` does not measure how long the message sat in the broker queue. To measure queue wait, you need broker metrics or enqueue/delivery timestamps with well-defined boundaries.

These observations can also carry correlation ID, destination name, and message ID into traces by convention. High-cardinality identifiers belong in traces and should not be turned into metric labels.

### 6.2. Spring AMQP and RabbitMQ

Spring AMQP supports Micrometer Observation for `RabbitTemplate` and listener containers. Enable `observationEnabled` on the template and the appropriate container or container factory; for annotated listeners, configure it on the factory. When Observation is enabled, legacy Micrometer timers are managed through the corresponding observation to avoid recording the same operation twice.

Common observations:

- `spring.rabbit.template`: send operations via `RabbitTemplate`.
- `spring.rabbit.listener`: message processing in Rabbit listeners.
- `spring.rabbit.stream.template` and `spring.rabbit.stream.listener`: corresponding operations with the Rabbit Stream API.

Listener observations include queue and listener ID information; template observations include exchange, routing key, and template name per convention. These observations measure time at the client/template or listener boundary. They do not replace RabbitMQ's internal metrics for queue depth, ready/unacked, oldest message age, consumer capacity, or publisher confirms.

### 6.3. Spring Integration

Spring Integration provides metrics for channels, handlers, and sources. Some legacy/standard metrics include:

| Metric | Meaning |
| --- | --- |
| `spring.integration.send` with `type=channel` | Time spent sending through a message channel |
| `spring.integration.send` with `type=handler` | Time spent processing at a message handler |
| `spring.integration.receive` | Number of message receives on a pollable channel or source |
| `spring.integration.channel.queue.size` | Number of messages currently in a `QueueChannel` |
| `spring.integration.channel.queue.remaining.capacity` | Remaining capacity of a `QueueChannel` |

Since Spring Integration 6.0, Observation can provide metrics and tracing for producers, handlers, and gateways. An `ObservationRegistry` and `@EnableIntegrationManagement` are required; `observationPatterns` selects which components to instrument. By default, not every component is automatically instrumented just because a registry exists.

Queue size and remaining capacity metrics are especially helpful for spotting bottlenecks in internal queues. They do not directly measure how long a message has waited; if you need exact local queue wait, add enqueue/dequeue timestamps or instrumentation at the channel boundary.

## 7. Measuring Queue Wait Accurately

### 7.1. In-process internal queues

For a queue within a single JVM, you can measure using a monotonic clock:

```java
record QueuedMessage<T>(T payload, long enqueuedNanos) {}

QueuedMessage<OrderMessage> queued =
        new QueuedMessage<>(message, System.nanoTime());

// At dequeue, immediately before dispatching to the handler:
long queueWaitNanos = System.nanoTime() - queued.enqueuedNanos();
```

Record `queueWaitNanos` into a `message.queue.wait` timer with low-cardinality tags such as channel name and outcome. Do not use message ID as a tag. When enqueue and dequeue happen in different processes, `System.nanoTime()` cannot be compared across machines; you need synchronized wall-clock timestamps or distributed tracing.

### 7.2. Broker queues

For brokers, prefer native broker metrics/APIs:

- Ready and unacked/in-flight message counts.
- Oldest message age or consumer lag.
- Publish, deliver, ACK/commit, and redelivery rates.
- Consumer count, consumer capacity, prefetch, and flow control.
- Disk/memory pressure, connection/channel errors, and throttling.

If you attach a timestamp to the message when the producer publishes, `consumer_received_at - producer_created_at` is producer-to-consumer age. It includes the publish path, broker residence, and delivery path. Only call it broker queue wait when the start timestamp is genuinely the broker enqueue time or when the broker provides an equivalent milestone.

If producer and consumer run on different machines, clocks must be synchronized. Clock skew can produce negative latencies or inaccurate percentiles. For in-process durations, prefer a monotonic clock; for distributed traces, use a tracing SDK and proper clock synchronization.

### 7.3. Consumer processing and ACK

Measure two separate intervals:

1. `consumer.processing`: from when the handler starts until processing logic completes.
2. `consumer.ack`: from when the handler finishes until ACK/commit completes per client semantics.

If the handler performs side effects and then ACK fails, the message may be redelivered. In that case processing time may be low while redeliveries climb. Design handlers to be idempotent and measure retries/duplicates separately.

## 8. Distributed Tracing Across Messaging

A useful trace can have this structure:

```text
HTTP/API request
  └─ producer.publish
       └─ broker publish/confirm
            └─ consumer.receive
                 └─ local.queue.wait
                      └─ business.process
                           ├─ database.query
                           └─ downstream.call
                 └─ consumer.ack
```

This is a suggested span hierarchy; actual spans depend on the libraries and instrumentation in use. When a message passes through a broker, tracing context must be injected into message headers on publish and extracted on consume to create linked spans. Spring Integration provides producer/consumer Observation mechanisms allowing propagators to write trace context into message headers and consumers to restore it.

Use:

- `traceId` to follow the entire flow across multiple services.
- `spanId` to identify each individual stage.
- `correlationId` to link messages belonging to the same business workflow or request/reply.
- `messageId` to identify a specific message and investigate duplicates/redeliveries.

Do not assume `correlationId` equals `traceId`: one business flow can spawn multiple traces, or one trace can contain multiple messages. Define the meaning of each ID explicitly.

## 9. RSocket and the Broker Concept

The RSocket protocol describes a requester and responder communicating over a connection; RSocket itself does not require a message broker or queue broker in between. A service may implement a gateway, router, or intermediary, but that is part of the application architecture.

Therefore, with plain RSocket:

- Do not label the time from requester send to responder as broker latency if there is no broker.
- Measure request round-trip, connection/transport behavior, and handler duration on both ends.
- Measure the local scheduler/executor queue if the server dispatches work through an internal queue.
- If a gateway forwards to a broker or another service, instrument each hop and create clear spans.

RSocket request-response latency is the time from when the client initiates the request until it receives the response; it includes network, server dispatch, processing, and the response path. It does not isolate business duration on its own. Trace or instrument the handler to break it down.

## 10. Dashboards and Alerting

An operational dashboard should have four sections:

1. **Producer/broker:** publish duration p50/p95/p99, publish failures, confirm latency, broker resource pressure.
2. **Queue:** depth/ready, oldest age, unacked, consumer lag, arrival rate, and completion rate.
3. **Consumer:** handler duration p50/p95/p99, active handlers, concurrency, retries, redeliveries, DLQ, and ACK latency.
4. **Business outcome:** end-to-end age, success rate, timeouts, business rejections, and downstream dependency latency.

Alert examples that must be tuned to actual SLOs and load:

- Oldest message age exceeds threshold over several consecutive windows.
- Queue depth rises continuously while completion rate is lower than publish rate.
- Queue remaining capacity nears 0 or broker begins rejecting/blocking publishes.
- Consumer processing p99 exceeds the business latency budget.
- Redelivery/DLQ rate increases abnormally.
- End-to-end latency violates SLO even though publish duration remains normal.

Do not alert solely on a single absolute queue depth point if traffic is cyclical. Use rate-of-change, oldest age, throughput, and SLOs to reduce false positives.

## 11. Incident Analysis Example

Suppose the dashboard shows:

| Metric | Normal | Current |
| --- | ---: | ---: |
| Publish p95 | 15 ms | 18 ms |
| Oldest queue age | 100 ms | 42 s |
| Ready messages | 120 | 48,000 |
| Handler p95 | 35 ms | 38 ms |
| Completion rate | 4,000 msg/s | 1,100 msg/s |

Handler duration is nearly unchanged and publishing is still fast, yet queue age/depth surged and completion rate dropped. The first direction to investigate is consumer capacity, consumer count, prefetch, scheduling, and pre-handler dependencies. Longer business processing time does not explain this data.

Conversely, if queue age is low and queue depth is steady, while handler p99 jumps from 40 ms to 2 s and traces show database spans taking 1.8 s, the bottleneck is in the database or transactions. Increasing consumer count may overload the database further.

If publish p95 spikes sharply, queues have not grown, and broker resource pressure is high, investigate broker disk/network/confirm paths or the producer connection pool. Do not adjust consumer concurrency before identifying the bottleneck.

## 12. Instrumentation and Operations Checklist

- [ ] Every timer has clearly documented start and end points.
- [ ] Publish duration distinguishes API return, broker confirm, and transaction commit.
- [ ] Broker queue residence is measured using reliable enqueue/delivery milestones or broker-native metrics.
- [ ] Producer timestamps are not mislabeled as broker enqueue timestamps.
- [ ] Local queue wait is measured separately from broker queue wait.
- [ ] Business processing starts at the handler/service boundary and excludes queue wait time.
- [ ] ACK/commit latency and redeliveries are observed separately.
- [ ] Queue depth, oldest age, ready/unacked, throughput, and consumer capacity are tracked.
- [ ] p50/p95/p99 and error rate are tracked, not just averages.
- [ ] Trace context is propagated via message headers and restored on the consumer.
- [ ] Metric tags have low cardinality; unique IDs stay in traces/logs when needed.
- [ ] Reactive observations end when the publisher completes/errors/cancels, not at publisher creation.
- [ ] Direct RSocket calls are not labeled as broker latency when no broker exists.
- [ ] Dashboards and alerts are tied to SLOs, backlog age, and processing rates.

## 13. References

- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html): Micrometer Observation, metrics, traces, and context propagation.
- [Spring Framework — Observability Support](https://www.springframework.org/spring/reference/integration/observability.html): JMS publish/process observations and how Spring integrates Micrometer.
- [Spring Integration — Metrics and Management](https://docs.spring.io/spring-integration/reference/metrics.html): send/handler timers, QueueChannel size/capacity gauges, and producer/consumer observations.
- [Spring Integration — QueueChannel](https://springframework.org/spring-integration/reference/7.2/channel/implementations.html): internal queue semantics, capacity, and send/receive behavior.
- [Spring AMQP — Micrometer Observation](https://docs.spring.io/spring-amqp/reference/appendix/micrometer.html): RabbitTemplate/listener observations and metric/span conventions.
- [Spring AMQP — Enabling Micrometer Observation](https://docs.spring.io/spring-amqp/reference/4.2/amqp/receiving-messages/micrometer-observation.html): enabling observation on templates and listener containers.

Metric names and instrumentation behavior may change across versions of Spring Framework, Spring Integration, Spring AMQP, Micrometer, and broker clients. Consult the documentation for the exact dependency version you are running before using metric names in dashboards or alerts.
