# Trading off ordering and throughput

Kafka is designed to process data in parallel by dividing a topic into multiple partitions. Each partition is its own ordered log. Consequently, Kafka can increase throughput by letting multiple producers, brokers, and consumers handle different partitions simultaneously, while global ordering across partitions is not guaranteed.

This is a core trade-off in messaging design: the finer you split data streams for parallel processing, the more precisely the application must define which ordering scope truly matters. With Spring Kafka, this decision affects keys sent via `KafkaTemplate`, topic partition counts, `@KafkaListener` concurrency, asynchronous handling, and retry strategies.

The goal is usually not preserving order for every record across the entire system. The goal is preserving order at the required business scope, such as by `orderId` or `accountId`, while allowing independent entities to be processed in parallel.

## Learning objectives

After this lesson, you can:

- Explain the ordering scope Kafka guarantees and the limits of cross-partition ordering.
- Choose message keys to preserve order per aggregate or business entity.
- Analyze the impact of partition count, consumer concurrency, and hot partitions on throughput.
- Configure producer batching, compression, idempotence, and in-flight requests while preserving per-partition order.
- Identify how asynchronous processing, retry topics, and replays can alter side-effect order.
- Design Spring Kafka listeners that process sequentially within each partition and in parallel across partitions.
- Select the right strategy among strict ordering, per-key ordering, and high throughput.
- Test ordering under retries, rebalances, multiple producers, and partition count changes.

## 1. Where does Kafka guarantee ordering?

Kafka guarantees record order within the same partition by offset. A record appended earlier has a smaller offset and is read earlier in that partition.

For example, topic `orders` has three partitions:

~~~text
Topic orders

Partition 0:  offset 10 -> Order A created
              offset 11 -> Order A paid
              offset 12 -> Order A shipped

Partition 1:  offset 20 -> Order B created
              offset 21 -> Order B cancelled

Partition 2:  offset 30 -> Order C created
              offset 31 -> Order C paid
~~~

In partition 0, the consumer reads offset 10 before 11 and 12. Kafka defines no ordering relationship between offset 12 of partition 0 and offset 20 of partition 1. The two partitions can be written by producers and processed by consumers simultaneously.

This creates two distinct scopes:

- **In-partition ordering:** Kafka preserves log order by offset.
- **Topic-wide ordering:** Kafka does not provide a total order across partitions.

A record with an earlier timestamp in partition 1 can still be processed by a consumer after a record with a later timestamp in partition 0. Timestamps do not create a global ordering clock for a topic.

### Why do partitions impose this boundary?

Each partition is an independent log. Kafka can distribute partitions across different brokers and consumers. As a result, partitions are written and read in parallel.

~~~mermaid
flowchart LR
    P["Producer"] --> T["Topic"]
    T --> A["Partition 0"]
    T --> B["Partition 1"]
    T --> C["Partition 2"]
    A --> CA["Consumer A"]
    B --> CB["Consumer B"]
    C --> CC["Consumer C"]
    CA --> SA["Parallel processing"]
    CB --> SA
    CC --> SA
~~~

If a global order for all records is required, records must pass through one stream capable of serializing order, usually a single partition and a sequential consumer. That limits parallelism. Most systems only need ordering per entity or per business group.

## 2. Choose ordering scope before choosing partition count

Before increasing partitions or concurrency, identify which events must be processed in sequence.

Example:

| Business domain | Typically needed ordering scope |
|---|---|
| Orders | By `orderId` |
| Accounts and balances | By `accountId` |
| Customer profiles | By `customerId` |
| IoT device state | By `deviceId` |
| Independent telemetry metrics | Usually no per-entity ordering needed |
| Audits needing one global sequence | Needs a sequencer or custom ordering design; multiple partitions do not provide global order automatically |

If all events for one order must be applied in create, pay, ship order, route events with the same `orderId` to the same partition. Different orders can live in different partitions and be processed in parallel.

If the chosen key is too broad, such as every event sharing one common key, all data concentrates into one partition. Order is preserved, yet throughput is capped by that single partition.

If the key is too narrow or changes across events of the same entity, events can land in different partitions and lose per-entity ordering guarantees.

## 3. Message keys preserve per-entity order

