# Bounding Internal Queues, Memory, and In-Flight Tasks

## Objectives

A Spring Cloud Stream application can receive messages faster than business logic can process them. If the application holds too many messages in memory, opens too many consumers, or submits work into an unbounded queue, heap usage climbs steadily, garbage collection pauses lengthen, and the process can eventually fail with an `OutOfMemoryError`. At that point the broker still holds a backlog, while the consumer itself has lost the ability to process reliably.

To control load, bound three distinct things:

- **Queues:** messages waiting in the broker, client prefetch, or internal application queues.
- **Memory:** heap/direct memory held by payloads, deserialized objects, batches, buffers, and pending tasks.
- **In-flight tasks:** handlers, threads, or asynchronous tasks currently executing and not yet completed/acknowledged.

Spring Cloud Stream provides common concurrency for input bindings; each binder also exposes its own controls such as Kafka poll/fetch settings, RabbitMQ prefetch, and Pulsar receiver queues. There is no single internal queue property that applies identically across all binders. Understand each layer accurately and place limits where data is actually buffered.

After this lesson, you can:

- Distinguish broker backlog, client prefetch, application queues, and in-flight work.
- Estimate memory held by messages and tasks.
- Choose concurrency according to partitions, subscriptions, and dependency capacity.
- Bound executor queues and apply backpressure.
- Configure Kafka `max.poll.records`, fetch limits, and poll interval.
- Configure RabbitMQ `concurrency`, `maxConcurrency`, `prefetch`, and queue length.
- Configure Pulsar `receiverQueueSize` and cross-partition receiver queue limits.
- Understand producer buffers and what happens when the broker slows down.
- Avoid acknowledging messages before asynchronous work finishes.
- Measure throughput, latency, backlog, heap, and active task counts.
- Test normal load, bursts, slow dependencies, and overload scenarios.

## 1. Distinguishing four places a message can be held

A message does not necessarily sit in a single queue. On its path from the broker to the handler and out to a destination, it can reside across multiple layers:

1. **Broker backlog:** messages persisted by the broker but not yet processed/acked by consumers. Examples include Kafka topic lag, RabbitMQ ready messages, or Pulsar subscription backlog.
2. **Client-side prefetch/fetch buffer:** messages the broker has sent to the client but the application has not finished processing. Examples include RabbitMQ unacknowledged deliveries, Kafka fetch cache, or Pulsar receiver queues.
3. **Application queue:** messages/tasks placed into an in-JVM queue, such as a `ThreadPoolTaskExecutor`, Reactor buffer, or custom queue.
4. **In-flight processing:** a handler or worker has started processing the message and holds the payload, objects, transactions, connections, or intermediate results.

You can visualize this as:

~~~mermaid
flowchart LR
    A[(Broker backlog)] --> B[Client prefetch / fetch]
    B --> C[Application queue]
    C --> D[In-flight workers]
    D --> E[ACK / offset commit]
    D --> F[Output producer buffer]
    F --> G[(Destination topic / queue)]
~~~

Broker backlog usually sits in broker storage and does not directly consume consumer JVM heap. By contrast, prefetch, batches, internal queues, and active processing objects consume application heap or direct memory.

An application can have a very large broker backlog while keeping heap stable if consumer fetching is bounded. That is usually far better than pulling the entire backlog into the JVM and storing it in an unbounded queue.

### Comparison table

| Layer | Examples | Where it lives | Typical limits |
|---|---|---|---|
| Broker backlog | Kafka lag, Rabbit ready, Pulsar backlog | Broker storage | Retention, queue max length/bytes, quotas |
| Client prefetch | Rabbit prefetch, Pulsar receiver queue | Client memory and broker unacked state | Prefetch count, `receiverQueueSize` |
| Client fetch cache | Kafka fetch buffers | Kafka client memory | `fetch.max.bytes`, `max.partition.fetch.bytes`, `max.poll.records` |
| Application queue | Executor queue, Reactor buffer | JVM heap | `queueCapacity`, `limitRate`, bounded buffers |
| In-flight task | Handler/thread executing | JVM heap, stacks, dependency resources | `concurrency`, semaphores, worker counts |
| Producer buffer | Kafka producer buffer, Pulsar pending sends | JVM/direct memory | `buffer.memory`, max pending messages, block/timeout |

Do not use a single number to describe all layers. For example, a RabbitMQ prefetch of 20 does not mean the application holds at most 20 messages if application code copies messages into an executor queue.

## 2. Why bound queues?

Suppose the producer sends 1,000 messages/second while the consumer only processes 600 messages/second. The 400 messages/second gap accumulates as backlog. If the broker holds that backlog, the system can continue operating and the consumer can catch up when load drops. If the application pulls the backlog into an unbounded heap queue, heap grows over time.

