# Partitions are Kafka's unit of ordering

Kafka organizes the data of each topic into one or more partitions. Each partition is an ordered, append-only log: the broker writes records sequentially to the log and assigns monotonically increasing offsets to each position. Consumers read a partition in offset order, so a partition is the unit of ordering that Kafka guarantees.

A topic can have multiple partitions to distribute data and enable parallel processing. In return, Kafka does not establish a total order across partitions. If two events are written to two different partitions, consumers can read and process them in parallel; it is impossible to infer which event must be observed first solely from offsets or timestamps.

When business logic requires preserving order per entity such as an order, account, or product, producers typically use the entity identifier as the record key so that related events are routed to the same partition. When business logic does not require per-entity ordering, a different key or no key can be used to take advantage of load distribution. Choosing a partitioning strategy is therefore a decision about both ordering and throughput.

This lesson belongs to the **Partitions and ordering** chapter of the **SPRING_KAFKA_MESSAGING** module. The module focuses on building applications that send and receive events using Spring Kafka, `KafkaTemplate`, and `@KafkaListener`, understanding topics, partitions, offsets, and consumer groups, while also learning serialization, retries, dead-letter handling, transactions, exactly-once semantics, concurrency, and testing to operate reliable messaging flows.

## 1. What is a partition?

A topic is the logical data stream name to which producers send records and from which consumers subscribe to read. A topic is divided into partitions. Each partition has its own log, leader replica, and independent offset sequence.

For example, the `order-events` topic has three partitions:

~~~text
Topic: order-events

Partition 0:  [offset 0] [offset 1] [offset 2] [offset 3] ...
Partition 1:  [offset 0] [offset 1] [offset 2] ...
Partition 2:  [offset 0] [offset 1] [offset 2] [offset 3] ...
~~~

These offsets only have meaning within their respective partition. A record at partition 0 offset 3 cannot be directly compared in order against a record at partition 1 offset 2. Each partition has an independent log and progress.

Partitions serve two primary goals:

- **Ordering:** Kafka maintains append and read order within each partition.
- **Parallelism:** multiple partitions allow multiple consumers in the same group to read different subsets of data in parallel.

At any given time, a partition is assigned to at most one active consumer within the same consumer group. A single consumer can receive multiple partitions. Therefore, the number of partitions sets an upper bound on read parallelism within a group, although actual throughput also depends on brokers, network, producers, consumers, and business logic.

## 2. At what scope is ordering guaranteed?

Kafka guarantees order within a partition according to the order in which records are appended to the log. When a consumer reads a partition, records are returned in offset order.

Kafka does not guarantee:

- Total order across partitions of the same topic.
- Order across different topics.
- Event order by business timestamp if producers send them out of that chronological order.
- Completion order of tasks that the application processes asynchronously on its own or dispatches to a thread pool.
- Order between records of the same entity if producers send them to different partitions.

Example:

~~~text
Partition 0:
  offset 10: OrderCreated(order-1)
  offset 11: OrderPaid(order-1)
  offset 12: OrderShipped(order-1)

Partition 1:
  offset 20: OrderCreated(order-2)
  offset 21: OrderCancelled(order-2)
~~~

In partition 0, Kafka preserves the order OrderCreated, OrderPaid, OrderShipped. In partition 1, Kafka preserves the order OrderCreated, OrderCancelled. However, there is no global order between offset 10 in partition 0 and offset 20 in partition 1.

If a consumer group has two consumers, each consumer can read one partition and process them in parallel. This is how Kafka increases throughput while still maintaining order within each partition.

## 3. How do offsets represent order?

An offset is the position of a record within a partition. When the broker appends a new record, it assigns the next offset in that partition's log.

Example:

| Partition | Record | Offset |
| --- | --- | ---: |
| 0 | OrderCreated(order-1) | 100 |
| 0 | OrderPaid(order-1) | 101 |
| 0 | OrderShipped(order-1) | 102 |
| 1 | OrderCreated(order-2) | 80 |
| 1 | OrderCancelled(order-2) | 81 |

The consumer reads partition 0 at offsets 100, 101, 102. The consumer reads partition 1 at offsets 80, 81. These offsets are not topic-wide sequence numbers; offset 102 does not mean that record always occurred after offset 81 in another partition.