With the default partitioner, the Kafka producer uses the serialized key to determine the partition. The same key is typically routed to the same partition while partition count and partitioning algorithm remain unchanged.

Example sending order events using `orderId` as the key:

The example uses the Spring Kafka 3.x API, where `KafkaTemplate.send()` returns `CompletableFuture`:

~~~java
@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderEvent> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderEvent>> publish(
            OrderEvent event) {

        return kafkaTemplate.send(
                "orders",
                event.orderId(),
                event
        );
    }
}
~~~

If `orderId` is `order-100`, events for that order are routed to the same partition under stable partition mapping. The consumer reads the partition by offset and can observe the order's event stream in append order.

Example:

~~~text
Key = order-100
        |
        v
Partitioner
        |
        v
Partition 2

Partition 2:
offset 50 -> OrderCreated(order-100)
offset 51 -> OrderPaid(order-100)
offset 52 -> OrderShipped(order-100)
~~~

Keys must be stable and meaningful to the business domain. Do not use a brand-new random key per event if `orderId` ordering is needed. Also do not use one shared key for the entire topic unless serializing every event is genuinely required.

### Keys do not automatically establish business order across multiple producers

The key only determines where a record is written. If multiple independent producers emit events for one `orderId`, Kafka appends records in the order the broker receives and processes requests. Function call order across separate processes does not automatically create a shared causal order.

If two services can emit versions of the same aggregate, use a proper coordination mechanism, such as:

- Designating one service as owner for emitting events of that aggregate.
- Using a monotonically increasing version or sequence number per aggregate.
- Having consumers validate the version before applying changes.
- Using a transactional outbox to emit events in database commit order.
- If necessary, using a sequencer or sequential queue per aggregate.

Keys help converge records into the same partition; they do not replace rules that determine which event must occur first in business logic.

## 4. Keyless records and load distribution

If a producer sends records without a key, modern Kafka clients use sticky partitioning to distribute records. A producer can stick to one partition for a window to accumulate batches efficiently and then switch to another partition; exact behavior depends on client version and configured partitioner.

This helps distribute keyless records and leverage batching. However, it does not guarantee events of the same entity land in the same partition. Therefore, do not use keyless records when ordering by `orderId`, `accountId`, or `deviceId` is needed.

| Send style | Goal | Per-entity ordering |
|---|---|---|
| Stable key | Route events with the same key into one partition | Yes, if mapping is unchanged and producer order is controlled |
| No key | Load distribution and batching | No per-entity guarantee |
| One shared key | Serialize all records in one partition | Ordered in partition, yet throughput is capped |
| Random key per record | Spread load | Does not preserve order for the same entity |

For independent telemetry or metrics, keyless records can be a good fit. For aggregate events, use the aggregate identifier as the key.

## 5. Partition count: scaling throughput and ordering trade-offs

More partitions allow more consumers in the same group to process in parallel. If a topic has P partitions, the number of consumer members that can actively receive partitions in a group cannot exceed P.

Example:

~~~text
6 partitions + concurrency 3

P0, P1 -> Consumer 1
P2, P3 -> Consumer 2
P4, P5 -> Consumer 3
~~~

When concurrency increases from 1 to 3, three consumers can handle different partitions simultaneously. Yet a single partition is still assigned to only one member in the same group at a time.

Adding partitions can improve overall throughput if:

- Producers supply enough data to distribute across partitions.
- Consumers have enough parallel processing capacity.
- Brokers and target systems still have headroom.
- Keys are not heavily skewed onto a few partitions.

In return, more partitions increase logs, files, metadata, replication traffic, and group management overhead. Do not increase partitions merely to set a large concurrency number.

### Increasing partitions can affect key-based ordering

With the default partitioner based on key hashing, the chosen partition depends on the partition count. When increasing partitions, the same key can map to a new partition.

Example:

~~~text
Before increasing partitions:
order-100 -> P1
offset 80  -> OrderCreated
offset 81  -> OrderPaid

After increasing partitions:
order-100 -> P4
P4 offset 0 -> OrderShipped
~~~

Old records remain in P1; new records may go to P4. Kafka does not move a key's history from old partitions to new partitions and does not create a shared order between P1 and P4.

