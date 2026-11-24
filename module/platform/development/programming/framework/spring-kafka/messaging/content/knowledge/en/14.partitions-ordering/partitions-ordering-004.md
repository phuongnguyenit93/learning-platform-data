# Ordering when increasing concurrency

## 1. Where does Kafka guarantee ordering?

Kafka guarantees record order within the scope of a single partition. Records are written to a partition in a deterministic order and consumers read them in offset order within that partition. Kafka does not guarantee total order across multiple partitions.

When increasing consumer group concurrency, distinguish three types of order:

- **Order in the log:** the order in which records are appended to a partition. This is Kafka's core guarantee.
- **Order the listener receives records:** the order in which the container passes records to the handler method. With a synchronous record listener, records from the same partition are invoked in read order.
- **Business completion order:** the order in which database/API operations actually finish. The application can alter this order if it processes in parallel or asynchronously.

Increasing concurrency does not itself alter the order of records stored in a partition. It changes the number of consumer members and how partitions are assigned within the group. Business order can be affected if the application runs multiple operations for the same partition concurrently, or uses non-blocking retries.

## 2. What does concurrency mean in Spring Kafka?

In Spring Kafka, `concurrency` is the number of consumers created by a listener container for an endpoint on a single application instance. With `ConcurrentMessageListenerContainer`, Spring manages child containers; each child container uses its own Kafka consumer.

These consumers typically join the same `group.id` and share partitions among themselves. Within a consumer group, a partition at any given time is assigned to at most one member. Therefore, increasing concurrency can increase the number of partitions processed in parallel, but does not split a single partition across multiple consumer threads.

For example, topic `orders` has 6 partitions:

```text
concurrency = 1
  Consumer A: P0, P1, P2, P3, P4, P5

concurrency = 3
  Consumer A: P0, P1
  Consumer B: P2, P3
  Consumer C: P4, P5

concurrency = 6
  Consumer A: P0
  Consumer B: P1
  Consumer C: P2
  Consumer D: P3
  Consumer E: P4
  Consumer F: P5
```

Actual assignment depends on the partition assignor and membership; the diagram only illustrates counts. With 6 partitions, concurrency greater than 6 creates no extra read parallelism for this topic in the group. Consumers exceeding the partition count may receive no partition assignments.

## 3. Does increasing concurrency break ordering within a partition?

If the listener processes synchronously in the standard way, increasing concurrency **does not break read order within the same partition**. Kafka still assigns that partition to one consumer member at a time, and the consumer reads records in offset order.

For example, partition `orders-2` contains:

```text
offset 100: OrderCreated
offset 101: OrderPaid
offset 102: OrderShipped
```

When this partition is assigned to Consumer A, the listener receives records in order `100 → 101 → 102`. After increasing concurrency and a rebalance moves the partition to Consumer C, Consumer C resumes from the group's committed offset. The partition is not split between A and C for two consumers to process different offsets concurrently.

The point to note is that **the consumer owner can change**, while order within the partition does not change. If prior processing had not been committed, records may be redelivered to the new owner. That is a duplicate-processing risk, not Kafka reordering records in the log.

## 4. Example of increasing concurrency with Spring Kafka

Concurrency can be set on the listener container factory:

```java
@Configuration
public class KafkaListenerConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    ordersListenerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);
        factory.getContainerProperties()
                .setAckMode(ContainerProperties.AckMode.RECORD);
        return factory;
    }
}
```

A listener using the factory:

```java
@Component
public class OrderListener {

    private final OrderService orderService;

    public OrderListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
            topics = "orders",
            groupId = "order-service",
            containerFactory = "ordersListenerFactory")
    public void onOrder(OrderEvent event) {
        orderService.process(event);
    }
}
```

Or configure directly on the endpoint:

```java
@KafkaListener(
        topics = "orders",
        groupId = "order-service",
        concurrency = "3")
public void onOrder(OrderEvent event) {
    orderService.process(event);
}
```

Pick one clear configuration location to avoid confusion when concurrency is set on both the factory and annotation. The concurrency value can be constrained by the number of partitions assigned to the endpoint.

## 5. Scaling across multiple application instances

In a deployment with multiple processes or pods, the effective number of consumer members for an endpoint is typically estimated as:

\[
C_{total} = N_{instances} \times concurrency
\]

For example, 3 application instances each with concurrency 2 create up to 6 consumer members for the corresponding endpoint and group. If the topic has 6 partitions, the group can utilize all 6 consumers. If scaled to 5 instances with concurrency 2, total members become 10, yet at most 6 members will receive partitions of the topic.

Crucially, instances of the same service must use the same, stable group ID if the goal is load sharing. If each instance uses a different group ID, each instance becomes an independent subscriber and can read the entire topic, completely changing processing behavior.

## 6. Rebalances when increasing concurrency

When adding consumer members, the Kafka group coordinator performs a rebalance to redistribute partitions. Some partitions may move from older consumers to newer consumers. Depending on the assignor and rebalance protocol, the group may pause all processing temporarily or revoke only part of the assignment.

