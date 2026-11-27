# Evaluating Backpressure Against Actual Binder Capabilities

Backpressure is a mechanism that lets a slow consumer inform a data producer how many additional elements it can accept. In Reactor, this mechanism is expressed as demand via Reactive Streams. However, a Spring Cloud Stream application also includes the broker, binder, listener/polling loop, internal queues, and consumer groups. Demand on a `Flux` does not automatically translate into direct throttling commands to Kafka, RabbitMQ, or Pulsar.

Therefore, evaluating backpressure requires answering two separate questions: does the reactive pipeline in the application propagate and bound demand properly; and which flow-control mechanism in the binder/broker actually engages when downstream slows down? The answers must be grounded in the binder version, active configuration, and measurements under increasing load—not merely on whether the code uses `Flux`.

## 1. Distinguishing Backpressure from Broker Flow Control

In Reactive Streams, a subscriber requests a number of elements via `request(n)`. A publisher may emit at most the number of requested elements. When downstream slows down, demand decreases; upstream can pause emission until new demand arrives.

~~~text
Reactive pipeline in the application

Publisher ---> Operator ---> Subscriber
    ^                            |
    |                            |
    +-------- request(n) --------+
            demand signal
~~~

This is backpressure at the Reactive Streams boundary. Brokers have their own flow-control mechanisms:

- A Kafka consumer actively calls `poll()` to fetch records; record count and poll cadence are influenced by consumer configs, partition assignment, and the poll lifecycle.
- RabbitMQ pushes deliveries to consumers; QoS/prefetch limits how many unacknowledged messages the broker sends to a consumer.
- A Pulsar consumer receives messages via its client; the client uses a receiver queue and flow permits to regulate how many messages are in flight to the consumer.

These mechanisms can limit queued data at the broker/client, but they do not automatically understand `request(1)` from a Reactor subscriber. The binder bridges the two models. You must inspect whether the binder translates demand into pause/resume, prefetch, or permits, or simply places messages into an internal queue.

| Layer | Mechanism to observe | Question |
|---|---|---|
| Reactor | `request(n)`, operator prefetch, queue, overflow | Can downstream throttle upstream? |
| Spring Cloud Stream | Function adapter, channel, executor, and buffer | Are there intermediate queues receiving messages before the function processes them? |
| Binder | Poll, listener container, ack, pause/resume, or flow permits | How does the binder react when the function slows down? |
| Broker | Kafka fetch/partition, Rabbit prefetch/unacked, Pulsar receiver queue/permits | How does the broker limit deliveries and backlog? |
| System | CPU, heap, GC, latency, lag, and throughput | When load exceeds processing capacity, does the system stay stable or grow backlog unboundedly? |

Never conclude "end-to-end backpressure works" just because a function accepts `Flux<T>`. You need evidence that consumer demand reaches a place capable of throttling message retrieval, or that explicit buffer bounds exist at every boundary.

## 2. Reactive Functions in Spring Cloud Stream

Spring Cloud Function supports reactive function types such as `Function<Flux<I>, Flux<O>>`. The function receives a publisher and sets up processing operators. Example:

~~~java
import java.time.Duration;
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import reactor.core.publisher.Flux;

@Configuration
public class OrderReactiveFunctions {

    @Bean
    Function<Flux<OrderEvent>, Flux<OrderEvent>> processOrders() {
        return events -> events
            .map(this::normalize)
            .filter(this::isValid)
            .delayElements(Duration.ofMillis(50));
    }

    private OrderEvent normalize(OrderEvent event) {
        return new OrderEvent(
            event.eventId(),
            event.orderId() == null ? null : event.orderId().trim(),
            event.total()
        );
    }

    private boolean isValid(OrderEvent event) {
        return event.orderId() != null
            && !event.orderId().isBlank()
            && event.total() > 0;
    }

    public record OrderEvent(
        String eventId,
        String orderId,
        long total
    ) {}
}
~~~

In the example, `delayElements` slows down result emission to simulate a slow downstream. The reactive function is invoked to construct the pipeline; elements are processed when the publisher is subscribed to. Do not call `subscribe()` manually inside the function because the framework manages the subscription lifecycle. Do not call `block()` to wait for each message in a production stream.