If per-key ordering must hold across an aggregate's lifecycle, do not change partition counts arbitrarily. You can create a new topic version, perform a migration with clear boundaries, or use an application-managed stable partitioning strategy. Test key mappings before and after the change.

## 6. Hot keys and the throughput limit of a single partition

If one key receives most of the traffic, every record for that key must go through the same partition to preserve order. That partition becomes a hot partition.

Example:

~~~text
Topic with 8 partitions

P0:  5% traffic
P1:  7% traffic
P2:  6% traffic
P3:  8% traffic
P4:  9% traffic
P5:  5% traffic
P6:  4% traffic
P7: 56% traffic  <- hot key / hot partition
~~~

Increasing concurrency cannot split one partition across multiple consumers in the same group. Other partitions may sit idle while P7 builds lag.

Mitigations depend on business requirements:

- Optimize processing for the hot key: cut database queries, trim payloads, cache, or batch side effects.
- Split the entity if business rules genuinely allow independent subsets of data to use separate keys.
- Partition an aggregate into sub-keys when ordering is only needed per subset.
- Use a dedicated pipeline for the hot key to allocate resources and control latency.
- If order across the entire hot key must remain intact, accept the partition's sequential limit and optimize processing capacity on that partition.

Do not append a random suffix to the key just to spread load if the entity's events still require ordering. That may raise throughput while breaking processing semantics.

## 7. Producer batching boosts throughput without sacrificing partition order

Kafka producers group records into batches per partition. Properties commonly affecting batching:

- `batch.size`: target batch size.
- `linger.ms`: how long the producer waits for extra records to fill batches more completely.
- `compression.type`: batch compression algorithm.
- `buffer.memory`: producer memory reserved for records awaiting send.

Batching reduces request counts and network overhead. Larger linger can improve batching efficiency while adding send wait latency. Compression reduces network bytes transferred at the cost of CPU for compression/decompression.

These optimizations do not break append order within the same partition. They affect send timing and efficiency without creating cross-partition ordering.

Example Spring Boot configuration:

~~~yaml
spring:
  kafka:
    producer:
      properties:
        "[batch.size]": 32768
        "[linger.ms]": 5
        "[compression.type]": lz4
        "[buffer.memory]": 67108864
~~~

These values are illustrative starting points only. Measure actual batch sizes, request latency, CPU, and network before tuning. Too low a linger can create many tiny batches; too high a linger can increase latency for low-volume events.

### Batching is not parallel business processing

Producer batching groups multiple records before sending. It does not mean consumers process records in the batch concurrently or out of order. If the application must process records sequentially, listeners still need to serialize work within the partition.

## 8. Producer idempotence, retries, and in-flight requests

A producer may retry requests when a broker has transient errors or responses are lost. If the producer is not idempotent and multiple requests are in flight, retrying an earlier request can make append order differ from original send order.

Example when idempotence is off and multiple requests are in flight:

~~~text
Application sends: A then B
Request A hits a transient error
Request B succeeds first
Retry A succeeds afterward

Broker may append: B then A
~~~

Producer idempotence uses a producer ID and sequence numbers so the broker recognizes retries from the same producer. With modern Kafka clients, idempotence protects per-partition order during retries and supports up to five in-flight requests per connection under compatible settings.

Example Spring Boot configuration:

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        "[enable.idempotence]": true
        "[max.in.flight.requests.per.connection]": 5
        "[retries]": 2147483647
        "[delivery.timeout.ms]": 120000
        "[request.timeout.ms]": 30000
~~~

When using older Kafka clients or disabling idempotence, capping `max.in.flight.requests.per.connection` at 1 is a way to preserve order during retries, though it reduces throughput by allowing only one uncompleted request per connection.

Idempotence has boundaries:

- It prevents duplicates caused by internal retries of the same producer session.
- It does not deduplicate two brand-new send calls from the application.
- It does not establish business order across multiple independent producers.
- It does not preserve side-effect order if consumers process asynchronously on their own.
- It does not create global order across partitions.

If the application catches a send error and calls `KafkaTemplate.send()` again as a new operation, the record can be duplicated if the first send was written by the broker before the response was lost. Use a stable `eventId` and consumer idempotency to handle this case.