Common symptoms:

- Heap usage rises continuously even though CPU is below 100%.
- Frequent full GCs or old-generation GCs occur.
- Message latency rises because messages wait longer in queues.
- Thread pools show many queued tasks with few completions.
- Database or HTTP connection pools are exhausted.
- Consumers experience rebalances, timeouts, or redeliveries because batches take too long.
- Pods get OOMKilled and restart repeatedly.
- Retries add load precisely when dependencies are already overloaded.

Bounding queues creates an explicit stopping point. When a queue is full, the system can slow down receiving, leave backlog on the broker, reject task submissions, or fail in a controlled way. That is backpressure.

### Backlog can grow while heap stays stable

A stable consumer can temporarily process slower than the producer. The broker holds the backlog; the client fetches only a bounded amount; handlers process at the rate dependencies can sustain.

It is important to distinguish:

- **Backlog growing on the broker:** requires increasing processing capacity, throttling producers, or accepting catch-up time.
- **Queue growing inside the JVM:** requires checking prefetch, batch, executor, and asynchronous fan-out limits.
- **In-flight count growing:** requires checking concurrency, processing duration, and resource pools.

Do not try to solve every backlog by raising queue capacity. Raising queue limits only delays overload if processing speed stays below the arrival rate.

## 3. Estimating memory for messages and tasks

Payload bytes on the broker are not the full heap footprint held by the application. Deserializing JSON into Java objects creates additional `String`s, collections, object graphs, headers, buffers, and temporary copies.

A simple estimation model:

`M_queue ≈ N × S_retained`

Where:

- `N` is the number of messages held in client/application queues.
- `S_retained` is the actual JVM memory occupied by one message, including the deserialized payload and related metadata.

If the average payload is 48 KiB and the deserialized object graph retains roughly 2.5x the wire byte size, one message can retain around 120 KiB. This is only a budgeting assumption; measure with a heap profiler or allocation metrics on your actual application.

Across multiple bindings and replicas:

`M_total ≈ replicas × (M_base + M_prefetch + M_appQueue + M_inFlight + M_producerBuffer)`

`M_base` covers framework heap, caches, connections, class metadata, and baseline application data. Direct memory, native memory, and RocksDB/off-heap must be accounted for separately if used.

### Quick calculation example

Suppose:

- 3 replicas.
- 4 consumers per replica.
- RabbitMQ prefetch of 8 messages per consumer.
- Average payload of 48 KiB.
- Post-deserialization retention factor of 2.5.

Approximate maximum unacknowledged messages due to prefetch:

`3 × 4 × 8 = 96 messages`

Estimated corresponding memory:

`96 × 48 KiB × 2.5 ≈ 11.25 MiB`

This excludes intermediate objects, task queues, output buffers, stacks, caches, and other bindings. Raising prefetch to 80 increases this memory footprint nearly tenfold even though the consumer count did not change.

### Use percentiles, not just averages

Message sizes and processing times typically have skewed distributions. A few large messages can dominate memory usage. Measure:

- Payload size p50, p95, and p99.
- Retained heap after deserialization.
- Processing time p50, p95, and p99.
- Messages in prefetch/queues.
- Active and queued task counts.
- Post-GC heap occupancy and direct memory.

When sizing, use p95/p99 values aligned with safety requirements rather than minimum or average values.

## 4. In-flight tasks and concurrency

Concurrency is the number of consumer/listener workers that can receive and process messages in parallel per the binder mechanism. In Spring Cloud Stream, the common input binding property is:

```yaml
spring:
  cloud:
    stream:
      bindings:
        processOrders-in-0:
          destination: orders.created
          group: order-service
          consumer:
            concurrency: 4
```

The common `concurrency` property defaults to 1. Binders map it to consumers, listeners, or threads according to middleware semantics. Therefore, do not assume concurrency works identically across Kafka, RabbitMQ, and Pulsar.

Higher concurrency can raise throughput when work is independent and dependencies still have headroom. However, it also increases:

- Messages processed simultaneously.
- Live objects and transactions.
- Connections or requests hitting databases/APIs.
- Unacknowledged/uncommitted messages.
- CPU contention and context switching.
- Contention over the same keys or shared resources.

### Choose concurrency around the bottleneck

If each message holds a database connection for its entire processing duration, setting concurrency higher than the connection pool size only creates threads waiting for connections. For example, with a 12-connection pool and concurrency 48, most workers may block waiting on the database while holding payloads and inflating latency.

Identify the constraining resource:

| Bottleneck | Limits to check |
|---|---|
| Database | Connection pool, query latency, lock contention |
| HTTP service | Connection pool, rate limits, timeouts |
| CPU | Core count, CPU time/message, serialization |
| File/object storage | Concurrent request quota, IOPS |
| Kafka partitions | Partition count and consumer assignment |
| Rabbit queue | Consumer count, prefetch, and queue capacity |
| Pulsar subscription | Subscription type, partitions, and receiver queue |

