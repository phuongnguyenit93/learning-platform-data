# Ordering across multiple partitions

Kafka guarantees record order within each individual partition. When a topic has multiple partitions, each partition is an independent log with its own offsets and leader. Producers can write concurrently to multiple partitions, and a consumer group can read multiple partitions in parallel. In return, Kafka does not provide a total order across all records in a topic.

When designing a Spring Kafka application, determine the exact ordering scope your business logic needs: no ordering across entities, per-key ordering, or a global order for all events. Each requirement leads to different partitioning, publishing, and consumption strategies. Increasing the partition count can increase parallelism, but does not add a shared ordering stream.

## 1. Why do multiple partitions lack a total order?

A topic is divided into multiple partitions. Each partition has its own log, its own offsets, and potentially a leader on a different broker.

For example, topic `orders` has three partitions:

```text
orders-0:
  offset 0 -> OrderCreated(order-101)
  offset 1 -> PaymentRequested(order-101)
  offset 2 -> OrderConfirmed(order-101)

orders-1:
  offset 0 -> OrderCreated(order-202)
  offset 1 -> PaymentRequested(order-202)

orders-2:
  offset 0 -> OrderCreated(order-303)
  offset 1 -> PaymentRequested(order-303)
```

You can state with certainty that the record at offset 0 of `orders-0` comes before the record at offset 1 of the same partition. However, you cannot use offsets to conclude whether the record at `orders-0` offset 2 occurred before or after the record at `orders-1` offset 1.

Each partition has local ordering:

- `orders-0` is ordered by the offsets of partition 0.
- `orders-1` is ordered by the offsets of partition 1.
- `orders-2` is ordered by the offsets of partition 2.

There is no shared global offset for the entire topic. Kafka also does not provide a global ordering clock for records across different partitions.

## 2. Producers writing concurrently to multiple partitions

A producer chooses a partition for each record through one of these mechanisms:

- Based on the key and partitioner.
- Application-specified partition in `ProducerRecord`.
- A custom partitioner deciding the partition.
- For keyless records, the partitioner may use a distribution strategy such as sticky partitioning.

One producer can have multiple batches in flight to different partitions simultaneously. The broker handles each partition independently; append order is guaranteed within each partition, establishing no ordering relationship across partitions.

Example:

```text
Producer sends:
  Event A -> orders-0
  Event B -> orders-1
  Event C -> orders-2

Broker may append:
  orders-2: Event C
  orders-0: Event A
  orders-1: Event B
```

This outcome does not violate Kafka ordering because the three records belong to three independent logs. If business logic requires Event A to be recorded before Event B topic-wide, a multi-partition design cannot enforce that requirement on its own.

Even if a single thread calls `send(A)` then `send(B)`, if A and B go to different partitions, there is no global append order that consumers can rely on. Completion futures for the two sends can also finish in a different order than the call order.

## 3. Distinguishing three ordering levels

Before choosing a partition count, classify the requirement:

| Ordering level | Example | Appropriate design |
|---|---|---|
| No order needed across events | View tracking, telemetry, independent updates | Multiple partitions and parallel consumers |
| Order by key/entity | Events for the same `orderId` or `accountId` | Stable key so events of the same entity land in one partition |
| Global order | Every transaction must follow one sequence | Single partition or centralized sequencing mechanism |

Most business systems do not require every event across the entire system to follow an absolute order. Usually only per-aggregate or per-entity ordering is needed. Choosing the right scope lets you leverage parallelism without forcing the entire topic into a single partition.

## 4. Preserving per-key ordering across multiple partitions

The common approach is to use a key representing the entity whose order must be preserved. With the default partitioner, records with the same key are typically hashed to the same partition, provided the topic retains the same partition count and partitioning strategy.

Example of a producer sending order events:

```java
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

@Service
class OrderPublisher {

    private final KafkaTemplate<String, OrderEvent> kafkaTemplate;

    OrderPublisher(KafkaTemplate<String, OrderEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    void publish(OrderEvent event) {
        kafkaTemplate.send(
                "orders",
                event.orderId(),
                event
        );
    }
}
```

If all events for `order-101` use key `order-101`, they go to the same partition under the same partitioning strategy. Events for `order-202` can be sent to another partition and processed in parallel.

Example:

```text
key=order-101 -> orders-0:
  OrderCreated
  PaymentRequested
  OrderConfirmed

key=order-202 -> orders-1:
  OrderCreated
  PaymentRequested

key=order-303 -> orders-2:
  OrderCreated
  PaymentRequested
```

Kafka preserves order within each partition. Therefore, events with the same key can be consumed in offset order within that partition, while different keys run in parallel.

This approach is often called per-key ordering or per-entity ordering. It does not establish an order between `order-101` and `order-202`.

## 5. Choose keys by aggregate, not by event type

The key should reflect the object whose events must be processed in order. Examples:

| Data stream | Key to consider | Why |
|---|---|---|
| Order lifecycle | `orderId` | State transitions of a single order must be sequential |
| Account balance | `accountId` | Transactions on the same account must follow sequence |
| Customer profile | `customerId` | Updates for the same customer must be consistent |
| IoT device | `deviceId` | Events for a single device have their own order |
| Inventory | `sku` or `warehouseId + sku` | Stock updates for the same item must be sequential |

Do not choose the event type as the key if multiple event types for the same entity must follow an order. For example, keys `OrderCreated` and `PaymentRequested` can route the two event types to different partitions; this choice does not keep events of the same order in the same partition.

A good key typically has these characteristics:

- Stable throughout the entity's lifecycle.
- Non-null if business logic requires per-entity ordering.
- Well-distributed enough to avoid concentrating too much load on one partition.
- Used uniformly by all producers.
- Does not vary in format or serialization across services in ways that alter key hashes.

## 6. Why don't timestamps establish cross-partition ordering?

Records carry timestamps, yet timestamps are not a global sequence.

Producers may run on different machines with clock skew. Two concurrent events can share the same timestamp. Brokers use `CreateTime` or `LogAppendTime` depending on configuration, yet record timestamps across two partitions still do not establish a global append relationship.

Example:

```text
orders-0:
  offset 10, timestamp 10:00:00.100 -> OrderCreated

orders-1:
  offset 22, timestamp 10:00:00.090 -> PaymentRequested
```

You cannot rely solely on timestamps to conclude that `PaymentRequested` actually happened before `OrderCreated`. Timestamps can be affected by clock skew, network latency, batching, and how the broker records them.

If business logic needs sorting by event time, use event time with watermarks and late-event handling rules. That is an event-time data processing problem, not a Kafka ordering guarantee.

## 7. How does a consumer group read multiple partitions?

Within a consumer group, each partition is assigned to at most one consumer member at a time. A single consumer can receive multiple partitions. When there are multiple consumers, Kafka distributes partitions according to the assignor.

For example, a topic has 6 partitions and a group has 3 consumers:

```text
Consumer A -> orders-0, orders-1
Consumer B -> orders-2, orders-3
Consumer C -> orders-4, orders-5
```

Each consumer reads its assigned partitions and preserves order within each partition. However, the consumer does not establish a shared order across the partitions it reads.

If the group has concurrency greater than 1 in Spring Kafka, the container creates consumer threads. Threads process assigned partitions independently; records in another partition may be handled or completed earlier by the listener.

`@KafkaListener` with concurrency:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
class OrderProjectionListener {

    @KafkaListener(
            topics = "orders",
            groupId = "order-projection",
            concurrency = "3"
    )
    public void onOrder(OrderEvent event) {
        projectionService.apply(event);
    }
}
```

Concurrency enables processing multiple partitions in parallel. It does not guarantee global order. If per-key ordering is required, the producer must ensure the same key goes to the same partition and the consumer must preserve processing order within that partition.

## 8. Batch polls have no global ordering across partitions

A single `poll()` can return records from multiple partitions. Records are ordered within each partition, but the application should not rely on the iteration order of the whole batch to infer order across partitions.

For example, a batch contains:

```text
orders-0: offset 10, 11, 12
orders-1: offset 7, 8
orders-2: offset 20, 21
```

You can process each partition sequentially by offset, but there is no basis to say `orders-0` offset 10 must be processed before `orders-1` offset 7.

With a batch listener, if logic requires local ordering, group records by topic-partition and process each group in offset order. Do not impose ordering across groups:

```java
import java.util.List;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.Map;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.TopicPartition;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
class BatchOrderListener {