### Multiple threads sending the same key

`KafkaProducer` is thread-safe, yet if multiple threads in the application concurrently call `KafkaTemplate.send()` for the same key, record order depends on the order in which the producer actually accepts and dispatches the calls. Business order across threads is not preserved automatically just because the key is identical.

If ordering among events of the same aggregate matters, serialize publishing per aggregate, such as using a sequential queue keyed by `orderId` or ensuring a single event-emission stream per aggregate.

## 9. acks and ordering are separate decisions

`acks` specifies how far the producer waits for broker confirmation:

- `acks=0`: do not wait for acknowledgment.
- `acks=1`: wait for the leader.
- `acks=all`: wait for replicas in the ISR.

These values affect durability and write latency. They do not establish topic-wide ordering. To preserve order within a partition, focus on keys, partitioners, producer concurrency, retries, and consumer processing.

A common configuration for business events is `acks=all` combined with `idempotence=true`. This strengthens producer reliability and protects internal retries, while still requiring proper keys and idempotent handlers.

Do not lower `acks` just to chase throughput when the real bottleneck is slow consumer processing or a hot partition. Measure the bottleneck before changing acknowledgment levels.

## 10. Consumer concurrency and ordering in Spring Kafka

Within the same consumer group, each partition is assigned to at most one consumer member at a time. Spring Kafka creates multiple child consumers using `concurrency` on `ConcurrentMessageListenerContainer`.

Example:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        orderListenerFactory(
                ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(4);

    factory.getContainerProperties().setAckMode(
            ContainerProperties.AckMode.RECORD
    );

    return factory;
}
~~~

Listener:

~~~java
@KafkaListener(
    id = "orders-listener",
    topics = "orders",
    groupId = "order-service",
    containerFactory = "orderListenerFactory"
)
public void onOrder(ConsumerRecord<String, OrderEvent> record) {
    orderService.process(record.key(), record.value());
}
~~~

With an eight-partition topic and concurrency four, four child consumers can receive roughly two partitions each depending on the assignor. Partitions are processed in parallel across consumer threads.

In a synchronous record listener, the container invokes the listener on the consumer thread. One consumer thread does not invoke the listener concurrently for multiple records; thus a partition's records are processed sequentially on that thread. Different partitions may interleave across poll loops while still preserving each partition's offset order.

### Concurrency cannot exceed partition limits

If a topic has three partitions and concurrency is six, at most three child consumers can receive partitions from that topic. The remaining three consumers do not increase throughput for that topic.

If the application runs multiple replicas, total consumer members equal the sum of concurrency across replicas in the same group. Account for both replica count and concurrency, rather than looking solely at a single instance's concurrency setting.

## 11. Do not break ordering with asynchronous processing

A common mistake is a listener receiving records in order and then submitting each record to a multi-threaded executor:

~~~java
@KafkaListener(topics = "orders", groupId = "order-service")
public void onOrder(OrderEvent event) {
    executor.submit(() -> orderService.process(event));
}
~~~

Suppose the partition delivers events in order A, B, C. The executor may complete B before A or C before B. Kafka still maintains log order, yet business side effects have executed out of order.

If per-partition or per-key ordering is required:

- Do not fire-and-forget order-sensitive work from a listener.
- Use synchronous processing inside the listener when processing time permits.
- If parallelism is needed, use dedicated sequential queues per partition or key.
- Acknowledge/commit only when the corresponding work completes.
- Track in-flight tasks before partitions are revoked.

You can process in parallel across partitions and sequentially within each partition. For example, partition 0 uses worker A, partition 1 uses worker B; inside each worker, records run one by one.

### asyncAcks is not a business ordering guarantee

Starting with Spring Kafka 2.8, `asyncAcks` is supported when listeners use manual acknowledgment (`MANUAL` or `MANUAL_IMMEDIATE`). The container can accept acknowledgments out of order within a poll and only commit once prior offsets have been acknowledged. This helps the container manage offsets when work completes out of order.

However, `asyncAcks` does not automatically invert or serialize side effects. If event B updates the database before event A, waiting for A's acknowledgment cannot turn already-executed side effects back into valid business order. Coordinate work before side effects occur.