Start concurrency low, then step it up during load tests. Do not habitually set concurrency equal to CPU cores if each message mainly waits on I/O; nor should you set it very high if each message holds significant heap or database connections.

### Concurrency does not mean the same thread count at every layer

An input binding may have concurrency 4, submit tasks to a 16-thread executor, and each task calls an HTTP client with a 20-connection pool. Effective concurrency and active requests can differ at every layer.

Document separate bounds:

- Consumer concurrency: number of listeners/consumers.
- Worker concurrency: number of business tasks executing in parallel.
- Executor queue capacity: tasks waiting inside the JVM.
- Dependency concurrency: requests actively holding connections/resources.
- Broker in-flight: delivered but unacknowledged messages.

## 5. Using Little's Law to estimate required in-flight work

Little's Law relates average work in the system, throughput, and residence time:

`L = λ × W`

Where:

- `L` is the average number of messages inside the system.
- `λ` is throughput in messages/second.
- `W` is the average time a message stays in the system in seconds.

For example, a system needing to process 800 messages/second with an average processing time of 25 ms:

`L = 800 × 0.025 = 20`

Roughly 20 messages need to be actively processed or waiting in the measured region to sustain that throughput under steady assumptions. This is not a rule to set queue capacity to 20. If service time varies widely, add headroom and explicit queue bounds.

One sequential worker taking 25 ms has a theoretical capacity of about 40 messages/second. Eight workers can reach roughly 320 messages/second if work is independent and not dependency-bound. To reach 800 messages/second, increase processing capacity or reduce service time; enlarging the queue alone does not increase throughput.

### Queue capacity equals acceptable wait time

If processing throughput is 500 messages/second and an internal queue holds 5,000 messages, a full queue represents about 10 seconds of queued work before new processing time. Choose queue capacity based on latency/SLA and recoverability, not merely free RAM.

## 6. Bounding internal JVM queues

Spring Cloud Stream does not provide a single cross-binder property named `internalQueueCapacity`. Internal queues arise when an application explicitly uses executors, asynchronous channels, Reactor buffers, or fan-out mechanisms.

For `ThreadPoolTaskExecutor`, `queueCapacity` must be finite. For example:

```java
@Bean
ThreadPoolTaskExecutor orderExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(8);
    executor.setMaxPoolSize(8);
    executor.setQueueCapacity(32);
    executor.setThreadNamePrefix("order-worker-");
    executor.setRejectedExecutionHandler(
            new ThreadPoolExecutor.CallerRunsPolicy()
    );
    executor.initialize();
    return executor;
}
```

In this example:

- At most 8 tasks execute concurrently.
- At most 32 tasks wait in the executor queue.
- When the queue is full, `CallerRunsPolicy` runs the task on the submitting thread, slowing the task producer and applying backpressure.
- The queue cannot grow unboundedly with arrival rate.

With `ThreadPoolExecutor`, once threads reach `corePoolSize`, new tasks are queued first; threads scale toward `maxPoolSize` only after the queue fills. Therefore, `queueCapacity` and core/max pool sizes must be designed together. Here core and max are both 8 to keep worker count fixed.

### Never ack a message before async tasks complete

A dangerous bug occurs when a function receives a message, submits a task to an executor, and returns immediately:

```java
@Bean
Consumer<OrderCreated> processOrders(
        OrderExecutor executor,
        OrderService orderService) {
    return event -> executor.submit(() -> orderService.process(event));
}
```

If the binder treats the function as finished and acks/commits the message right after `submit`, the process may crash before the task finishes. The broker will not redeliver an acknowledged message, while the work existed only in heap and was lost when the JVM stopped.

If using an internal executor, ensure acknowledgement happens only after work completes. You can await the `Future` in the handler, use the binder's manual acknowledgment API and ack only on task completion, or persist the work to a durable store/queue before returning. Never rely on an in-memory executor to replace a durable queue.

### Rejection policies must match semantics

| Policy | Behavior | When appropriate |
|---|---|---|
| `CallerRunsPolicy` | Submitting thread executes the task when queue is full | Want to push backpressure onto the listener/request thread |
| `AbortPolicy` | Throws `RejectedExecutionException` | Want explicit rejection routed into error handling |
| `DiscardPolicy` | Drops the newest task | Only when task loss is explicitly acceptable |
| `DiscardOldestPolicy` | Drops the oldest queued task | Only for replaceable data with a proven policy |

Never use `DiscardPolicy` or `DiscardOldestPolicy` for business messages requiring guaranteed delivery unless durable replay exists. With `CallerRunsPolicy`, the handler slows down; ensure timeouts, heartbeats, poll intervals, and shutdown behavior remain safe.