An offset is also not a timestamp. An event with an earlier `occurredAt` can still be sent later by a producer and receive a higher offset. If business logic needs to sort by event time, you must design timestamps, watermarks, or a separate time-handling mechanism; you cannot use offsets across multiple partitions to construct a global chronological order.

In log compaction or with transactions, there may be offset gaps that consumers do not see as regular business records. That does not break the ordering rule: the records a consumer receives are still read according to their log positions in the partition.

## 4. Using keys to preserve per-entity ordering

A common way to preserve ordering for events of the same entity is to use the entity identifier as the key.

For example, events for the same order use `orderId`:

~~~java
@Service
@RequiredArgsConstructor
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderEvent> kafkaTemplate;

    public CompletableFuture<SendResult<String, OrderEvent>> publish(
            OrderEvent event) {

        return kafkaTemplate.send(
            "order-events",
            event.orderId(),
            event
        );
    }
}
~~~

With the default partitioner and a non-null key, the Kafka producer uses the serialized key to select a partition. Records with the same key are typically routed to the same partition within the same partition topology.

Illustrative example:

~~~text
Topic order-events has 3 partitions

key = order-1:
  OrderCreated  ─┐
  OrderPaid     ─┼──> Partition 1
  OrderShipped  ─┘

key = order-2:
  OrderCreated  ─┐
  OrderCancelled ─┴──> Partition 0
~~~

When the same `orderId` is routed to one partition, the consumer reads those events in the partition's offset order. This establishes the foundation for sequential per-order processing.

However, a key only guarantees stable routing according to the algorithm and topology in use. It does not itself verify whether events are in the correct business order. If two producers send events with the same key concurrently, the append order reflects the order in which the broker receives and processes the requests, not necessarily the business occurrence order across the two services.

## 5. Choosing keys based on business requirements

The key should represent the unit of data that needs to be processed sequentially. Some examples:

| Domain | Common key | Reason |
| --- | --- | --- |
| Orders | orderId | Preserves the order of state transitions for a single order. |
| Accounts | accountId | Serializes updates related to balance or account status. |
| Inventory | sku or warehouseId + sku | Preserves the order of stock updates for an item in a warehouse. |
| Devices | deviceId | Preserves telemetry or status order per device. |
| Customers | customerId | Serializes events related to a customer when business logic requires it. |

You should not choose a key just because that field is always present. If a key has low cardinality, for example using only `country` or `eventType`, many records can pile up into a single partition. This is the hot partition phenomenon and reduces parallelism.

A good key needs to balance two requirements:

- Events that require ordering must share the same key.
- Different keys should distribute evenly enough across partitions to prevent overloading a single partition.

If a single entity generates a very large volume of events, using a single key can create a bottleneck that cannot be solved merely by adding consumers. You should revisit the ordering requirement: does every event of that entity truly need to be serialized, or can it be split by a smaller sub-entity/aggregate?

## 6. How does the partitioner select a partition?

The producer selects a partition before sending a record to the broker. Common cases include:

1. The application specifies the partition directly in `ProducerRecord`.
2. The record has a key; the partitioner uses the serialized key to select a partition.
3. The record has no key; the partitioner uses the strategy for null keys, typically sticky partitioning in modern Kafka clients.
4. The application configures a custom partitioner to apply custom rules.

With the default partitioner, a non-null key is typically hashed and then mapped onto the available number of partitions. You can conceptualize it simply as:

\[
\text{partition} = \text{positive(hash(serializedKey))} \bmod N
\]

Where N is the number of partitions in the topic. This is a general description; the exact algorithm depends on the partitioner and Kafka client version.

The key point is that the partitioner uses the bytes of the key after serialization. If two producers use different serializers or different key normalization rules, the same business value might not produce the same bytes and will not necessarily go to the same partition.

When using a custom partitioner, ensure all producers sending the same type of key follow a consistent rule. If each service uses a different algorithm, key-based ordering can break even though the payloads contain the same `orderId`.

## 7. Sending keyless records and ordering