During scale-up:

1. New consumers start up and join the group.
2. The group detects membership changes.
3. Partition assignments are recomputed.
4. Old consumers revoke transferred partitions; new consumers receive assignments.
5. New consumers restore positions from committed offsets and resume polling.

If an old consumer processed a record but had not committed before the partition was revoked, the new consumer may read that record again. Therefore, scaling up can cause redelivery around rebalance time. Handlers must be idempotent to avoid updating a database, sending emails, or producing side effects twice.

Cooperative assignors can reduce the number of partitions revoked in each rebalance round, but do not eliminate all disruptions or all redelivery possibilities. Monitor rebalance duration, consumer lag, and logs when changing concurrency in production.

## 7. Concurrency does not split a single partition

Suppose a topic only has one partition and the consumer group has concurrency 8:

```text
Topic orders: P0

Consumer group order-service:
  Consumer A: P0
  Consumer B: no partition
  Consumer C: no partition
  Consumer D: no partition
  Consumer E: no partition
  Consumer F: no partition
  Consumer G: no partition
  Consumer H: no partition
```

Only one consumer can own P0 at a time. The remaining seven consumers cannot concurrently read different offsets of P0 within the same group under standard consumer group semantics.

If throughput is bottlenecked by a single partition, increasing concurrency will not solve that bottleneck. You may need to increase the partition count, though changing partition count can alter key mappings and affect ordering across the expansion boundary. Evaluate ordering requirements before making that change.

## 8. Preserving order by key

If a producer sends a stable key such as `orderId`, the partitioner typically routes records with the same key to the same partition. This allows Kafka to maintain append order for events related to the same order.

Example:

```java
kafkaTemplate.send("orders", event.orderId(), event);
```

Suppose events for `ORD-100` all go to `orders-2`:

```text
orders-2:
  offset 100: ORD-100 / OrderCreated
  offset 101: ORD-100 / OrderPaid
  offset 102: ORD-100 / OrderShipped
```

Increasing concurrency from 1 to 3 or 6 can only reassign `orders-2` to a different consumer member. It does not itself change which partition is chosen for key `ORD-100`, as long as partition count and partitioner do not change. Thus, read order within the partition is preserved.

If the partition count is increased, key mapping can change. This is a different change from increasing concurrency and requires separate planning. Do not confuse these two operations when investigating ordering bugs.

## 9. When does the application break ordering itself?

Even when Kafka and the listener container deliver records in the right order, the application can still finish processing out of order if it introduces concurrency inside the listener.

### Dispatching tasks to an executor and returning immediately

Dangerous example:

```java
@KafkaListener(topics = "orders", groupId = "order-service")
public void onOrder(OrderEvent event) {
    executor.submit(() -> orderService.process(event));
    // Listener finishes before the business task completes.
}
```

The container may consider the listener finished and advance progress/commits according to `AckMode`, while the background task is still running. A later record can start processing before an earlier record; if the process stops, committed offsets can prevent incomplete work from being redelivered.

### Using CompletableFuture without control

```java
@KafkaListener(topics = "orders", groupId = "order-service")
public CompletableFuture<Void> onOrder(OrderEvent event) {
    return CompletableFuture.runAsync(
            () -> orderService.process(event), executor);
}
```

Spring Kafka supports some asynchronous return types in modern versions, but acknowledgment and error behavior depend on version, listener type, and configuration. Do not assume every `CompletableFuture` automatically holds the partition until completion. Check the documentation for your version and configure async listener/acknowledgment behavior accordingly. If async processing is unnecessary, synchronous listeners are usually easier to reason about for ordering and commits.

### Using parallel streams in a batch listener

```java
events.parallelStream().forEach(orderService::process);
```

This snippet can cause records in the batch to complete out of input order. If records from the same partition represent states that must be applied sequentially, the business outcome can be wrong even though Kafka delivered the records in the right order.

## 10. How to process in parallel while preserving required ordering

If you need higher throughput while preserving per-entity order, clearly define the scope requiring serialization:

- **Per partition:** process records sequentially within a partition; allow different partitions to run in parallel. This aligns naturally with Kafka.
- **Per key/entity:** keep keys stable so an entity's records enter the same partition and are processed sequentially within that partition.
- **Topic-wide:** if every record must follow a single global order, you need one partition and one processing stream; this limits parallelism.
- **Downstream tasks:** if background dispatch is unavoidable, use a per-partition/per-key serialization mechanism and only acknowledge once prior offsets have completed contiguously.

With asynchronous processing, track completion state per partition. Only commit the next offset after a contiguous range of records has completed; never commit past an in-flight record. You must also handle shutdown/rebalance to drain or cancel tasks properly without losing progress.

## 11. How can retries affect ordering?

Distinguish between blocking retries and non-blocking retries via separate topics.

### Blocking retry

With `DefaultErrorHandler` and standard backoff, the consumer reprocesses the failing record on the partition's thread. During retries, processing of subsequent records in that partition is typically blocked, preserving processing order while pausing the partition and potentially increasing lag.

