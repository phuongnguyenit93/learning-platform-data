# Optimizing Batching, Prefetch, and Poll Limits

In Spring Cloud Stream, throughput and latency depend on the function, binder, client, and broker together. Producers can group multiple messages into a single send; consumers can prefetch a number of messages ahead of time; the framework can pass a group of records into a function; Kafka also limits how many records each poll returns. These mechanisms reduce overhead, but they also increase memory in use, wait times, and the blast radius of redelivery on errors.

Before tuning, distinguish four concepts:

1. **Producer batching:** grouping multiple messages into a single send or broker request.
2. **Consumer batch delivery:** passing multiple records into a function/listener in one invocation, typically as `List<?>`.
3. **Prefetch/receiver queue:** the number of messages a consumer is permitted to receive ahead of completing application processing or acknowledgement.
4. **Poll limit:** the cap on how many records a single fetch operation can return. Kafka has `max.poll.records`; Spring Integration pollers have their own limit.

These parameters are related, not interchangeable. Raising `max.poll.records` does not automatically enable function batch mode; raising RabbitMQ prefetch does not make the listener receive a `List`; enabling Pulsar producer batching does not mean the function receives a batch object.

## 1. Four mechanisms operate at different layers

| Mechanism | Layer | What is bounded or grouped | Primary impact |
|---|---|---|---|
| Producer batching | Producer/client | Multiple messages into one protocol batch or request | Cuts request overhead; usually improves throughput and compression. |
| Consumer batch mode | Framework/listener | Multiple records in a single function invocation | Reduces framework dispatch calls and enables bulk processing. |
| Prefetch | Broker/consumer protocol | Delivered but unacknowledged messages | Keeps consumers fed; increases data held in consumer memory. |
| Receiver queue | Client consumer | Locally buffered messages before application receives them | Absorbs bursts and reduces round trips; oversized queues increase memory and wait time. |
| Poll limit | Consumer API | Maximum records returned by one poll | Caps per-iteration work size and helps control time between polls. |
| Spring Integration poller | Application scheduler | Messages processed per poller trigger | Controls the cadence of pulling data from a Supplier or pollable source. |

A single flow may use several mechanisms simultaneously. A Kafka producer batches records per partition; a Kafka consumer fetches a group of records per poll; Spring Cloud Stream passes that group into the function when batch mode is enabled. RabbitMQ applies prefetch per consumer and the container can assemble deliveries into batches. Pulsar has producer batching and a client-side receiver queue.

~~~mermaid
flowchart LR
    A[Producer] --> B[Producer batching]
    B --> C[(Broker)]
    C --> D[Prefetch / receiver queue / poll]
    D --> E[Consumer batch delivery]
    E --> F[Function]
    F --> G[ACK or commit]
~~~

## 2. Measure a baseline before increasing batching

Before changing configuration, measure:

- Input and output throughput: messages/second, bytes/second.
- Average and p95/p99 message sizes.
- Processing time for one message and for one batch.
- Latency from publish time to when the function starts processing.
- Consumer lag, queue depth, or subscription backlog.
- CPU, heap, direct memory, GC pauses, and network throughput.
- Retry, redelivery, timeout, and processing error rates.
- Consumer/partition counts, concurrency, and instance counts.

If the consumer already processes faster than messages arrive, increasing prefetch or batch size may bring no benefit. If the producer emits sparse messages, large batches may simply force messages to wait longer. If the function is bottlenecked on a slow database or API, buffering more messages inside the JVM usually just shifts backlog from the broker into the application.

Define your minimum required throughput and maximum business-acceptable latency upfront, including batch accumulation wait time. Tuning balances throughput, latency, memory, and recoverability; there is no universal batch size or prefetch value for every system.

## 3. Producer batching

Producer batching groups multiple messages into one send. Benefits typically come from fewer requests, lower serialization/protocol overhead, and better compression ratios when messages share similar structure.

A batch is typically sent when one of these conditions is met:

- Maximum message count is reached.
- Byte size limit is reached.
- Batch linger/wait timeout expires.
- The producer must flush due to close, error, or another send condition.

At low traffic, batches may not fill and messages wait until the batch timeout expires. At high traffic, batches fill quickly. Larger batch sizes usually reduce send calls but increase data buffered before sending; longer batch delays can improve throughput under light load at the cost of higher latency.

Compression can cut network traffic, but increases producer/consumer CPU. Measure both CPU and network before turning on heavy compression.

## 4. Kafka: producer batching and consumer polling

Kafka has two separate configuration groups:

- Producer: `batch.size`, `linger.ms`, `compression.type`, `buffer.memory`.
- Consumer: `max.poll.records`, `max.poll.interval.ms`, `fetch.min.bytes`, `fetch.max.wait.ms`.

### 4.1. Producer batching configuration

Example output binding configuration:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orders-out-0:
          destination: orders.created
      kafka:
        bindings:
          orders-out-0:
            producer:
              batch-timeout: 5
              configuration:
                batch.size: 65536
                linger.ms: 5
                compression.type: lz4
~~~

- `batch.size` is the target batch byte size per partition. A batch may still be sent before it is full.
- `linger.ms` is how long the producer waits for extra records to batch before sending. Raising this can increase throughput while adding latency.
- `compression.type` selects the compression codec. Measure CPU and network to choose `lz4`, `snappy`, or `zstd` according to client/broker versions.
- `batch-timeout` is a Kafka binder property allowing additional messages to accumulate in a batch.

The Kafka binder also has a `bufferSize` property for the byte limit the producer attempts to accumulate before sending; binder documentation lists a default of 16 KiB. This property and Kafka client producer properties can affect the same send path, so verify the effective configuration when setting both.

Kafka producers build batches per partition. If keys scatter messages across many partitions, per-partition arrival rates may be low and batches rarely fill. Do not set `batch.size` excessively large if per-partition traffic is low; producer memory may stay held longer without throughput gains.

### 4.2. Consumer batch mode

When `batch-mode` is enabled, the Kafka binder passes records received from a single `poll()` into the function as `List<?>`. When batch mode is off, the function is called per record.

~~~java
@Bean
Consumer<List<OrderCreated>> processOrders() {
    return orders -> orderService.processBatch(orders);
}
~~~

~~~yaml
spring:
  cloud:
    function:
      definition: processOrders
    stream:
      bindings:
        processOrders-in-0:
          destination: orders.created
          group: order-processor
          consumer:
            batch-mode: true
      kafka:
        bindings:
          processOrders-in-0:
            consumer:
              configuration:
                max.poll.records: 200
                max.poll.interval.ms: 300000
                fetch.min.bytes: 65536
                fetch.max.wait.ms: 100
~~~

`max.poll.records` caps the maximum records returned from a single poll. Actual returned counts may be lower if the broker lacks enough data, fetch limits apply, or partitions have no ready records.

`fetch.min.bytes` asks the broker to accumulate enough data before returning a response; `fetch.max.wait.ms` limits how long the broker waits to satisfy the fetch condition. Raising `fetch.min.bytes` can cut small responses and improve high-load throughput, while making low-load messages wait longer.

`max.poll.interval.ms` is the maximum allowed interval between `poll()` calls before the consumer is considered stalled and evicted from the group. It is not a per-message timeout. If the function takes too long to process a batch, the consumer can breach this threshold and trigger a rebalance.

### 4.3. Calculating batch processing time

Suppose `max.poll.records = 200`, p95 processing time per record is 20 ms, and records are processed sequentially on one thread:

\[
200 \times 20\text{ ms} = 4\,000\text{ ms}
\]

This is only the estimated business logic time. Add deserialization, database/API calls, offset commits, GC, retries, and other pauses. With long retry/backoff intervals, actual duration can be much higher.