If a producer does not provide a key, the partitioner selects a partition using the strategy for keyless records. In modern Kafka clients, the default partitioner typically uses sticky partitioning: sticking to one partition for an interval/batch to accumulate records efficiently, and then switching to another partition.

This helps batching and throughput, but provides no entity affinity. Two events belonging to the same order can land in two different partitions if the producer does not pass `orderId` as the key.

Example:

~~~java
// No key: no guarantee that events with the same orderId land in the same partition
kafkaTemplate.send("order-events", event);

// With key: routed by orderId
kafkaTemplate.send("order-events", event.orderId(), event);
~~~

If business logic requires ordering by `orderId`, do not rely on sticky partitioning or events accidentally landing in the same partition. Pass the key explicitly.

## 8. Increasing partition count can affect key-based ordering

With a partitioner based on hashing and modulo of the partition count, changing the number of partitions can alter the key mapping result. For example, the key `order-1` previously mapped to partition 1 when the topic had three partitions; after scaling up to six partitions, that key may be routed to partition 4.

Old records remain in the old partition. New records may go to the new partition. At that point, consumers can read old and new events for the same `orderId` from two different partitions; Kafka does not guarantee ordering between them.

Therefore, increasing partitions is not a harmless change if key-based ordering is a critical requirement.

Before increasing partitions, consider:

- Can you tolerate a transition period where one key appears in both old and new partitions?
- Do you need to drain the backlog before making the change?
- Can you version the topic or create a new topic with the new topology?
- Does the consumer need to coordinate an event sequence/version to detect out-of-order events?
- Can a more stable custom partitioning approach be used?

An architecturally safe approach is to treat the partition count as part of the topic's operational contract, not something to change arbitrarily once the system has produced order-dependent data.

## 9. Producer concurrency, retries, and send order

`KafkaProducer` supports asynchronous sending and batching. Multiple threads can call `send` on the same producer; the producer manages requests and partition buffers.

For the same partition, Kafka maintains append order according to the order in which records enter the producer's send pipeline and are recorded by the broker. However, retries and multiple in-flight requests can affect ordering if the producer is not configured appropriately.

When idempotence is disabled, retries are enabled, and `max.in.flight.requests.per.connection` is greater than one, a failed batch may be resent after a newer batch, causing records to be reordered in certain scenarios. An idempotent producer helps protect order during retries using Kafka's sequence number mechanism.

Commonly considered producer configuration:

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        "enable.idempotence": true
~~~

Idempotence requires compatible related settings. Modern Kafka clients validate several constraints; if overriding retries or max in-flight requests, check the documentation for your exact client version. Idempotence protects retries at the producer layer; it does not solve cases where the application actively emits the same event twice or two producers race on business order.

If ordering of events with the same key matters, keep a clear sending rule on the producer, use a stable key, and avoid scattering the same event stream across multiple independent producers without a business sequence/version mechanism.

## 10. Consumers read sequentially within a partition

A Kafka consumer reads records in offset order for each assigned partition. Within the same consumer group, a partition at any point in time is assigned to at most one active consumer.

For example, a topic has four partitions and a group has two consumers:

~~~text
Topic order-events

Partition 0 ─┐
Partition 1 ─┼──> Consumer A
Partition 2 ─┐
Partition 3 ─┴──> Consumer B
~~~

Each consumer can receive multiple partitions, but records within each partition are still delivered in offset order. Consumer A may process partitions 0 and 1; consumer B processes partitions 2 and 3. There is no global order across records from the four partitions.

Spring Kafka's listener container manages the poll loop and invokes the listener. Example:

~~~java
@Component
public class OrderEventListener {

    @KafkaListener(
        topics = "order-events",
        groupId = "order-projection"
    )
    public void onOrderEvent(OrderEvent event) {
        orderProjection.apply(event);
    }
}
~~~

With synchronous listener processing by default, the container invokes the listener method on the consumer processing thread. When the listener completes, the container proceeds according to the configured poll/ack/commit mechanism.

## 11. Listener container concurrency and ordering

Spring Kafka lets you configure concurrency to create multiple consumers within a listener container. Concurrency enables reading multiple partitions in parallel; it does not allow a single partition to be processed concurrently by multiple consumers in the same group.