Input/output binding configuration:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrders

    stream:
      bindings:
        processOrders-in-0:
          destination: orders.raw
          group: order-processor
          content-type: application/json

        processOrders-out-0:
          destination: orders.processed
          content-type: application/json
~~~

This is an example of a reactive function with output. If `Consumer<Flux<T>>` is used, the function has no output binding; if `Function<Flux<T>, Flux<R>>` is used, results go to the output binding. Pick the right function signature for your testing objective.

### Tracking Demand in the Pipeline

You can observe demand and when an element passes through:

~~~java
return events
    .doOnRequest(n ->
        log.debug("Reactive downstream requested {} events", n))
    .doOnNext(event ->
        log.debug("Processing eventId={}", event.eventId()))
    .limitRate(64)
    .map(this::normalize);
~~~

`doOnRequest` reports how many elements the subscriber/operator requests at that observation boundary. `limitRate(64)` splits requests into smaller chunks to regulate demand sent to the preceding publisher. This is a Reactive Streams throttling tool; it does not automatically configure Kafka poll, Rabbit prefetch, or Pulsar permits unless the binder connects those mechanisms to demand.

Set demand logs to DEBUG or use aggregated metrics. Do not create metrics with an event ID label because cardinality will grow with every message.

## 3. Operators That Can Alter Backpressure

A pipeline may support demand at the input yet create large buffers in the middle. Understand each operator's behavior:

| Operator | Impact | What to evaluate |
|---|---|---|
| `map` | Synchronously transforms one element | Generally preserves stream demand |
| `filter` | Drops elements not matching condition | May need to read more elements to satisfy output demand |
| `concatMap` | Processes inner publishers sequentially | Preserves order, but speed is bounded by slow elements |
| `flatMap` | Runs multiple inner publishers concurrently | Increases throughput; bound concurrency and prefetch |
| `flatMapSequential` | Processes concurrently but emits in source order | May have to buffer early-completing results |
| `publishOn` | Shifts processing to another scheduler | Introduces a queue and prefetch at the scheduler boundary |
| `limitRate` | Splits upstream requests into smaller chunks | Does not guarantee broker throttling if adapter does not propagate demand |
| `onBackpressureBuffer` | Holds elements when downstream cannot keep up | Requires capacity bounds and an overflow policy |
| `onBackpressureDrop` | Drops elements when there is no demand | Suitable only for data that can be lost |
| `onBackpressureLatest` | Keeps only the latest value | Fits snapshots/state, not events requiring full processing |
| `onBackpressureError` | Emits error when demand cannot be met | Requires defining retry, DLQ, or pipeline stop behavior |

Example of a bounded buffer:

~~~java
import reactor.core.publisher.BufferOverflowStrategy;

return events
    .onBackpressureBuffer(
        500,
        dropped -> log.error(
            "Backpressure buffer overflow for eventId={}",
            dropped.eventId()
        ),
        BufferOverflowStrategy.ERROR
    )
    .map(this::normalize);
~~~

When the buffer reaches its limit, the pipeline emits an error instead of continuing to grow memory unboundedly. Depending on operator placement and the source publisher, `onBackpressureBuffer` may request unboundedly from upstream and buffer internally. That means it can absorb upstream pressure into a buffer rather than propagating backpressure intact to the source. Treat it as a bounding and overflow policy, not proof of broker flow control.

For telemetry data that can tolerate loss, `onBackpressureDrop` may fit if you expose a counter for dropped elements. For state where only the latest value matters, `onBackpressureLatest` can be useful. For orders, payments, or audit events, drop/latest are generally unacceptable; use durable buffering, retries, broker retention, and controlled recovery.

## 4. Kafka Binder: Poll, Partitions, and Fetch Limits

A Kafka consumer uses a pull model: the consumer calls `poll()` to fetch records from assigned partitions. Properties such as `max.poll.records` limit the number of records returned in one poll. `fetch.min.bytes` and `fetch.max.wait.ms` affect how the broker batches data before returning a fetch response.

Example configuration limiting records per poll:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrders-in-0:
          consumer:
            concurrency: 2

      kafka:
        bindings:
          processOrders-in-0:
            consumer:
              configuration:
                max.poll.records: 100
                fetch.max.wait.ms: 500
~~~