Keep a substantial safety margin between p99 batch processing time and `max.poll.interval.ms`. If that cannot be guaranteed, lower `max.poll.records`, split into smaller batches, optimize the function, or move retries to an appropriate container/error handler.

### 4.4. How batch mode affects retries and ACK

The Kafka binder does not support standard binder-level retries when batch mode is enabled; `maxAttempts` may be overridden to 1. If you need batch retries, configure a batch error handler on the listener container or use manual acknowledgment/nack via the appropriate Spring Kafka API.

When using manual acknowledgment, clearly define which batches succeeded, which offsets are committed, which records require redelivery, and whether the DLQ receives individual records or batches. Batch processing can widen redelivery scope when one item fails; functions should be idempotent and use event IDs to avoid duplicate side effects.

### 4.5. Distinguishing pollTimeout from max.poll.records

The Kafka binder has `pollTimeout` for pollable consumers; binder docs list a default of 5 seconds. That property is the wait timeout of a poll operation on a pollable source. `max.poll.records` caps the records returned from a single Kafka consumer poll.

| Property | Effect |
|---|---|
| `pollTimeout` | Wait timeout when the application uses a pollable consumer. |
| `max.poll.records` | Maximum records returned per Kafka consumer poll. |
| `max.poll.interval.ms` | Maximum time gap allowed between polls to stay in the consumer group. |
| `fetch.max.wait.ms` | Maximum time the broker waits for data to satisfy a fetch request. |

## 5. Spring Integration poller and PollableMessageSource

Spring Cloud Stream uses the Spring Integration poller for a `Supplier` or scheduled polling components. Poller settings are not Kafka consumer poll settings.

~~~yaml
spring:
  integration:
    poller:
      fixed-delay: 500
      max-messages-per-poll: 10
~~~

In this example, the poller triggers every 500 ms and permits up to 10 messages per trigger. Modern Spring Integration poller defaults are 1,000 ms fixed delay and 1 message per poll; verify the Spring Boot/Spring Integration version in use.

With `PollableMessageSource`, the application explicitly calls `poll()` to retrieve a message. Each call receives one message; the application controls call frequency, threads, and loop behavior. Do not use `max-messages-per-poll` expecting it to control Kafka's `max.poll.records`.

Example controlled polling loop:

~~~java
@Bean
ApplicationRunner pollOrders(PollableMessageSource source) {
    return args -> {
        while (!Thread.currentThread().isInterrupted()) {
            boolean received = source.poll(message ->
                orderService.process((OrderCreated) message.getPayload())
            );
            if (!received) {
                Thread.sleep(250);
            }
        }
    };
}
~~~

This is a conceptual example. Production applications must manage worker lifecycle, interruption, exceptions, and acknowledgments; never create an infinite loop without a clean shutdown mechanism.

## 6. RabbitMQ: prefetch and batching

RabbitMQ pushes messages to consumers via deliveries. `prefetch` caps how many unacknowledged messages the broker may deliver to each consumer under QoS.

The Spring Cloud Stream Rabbit binder has a `prefetch` property; current binder defaults set it to 1. This keeps unacked messages low, but can limit throughput when consumers are fast and ACK round trips take noticeable time.

### 6.1. Calculating in-flight messages

If each instance has `C` consumers and each consumer has prefetch `P`, maximum unacked messages per instance is roughly:

\[
N_{\text{in-flight}} \approx C \times P
\]

For example, 4 consumers with prefetch 25:

\[
4 \times 25 = 100\text{ messages}
\]

If messages average 64 KiB, raw held payloads are around 6.25 MiB. Actual memory is higher due to Java objects, headers, byte buffers, batch lists, deserialization, and temporary business-logic data. Multiple instances multiply total in-flight memory by the instance count.

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orders-in-0:
          destination: orders.created
          group: order-processor
      rabbit:
        bindings:
          orders-in-0:
            consumer:
              prefetch: 25
              max-concurrency: 4
~~~

`max-concurrency` limits the container's consumer count. Evaluate prefetch per consumer and concurrency per instance; do not multiply prefetch across instances without tracking memory limits.