Example:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        orderListenerContainerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(4);
    return factory;
}
~~~

If the topic has four partitions, a concurrency of four allows each consumer to process one partition. If the topic only has two partitions, at most two consumers have useful assignments in the group at a time.

Increasing concurrency does not break read order within a partition as long as the container continues processing sequentially per consumer. However, if the listener itself dispatches work to a thread pool or processes asynchronously, task completion order may differ from record order.

Dangerous example:

~~~java
@KafkaListener(topics = "order-events", groupId = "order-service")
public void onOrderEvent(OrderEvent event) {
    executor.submit(() -> orderService.handle(event));
}
~~~

The listener method returns immediately after submitting. Tasks can finish in a different order, while the container can continue polling and committing as configured. If business logic requires sequential execution, you must wait for processing to finish before acknowledging the record or design an executor that serializes work by partition/key.

You should not look solely at container concurrency to conclude that ordering is guaranteed; you must inspect all logic inside the listener.

## 12. How can retries affect ordering?

When a listener fails to process a record, Spring Kafka can retry the record according to the error handler. With blocking retry on the same partition, the container can pause progress on that partition during the backoff/retry window. This prevents later records from overtaking the failing record under normal processing, but reduces throughput on that partition.

If you use non-blocking retry with retry topics, the failing record is sent to a retry topic for later processing, while subsequent records in the original topic can proceed. In that case, the business order between the failing record and later records is no longer preserved as in the original sequential stream.

Example:

~~~text
Original topic:
  OrderCreated(order-1)
  OrderPaid(order-1)       -> failed, moved to retry topic
  OrderShipped(order-1)    -> processed before OrderPaid retry succeeds

Retry topic:
  OrderPaid(order-1)       -> processed later
~~~

If order states must transition in strict order, consider blocking retries, sequence numbers, or version-checking logic on the consumer. Retry topics improve fault isolation and throughput, but can change completion order.

With Spring Kafka, non-blocking retries have limitations and semantics that depend on how retry topics are configured and the version in use. Consult the corresponding documentation before combining them with batch listeners or transactions.

## 13. Rebalances do not alter log order

A rebalance occurs when a consumer group changes its members, topic subscriptions, or partition assignments. Partitions can be transferred from one consumer to another.

A rebalance does not reorder records in a partition. The log and offsets preserve append order. The new consumer resumes reading from the group's committed offset according to the configured policy.

However, uncommitted records may be redelivered after a rebalance. This creates duplicates, not out-of-order log entries from Kafka. The application needs idempotency if reprocessing the same event could cause duplicate side effects.

If the listener processes asynchronously or commits at the wrong time, business completion order may differ from log order even though Kafka still delivers records in offset order.

## 14. Timestamps do not replace partition ordering

Kafka records carry timestamps, but timestamps do not create a global order. Multiple records across different partitions can have identical timestamps, or a record can arrive with a later timestamp even though the event occurred earlier.

Depending on configuration, a timestamp can be `CreateTime` set by the producer or `LogAppendTime` assigned by the broker. The two modes have different semantics:

- **CreateTime:** the timestamp reflects when the record was created according to the producer.
- **LogAppendTime:** the broker assigns the timestamp when appending the record to the log.

Clocks across producers can drift; events can be delayed in transit; retries can make the append time differ from the business occurrence time. Therefore, you should not rely on timestamps alone to deduce the exact order of events across an entire topic.

If business logic needs to detect out-of-order events, you can include a monotonically increasing sequence/version per aggregate in the payload and validate it on the consumer. Timestamps are useful for observability and event-time processing, whereas sequence/version validates business ordering.

## 15. Transactions and ordering

Kafka transactions allow a producer to write multiple records within a single transaction and commit or abort that batch of writes atomically. Transactions enable consumers using `read_committed` to read only records belonging to committed transactions.

Transactions do not establish a total order across partitions. Within one transaction, records can be written to multiple partitions; consumers read each partition in its own order and there is no overall ordering across them.

When using a transactional producer, configure a unique transaction ID prefix across instances. If consumers must only see committed records, configure the appropriate isolation level. Transactions provide atomicity for a group of Kafka operations within the supported scope; they do not replace keys/partitioning for maintaining per-entity order.