`max.poll.records` limits the records returned by a single Kafka consumer poll; it is not a limit on the total number of messages existing inside the binder, Reactor, or application. `concurrency` creates multiple consumer threads per binding. With Kafka, the number of consumers that can do useful work in a group is bounded by the number of assigned partitions.

When evaluating load, monitor:

- Consumer lag by topic-partition and group.
- Records per poll, batch processing duration, and time between polls.
- Rebalance counts and duration consumers spend without partitions.
- Heap, GC, and number of messages queued inside the application.
- Per-event processing latency and error/retry rates.

If downstream is slow, Kafka lag can grow even when the application does not accumulate the entire backlog on the heap. That backlog is stored durably in the broker. Still, already-polled batches and intermediate queues consume memory. Measure in-flight message counts and actual batch sizes.

Do not increase `max.poll.records` merely to improve throughput if batch processing exceeds `max.poll.interval.ms` or drives memory too high. Likewise, do not increase concurrency when partition count is insufficient or downstream services are already overloaded. Broker throttling and Reactor throttling are two separate layers; check your binder version to confirm pause/resume or specific adapter mechanics before claiming reactive demand reaches the Kafka poll loop.

## 5. RabbitMQ Binder: Prefetch and Unacknowledged Messages

RabbitMQ typically pushes messages to consumers. QoS/prefetch limits how many unacknowledged deliveries a consumer can hold. When a consumer processes slowly and hits the prefetch limit, the broker stops sending additional deliveries to that consumer until acknowledgements free up capacity.

Example:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrders-in-0:
          destination: orders.raw
          group: order-processor

      rabbit:
        bindings:
          processOrders-in-0:
            consumer:
              prefetch: 50
~~~

`prefetch` is the unacknowledged delivery limit configured on the binder's consumer/channel. A useful value depends on message size, processing time, concurrency, and consumer count. Too low a prefetch can reduce throughput because consumers frequently wait on the broker; too high can increase in-flight messages, memory usage, and how long a message sits inside the consumer.

During testing, monitor:

- Ready messages in the queue.
- Unacknowledged messages.
- Consumer utilization and ack rate.
- Queue depth and oldest message age.
- Redeliveries, retries, and DLQ counts.
- Consumer count, concurrency, and effective prefetch.

Prefetch limits unacknowledged deliveries on the RabbitMQ side. It does not by itself prove that every Reactor queue in the application has a corresponding bound. If the binder receives deliveries and pushes them into an internal queue, measure both that queue and heap usage. Read the documentation for your exact Rabbit binder version to confirm the relationship between the listener container, acknowledgement, and reactive functions.

## 6. Pulsar Binder: Receiver Queue and Flow Permits

A Pulsar consumer uses permit-based flow control. The client maintains a receiver queue to hold received messages before the application processes them. As the queue is consumed, the client issues additional permits to receive new messages. Receiver queue size affects how much data can sit pre-buffered in the client.

Illustrative example configuring an extended consumer property:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrders-in-0:
          destination: orders.raw
          group: order-processor

      pulsar:
        bindings:
          processOrders-in-0:
            consumer:
              receiverQueueSize: 100
~~~

Property names and mappings can vary across Spring Cloud Stream Pulsar binder and Pulsar client versions. Verify the configuration schema for the exact version in use before deploying. Do not infer default values or semantics solely from YAML examples.

When evaluating, measure:

- Subscription backlog and pending message count.
- Effective receiver queue size.
- Permit/delivery rate and acknowledgement rate.
- Number of consumers attached to the subscription.
- Subscription type: Exclusive, Failover, Shared, or Key_Shared.
- Redelivery, negative acknowledgement, and ack timeout.
- Client memory and message processing time.

Receiver queues and permits are Pulsar client flow control. They do not automatically prove that `Flux` demand propagates back to the broker. Check whether the binder includes any reactive adapter and how that adapter throttles the consumer. Especially when using Shared or Key_Shared, verify distribution, per-key ordering, and how many messages each consumer holds.

## 7. Comparing Practical Capabilities by Binder