### 6.2. Choosing prefetch based on processing time

Too low a prefetch forces consumers to wait for the broker to deliver new messages after every ACK, reducing throughput when network round trips matter. Too high a prefetch holds many messages in the JVM, can starve other consumers by piling messages onto one consumer, increases redeliveries on consumer crash, and worsens p95/p99 latency.

Increase prefetch in small increments while watching throughput, unacked counts, memory, redeliveries, and load distribution across consumers. If the function takes long to process each message or payloads are large, keep prefetch lower.

### 6.3. Producer-side batching

The Rabbit binder can batch multiple messages at the producer into a single batch message. Main properties:

| Property | Meaning | Default in binder docs |
|---|---|---:|
| `batching-enabled` | Enables producer-side batching. | `false` |
| `batch-size` | Target message count in the buffer. | `100` |
| `batch-buffer-limit` | Buffer limit when batching is enabled. | `10000` |
| `batch-timeout` | Maximum wait time to form a batch. | `5000` ms |

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orders-out-0:
          destination: orders.created
      rabbit:
        bindings:
          orders-out-0:
            producer:
              batching-enabled: true
              batch-size: 100
              batch-buffer-limit: 2000
              batch-timeout: 25
~~~

The 25 ms timeout in the example is an illustrative choice to reduce waiting compared to the 5-second default; measure with real traffic. Rabbit binder producer batching packs messages into an AMQP-level batch. By default, the consumer can de-batch and invoke the listener per item; to receive a `List`, configure consumer batch mode appropriately.

### 6.4. Consumer-side batching

The Rabbit binder supports grouping multiple individual deliveries into a single consumer batch:

~~~java
@Bean
Consumer<List<OrderCreated>> processOrders() {
    return orders -> orderService.processBatch(orders);
}
~~~

~~~yaml
spring:
  cloud:
    function:
      definition: processOrders
    stream:
      bindings:
        processOrders-in-0:
          destination: orders.created
          group: order-processor
          consumer:
            batch-mode: true
      rabbit:
        bindings:
          processOrders-in-0:
            consumer:
              enable-batching: true
              batch-size: 20
              receive-timeout: 200
              prefetch: 20
~~~

- `enable-batching` turns on container aggregation of received messages into batches.
- `batch-size` is the target number of messages per batch.
- `receive-timeout` is how long to wait for more messages; on expiry, the container can emit a partial batch.
- `consumer.batch-mode` instructs Spring Cloud Stream to pass the batch into the function as a `List`.
- `prefetch` controls how many unacked deliveries each consumer can hold; consider its relationship with batch size.

Consumer-side batching in the Rabbit binder is only supported with container type `simple`. If using the `direct` container, check binder version support and select the appropriate container.

### 6.5. Distinguishing producer-created vs. consumer-created batches

Producer-created batches pack multiple messages on the sender side; the consumer can de-batch into separate invocations or pass the whole batch as a `List` if batch mode is enabled. Consumer-created batches have the container collect multiple individual deliveries over a window and assemble them into a `List`.

Do not enable both simply assuming bigger batches are always faster. Clarify your goal, check how the binder de-batches, and verify per-element headers.

## 7. Pulsar: producer batching and receiver queue

Pulsar has automatic producer batching. In Spring Boot/Spring for Apache Pulsar, producer-side batching is enabled by default in current versions; it can be configured via `spring.pulsar.producer.batching-enabled`.

~~~yaml
spring:
  pulsar:
    producer:
      batching-enabled: true
~~~

A Pulsar producer batch can be dispatched when it reaches maximum message count, byte limit, or publish delay timeout. Pulsar `ProducerBuilder` properties include `batchingMaxMessages`, `batchingMaxBytes`, and `batchingMaxPublishDelay`. Defaults depend on the Pulsar client version; client releases commonly default to 1,000 messages and 128 KiB, while batch delay can vary between versions.