## 16. Testing partition-based ordering

Ordering tests should focus on what the system actually guarantees:

1. Send multiple events with the same key to a topic.
2. Wait for the producer sends to complete.
3. Have a consumer read from the corresponding partition.
4. Verify offset order and business sequence.
5. Check that events with the same key land in the same partition in the topology under test.
6. Send different keys to verify they can be distributed to other partitions, without assuming exact partition numbers unless the partitioner/topology is fixed.
7. Test retries and rebalances if those flows are part of the requirements.

Example event with sequence:

~~~java
public record OrderEvent(
    String orderId,
    long sequence,
    String eventType
) {}
~~~

A test can send a sequence of events:

~~~java
@Test
void eventsForSameOrderShouldBeWrittenToSamePartitionInOrder()
        throws Exception {

    kafkaTemplate.send(
        "order-events",
        "order-100",
        new OrderEvent("order-100", 1, "CREATED")
    ).get(10, TimeUnit.SECONDS);

    kafkaTemplate.send(
        "order-events",
        "order-100",
        new OrderEvent("order-100", 2, "PAID")
    ).get(10, TimeUnit.SECONDS);

    kafkaTemplate.send(
        "order-events",
        "order-100",
        new OrderEvent("order-100", 3, "SHIPPED")
    ).get(10, TimeUnit.SECONDS);

    // The test consumer reads the partition and asserts sequences 1, 2, 3.
}
~~~

This is an illustrative skeleton; a complete test needs to provision the topic/broker, set up a test consumer with its own group, configure offsets, and wait for all three records. You should assert that the records share the same partition and have ascending sequences in the order received.

Do not write tests requiring every distinct key to land in a different partition. Hash collisions can occur and the partition count is finite; multiple keys can still share the same partition.

## 17. Common misconceptions

| Misconception | Accurate understanding |
| --- | --- |
| Kafka guarantees order across the entire topic. | Kafka guarantees order within each individual partition. |
| A higher offset in one partition means the record is newer than in another partition. | Offsets only have meaning within the partition that contains them. |
| The same key always guarantees business order regardless of producer. | The same key supports routing to the same partition; multiple concurrent producers still need sequencing/coordination if business order matters. |
| A key inside JSON is automatically used for partitioning. | The producer partitioner uses the record key; it does not inspect fields inside the value. |
| Increasing partitions does not affect ordering. | Key mapping can change; old and new records for the same key may reside in different partitions. |
| Increasing concurrency allows a single partition to be processed safely in parallel. | Within the same group, a partition at any time is assigned to at most one consumer. |
| A listener returning immediately after submitting to a thread pool still preserves completion order. | Async tasks can finish out of order and commits can advance past processing. |
| Retry topics always preserve the original order. | Non-blocking retries can allow later records to be processed before the failing record. |
| Timestamps create a global order. | Timestamps can drift, collide, or arrive late; they do not replace partition ordering. |
| Rebalances reorder the log. | Rebalances change partition ownership; log order and offsets remain unchanged. |

## 18. Ordering design checklist

Before designing a topic and producer, answer these questions:

1. Which business unit needs to be processed sequentially: order, account, device, or another aggregate?
2. Does the record key stably represent that unit?
3. Do all producers use the same serialization and key partitioning rules?
4. Does the partition count provide enough throughput while still aligning with ordering requirements?
5. Is there a plan for scaling partitions and evaluating old/new key mappings?
6. Does the producer enable idempotence and configure retries/in-flight requests appropriately?
7. Does the listener process sequentially within a partition or dispatch asynchronously?
8. Are retries blocking or non-blocking, and is changing completion order acceptable?
9. Is there a sequence/version to detect out-of-order events?
10. Do tests verify ordering by partition and key without assuming topic-wide ordering?

A partition is Kafka's ordering boundary. To preserve order for an entity, the producer must route that entity's events to the same partition using a stable key; the consumer must process them in order without breaking ordering through thread pools, retries, or commits. Multiple partitions enable parallelism, but ordering across them is the responsibility of the application's business design.