## 12. Batch listeners: higher throughput while preserving per-partition order

A batch listener receives multiple records in one invocation. Batch processing can reduce method-call overhead or coalesce database operations.

Example enabling a batch listener:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        batchOrderListenerFactory(
                ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setBatchListener(true);
    factory.setConcurrency(4);

    return factory;
}
~~~

Listener receiving a list of records:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "order-batch-service",
    containerFactory = "batchOrderListenerFactory"
)
public void onOrders(List<ConsumerRecord<String, OrderEvent>> records) {
    Map<TopicPartition, List<ConsumerRecord<String, OrderEvent>>> byPartition =
            records.stream().collect(Collectors.groupingBy(
                    record -> new TopicPartition(
                            record.topic(), record.partition()
                    )
            ));

    for (List<ConsumerRecord<String, OrderEvent>> partitionRecords
            : byPartition.values()) {
        partitionRecords.sort(
                Comparator.comparingLong(ConsumerRecord::offset)
        );
        orderService.processPartitionSequentially(partitionRecords);
    }
}
~~~

This snippet shows how to group by partition and process sequentially within each group. If you want to process partition groups in parallel, ensure each group has one sequential stream and offset commits never advance past incomplete records.

Batch listeners do not automatically process records in a batch in parallel. Application code decides how to process the batch. When using batches, clearly determine:

- Which records succeeded.
- Which records failed.
- Whether records after a failure may continue.
- Safe offsets to commit per partition.
- How to retry or route failed records to a DLT without breaking business order.

## 13. Retries and DLTs can alter processing order

Retries directly affect ordering, especially when using retry topics or non-blocking retries.

### Blocking retry

With blocking retries, failing records are retried on the current processing thread. Later records in the partition normally wait until the failing record succeeds or is recovered.

Advantages:

- Easier to preserve processing order within the partition.
- Fits when later events depend on earlier events.
- Prevents later records from overtaking a record awaiting retry.

Trade-offs:

- One failing record can block the entire partition.
- Lag grows during backoff periods.
- Prolonged failures can impact partition throughput.

### Non-blocking retry topic

With retry topics, a failing record moves to a retry topic for later processing. The main consumer can proceed with the next record.

Example:

~~~text
orders partition 0:
A -> B (failed) -> C

Main stream:
A -> B moved to retry topic -> C continues

Retry stream:
          B reprocessed later
~~~

In this case, C can be processed before B. Thus, non-blocking retries can break original business order. This is an intentional trade-off to keep the main stream moving.

If strict ordering is needed, consider blocking retries, pausing partitions, or aggregate-locked retry designs. With retry topics, add a version/sequence number and apply events only when prior versions have completed; otherwise buffer or retry according to business rules.

DLTs also introduce a gap in the processing stream. When record B goes to a DLT and the consumer continues with C, replaying B later does not automatically place its side effects ahead of C. Design controlled replays or use version guards to prevent stale state overwrites.

## 14. Rebalances, in-flight work, and side-effect ordering

During a group rebalance, partitions may be revoked from an old consumer and assigned to a new consumer. If the listener processes synchronously, the container manages stopping/revocation and commits according to configuration.

If the application offloads work to an executor, a task from the old consumer may still be running after the partition moves to a new consumer. Two workers can then apply side effects concurrently or out of order.

To reduce risk:

- Avoid letting background tasks run indefinitely after the listener returns.
- Track and drain in-flight tasks when partitions are revoked.
- Only commit offsets whose work has finished.
- Use idempotency keys and version/sequence guards in the database.
- Use fencing tokens or ownership epochs if multiple workers might contend to write the same aggregate.
- Keep processing time compatible with `max.poll.interval.ms` and shutdown timeouts.

Rebalances do not change offset order inside a partition. Yet asynchronous side effects outside Kafka can complete in a different order, particularly if old workers still hold active tasks.

## 15. Measuring throughput and identifying bottlenecks

Pipeline throughput is limited by the slowest component in the path:

~~~text
Producer
   |
   v
Broker append + replication
   |
   v
Consumer poll + listener
   |
   v
Database / HTTP / downstream
~~~

A topic with many partitions still fails to achieve high throughput if producers are too slow, brokers lack resources, or the database processes slowly.