    @KafkaListener(
            topics = "orders",
            groupId = "order-batch",
            containerFactory = "batchFactory"
    )
    public void onBatch(
            List<ConsumerRecord<String, OrderEvent>> records) {

        Map<TopicPartition, List<ConsumerRecord<String, OrderEvent>>> byPartition =
                new HashMap<>();

        for (ConsumerRecord<String, OrderEvent> record : records) {
            TopicPartition topicPartition =
                    new TopicPartition(record.topic(), record.partition());
            byPartition.computeIfAbsent(
                    topicPartition,
                    ignored -> new ArrayList<>()
            ).add(record);
        }

        for (List<ConsumerRecord<String, OrderEvent>> partitionRecords
                : byPartition.values()) {
            partitionRecords.sort(
                    Comparator.comparingLong(
                            (ConsumerRecord<String, OrderEvent> record) ->
                                    record.offset()
                    )
            );

            for (ConsumerRecord<String, OrderEvent> record : partitionRecords) {
                log.info(
                        "key={}, partition={}, offset={}",
                        record.key(),
                        record.partition(),
                        record.offset()
                );
            }
        }
    }
}
```

Do not sort all records solely by offset because offsets across partitions are not on the same scale. If you need to merge by a business field such as sequence or event time, define explicit merge rules.

## 9. When is global ordering needed?

If every event must follow a single order, the simplest approach is writing all of them to a single partition. One partition has one leader and one ordered log, so every record appended to that partition shares a single offset position sequence.

Example:

```text
events-0:
  offset 0 -> AccountOpened
  offset 1 -> MoneyDeposited
  offset 2 -> MoneyWithdrawn
  offset 3 -> AccountClosed
```

In return, a single partition limits the topic's write and read parallelism. A consumer group can also assign that partition to only one consumer at a time. This is the trade-off between global ordering and throughput/parallelism.

One partition produces a single append order established by the broker. If multiple producers send concurrently, that order is still the order in which the broker processes requests; it does not automatically know the business order the producers intend. When global business sequence must be guaranteed, the application must serialize event emission or use a sequencer/owner responsible for coordination before sending.

A single-partition topic fits when:

- Traffic volume is small or moderate.
- Every event genuinely needs one shared sequence.
- Latency and throughput targets can be met with one partition.
- The system accepts a single point of parallelism limit.

Do not use a single partition merely for simplicity. If ordering is only needed per account or per order, per-key ordering usually scales better.

## 10. Using sequence numbers to merge multiple partitions

If data must be written across multiple partitions yet consumers need to reconstruct a shared business order, the application can attach a sequence number or global event number.

Example:

```java
public record BusinessEvent(
        long globalSequence,
        String aggregateId,
        String eventType,
        String payload
) {
}
```

Consumers can use the sequence to check which event came first and which came after. However, merely adding a sequence number is not enough to achieve ordering. The consumer must have mechanisms to:

1. Track the next expected sequence.
2. Buffer events arriving ahead of or out of the desired order.
3. Detect gaps when a sequence is missing.
4. Wait for missing events or apply a timeout.
5. Handle duplicates and stale sequences.
6. Recover after restarts without losing the buffer.

Example of a consumer receiving sequence 12 before sequence 11:

```text
Expected sequence = 11

Received 12:
  buffer event 12
  wait for event 11

Received 11:
  process 11
  process buffered 12
  Expected sequence = 13
```

This is resequencing. It requires state and can increase latency. If event 11 is lost or never emitted, the consumer needs timeout, alerting, or gap-handling policies.

A global sequence must also be issued by a sequential mechanism. If each producer increments an in-memory counter, instances can generate duplicate or out-of-order sequences. You can use a database sequence, transactional outbox, or centralized sequencing service, while coordinating sequence issuance with publish order so false gaps are not created.

## 11. How should a resequencer manage state?

A resequencer typically maintains state per stream to be ordered. For global ordering, state is shared across the whole stream; for per-aggregate ordering, state can be partitioned by aggregate ID.

Basic components:

| Component | Responsibility |
|---|---|
| Expected sequence | Next sequence number to process |
| Pending buffer | Events received while preceding events are still missing |
| Duplicate detection | Identifies already processed events or stale sequences |
| Gap timer | Detects sequences missing for too long |
| Recovery state | Persists expected sequence and buffer for restart recovery |
| Poison/gap handling | Decides whether to halt, alert, skip, or route to an error stream |

Do not let the pending buffer grow unbounded. Bound event count, size, and wait duration; if thresholds are exceeded, raise alerts and apply a recovery policy.

If events arrive from multiple partitions, the consumer must manage offset commits carefully. Do not commit the offset of a buffered event as if it had completed business processing unless buffer recovery is durably persisted. You can store events in a durable store before committing Kafka offsets, or use a stateful stream processor design with proper checkpointing.

## 12. Kafka Streams and repartitioning by key

Kafka Streams lets you process, group, and repartition data by key. When per-key ordering is needed, a repartition operation by aggregate ID can bring records with the same key into the same partition of an internal topic.

Conceptual example:

```java
KStream<String, OrderEvent> orders = builder.stream("orders");