## 7. Backpressure in function/reactive pipelines

For reactive functions, you can bound Reactor operator concurrency and prefetch:

```java
@Bean
Function<Flux<OrderCreated>, Flux<OrderResult>> processOrders() {
    return orders -> orders.flatMap(
            this::processOne,
            8,
            16
    );
}
```

In this example, `flatMap` permits at most 8 concurrent inner publishers and prefetches 16 elements per inner subscription under Reactor semantics. This bounds the Reactor pipeline; it does not automatically bound all fetching/prefetching inside Kafka, RabbitMQ, or Pulsar clients.

Do not manually call `subscribe()` inside a function to detach work from the binder-managed lifecycle. Manual subscription breaks backpressure, lets the function complete before processing finishes, and detaches errors/acks from the original message.

Operators like `onBackpressureBuffer` can create additional queues. If used, specify a finite capacity and define overflow behavior. Never use an unbounded buffer on a continuous message stream.

### Backpressure only works when connected across all layers

A pipeline might limit `flatMap` to 8 while the binder still prefetches 1,000 messages. Heap can still hold many messages before Reactor receives them. Conversely, a small prefetch where the function pushes every message into an unbounded executor queue is equally unsafe.

Bound every layer and test the total number of retained messages, not just one operator.

## 8. Kafka: poll batches, fetch buffers, and partitions

With the regular Kafka binder, consumer properties can be configured per binding. Example:

```yaml
spring:
  cloud:
    stream:
      bindings:
        processOrders-in-0:
          destination: orders.created
          group: order-service
          consumer:
            concurrency: 4
      kafka:
        bindings:
          processOrders-in-0:
            consumer:
              configuration:
                max.poll.records: 100
                max.poll.interval.ms: 300000
                fetch.max.bytes: 10485760
                max.partition.fetch.bytes: 1048576
```

Each property plays a distinct role:

| Property | Role | Impact |
|---|---|---|
| `concurrency` | Number of consumers/listeners for the binding | Increases parallelism and fetch loops |
| `max.poll.records` | Maximum records returned per poll | Bounds the batch handed to the listener each poll |
| `max.poll.interval.ms` | Maximum time between polls | If batch processing runs too long, consumer may be considered dead and trigger group rebalance |
| `fetch.max.bytes` | Maximum data returned for one fetch request | Affects fetch buffer size |
| `max.partition.fetch.bytes` | Per-partition data limit in a fetch | Scales memory with fetched partition count |

`max.poll.records` is not an absolute cap on all data cached by the client. A Kafka consumer can prefetch data into its internal buffer; `poll()` returns batches from that cache. Nor is `fetch.max.bytes` an absolute ceiling in every scenario: Kafka permits returning the first partition batch even if it exceeds the limit so the consumer can still make progress. Check maximum message size settings at the broker/topic level.

### Example batch and processing time calculation

If `max.poll.records = 100` and each record takes 40 ms sequentially, batch processing time is approximately:

`100 × 40 ms = 4,000 ms`

This excludes deserialization, offset commits, and dependency calls. It must stay well below `max.poll.interval.ms` with ample headroom. If batch processing uses concurrency, measure p95/p99 and verify offset commit semantics; do not simply divide average time by threads and assume it is safe.

### Concurrency and partition count

Within a consumer group, a partition is assigned to only one consumer member at a time. If a topic has 6 partitions and each replica uses concurrency 4, three replicas create up to 12 consumers, yet only 6 consumers can receive partitions from that topic; the rest stay idle for this topic.

Do not raise concurrency far past partition count without another reason. If higher throughput is needed, evaluate partition count, key distribution, processing time, and dependency capacity. Adding partitions can affect per-key ordering and requires operational planning.

### Kafka Streams differs from the regular Kafka binder

The Kafka Streams binder uses its own topology/task/thread model. Processing threads can be controlled via `num.stream.threads` or input binding `concurrency` depending on binder version support. Actual task count is still constrained by partitions and topology. Do not mechanically apply regular Kafka binder concurrency settings to Kafka Streams without checking the binder reference.

## 9. RabbitMQ: prefetch, concurrency, and queue length

RabbitMQ pushes messages to consumers via deliveries. Prefetch limits how many unacknowledged deliveries the broker may keep outstanding for a consumer/channel. Once prefetch is reached, the broker pauses further deliveries until acknowledgements arrive.

Key Spring Cloud Stream Rabbit binder properties:

- `concurrency`: generic Spring Cloud Stream consumer property.
- `maxConcurrency`: maximum consumers on the listener container; not supported with `containerType` `direct`.
- `prefetch`: unacked messages pre-delivered to a consumer; current binder default is 1.
- `maxLength` and `maxLengthBytes`: queue limits by message count or total bytes when the binder declares the queue.
- `overflowBehavior`: behavior when the queue exceeds its limit.