Metrics to measure:

| Component | Metrics to watch | Optimization direction |
|---|---|---|
| Producer | Record send rate, request latency, batch size, retry rate | Batching, compression, async sends, buffers |
| Broker | Request latency, disk/network, replication lag, ISR | Broker resources, replication, and partition balance |
| Partition | Traffic and lag per partition | Key distribution, hot keys, partition count |
| Consumer | Records consumed, listener duration, poll interval, rebalances | Concurrency, batch handling, listener optimization |
| Downstream | Database latency, pool saturation, HTTP latency | Batch writes, connection pools, caching, bounded concurrency |

Do not look solely at total consumer lag. If one partition's lag climbs while others stay near zero, the issue may be a hot key or slow processing on that partition. Adding consumers cannot split a hot partition.

### A quick estimate of parallelism

If a topic has P partitions and a consumer group has C consumer members, at most min(P, C) consumers can actively process that topic. This only bounds partition-level reader threads, not throughput.

Actual throughput also depends on:

- How fast producers write records.
- Record and batch sizes.
- Deserialization and business logic cost.
- Side-effect duration.
- Replication factor and broker latency.
- Key distribution uniformity.
- Retry and rebalance overhead.

## 16. Choosing design strategies by ordering requirement

| Requirement | Suitable design | Trade-off |
|---|---|---|
| Global order for all events | Single partition, single sequential stream, or dedicated sequencer | Low throughput and parallelism |
| Per-aggregate ordering | Key = aggregate ID, sequential processing per partition | One hot aggregate is bounded by one partition |
| No per-entity ordering needed | Keyless or distributed keys, multiple partitions | No per-entity ordering |
| Per-partition ordering, high throughput | Multiple partitions and consumers; sequential per partition | No cross-partition ordering |
| Retries without letting later events pass failing ones | Blocking retry or pause partition | One error can block a partition |
| Main stream continues when an event fails | Retry topic + version guard/resequencing | Later events can complete before the failing event |
| Multiple producers emitting for the same aggregate | Single publisher owner or business sequence/version | Requires event emission coordination |

### Example design for an order service

A balanced design typically looks like:

1. Topic `orders` has enough partitions for projected parallelism.
2. Producer uses `orderId` as the key.
3. Producer enables idempotence and appropriate batching/compression.
4. Consumer group `order-service` sets concurrency no higher than useful partitions.
5. Listener processes synchronously per partition or uses sequential queues per `orderId`.
6. Blocking retries for order-sensitive errors; if using retry topics, apply version guards.
7. Database updates check event version and `eventId` to block duplicates or out-of-order events.

This way, different orders process in parallel while events of the same order land in the same partition and apply in deterministic order.

## 17. Illustrative Spring Kafka configuration

Producer:

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        "[enable.idempotence]": true
        "[max.in.flight.requests.per.connection]": 5
        "[batch.size]": 32768
        "[linger.ms]": 5
        "[compression.type]": lz4
        "[delivery.timeout.ms]": 120000
~~~

Listener container:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        orderListenerFactory(
                ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(6);
    factory.getContainerProperties().setAckMode(
            ContainerProperties.AckMode.RECORD
    );

    return factory;
}
~~~

Listener:

~~~java
@KafkaListener(
    id = "orders-listener",
    topics = "orders",
    groupId = "order-service",
    containerFactory = "orderListenerFactory"
)
public void onOrder(ConsumerRecord<String, OrderEvent> record) {
    orderService.processInOrder(
            record.key(),
            record.value(),
            record.offset()
    );
}
~~~

This illustrative configuration assumes the topic has at least six partitions and target systems can handle six concurrent consumers. Batch size, linger, compression, and concurrency values must be measured under realistic loads. Using `AckMode.RECORD` lets the container acknowledge after each successful listener invocation; it does not automatically make database side effects and Kafka offset commits one atomic transaction.

## 18. Testing ordering and throughput

Tests must verify both in-partition ordering and parallel processing across partitions.

Useful integration scenarios:

- Send multiple events with the same key and verify they are written to the same partition while partition mapping is unchanged.
- Send events for many different keys and verify they distribute across multiple partitions.
- Send sequences 1, 2, 3 for the same aggregate and verify the listener applies them in order.
- Build a slow listener to measure throughput, lag, and processing time per partition.
- Run concurrency at 1, 2, 4, and 8 to compare throughput when enough partitions exist.
- Raise concurrency above partition count and verify surplus consumers do not raise throughput.
- Send records with producer idempotence enabled, simulate connection errors, and verify internal retries.
- Have multiple threads send the same key to verify whether the application serializes event emission order.
- Simulate a hot key and observe lag on the corresponding partition.
- Build a listener offloading to an executor to demonstrate side effects can finish out of order.
- Test blocking retries and retry topics to observe whether later events overtake failing events.
- Trigger a rebalance while tasks are running and verify duplicates, version guards, and ownership.
- Change partition count in a test environment to check key mapping and migration plans.

Do not rely on short fixed sleeps to assert ordering. Record keys, partitions, offsets, event versions, and side-effect completion timestamps for comparison. For throughput, run loads long enough to observe steady state, rebalances, and downstream saturation.

## 19. Common design mistakes

**Using multiple partitions while expecting topic-wide ordering.** Kafka only guarantees order within each partition. Define business ordering scopes and choose keys accordingly.

**Using null keys for events needing per-aggregate order.** Events can scatter across partitions. Send a stable business key.

**Using one shared key to order everything.** All traffic piles onto one partition and caps throughput. Use this only when global order is genuinely needed.

**Expanding partitions without evaluating key mapping.** New events for the same key may go to another partition. Plan migrations or stable partitioning.

**Disabling producer idempotence while leaving multiple in-flight requests during retries.** Records can be appended out of order inside a partition. Enable idempotence or limit in-flight requests per client requirements.

**Offloading all records to a multi-threaded executor.** Side effects can complete out of order. Serialize by partition or key.

**Using retry topics in flows requiring strict ordering.** Failing records are processed after subsequent records. Use blocking retries or version guards/resequencing.

**Confusing asyncAcks with business ordering.** This mechanism manages offset acknowledgments, not side-effect serialization. Coordinate execution before writing data.

**Increasing concurrency when downstream systems are already saturated.** Lag may not drop and target systems overload. Measure bottlenecks before scaling up.

**Assuming producer idempotence prevents duplicates system-wide.** Application retries, multiple producers, and consumer redeliveries can still create duplicate side effects. Use `eventId` and idempotent consumers.

## 20. Checklist for balancing ordering and throughput

- [ ] Determined whether ordering is needed topic-wide, per partition, or per aggregate/key.
- [ ] Events requiring order share the same stable key.
- [ ] Producers do not emit for the same aggregate from multiple threads/instances without sequence or serialization.
- [ ] Partition count suffices for required parallelism without arbitrary over-provisioning.
- [ ] Evaluated the impact of partition expansion on key mappings.
- [ ] Producer idempotence enabled when protecting internal retries is needed.
- [ ] `max.in.flight` matches idempotence and Kafka client version requirements.
- [ ] Batching and compression tuned with real measurements.
- [ ] Consumer concurrency sized to partitions and downstream capacity.
- [ ] Listeners do not fire-and-forget order-sensitive work.
- [ ] Batch/async processing advances offset commits along contiguous completed prefixes.
- [ ] Retries/DLTs do not allow later events to overtake earlier ones unintentionally.
- [ ] Rebalances handle in-flight tasks and duplicates properly.
- [ ] `eventId`/version present to protect side effects and detect out-of-order events.
- [ ] Monitoring lag, throughput, listener duration, and per-partition load distribution.

## Conclusion

Kafka scales throughput by splitting data into multiple partitions and processing partitions in parallel. In return, Kafka only guarantees order within each partition rather than establishing global order across partitions. To preserve per-entity order, use a stable business key to route an aggregate's events into one partition and process sequentially within that partition. Batching, compression, producer idempotence, and consumer concurrency can increase throughput while preserving per-partition ordering when configured properly. Pay close attention to hot keys, partition expansion, asynchronous processing, retry topics, and rebalances since these mechanisms can cause side effects to complete out of order. Start from business ordering requirements before choosing partition counts and parallelism levels.