| Binder | Key broker mechanism | Parameters often measured/tuned | Limits to note |
|---|---|---|---|
| Kafka | Pull via poll, per-partition fetch | `max.poll.records`, fetch settings, concurrency, partition count | Poll batch and lag; do not assume Reactor demand drives poll |
| RabbitMQ | Push delivery, QoS/prefetch, ack | `prefetch`, concurrency, ack mode | Prefetch limits unacked deliveries, but internal queues still need measuring |
| Pulsar | Receiver queue and flow permits | `receiverQueueSize`, subscription type, ack/redelivery settings | Client queue/permits do not imply end-to-end Reactive Streams demand |

There is no single prefetch or concurrency number that fits every binder. Message size, processing duration, partition/consumer counts, instance counts, network latency, and dependent service limits all influence the outcome.

Build a capability matrix for the exact version you run:

| Evaluation question | Evidence to gather |
|---|---|
| Does the function accept `Flux<T>`? | Function type and startup logs |
| Does the binder propagate demand to the consumer? | Version docs, adapter code/metrics, or a controlled test |
| Where are internal buffers located? | Channel/executor/listener config and queue/heap metrics |
| Is the number of in-flight messages bounded? | Poll batch, prefetch, receiver queue, concurrency |
| When downstream stops consuming, what does the broker do? | Lag/backlog grows, deliveries pause, permits stop being issued, or unacked queue hits limit |
| When buffers fill up, what happens? | Overflow error, drop, retry, redelivery, or heap growth |
| When are messages acked/committed? | Ack mode, offset commit, transactions, and empirical logs |
| How does recovery work after a restart? | Replay, redelivery, duplicates, and idempotency tests |

## 8. Measuring Ingress Rate, Processing Rate, and Backlog

Backpressure is only meaningful when you know the ingress rate and processing capacity. Let:

- `λ` (lambda): message arrival rate, in messages/second.
- `μ` (mu): sustained processing capacity, in messages/second.
- `B`: pending backlog awaiting processing.

If `λ < μ` for long enough, the system can catch up. If `λ > μ` persists, backlog grows roughly according to `λ - μ`, unless the broker or source throttles, data is dropped, or producers slow down.

For example, if a sequential consumer takes an average of 100 ms per message, theoretical capacity is roughly 10 messages/second before overhead. With four independent tasks running concurrently and downstream able to handle the load, capacity may increase nearly fourfold; in practice it also depends on CPU, I/O, locks, partitions, and API limits.

Measure at least the following metrics:

| Metric | Purpose |
|---|---|
| Ingress rate | Determine how fast producers push data in |
| Completion rate | Measure successful processing rate |
| Processing latency | Identify which step is slow |
| Backlog/lag | Measure pending work |
| In-flight/unacked | Measure delivered but unfinished messages |
| Buffer occupancy | Detect internal queues nearing capacity |
| Overflow/drop count | Identify lost data or failing pipelines |
| Heap/GC | Detect buffers creating memory pressure |
| Retry/redelivery | Identify errors causing repeated work |

Do not look only at average throughput. Use p95/p99 latency, backlog over time, and oldest message age to catch growing queues even when average throughput appears steady.

## 9. Designing a Controlled Backpressure Test

The test should generate load exceeding processing capacity for a period of time, then observe where backlog forms.

### Step 1: Establish Baseline

- Run one broker and one consumer instance.
- Send messages slower than expected processing capacity.
- Record ingress rate, completion rate, latency, lag/backlog, and heap.
- Confirm no unexpected serialization errors, retries, or redeliveries occur.

### Step 2: Slow Down Downstream

Temporarily slow down the function with a controlled delay:

~~~java
@Bean
Function<Flux<OrderEvent>, Flux<OrderEvent>> slowProcessor() {
    return events -> events
        .doOnRequest(n -> log.debug("requested={}", n))
        .concatMap(event ->
            Mono.delay(Duration.ofMillis(100))
                .thenReturn(event)
        );
}
~~~

The snippet requires importing `reactor.core.publisher.Mono`, `reactor.core.publisher.Flux`, `java.time.Duration`, and `java.util.function.Function`. Using `concatMap` enforces sequential processing; with a 100 ms delay, a single subscription theoretically processes roughly 10 messages/second.

### Step 3: Ramp Up Load in Steps

Increase producer rate step by step—for example 5, 10, 20, 50, and 100 messages/second. Hold each step long enough for backlog and latency to show either a steady trend or steady growth. Do not jump straight to maximum load, as that makes it hard to identify the instability threshold.