Example:

```yaml
spring:
  cloud:
    stream:
      bindings:
        processOrders-in-0:
          destination: orders.created
          group: order-service
          consumer:
            concurrency: 4
      rabbit:
        bindings:
          processOrders-in-0:
            consumer:
              maxConcurrency: 4
              prefetch: 8
              maxLength: 100000
              maxLengthBytes: 1073741824
              overflowBehavior: reject-publish
```

With concurrency 4 and prefetch 8, maximum unacked deliveries can reach roughly 32 per instance when each consumer has its own prefetch limit. Across 3 replicas, total in-flight deliveries can reach roughly 96. Check your container type and how the binder/Spring AMQP applies QoS in your version.

Modern RabbitMQ configurations apply prefetch per consumer. Do not confuse it with a single global limit across the entire connection. Global QoS behaves differently, and in RabbitMQ 4.3 legacy global/per-channel prefetch was deprecated and disabled by default. Use per-consumer prefetch and consult the broker docs for your exact version.

### Pros and cons of high prefetch

High prefetch keeps consumers fed during processing, cuts round trips, and improves throughput. However, it also:

- Increases unacked message count.
- Increases client heap if messages are held in memory.
- Lets one consumer hoard more messages while other consumers sit lightly loaded.
- Lengthens drain time when stopping a consumer.
- Increases redeliveries when a connection drops.
- Adds latency to messages queued behind a slow message if the handler runs sequentially.

Prefetch `0` in AMQP means unlimited, not zero prefetch. Never use `0` as a default way to increase throughput.

### Queue limits on the broker

`maxLength` and `maxLengthBytes` bound the queue when the binder creates it. When breached, overflow policy decides whether new publishes are rejected or older messages are dropped as configured. Choose policy based on business rules; never set `drop-head` if older data cannot be lost.

If infrastructure provisions queues externally via policies/definitions, inspect actual queue arguments and policies on the broker. Binder properties may not alter an already-existing queue with differing declarations.

## 10. Pulsar: receiver queues and partition queues

A Pulsar consumer uses a receiver queue to prefetch messages on the client before the application calls receive or the listener executes. A larger queue can raise throughput but increases memory usage.

Important Pulsar Java client properties:

| Property | Meaning |
|---|---|
| `receiverQueueSize` | Number of messages that can accumulate in the receiver queue |
| `maxTotalReceiverQueueSizeAcrossPartitions` | Total receiver queue cap for a consumer across partitions |
| `maxPendingMessages` | Cap on pending messages in the producer |
| `maxPendingMessagesAcrossPartitions` | Cap on pending messages across partitions for a partitioned topic producer |

In the Spring Cloud Stream Pulsar binder, the binder leverages Spring for Apache Pulsar and Spring Boot auto-configuration. Pulsar consumer properties can be set at application level, binder level, or extended binding level. Extended binding takes precedence over binder-level and Spring Boot properties.

Example configuring the receiver queue for a binding:

```yaml
spring:
  cloud:
    stream:
      pulsar:
        bindings:
          processOrders-in-0:
            consumer:
              receiver-queue-size: 200
              max-total-receiver-queue-size-across-partitions: 5000
```

Or configuring globally at the Spring Boot level:

```yaml
spring:
  pulsar:
    consumer:
      receiver-queue-size: 200
      max-total-receiver-queue-size-across-partitions: 5000
```

This illustrates Spring for Apache Pulsar property mapping. Check metadata for your exact Spring Pulsar/binder version because property names and locations can change across releases.

### Partitioned topics

With partitioned topics, receiver queues can be created per partition. `maxTotalReceiverQueueSizeAcrossPartitions` caps total messages pushed to a consumer across all partitions. Looking only at `receiverQueueSize` while ignoring the cross-partition cap can result in much higher memory usage than expected.

For instance, a topic with 24 partitions and `receiverQueueSize` set to 500 messages. Without a proper total cap, total buffered messages can far exceed 500. Verify how your client version enforces `maxTotalReceiverQueueSizeAcrossPartitions` and measure actual queued message counts.

### Zero queue size

Some Pulsar client versions support `receiverQueueSize = 0` to disable prefetch and pull messages only when the application is ready. This can improve fairness in some shared subscriptions, but reduces throughput and carries restrictions with partitioned topics, batched messages, or receive APIs. Do not use `0` as a blanket setting across topologies; verify client version and subscription type before testing.

## 11. Bounding producer buffers

Consumers are not the only place messages accumulate. When the broker is slow or the network is congested, producers can accumulate unsent or unacknowledged messages.

### Kafka producer