### Non-blocking retry topic

With retry topics (for example `@RetryableTopic`), failing records are routed to a retry topic for later processing. The main topic consumer can move on to the next record. Consequently, a record at a higher offset can be processed before the failing record waiting in the retry topic.

Example:

```text
Topic orders:
  offset 10: OrderCreated ── failed, routed to orders-retry
  offset 11: OrderPaid    ── processed immediately and succeeds

Topic orders-retry:
  OrderCreated retried later
```

As a result, business order for the same entity can be inverted. If ordering is a strict requirement, consider blocking retries, pausing the partition, key-aware retry design, or checking version/state before applying events. Non-blocking retry is a trade-off between continuing throughput and ordering.

## 12. Impact of AckMode and error handling

Concurrency does not change the meaning of `AckMode`, but multiple consumer members will commit offsets independently for the partitions each consumer owns.

| AckMode | Impact when increasing concurrency |
|---|---|
| `RECORD` | Each consumer commits after the listener successfully processes each record on its assigned partitions |
| `BATCH` | Each consumer commits the poll batch offsets after the batch finishes processing successfully |
| `MANUAL` | Listener acknowledges under manual rules; ensure only completed work is acknowledged |
| `MANUAL_IMMEDIATE` | Commits immediately when acknowledged on the consumer thread; do not use to commit past incomplete earlier records |

If the listener processes synchronously, the container can manage commits alongside processing progress. If the listener spawns background tasks and returns, commits can race ahead of side effects. Keep required work within the listener invocation or use async listener/acknowledgment mechanisms properly supported by your Spring Kafka version.

During a rebalance, partitions can be handed to another consumer. Uncommitted records may be read again. Do not use concurrency as an exactly-once guarantee; use idempotency or transactions aligned with your data boundaries.

## 13. Configuration and operations to avoid unnecessary rebalances

Several consumer settings affect how the group retains members and processing time:

| Property | Role |
|---|---|
| `max.poll.interval.ms` | Maximum time between polls; overly long processing can cause the member to leave the group |
| `max.poll.records` | Maximum records returned in one poll; large batches increase processing time before the next poll |
| `session.timeout.ms` | Time to detect missed member heartbeats under protocols using this setting |
| `heartbeat.interval.ms` | Heartbeat interval in consumer protocol configurations using this property |
| `partition.assignment.strategy` | Selects the partition distribution strategy when membership changes |

Do not blindly keep increasing concurrency when lag grows without finding the root cause. If the bottleneck is a database, hot key, downstream API, or a single partition, adding consumers may only increase resource contention and rebalances.

When scaling deployments, scale incrementally and observe:

- Actual number of consumer members in the group.
- Partition assignments before and after scaling.
- Rebalance count and rebalance duration.
- Consumer lag per partition.
- Listener throughput and processing latency.
- CPU, heap, connection pools, and database load.

## 14. Testing ordering when increasing concurrency

Testing must verify both partition record order and business completion order. You can construct scenarios such as:

1. Create topic `orders` with multiple partitions and send events sharing the same `orderId` as key.
2. Run a synchronous listener with concurrency 1, recording offset order and business outcome.
3. Increase concurrency to 3, send a sequence of events with the same key, and verify they still land in the same partition and are processed in order.
4. Send different keys to verify multiple partitions can be processed in parallel.
5. Scale up another application instance to trigger a rebalance; verify partition ownership changes and uncommitted records may be redelivered.
6. Make a listener throw errors and compare blocking retry against retry topics to observe ordering differences.
7. Try dispatching tasks to an executor or `parallelStream()` and measure completion order to catch application-introduced concurrency.
8. Stop the process while tasks are in progress, then restart and verify offsets, redelivery, and idempotency.

Each test record should include `eventId`, `aggregateId`/`orderId`, and business sequence/version. Log topic, partition, offset, consumer ID, and processing start/end timestamps to distinguish read order from completion order.

## 15. Summary

- Kafka preserves order within each partition; there is no total order across partitions.
- Increasing concurrency creates more consumer members and can increase parallel processing across partitions.
- A partition at any point in time is assigned to at most one consumer in a group; increasing concurrency does not split one partition across multiple consumers.
- Scaling up triggers rebalances and can redeliver uncommitted records; consumers must be idempotent.
- The same key is typically routed to the same partition; increasing concurrency does not change key mapping, whereas increasing partitions can.
- Applications can break completion order via executors, futures, or parallel processing unless serialization per partition/key is managed.
- Blocking retries generally hold the partition waiting for failing records; retry topics can let later records overtake earlier ones.
- Choose concurrency based on partition count, throughput, lag, resources, and ordering requirements; test before production rollout.

When concurrency is scaled properly, Spring Kafka can process multiple partitions in parallel while preserving order within each partition. To preserve business sequence, you must simultaneously control keys, listener execution, retries, offset commits, and rebalance behavior.