### Step 4: Observe Every Layer

- Reactor: demand, operator prefetch, buffer occupancy, and overflow.
- Application: heap, GC, active tasks, threads, and latency.
- Binder: poll batch, listener concurrency, prefetch, or receiver queue.
- Broker: Kafka lag, Rabbit ready/unacked, Pulsar subscription backlog.
- Business: completed events, duplicates, drops, and errors.

### Step 5: Reduce Load and Test Recovery

Lower producer rate below consumer capacity. Backlog should gradually drain and latency should return to normal. Then restart a consumer while backlog remains to verify messages resume, redeliver, or replay according to configured semantics.

## 10. Interpreting Test Results

| Observation | Possible interpretation | What to inspect |
|---|---|---|
| Reactor demand drops, Kafka lag rises, heap stays steady | Broker holds most of the backlog; consumer pulls no faster than it can process | Poll cadence, batch, and partitions |
| Reactor demand drops but Rabbit unacked climbs to prefetch | Broker has delivered up to the allowed message limit | Ack timing, listener/binder buffers |
| Pulsar receiver queue fills up and permits are issued slowly | Client is throttling incoming messages | Receiver queue, ack, and subscription type |
| Heap climbs steadily when ingress exceeds completion | An internal buffer or queue is growing | Find unbounded queues, operator prefetch, executors |
| Backlog does not grow but drop counter rises | A drop policy is discarding data | Verify whether data loss is permitted |
| Latency spikes before backlog grows | Consumer or dependency is starting to saturate | CPU, I/O, connection pools, concurrency |
| Restart causes messages to be reprocessed | Ack/commit incomplete or offset not persisted | Idempotency and transaction boundaries |
| Raising concurrency does not raise throughput | Bottleneck lies in partitions, CPU, or dependencies | Partition count, downstream rate limits, and locks |

A passing test does not necessarily keep backlog at 0. In event-driven systems, the broker is usually the durable backlog store when producers outpace consumers. The goal is controlled backlog growth, bounded application memory, no out-of-policy message loss, and the ability to catch up once load subsides.

## 11. Choosing a Policy When Downstream Cannot Keep Up

There are four common choices. Each carries different business consequences:

| Policy | When appropriate | Risk |
|---|---|---|
| Throttle source/consumer | Producer or broker delivery can be slowed down | Increases latency; backlog sits at broker or source |
| Bounded buffer | Need to absorb short bursts | Must have an overflow policy when full |
| Drop/latest | Telemetry or snapshot data allowed to be lost | Unsuitable for business events requiring completeness |
| Fail/retry/persist | Critical events needing reprocessing | Can grow backlog, cause retry storms, or redelivery |

Do not use an unbounded buffer to hide insufficient consumer capacity. A buffer only relocates backlog and can grow heap until the application hits OOM. For critical events, favor broker retention, observable consumer lag, bounded retries, and idempotency.

When using `onBackpressureBuffer`, set a limit and define full-buffer behavior. When using drop, maintain counters and alerts. When failing, ensure errors enter a proper recovery mechanism and do not turn into false success. When slowing producers, establish who is responsible for throttling and how to handle producers that cannot pause.

## 12. Testing with StepVerifier and Test Binder

Reactor unit tests can verify that a pipeline respects demand at the publisher level:

~~~java
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class BackpressurePipelineTest {

    @Test
    void emitsOnlyWhenTheSubscriberRequests() {
        Flux<Integer> source = Flux.range(1, 5);

        StepVerifier.create(source, 0)
            .thenRequest(2)
            .expectNext(1, 2)
            .thenRequest(1)
            .expectNext(3)
            .thenRequest(2)
            .expectNext(4, 5)
            .verifyComplete();
    }
}
~~~

This test proves the Reactor publisher emits according to demand. It does not prove the binder converts `request(n)` into Kafka pause, Rabbit prefetch, or Pulsar permits.

Spring Cloud Stream's Test Binder helps verify functions and bindings within the application. However, the Test Binder does not fully simulate real broker flow control. Write dedicated integration tests per binder:

- Kafka: create a multi-partition topic, slow down the consumer, and observe lag, poll batches, rebalances, and heap.
- RabbitMQ: set finite prefetch, slow down the handler, and observe ready/unacked counts and acknowledgements.
- Pulsar: set an appropriate receiver queue, slow down the handler, and observe backlog, permits, acks, and subscription type.

In integration tests, record the versions of Spring Cloud Stream, binder, broker, configuration, and observed results. When upgrading versions, re-run the tests because adapters, listener containers, and binder properties may change.

## 13. Pre-Deployment Binder Evaluation Checklist

| Item | Required evidence |
|---|---|
| Reactive API | Function uses proper `Flux`/`Mono` types without manual subscribe/block |
| Demand propagation | Evidence that the binder propagates demand or clear documentation of unsupported boundaries |
| Internal buffering | Knowledge of where queues, executors, and prefetch reside |
| Buffer bounds | Size limits and overflow policy are defined |
| Broker flow control | Poll, prefetch, or receiver queue/permits configured and measured |
| In-flight limit | Known limit on messages processed or awaiting ack concurrently |
| Ack/commit | Clear definition of when messages are acknowledged |
| Failure recovery | Retries, redelivery, DLQ/quarantine, and replay tested |
| Data integrity | Critical events not dropped; consumer is idempotent |
| Observability | Ingress/completion rate, latency, lag/backlog, heap, and overflow tracked |
| Load test | Results captured at baseline, overload, and recovery |
| Version evidence | Recorded versions of Spring Cloud Stream, binder, and broker |

## 14. Practice Sequence and Completion Criteria

Run the same order-processing function across the binders used in your project:

1. Write a reactive function receiving `Flux<OrderEvent>` and returning `Flux<OrderEvent>`.
2. Add `doOnRequest` to observe demand, and use `limitRate` to experiment with splitting requests.
3. Create a slow downstream with a fixed delay.
4. Run baseline and record ingress rate, completion rate, latency, backlog, and heap.
5. For Kafka, vary `max.poll.records`, concurrency, and partition count; observe lag and poll behavior.
6. For RabbitMQ, vary `prefetch`; observe ready/unacked counts and ack rate.
7. For Pulsar, vary receiver queue size; observe backlog, permits, and acks.
8. Test bounded buffering and overflow; confirm the application does not grow heap unboundedly.
9. Test drop/latest only on synthetic data allowed to be lost and measure dropped element counts.
10. Stop the consumer, restart it, and confirm redelivery/replay does not duplicate side effects.
11. Document actual limits for each binder and select configurations from measured results.

You have completed this exercise when you can distinguish Reactive Streams demand from broker flow control; explain where a specific binder throttles; measure in-flight limits and backlog; identify whether buffers are bounded; and demonstrate that the system survives overload and recovers without out-of-policy event loss.

## 15. Official References

- [Spring Cloud Stream Reference](https://docs.spring.io/spring-cloud-stream/reference/index.html) — function, binding, and binder model.
- [Spring Cloud Stream — Reactive programming](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/reactive-programming.html) — using reactive functions in Spring Cloud Stream.
- [Spring Cloud Stream — Kafka binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/overview.html) — Kafka consumer and binder configuration.
- [Apache Kafka — Consumer configs](https://kafka.apache.org/documentation/#consumerconfigs) — poll, fetch, and record limits.
- [Spring Cloud Stream — RabbitMQ binder](https://docs.spring.io/spring-cloud-stream/docs/current/reference/html/spring-cloud-stream-binder-rabbit.html) — prefetch, concurrency, and consumer properties.
- [RabbitMQ — Consumer prefetch](https://www.rabbitmq.com/docs/confirms#channel-qos-prefetch) — QoS and unacknowledged delivery limits.
- [Spring Cloud Stream — Pulsar binder](https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html) — Pulsar binder consumer properties.
- [Apache Pulsar — Messaging](https://pulsar.apache.org/docs/concepts-messaging/) — consumers, subscriptions, and flow control.
- [Reactive Streams Specification](https://www.reactive-streams.org/) — demand and backpressure protocol.
- [Project Reactor — Backpressure](https://projectreactor.io/docs/core/release/reference/coreFeatures/backpressure.html) — backpressure operators and strategies.
- [Project Reactor — StepVerifier](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html) — testing demand and publishers.