Kafka producers maintain buffer memory to hold records waiting to be sent. Key properties to review:

- `buffer.memory`: total producer buffer capacity.
- `batch.size`: target batch size per partition.
- `linger.ms`: wait time for additional records to batch.
- `max.block.ms`: how long `send`/metadata calls block when the buffer is exhausted or metadata is unavailable.
- `compression.type`: compresses batches, reducing network and storage at the cost of CPU.

If the buffer fills up, `send` can block up to `max.block.ms` and then fail. Do not increase `buffer.memory` unboundedly; that merely moves backlog from the broker into producer heap.

### RabbitMQ publisher

Publisher confirms indicate when the broker has confirmed a publish. If the application retains too many pending futures/callbacks awaiting confirms, heap and pending state can grow. Cap outstanding publishes, batch appropriately, and process confirms/returns promptly.

### Pulsar producer

Pulsar producers limit pending messages. When the queue is full, the producer can block or fail depending on `blockIfQueueFull` and timeout settings. Bounding pending messages protects client memory when the broker slows down.

Account for producer buffers in your application memory budget, especially when one process both consumes and produces.

## 12. Retries and DLQs also consume capacity

When a handler fails, retries hold workers and messages longer. If retries fire rapidly and continuously, a large fraction of concurrency can be tied up by failing messages.

Example:

- 8 workers can process 8 messages simultaneously.
- 6 messages hit a dependency timeout and retry repeatedly.
- Only 2 workers remain to serve new messages.
- Queue/backlog grows even though the producer rate has not changed.

Guidelines:

- Use bounded backoff for transient errors.
- Classify non-retryable errors and route them to a DLQ early.
- Never requeue poison messages indefinitely.
- Define an overall retry budget and timeout.
- Track retry rate separately from success rate.
- Avoid stacking retries across multiple layers without counting total attempts.
- Preserve idempotency when messages can be redelivered.

Increasing concurrency to compensate for a retry storm can overload downstream databases or APIs even further. Address the error source, apply backoff, and cap in-flight retries first.

## 13. Ordering, fairness, and batch size

Concurrency and prefetch can affect processing order.

- With Kafka, ordering is guaranteed within a single partition; raising concurrency does not create topic-wide ordering.
- With RabbitMQ, multiple consumers on the same queue can process in parallel and finish out of delivery order.
- With Pulsar `Shared` subscriptions, multiple consumers process in parallel; `Key_Shared` is better suited when per-key distribution is needed under Pulsar semantics.
- Large batches boost throughput but increase memory, processing time, and failure redelivery scope.
- Oversized prefetch can let one consumer hoard more messages than others.

If business logic requires ordering per account or order ID, partition by key or use an appropriate subscription/queue strategy. Do not solve ordering by setting concurrency = 1 across the whole system when only per-key ordering is needed; choose a scalable partitioning model.

## 14. Combined sizing example

Suppose a service runs 3 replicas. Each replica has:

- 4 consumers.
- Each consumer holds up to 8 unacked messages.
- Workers run up to 8 concurrent tasks.
- Executor queue holds up to 32 tasks.
- Average payload is 48 KiB.
- Retained size factor is 2.5.

Fleet-wide prefetch memory estimate:

`3 × 4 × 8 × 48 KiB × 2.5 ≈ 11.25 MiB`

Fleet-wide executor queue memory estimate:

`3 × 32 × 48 KiB × 2.5 ≈ 11.25 MiB`

Estimate for 8 active workers per replica:

`3 × 8 × 48 KiB × 2.5 ≈ 2.81 MiB`

This estimate totals roughly 25.31 MiB, excluding extra object graphs, producer buffers, batch copies, headers, retry state, caches, and baseline memory.

This model is only for preliminary budgeting. In practice, multiple object copies of the same message may coexist, or the binder may convert payloads differently. Use heap dumps, allocation profilers, and metrics to calibrate.

### Keep headroom for the JVM

Do not allocate the entire heap to queues. The JVM needs memory for:

- Framework, beans, and metadata.
- Thread stacks and task contexts.
- Connection/client buffers.
- Serialization/deserialization.
- Caches, transactions, and database drivers.
- GC survivor/old generation.
- Metrics, tracing, and logging.

Set queue bounds low enough to leave headroom for bursts and unusually large messages. Test with p99 payloads and p99 dependency latencies, not just averages.

## 15. When to use an internal queue vs. leaving backlog on the broker

Use a bounded internal queue when:

- A small buffer of pending tasks is needed to absorb brief micro-bursts.
- Work is independent and handled by a fixed worker pool.
- Clear backpressure/rejection policies are in place.
- Messages can remain unacknowledged until tasks finish.
- Queue capacity is included in the memory budget.

Leave backlog on the broker when:

- Load exceeds processing capacity over sustained periods.
- Durability across process restarts is required.
- Multiple consumer instances share the work.
- Broker-level retry/replay semantics are needed.
- The application cannot guarantee finishing in-memory tasks on JVM shutdown.

Never use an in-memory queue as a durable buffer between two systems. If producers and workers must be decoupled long-term, use a broker topic/queue or a durable work store.

## 16. Observing capacity and overload signals

Monitor the broker, binder, and JVM together.

| Metric | Meaning | Signal to investigate |
|---|---|---|
| Broker backlog/lag | Work not yet processed by consumers | Rising continuously |
| Ready messages (RabbitMQ) | Messages not yet delivered | Rising while consumer capacity is low |
| Unacked messages (RabbitMQ) | Deliveries held by consumers | Unusually high or not draining |
| Pulsar subscription backlog | Unacknowledged messages | Rising over time |
| Client receiver/fetch queue | Messages pulled onto the client | Consistently near limit |
| Executor queue size | Tasks waiting in the JVM | Always full or growing without draining |
| Active worker count | Currently executing tasks | Saturated at max while latency climbs |
| Rejected task count | Tasks rejected by the executor | Greater than 0 |
| JVM heap after GC | Live memory retained post-GC | Climbing over time |
| Direct memory | Off-heap buffers | Rising abnormally |
| GC pause/time | Collection overhead | Long pauses, dropping throughput |
| Processing latency p95/p99 | Handling duration | Climbing alongside queue growth |
| Dependency pool usage | Downstream resource usage | Pool maxed out, wait time climbing |
| Retry/DLQ rate | Failed message processing | Retry storm or poison messages |

A binding being in a running state does not mean the consumer still has capacity. Inspect throughput, latency, backlog, and in-flight counts together.

## 17. Testing overload and backpressure

Do not load test only the happy path. Verify queues stay bounded when the system slows down.

### Baseline test

- Use realistically sized payloads.
- Ramp load from low up to target level.
- Record throughput, p50/p95/p99 latency, heap, and backlog.
- Verify queues do not grow unboundedly.
- Verify consumer concurrency and worker counts match configuration.

### Burst test

- Spike producer rate briefly.
- Verify broker backlog grows instead of uncontrolled heap growth.
- Verify client prefetch and executor queues respect their limits.
- After the burst, verify consumers catch up and backlog drains.

### Slow dependency test

- Slow down the database/API beyond normal latency.
- Verify concurrency does not exhaust the connection pool.
- Verify full internal queues trigger the chosen backpressure/rejection policy.
- Verify messages are not acked before business work finishes.

### Failure/restart test

- Stop a consumer mid-processing.
- Check redelivery/offset semantics.
- Restart the broker or dependency if needed.
- Verify no tasks were lost due to premature acks.
- Verify retries do not cause unbounded queue growth.

### Memory pressure test

- Use p95/p99 payloads and messages with large object graphs.
- Increase partition or subscription counts to test aggregate prefetch.
- Watch heap, direct memory, and GC.
- Verify no OOM occurs during soak tests.
- Verify graceful shutdown drains or halts tasks per policy.

## 18. Ordered tuning workflow

When a service processes slowly or memory is high, tune in sequence:

1. Measure producer rate, consumer throughput, and backlog.
2. Determine p95/p99 message size and retained heap.
3. Determine actual active consumer/worker counts.
4. Inspect dependency pools and processing time.
5. Bound application queues and asynchronous fan-out.
6. Tune concurrency to match partitions/subscriptions and dependency capacity.
7. Tune prefetch/fetch/receiver queues to cap client buffers.
8. Set broker queue length/byte limits if appropriate.
9. Set sensible batch sizes and retry budgets.
10. Rerun load, burst, and failure tests.
11. Record throughput/latency/memory before and after changes.

If throughput is low due to slow database queries, raising prefetch or concurrency usually just increases queued messages and lock/connection contention. Fix the bottleneck before increasing parallelism.

## 19. Common mistakes