KStream<String, OrderEvent> byOrderId =
        orders.selectKey((oldKey, event) -> event.orderId())
              .repartition();

byOrderId.processValues(() -> new OrderStateProcessor());
```

Records with the same key are processed in the same partition after repartitioning. Kafka Streams preserves per-partition record order within the topology, but does not establish global ordering across partitions. If a global order is needed, the repartition topic must also have a single partition or application-level sequencing/resequencing is required.

Repartitioning helps normalize keys when an upstream topic uses an unsuitable key. It does not repair business order that was already lost before records entered the topology.

## 13. Retries and dead-letter handling can affect ordering

When a record fails, the retry strategy determines whether later records proceed.

With blocking retries in the listener container, the consumer typically pauses progress on the affected partition while retrying or recovering the record, helping prevent later records from overtaking the failing record depending on error handler configuration.

With non-blocking retries using retry topics, the failing record is routed to a retry topic and subsequent records on the original topic can continue processing. This increases throughput, but can invert per-key business order:

```text
Original topic:
  offset 10 -> OrderCreated
  offset 11 -> PaymentRequested (failed, moved to retry topic)
  offset 12 -> OrderConfirmed (processed immediately)

Retry topic:
  PaymentRequested processed later

Resulting side effects:
  OrderCreated
  OrderConfirmed
  PaymentRequested
```

If strict per-key ordering is required, carefully evaluate blocking retries, partition pausing, or sequenced retry designs. Do not adopt retry topics by default while ignoring their ordering impact on subsequent events.

Dead-letter topics store unprocessable records for investigation or reprocessing. When replaying from a DLT, check the aggregate sequence/version and avoid overwriting newer state with stale side effects.

## 14. Changing partition count affects per-key ordering

With the default hash partitioner, the partition is selected from the key and current partition count. When increasing partitions, the same key may map to a different partition.

Example:

```text
Before scaling:
  order-101 -> orders-1

After scaling:
  order-101 -> orders-4
```

Old events for `order-101` remain in partition 1, while new events may land in partition 4. The two partitions have separate offsets, so consumers cannot infer continuous order between old and new events from offsets alone.

If per-key ordering is a critical requirement:

- Size the partition count based on long-term load forecasts.
- Have a migration plan whenever partition counts must increase.
- Consider a stable partitioner or versioned sharding strategy.
- Carry an aggregate sequence in events to detect broken order.
- Consider switching to a new topic with a controlled cutover if topology changes are needed.

Do not arbitrarily increase partitions on a topic with per-key ordering requirements without assessing the impact.

## 15. Consumer concurrency and side effects

Even when a producer writes in exact order to one partition, the consumer can still apply side effects out of order if the application hands records off to an executor or processes asynchronously.

Example:

```text
Partition orders-0:
  offset 10 -> OrderCreated
  offset 11 -> PaymentRequested
  offset 12 -> OrderConfirmed

Worker pool:
  task 10: takes 500 ms
  task 11: takes 100 ms
  task 12: takes 50 ms