If you need to fine-tune these limits, Spring for Apache Pulsar provides `ProducerBuilderCustomizer`:

~~~java
@Bean
ProducerBuilderCustomizer<OrderCreated> orderProducerBatching() {
    return builder -> builder
        .enableBatching(true)
        .batchingMaxMessages(200)
        .batchingMaxBytes(128 * 1024)
        .batchingMaxPublishDelay(2, TimeUnit.MILLISECONDS);
}
~~~

The customizer applies at the producer factory according to Spring Pulsar's configuration scope. If an application has multiple producers with different requirements, inspect factory caching and customizer scope for your version; avoid letting a global customizer unintentionally alter all producers.

### 7.1. Receiver queue

Pulsar consumers have a client-side receiver queue. `receiverQueueSize` is the number of messages buffered locally before the consumer dequeues them for processing. Values that are too low can cause consumers to repeatedly wait on the broker; values that are too high hold many payloads in heap/direct memory.

For partitioned topics, consider `receiverQueueSize`, `maxTotalReceiverQueueSizeAcrossPartitions`, partition count, consumer/concurrency count, message size, and processing speed together.

Example in Spring Pulsar versions supporting these properties:

~~~yaml
spring:
  pulsar:
    consumer:
      receiver-queue-size: 500
      max-total-receiver-queue-size-across-partitions: 10000
~~~

Exact property paths and per-binding configurability depend on the Spring Boot/Spring Pulsar version selected by your project BOM. The Spring Cloud Stream Pulsar binder builds on Spring Boot auto-configuration and allows consumer properties at the binder or extended binding level. Inspect the metadata for your exact version; if a property is not exposed, you can pass native consumer properties via the `properties` map or use an appropriate consumer builder customizer.

### 7.2. Consumer batching

The Spring for Apache Pulsar listener container uses the `batchReceive` API to pull data from the consumer. For single-record listeners, the container can receive an internal batch and invoke the listener message by message. With `@PulsarListener`, `batch=true` lets the listener receive an entire `List`.

This does not mean every function binding in the Spring Cloud Stream Pulsar binder supports `batch-mode` the exact same way as Kafka or Rabbit. Check the documentation and configuration metadata of your exact binder version before changing a function signature to `Consumer<List<T>>`.

### 7.3. ACK during batch processing

In Spring for Apache Pulsar:

- With a per-record listener and default `BATCH` ACK mode, the container receives an internal batch and calls the listener per message; successful records can be ACKed and failed records NACKed individually after the batch finishes.
- With a batch listener receiving `List`, if the whole batch succeeds, the whole batch is ACKed; if one record throws an exception, by default the entire batch can be NACKed.
- Batch listeners do not use `RECORD` ACK mode; if per-message ACK/NACK is needed, use `MANUAL` and acknowledge by message ID.

This is a critical distinction when designing idempotency and retries. An error on the last item in a batch can cause earlier items to be redelivered if the ACK policy applies to the whole batch.

## 8. Memory limits and in-flight message counts

Batch size, prefetch, and receiver queues all increase the number of messages resident in the application. A simple estimate:

\[
M_{\text{payload}} \approx N_{\text{in-flight}} \times S_{\text{avg}}
\]

Where `N_in-flight` is the number of messages delivered/read but not yet finished or acknowledged, and `S_avg` is the average payload size.

This accounts only for raw payload bytes. Actual heap also includes object headers, Strings/collections, byte buffers, headers, deserialized copies, batch lists, and temporary business-logic objects.

RabbitMQ example: 4 consumers, prefetch 50, average payload 64 KiB. Maximum held messages is roughly 200; raw payload is around 12.5 MiB. With 3 instances, that reaches around 37.5 MiB before overhead.

Kafka example: `max.poll.records = 200`, average payload 64 KiB. One batch holds roughly 12.5 MiB of raw payloads. If multiple consumer threads process concurrently, multiply by the active consumers holding batches and add fetch buffers, producer buffers, and deserialized objects.