| Symptom | Possible cause | Fix |
|---|---|---|
| Heap grows even though broker backlog is small | Client prefetch or app queue is too large | Reduce prefetch, batches, and queue capacity |
| Broker backlog grows while heap stays stable | Consumer throughput lower than producer | Optimize handler, scale capacity safely, or throttle producer |
| Many tasks waiting in executor | Worker pool too small or slow dependency | Measure service time and bound the queue |
| OOM after increasing concurrency | Too many live payloads/tasks simultaneously | Lower concurrency/prefetch and recalculate memory budget |
| Rabbit unacked grows high | Large prefetch or handlers not acking | Reduce prefetch, check processing/ack duration |
| Kafka rebalance during batch processing | Poll not called before `max.poll.interval.ms` | Lower `max.poll.records`, speed up processing, or redesign poll/worker safety |
| Kafka consumers idle despite high concurrency | Consumer count exceeds partition count | Adjust concurrency or partition plan |
| Pulsar memory high with many partitions | Receiver queue multiplies per partition | Reduce `receiverQueueSize` and set cross-partition total cap |
| Retries slash throughput | Many workers tied up by failing messages | Apply backoff, error classification, and DLQ |
| Messages lost after executor submit | Binder acks before task finishes | Await task or manually ack after completion |
| Queue full and tasks disappear | Discard rejection policy | Use backpressure or durable error handling |
| Low CPU with high latency | Workers waiting on connections/dependencies | Check pool wait, timeouts, and downstreams |
| Producer blocks | Producer buffer full or broker slow | Bound outstanding sends, handle confirms, and check broker |
| Increasing prefetch yields no throughput gain | Bottleneck is in handler/dependency or broker | Measure each layer; stop inflating buffers |

## 20. Production configuration checklist

Before release:

- Define broker backlog, client prefetch, app queue, and in-flight task bounds separately.
- Set explicit concurrency on critical input bindings.
- Set finite executor queue capacity if using asynchronous workers.
- Choose a rejection policy that avoids silent message loss.
- Ensure ack/offset commit occurs only after required work completes.
- For Kafka, configure `max.poll.records` and verify `max.poll.interval.ms`.
- For RabbitMQ, set prefetch and concurrency based on message size/processing time.
- For Pulsar, set `receiverQueueSize` and a cross-partition total cap.
- Include producer buffers in the memory budget.
- Set broker queue max length/bytes when backlog needs capping.
- Verify retry/backoff settings do not cause a retry storm.
- Leave headroom for heap, direct memory, and GC.
- Monitor queue depth, in-flight counts, heap, latency, and dependency pools.
- Run burst, slow-dependency, restart, and memory-pressure tests.
- Document configuration and test results to enable safe rollback.

## Conclusion

Bounding queues, memory, and in-flight tasks are three facets of the same capacity problem. Broker backlog usually sits in broker storage; client prefetch/fetch buffers, application queues, and in-flight tasks directly hold data inside the JVM. Raising one limit without accounting for the other layers can shift a bottleneck from the broker into the heap or a dependency pool.

In Spring Cloud Stream, common input binding concurrency defaults to 1. Kafka requires controlling poll batches, fetch buffers, poll intervals, and partition assignments. RabbitMQ requires controlling consumer concurrency, `maxConcurrency`, prefetch, and queue length/bytes. Pulsar requires controlling `receiverQueueSize` and total receiver queues across partitions. Each binder has distinct semantics, so verify properties for your exact version.

Use bounded queues, explicit worker counts, and backpressure to keep memory stable. Never ack messages before async tasks finish; never treat an in-memory queue as a durable broker. Measure throughput, latency, heap, queue depth, and in-flight work, and test bursts, slow dependencies, and restarts to prove your bounds actually hold.

## Official References

- [Spring Cloud Stream 5.0 — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/5.0/spring-cloud-stream/binding-properties.html): consumer concurrency and common input binding properties.
- [Spring Cloud Stream 5.0.4 — RabbitMQ Consumer Properties](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview/rabbitmq-consumer-properties.html): `prefetch`, `maxConcurrency`, `maxLength`, and `maxLengthBytes`.
- [RabbitMQ — Consumer Prefetch](https://www.rabbitmq.com/docs/consumer-prefetch): per-consumer unacked delivery limits and memory impact.
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): in-flight deliveries, QoS, and throughput.
- [Spring Cloud Stream 5.1 — Kafka Binder Configuration](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html): consumer-specific configuration and `max.poll.records`.
- [Apache Kafka 4.4 — Consumer Configs](https://kafka.apache.org/44/configuration/consumer-configs/): `max.poll.records`, `max.poll.interval.ms`, `fetch.max.bytes`, and `max.partition.fetch.bytes`.
- [Apache Kafka 4.4 — KafkaConsumer API](https://kafka.apache.org/44/javadoc/org/apache/kafka/clients/consumer/KafkaConsumer.html): poll loop, processing threads, and partition pause considerations.
- [Spring Cloud Stream — Pulsar Binder](https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html): Pulsar Boot properties, binder properties, and extended binding precedence.
- [Apache Pulsar 4.0 — ConsumerBuilder API](https://pulsar.apache.org/api/client/4.0.x/org/apache/pulsar/client/api/ConsumerBuilder.html): `receiverQueueSize` and receiver queue limits on partitioned topics.

When deploying, use the reference guide matching the exact Spring Cloud Stream, Spring Boot, binder, Kafka client, RabbitMQ, or Pulsar versions in your dependency/runtime BOM. Do not assume defaults or property mappings from one release carry over unchanged to every version.