```

Task 12 can finish before task 10. Kafka cannot control database write order once the listener offloads work to another thread.

To preserve end-to-end order:

- Process records sequentially within each partition.
- If parallel processing is needed, use per-key queues/workers so the same key always enters one sequential pipeline.
- Commit offsets only once the corresponding work has completed under the chosen semantics.
- Use optimistic locking or aggregate versions to prevent stale updates from overwriting newer state.
- Make handlers idempotent because records may be redelivered after failures or rebalances.

Spring Kafka concurrency increases consumer threads; it does not create global ordering across partitions. Within the same group, a partition is assigned to one consumer member at a time, though one consumer can manage multiple partitions.

## 16. Choosing an ordering strategy by requirement

| Requirement | Strategy | Trade-off |
|---|---|---|
| No order needed between events | Multiple partitions, parallel consumers | High throughput, simple logic |
| Per-entity ordering | Key by aggregate ID | Parallel across entities, sequential per entity |
| Global ordering | Single partition or centralized sequencer | Throughput limit, increased coordination |
| Merge multi-partition events by sequence | Sequence number + resequencer | Requires buffers, durable state, and gap handling |
| Re-key upstream stream | Kafka Streams repartition | Adds internal topic and data movement cost |
| Retries while preserving order | Blocking retry or sequenced retry | Can reduce throughput and increase latency |

No `acks`, `retries`, or `concurrency` setting creates global ordering across multiple partitions. That is an architectural decision about how logs are partitioned and how the application coordinates events.

## 17. Verifying ordering across multiple partitions

When testing, create events containing an aggregate ID and sequence number:

```java
public record OrderEvent(
        String orderId,
        long sequence,
        String eventType
) {
}
```

Producer emits events for multiple orders:

```java
kafkaTemplate.send(
        "orders",
        "order-101",
        new OrderEvent("order-101", 1, "OrderCreated")
);

kafkaTemplate.send(
        "orders",
        "order-101",
        new OrderEvent("order-101", 2, "PaymentRequested")
);

kafkaTemplate.send(
        "orders",
        "order-202",
        new OrderEvent("order-202", 1, "OrderCreated")
);
```

Consumer logs partition, offset, and sequence:

```java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;

@KafkaListener(topics = "orders", groupId = "orders-audit")
public void audit(ConsumerRecord<String, OrderEvent> record) {
    OrderEvent event = record.value();

    log.info(
            "orderId={}, sequence={}, partition={}, offset={}",
            event.orderId(),
            event.sequence(),
            record.partition(),
            record.offset()
    );
}
```

Points to verify:

1. Events with the same `orderId` go to the same partition.
2. Offsets increase with sequence within each entity.
3. Events of different entities can reside in different partitions and be processed in parallel.
4. Do not compare offsets of two partitions as a shared order.
5. Test with consumer concurrency greater than 1.
6. Test retries, rebalances, and DLT replays if ordering is a key requirement.
7. Test partition expansion in a test environment if the design allows changing partition counts.

If global ordering is required, also test sequence issuance, buffering, gap detection, and resequencer state recovery. Observing timestamps or callback completion times alone is insufficient.

## 18. Common misconceptions

| Misconception | Reality | Resolution |
|---|---|---|
| A higher offset means a newer event topic-wide | Offsets belong only to a single partition | Compare within the same topic-partition |
| Timestamps determine cross-partition order | Clock skew and broker timing can differ | Use sequences or business event-time watermarks |
| Same key guarantees global order | Same key only selects the same partition via partitioner | Use one partition or a sequencer if global order is required |
| Increasing concurrency still keeps all events ordered | Consumers process partitions independently | Define ordering scope and serialize per key |
| One poll returns a topic-wide ordered list | A batch can contain records from multiple independent partitions | Process per partition or use explicit merge rules |
| Retry topics preserve original topic order | Non-blocking retries allow later events to overtake | Choose a retry strategy matching ordering requirements |
| Kafka transactions create global order | Transactions ensure atomic visibility, not cross-partition total order | Use keys/partitions or sequencing |
| Increasing partitions does not affect keys | Hash mapping can switch partitions | Plan migration and sequence validation |

## 19. Checklist for designing ordering across multiple partitions

1. Determine whether business logic needs global ordering, per-key ordering, or no ordering.
2. Choose keys by the aggregate/entity that requires sequential processing.
3. Ensure all producers follow the same key and partitioning conventions.
4. Do not use timestamps or offsets to infer ordering across partitions.
5. Keep consumer processing sequential within a partition if side effects require ordering.
6. If processing asynchronously, use workers/queues ordered by key.
7. Evaluate retry topics and DLTs since they can alter side-effect order.
8. Plan ahead for partition count changes.
9. Use sequence/version numbers to detect gaps or out-of-order events.
10. If global ordering is mandatory, consider a single partition or centralized sequencer and accept throughput limits.

Kafka provides local ordering within each partition. To maintain order across multiple partitions, the application must define its ordering scope and add an appropriate strategy: keys for per-entity ordering, a single partition for a global log, or sequences/resequencers to merge multiple streams. Choosing the right scope lets the system utilize parallelism while protecting required business order.