Pulsar example: `receiverQueueSize = 500`, average payload 64 KiB. A receiver queue can hold roughly 31.25 MiB of raw payloads per consumer queue before overhead; partitioned topics and cross-partition limits complicate the buffer structure further.

Do not use this formula as an exact heap ceiling. Factor in p95/p99 message sizes, consumer counts, concurrency, partitions, and client buffering behavior to set a safe memory budget.

## 9. Backpressure: do not use buffers to hide bottlenecks

Suppose the producer sends 10,000 messages/second while the consumer only processes 6,000 messages/second. The 4,000 messages/second gap accumulates as backlog.

Increasing prefetch or receiver queues may keep consumers fed briefly, but does not solve a sustained rate mismatch. Larger buffers shift the backlog from broker storage into application RAM; this raises memory pressure and slows recovery after crashes.

When backlog grows continuously:

1. Identify whether the bottleneck is CPU, database, external API, serialization, or network.
2. Measure per-consumer throughput and distribution across partitions/queues.
3. Increase concurrency if partition/consumer capacity remains and dependencies can handle it.
4. Optimize batch size if per-message processing overhead is a large fraction.
5. Cap in-flight counts so slow downstreams do not exhaust heap.
6. Use pause/resume or appropriate flow control if receive rates must be throttled.
7. Monitor backlog and drain time once downstream recovers.

If downstream is constrained by a connection pool, increasing concurrency can worsen things. Concurrency must align with database/API resource limits.

## 10. Choosing batch size for latency and throughput

Small batch sizes have low accumulation wait time, low memory usage, and a smaller retry/redelivery blast radius, but higher per-message overhead.

Large batch sizes can cut framework calls, requests, or commits; they often improve throughput for small payloads under heavy load. In return, they increase memory and latency when batches are partial, one failure can affect more records, and each invocation takes longer.

Step up gradually—for example 10, 25, 50, 100—and measure throughput, p95 latency, and memory. Stop increasing once throughput plateaus or latency/memory approaches budget limits.

A good batch size is not necessarily the maximum the broker permits. Choose based on actual processing time and payload size, not just message count.

## 11. Concurrency and partition/consumer count

Batching does not replace concurrency. A function accepting `List<T>` can still run sequentially on a single consumer thread. For CPU-bound or I/O-bound work, benchmark whether batch processing or increasing consumer count delivers greater gains.

### Kafka

- One partition is assigned to at most one consumer in the same group at a time.
- Consumers exceeding the partition count sit idle.
- Increasing concurrency cannot exceed the parallelism ceiling set by partition count.
- Keys/partitioning govern load distribution; one hot key can bottleneck a partition.

### RabbitMQ

- Each consumer receives deliveries from a queue.
- Increasing concurrency adds competing consumers pulling from the queue.
- Prefetch applies per consumer; total in-flight scales with concurrency.
- For strict ordering, consider single-active-consumer or an appropriate routing strategy.

### Pulsar

- Concurrency depends on subscription type and partition count.
- `Exclusive` subscriptions permit only one active consumer.
- `Shared` distributes messages across multiple consumers without global ordering guarantees.
- `Key_Shared` enables parallelism across keys while preserving per-key order as configured.
- `Failover` uses active/standby consumers and can preserve ordering on partitioned topics.

Increasing concurrency must go hand in hand with reviewing ordering, partitions, key affinity, and business-level parallel safety.

## 12. Delivery semantics and failures during batch processing

Batching and prefetch change how many messages have been delivered but not yet ACKed. When a consumer dies, unacknowledged messages may be redelivered. If the function already executed external side effects before crashing, redelivery can duplicate those side effects.

Principles to follow:

- Make processing idempotent using event IDs or business keys.
- ACK/commit only after required work completes per your delivery contract.
- For partially processed batches, track per-item state or use manual acknowledgment if the binder supports it.
- Do not assume a batch is an atomic transaction unless the binder/broker explicitly provides that guarantee.
- Test retry/DLQ behavior when an item fails mid-batch.
- Do not set prefetch so high that shutdown/rebalance causes excessive redeliveries.

With Kafka batch mode, standard binder-level retries are not supported and `maxAttempts` may be forced to 1. With Pulsar batch listeners, a single-item failure can NACK the whole batch under default ACK mode. With Rabbit, how the container de-batches and ACKs depends on producer batching, consumer batch mode, and acknowledgement mode.

## 13. Measuring performance and observability

Do not measure total throughput alone. Track:

| Metric | What to detect |
|---|---|
| Actual producer batch size | Do batches fill up or usually flush on timeout? |
| Producer send latency | Does batching push latency beyond targets? |
| Actual consumer batch size | Are batches large enough to amortize overhead? |
| Processing time per batch | Does any batch run too long relative to poll/ACK timeouts? |
| In-flight/unacked messages | Are prefetch or receiver queues too high? |
| Consumer lag/backlog | Is processing keeping up with arrival rates? |
| Redelivery/retry rate | Are failing batches causing repeated reprocessing? |
| Heap/direct memory and GC | Are buffers creating memory pressure? |
| Partition/consumer utilization | Is load balanced or stuck on hot partitions/consumers? |
| End-to-end latency p95/p99 | Do users wait longer after increasing batching? |

Measure both steady state and bursts. A setup with good average throughput but terrible p99 latency or steadily climbing memory is not stable.

## 14. Controlled benchmark workflow

1. Generate representative load matching production payload sizes and key distributions.
2. Record a baseline with batch mode off or using the current configuration.
3. Change only one parameter group per test run.
4. Increase producer batch size or linger/delay and measure throughput/latency.
5. Increase consumer batch size or poll limit and measure batch processing time.
6. Increase prefetch/receiver queue step by step and measure in-flight counts, memory, and redeliveries.
7. Test burst load and slow-downstream periods.
8. Kill a consumer mid-batch to verify redelivery and idempotency.
9. Measure backlog drain time after load subsides.
10. Select the configuration that simultaneously satisfies throughput, latency, memory, and recovery targets.

Never compare two configurations if you changed batch size, concurrency, partition count, and compression at the same time. When multiple variables move together, you cannot tell which one caused an improvement or regression.

## 15. Suggested configurations by scenario

| Scenario | Tuning direction | What to watch |
|---|---|---|
| Small messages, high throughput, latency tolerates a few extra ms | Increase producer batching and suitable compression. | Producer latency, CPU, network, and batch fill ratio. |
| Fast Kafka consumer, high per-call function overhead | Enable batch mode, pick moderate `max.poll.records`. | Batch processing time and `max.poll.interval.ms`. |
| Fast Rabbit consumer waiting frequently for deliveries | Raise prefetch incrementally, consider concurrency. | Unacked count, fairness, and memory. |
| Rabbit flow needs bulk database writes | Enable consumer-side batching with suitable batch size/receive timeout. | Batch fill ratio, DB batch latency, and redeliveries. |
| Pulsar producer emitting many small messages | Keep batching enabled, tune max messages/bytes/delay for client version. | Publish latency, batch size, and pending messages. |
| Pulsar consumer sees bursts while function is slow | Lower receiver queue or increase appropriate consumer capacity. | Queue memory, backlog, and redeliveries. |
| Large messages | Reduce message count in batches/prefetch; consider byte limits and compression. | Heap/direct memory and p99 processing time. |
| Low traffic, messages must arrive quickly | Reduce batch delay/receive timeout and fetch wait accordingly. | End-to-end latency and request rate. |
| Batches take too long to process | Lower batch/poll limit or split work smaller. | Rebalances, timeouts, retries, and batch p99. |

These directions are starting points. Verify actual configuration and broker/client version characteristics before rollout.

## 16. Common mistakes

1. Assuming enabling producer batching automatically makes the consumer function receive a `List`.
2. Raising Kafka `max.poll.records` without checking processing time and `max.poll.interval.ms`.
3. Confusing Kafka `pollTimeout` with `max.poll.records`.
4. Raising `fetch.min.bytes` while forgetting low traffic can make messages wait longer.
5. Enabling Kafka batch mode while still expecting binder retry `maxAttempts` to work like record mode.
6. Increasing Rabbit prefetch without accounting for consumer count/concurrency and memory.
7. Setting Rabbit prefetch too high so one consumer hoards messages while others sit idle.
8. Enabling both producer batching and consumer batching without understanding how the container de-batches.
9. Setting Rabbit `receive-timeout` too large, causing small batches to wait too long.
10. Confusing Pulsar's receiver queue with the batch size passed to the function.
11. Setting a large receiver queue on a partitioned topic without considering total queue across partitions.
12. Increasing batch size without handling idempotency and redelivery.
13. Measuring throughput while ignoring p95/p99 latency, GC, and backlog drain time.
14. Changing multiple settings at once and losing visibility into what helped.
15. Copying defaults from documentation for a different broker/client version than the application's BOM.

## 17. Pre-deployment checklist

- [ ] Distinguished producer batching, consumer batch mode, prefetch/receiver queue, and poll limits.
- [ ] Measured payload size, throughput, processing time, and p95/p99 latency.
- [ ] Calculated in-flight messages from consumer count and prefetch/queue size.
- [ ] Checked heap, direct memory, and GC under burst load.
- [ ] Kafka: batch mode and `max.poll.records` chosen alongside `max.poll.interval.ms`.
- [ ] Kafka: retry/ACK/DLQ verified when a batch contains a failing record.
- [ ] Rabbit: prefetch aligned with concurrency and batch size.
- [ ] Rabbit: producer batching and consumer-side batching configured deliberately.
- [ ] Pulsar: producer batching and receiver queue aligned with client/broker version.
- [ ] Pulsar: total receiver queue across partitions accounted for on partitioned topics.
- [ ] Ordering and partition/key affinity still meet business requirements.
- [ ] Consumer handles redelivered messages idempotently.
- [ ] Tested mid-batch errors, consumer restarts, and slow downstreams.
- [ ] Dashboards/alerts cover backlog, in-flight, redelivery, batch latency, and memory.
- [ ] Benchmarked with production-like payloads and key distributions.

Optimizing batching, prefetch, and poll limits means tuning how much data is grouped or buffered before processing. Producer batching reduces send overhead; consumer batch mode reduces handler invocation overhead; prefetch/receiver queues keep consumers supplied with data; poll limits bound the records returned in a Kafka poll or application poller run. Selecting values based on throughput, latency, memory, concurrency, and delivery semantics helps Spring Cloud Stream achieve stable performance without turning backlog into memory pressure or unruly redeliveries.

## References

- [Spring Cloud Stream – Kafka Binder: Consuming Batches and Consumer Properties](https://docs.spring.io/spring-cloud-stream-binder-kafka/docs/current/reference/html/spring-cloud-stream-binder-kafka.html)
- [Spring Cloud Stream – RabbitMQ Binder: Prefetch and Batching](https://docs.spring.io/spring-cloud-stream/docs/current/reference/html/spring-cloud-stream-binder-rabbit.html)
- [Spring Cloud Stream – Apache Pulsar Binder](https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html)
- [Spring Cloud Stream – Pollable Consumers and Polling Configuration](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
- [Spring for Apache Pulsar – Message Consumption and Batch Acknowledgment](https://docs.spring.io/spring-pulsar/reference/reference/pulsar/message-consumption.html)
- [Spring for Apache Pulsar – Producer Builder Customization](https://docs.spring.io/spring-pulsar/reference/reference/pulsar/message-production.html)
- [Apache Kafka – Consumer Configuration](https://kafka.apache.org/documentation/#consumerconfigs)
- [Apache Pulsar – Producer Batching](https://pulsar.apache.org/docs/client-libraries/producers/)
