# Manual Partition Assignment

A Kafka consumer can receive partitions in two ways: joining a consumer group so the coordinator distributes partitions automatically, or directly specifying the partitions the consumer will read. The second approach is called **manual partition assignment**. It is useful when the application or an external orchestrator already knows which consumer is responsible for which partition.

In Spring Kafka, partitions can be specified directly on `@KafkaListener` using `topicPartitions`, or by creating a container with specific `TopicPartitionOffset` instances. At the Kafka Consumer API level, the `assign()` method performs direct assignment. When using this approach, the application must manage partition ownership and update assignments over the system lifecycle on its own.

One distinction to establish up front: **manual assignment does not mean manual offset commit**. Assignment determines which partitions the consumer reads; acknowledgment and offset commit determine how far read progress has been confirmed.

## Learning objectives

After this lesson, you will be able to:

- Distinguish between `subscribe()` and `assign()` in the Kafka Consumer API.
- Explain why manual assignment does not participate in consumer group automatic distribution and rebalancing.
- Assign partitions using `KafkaConsumer.assign()` and `@KafkaListener` `topicPartitions`.
- Configure an initial offset for assigned partitions.
- Distinguish manual partition assignment from manual acknowledgment/offset commit.
- Design partition partitioning across multiple instances without unintended duplicate processing.
- Understand the impact of concurrency, adding partitions, restarts, and failover.
- Choose between manual assignment and consumer group subscription based on operational requirements.

## 1. Two ways a Kafka consumer receives partitions

The Kafka Consumer API has two main mechanisms:

- `subscribe()`: the consumer subscribes to topics or a topic pattern and joins a consumer group. The group coordinator and partition assignor decide which partitions are assigned to each member.
- `assign()`: the application directly specifies the list of `TopicPartition` instances the consumer will read.

High-level diagram:

~~~text
SUBSCRIBE - group-managed assignment

Consumer A ----\
Consumer B -----+----> Group Coordinator / Partition Assignor
Consumer C ----/                    |
                                    v
                         Automatic partition distribution


ASSIGN - manual assignment

Application / coordinator
        |
        +---- Consumer A: topic orders, partition 0
        |
        +---- Consumer B: topic orders, partition 1
        |
        +---- Consumer C: topic orders, partition 2
~~~

With `subscribe()`, Kafka can automatically redistribute partitions when members join, leave the group, or the topology changes. With `assign()`, the application has already specified the partitions; Kafka does not automatically rebalance assignments across consumers under the group protocol.

These two approaches are mutually exclusive on a single `KafkaConsumer` at any given time. Calling `subscribe()` after `assign()`, or `assign()` after `subscribe()`, replaces the current assignment mechanism; do not mix both as if they complemented each other.

## 2. When should you assign partitions manually?

Manual assignment is appropriate when partition allocation has already been decided by another component or when the application needs exact control over its reading scope.

Common use cases:

- **Sharding managed by an orchestrator:** a shard manager or deployment controller has already assigned partitions to each worker.
- **Applications reading a fixed set of partitions:** for example, a job dedicated to processing partitions 0 and 1 during a migration phase.
- **Scoped replay or backfill:** a process reads specific partitions to rebuild data.
- **Separating read streams by operational responsibility:** each worker is configured to read only its assigned partitions.
- **Controlling assignment in a specialized tool:** an admin application needs to read specific partitions to inspect or migrate data.

Manual assignment is not the default choice for every consumer. If you need automatic scaling, redistribution when an instance fails, and partition balancing across members, `subscribe()` with a consumer group is usually simpler and safer.

### Responsibilities the application must take on

When assigning partitions manually, the application must know:

1. Which partition belongs to which instance.
2. Whether two instances might accidentally read the same partition.
3. What happens when an instance stops or restarts.
4. Who detects a failed instance and transfers partition ownership.
5. How to update assignments when a topic's partition count increases.
6. How to prevent two workers from concurrently committing offsets for the same group/partition.

Kafka does not solve these questions automatically through consumer group rebalancing when the application uses `assign()`.

## 3. Assigning partitions with the Kafka Consumer API

At the raw Kafka client level, the application builds a list of `TopicPartition` objects and passes it to `assign()`.

Example of a consumer reading only partitions 0 and 1 of the `orders` topic:

~~~java
Properties props = new Properties();
props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
props.put(ConsumerConfig.GROUP_ID_CONFIG, "orders-manual-reader");
props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class);
props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
        OrderEventDeserializer.class);
props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);

KafkaConsumer<String, OrderEvent> consumer =
        new KafkaConsumer<>(props);

TopicPartition partition0 = new TopicPartition("orders", 0);
TopicPartition partition1 = new TopicPartition("orders", 1);

consumer.assign(List.of(partition0, partition1));

try {
    while (running) {
        ConsumerRecords<String, OrderEvent> records =
                consumer.poll(Duration.ofMillis(500));

        for (ConsumerRecord<String, OrderEvent> record : records) {
            processIdempotently(record);

            // commitSync() after successful processing.
            // Can commit in batches to reduce overhead.
        }

        consumer.commitSync();
    }
} finally {
    consumer.close();
}
~~~

The example illustrates the basic lifecycle. In a real application, handle exceptions, shutdown signals, timeouts, and appropriate offset commits. Do not allow the `running` variable or consumer lifecycle to be mutated from multiple threads without synchronization.

Key steps:

1. Initialize `KafkaConsumer` with bootstrap servers, deserializers, and `group.id` if offsets need to be stored under a consumer group.
2. Create a `TopicPartition` for each partition to read.
3. Call `assign()` before the poll loop.
4. Call `poll()` to fetch records.
5. Process records and commit offsets according to application policy.
6. Call `close()` on shutdown to release resources.

### KafkaConsumer is not thread-safe

`KafkaConsumer` is not designed for concurrent calls from multiple threads. Operations like `assign()`, `poll()`, `seek()`, `commitSync()`, and `close()` must be coordinated around the consumer thread or thread-ownership rules supported by Kafka.

Do not inject a shared `KafkaConsumer` into multiple service threads and call `poll`/`assign` from different threads. If parallel processing is needed, decouple record fetching from business processing and design acknowledgment/commit so offsets are never confirmed before the corresponding work completes.

## 4. Assign does not automatically rebalance

When using `subscribe()`, the consumer group coordinator tracks membership and can redistribute partitions. When using `assign()`, the consumer receives only the exact list of partitions specified by the application.

Example with three instances:

~~~text
orders topic: P0  P1  P2  P3  P4  P5

Instance A:   P0  P1
Instance B:   P2  P3
Instance C:   P4  P5
~~~

If Instance B stops, Kafka does not automatically move P2 and P3 to A or C. Assignment remains an application decision. An external coordinator must detect the failure and reassign those two partitions to healthy workers.

If all three instances start with the same partition list, each instance can simultaneously read all specified partitions. This behavior is possible because manual assignment does not require the coordinator to divide partitions exclusively among members.

### Group ID can still be used to store offsets

Manual assignment does not use the group coordinator to distribute partitions, yet the consumer can still use `group.id` to store and read committed offsets for partitions. The coordinator still participates in offset commit requests; that does not turn manual assignment into a subscription with automatic rebalancing.

Therefore, distinguish between:

- **Partition ownership:** specified by the application.
- **Offset storage:** can use `group.id` to save committed read positions.
- **Group-managed assignment:** does not occur when the consumer uses `assign()`.

If multiple consumers manually assign the same partition and share the same `group.id`, they can process the same data concurrently and write offsets for that partition concurrently. Commits may race or overwrite each other's positions. Allow only one worker to own a partition within the same group if you want to avoid duplicate processing and offset races.

If each process needs to read all data independently, use a distinct `group.id` for each reader. If you need partitions divided across instances with automatic failover, consider `subscribe()`.

## 5. Manual assignment in Spring Kafka with @KafkaListener

Spring Kafka supports assigning partitions directly in the annotation via the `topicPartitions` attribute. When `topicPartitions` is used, the listener container creates a consumer with the specified assignment instead of subscribing to topics via group subscription.

Example listener receiving only partitions 0 and 1:

~~~java
@Component
public class OrdersPartitionListener {

    @KafkaListener(
        id = "orders-partition-listener",
        groupId = "orders-manual-reader",
        topicPartitions = @TopicPartition(
            topic = "orders",
            partitions = {"0", "1"}
        )
    )
    public void onOrder(OrderEvent event) {
        orderService.processIdempotently(event);
    }
}
~~~

In the example:

- `id` identifies the listener container for lifecycle management.
- `groupId` identifies the offset group used for the consumer.
- `topicPartitions` specifies the concrete topic and partitions.
- The listener receives records only from the assigned partitions.

When multiple topics or partitions are needed, multiple `@TopicPartition` entries can be declared:

~~~java
@KafkaListener(
    id = "billing-manual-listener",
    groupId = "billing-manual-reader",
    topicPartitions = {
        @TopicPartition(topic = "orders", partitions = {"0", "2"}),
        @TopicPartition(topic = "refunds", partitions = {"1"})
    }
)
public void onBillingEvent(Object event) {
    billingService.handle(event);
}
~~~

One endpoint can be assigned partitions from multiple topics. Ensure the payload type or record-receiving approach fits those topics; if schemas differ, you can use `ConsumerRecord` or configure separate listeners per message type.

In the annotation, `topics`, `topicPattern`, and `topicPartitions` are different ways of declaring subscription/assignment. Use `topicPartitions` when static assignment is required; do not declare them simultaneously as if they were additive partition sources.

## 6. Specifying an initial offset for partitions

In addition to the partition list, Spring Kafka lets you declare an initial offset using `@PartitionOffset` inside `@TopicPartition`.

Example:

~~~java
@KafkaListener(
    id = "orders-replay-listener",
    groupId = "orders-replay-reader",
    topicPartitions = @TopicPartition(
        topic = "orders",
        partitionOffsets = {
            @PartitionOffset(partition = "0", initialOffset = "0"),
            @PartitionOffset(partition = "1", initialOffset = "100")
        }
    )
)
public void replayOrder(OrderEvent event) {
    replayService.handle(event);
}
~~~

In the example, the listener is configured to start partition 0 at offset 0 and partition 1 at offset 100 according to Spring Kafka's initial seek policy.

Distinguish initial offset from an already existing committed offset:

- The consumer group may already have a committed offset for the partition.
- `auto.offset.reset` is used when there is no valid committed offset or the offset has fallen out of the log range, depending on configuration.
- `initialOffset` in `TopicPartitionOffset`/`@PartitionOffset` is an initial seek directive for the partition. Check how it interacts with committed offsets in the Spring Kafka version you are using; do not assume `auto.offset.reset` is the only mechanism deciding the starting position.
- If the goal is an intentional replay from the beginning, use a dedicated group ID for the replay job or perform a controlled offset seek/reset procedure.

Do not share the production consumer's group ID when running a replay job that could commit offsets back to an older position. The replay job can alter the committed offsets that the production consumer relies on.

### Seeking after assignment

In the Kafka Consumer API, `seek()` lets you change the read position of an already assigned partition:

~~~java
TopicPartition partition = new TopicPartition("orders", 0);

consumer.assign(List.of(partition));
consumer.seek(partition, 500L);
~~~

You must assign the partition before seeking. The offset must fall within the existing log range; if the offset is smaller than the log start offset or larger than the valid position, the application must handle that scenario accordingly.

Kafka Consumer also supports `seekToBeginning()`, `seekToEnd()`, and `position()` to control or inspect read positions. When operating on multiple partitions, handle each partition individually and do not assume offsets across partitions are related.

## 7. Manual assignment does not mean manual offset commit

These are two frequently confused concepts:

| Concept | Meaning | Mechanism |
|---|---|---|
| Manual partition assignment | Specifying which partitions the consumer reads | `assign()`, `@KafkaListener` `topicPartitions` |
| Manual acknowledgment | Listener explicitly tells the container a record is finished | `Acknowledgment.acknowledge()` |
| Manual offset commit | Application explicitly writes committed offsets | `commitSync()`, `commitAsync()` |

A listener using `topicPartitions` can still use `AckMode.RECORD` or `BATCH` so the container manages commits. Conversely, a consumer using `subscribe()` can still disable auto-commit and commit manually.

Example of manual acknowledgment in Spring Kafka:

~~~java
@KafkaListener(
    id = "orders-manual-ack",
    groupId = "orders-manual-reader",
    topicPartitions = @TopicPartition(
        topic = "orders",
        partitions = {"0"}
    ),
    containerFactory = "manualAckListenerContainerFactory"
)
public void onOrder(
        OrderEvent event,
        Acknowledgment acknowledgment) {

    orderService.processIdempotently(event);

    // Acknowledge only after required side effects complete.
    acknowledgment.acknowledge();
}
~~~

The corresponding factory must have its acknowledgment mode configured:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        manualAckListenerContainerFactory(
                ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties().setAckMode(
            ContainerProperties.AckMode.MANUAL
    );

    return factory;
}
~~~

Spring Kafka listener containers manage offset commits by default and disable Kafka auto-commit unless the application explicitly configures otherwise. Choose an acknowledgment mode based on how records are processed, not solely on whether partitions are assigned manually or automatically.

With the raw `KafkaConsumer` API, you can disable `enable.auto.commit` and call `commitSync()` after successful processing. `commitSync()` saves the consumer's next read position, not the offset of the record just processed. The Kafka client handles translating the current read position into the appropriate committed offset.

## 8. Concurrency with manual assignment in Spring Kafka

Spring Kafka can use `ConcurrentMessageListenerContainer` to run multiple child consumers for a single listener endpoint. When the endpoint uses `topicPartitions`, Spring distributes the specified partition list across the child consumers of the concurrent container.

Example of an endpoint with six partitions and concurrency equal to three:

~~~text
ConcurrentMessageListenerContainer
       |
       +-- Consumer 1: P0, P1
       |
       +-- Consumer 2: P2, P3
       |
       +-- Consumer 3: P4, P5
~~~

This is an illustrative example; actual distribution depends on container configuration and the declared partition count.

Key points to remember:

- Concurrency does not create more partitions.
- If concurrency exceeds the number of assigned partitions, some child consumers will have no partitions to read.
- If concurrency is lower than the number of partitions, one consumer can read multiple partitions.
- The listener bean can be invoked concurrently by multiple consumer threads; the bean must be stateless or thread-safe.
- Internal distribution inside one concurrent container does not trigger a group rebalance across independent applications.

If running multiple application instances, each instance creates its own concurrent container. If instances declare the same set of partitions, they can all read those partitions simultaneously. Design per-instance assignments or use an external coordinator to divide ownership.

## 9. Managing assignments when the application scales or restarts

Manual assignment is often paired with static partition configuration or a dedicated orchestration mechanism.

Example of three instances assigned partitions by configuration:

| Instance | Assigned partitions |
|---|---|
| worker-a | orders-0, orders-1 |
| worker-b | orders-2, orders-3 |
| worker-c | orders-4, orders-5 |

If `worker-b` stops, a procedure is needed:

1. Detect that `worker-b` is no longer active.
2. Ensure `worker-b` does not continue processing or committing offsets.
3. Choose a replacement worker.
4. Update the assignment so the replacement worker takes over `orders-2` and `orders-3`.
5. Start or update the container.
6. Monitor offsets, duplicates, and processing order during handover.

Without fencing or an ownership verification mechanism, the old worker could keep running after a network partition and process the partition alongside the new worker. This is an application-level split-brain scenario. Leases, distributed locks with fencing tokens, orchestration, or an appropriate ownership mechanism can prevent two workers from holding write permission for side effects simultaneously.

### When a topic increases partitions

Consumers using manual assignment do not automatically pick up new partitions if the assignment list is declared statically. When a topic's partition count increases, configuration must be updated and new partitions distributed to workers.

Do not change partition counts without re-evaluating key mapping and assignments. If keys can map to new partitions, old and new records for the same entity may end up in different partitions. This affects ordering and state handling.

### Stopping the container before changing assignment

With Spring Kafka, assignments are established when the container initializes. To change the partition list safely, manage the lifecycle: stop the container, recreate/update the container with the new assignment, and restart according to procedure. Do not call `KafkaConsumer.assign()` directly from another thread while the listener container owns the consumer.

## 10. Handling errors and duplicates with manual assignment

Manual assignment does not prevent records from being processed multiple times. If the listener has already written to the database but the offset has not yet committed, the record may be re-read after a restart. If two workers assign the same partition simultaneously, both can process the same record.

Important safeguards:

- Use a stable `eventId` and a unique constraint/inbox table to deduplicate.
- Only commit offsets after required side effects complete.
- Establish a single partition owner at a time for each processing stream.
- Enforce fencing during ownership transfer so old workers cannot keep writing data.
- Monitor committed offsets and log start offsets.
- Test restarts between processing and committing.
- Define how failed records, retries, and dead-lettering are handled per partition.

If ordering is required, process records within each partition sequentially or explicitly manage asynchronous tasks so offsets never advance past incomplete work.

## 11. Testing manual assignment

Testing should verify both actual assignments and offset behavior.

Integration scenarios:

- Create a topic with multiple partitions, assign a consumer to one partition, and verify it only receives records from that partition.
- Assign two partitions to one consumer and verify the consumer reads both.
- Assign the same partition to two independent consumers to observe duplicate reading behavior and prove the application must manage ownership.
- Use a separate group ID for a replay job to verify the job does not alter production offsets.
- Use `@KafkaListener` `topicPartitions` and verify the container receives the right partitions.
- Verify `initialOffset` when the group has no committed offset yet.
- Process a record successfully but stop the process before commit, then restart to verify the handler is idempotent.
- Increase the partition count and verify a manual-assignment consumer does not automatically receive new partitions until configuration is updated.
- Stop a worker and perform assignment transfer using the application's coordination mechanism.

In tests, do not only check whether the listener was called. Verify the topic, partition, offset, group ID, and actual assignment to avoid mistakenly testing a consumer reading a different partition.

## 12. Observability and operations

Signals to monitor:

- Partitions assigned to each instance/container.
- Consumer lag by group and partition.
- Committed offset and log start/end offset.
- Counts of processed records, errors, retries, and duplicates.
- Processing time per partition.
- Worker ownership/lease status if an external coordinator is used.
- Restarts, assignment transfers, and intervals where a partition has no active consumer.

Manual assignment does not emit group-managed rebalance events. Therefore, dedicated metrics or logs are needed to know current assignments and when ownership changes.

## 13. Comparing manual assignment and subscribe

| Criterion | `subscribe()` | `assign()` |
|---|---|---|
| Who decides partitions? | Group coordinator/assignor | Application |
| Automatic rebalance | Yes | No |
| Auto-distributes on member join/leave | Yes | No |
| Auto-receives new partitions on topic subscription | Yes, after metadata/group rebalance | No, unless static assignment is updated |
| Control over specific partitions | Via assignor or subscription pattern | Direct |
| Ownership management across instances | Primarily handled by consumer group | Application/orchestrator |
| Best suited for | Consumer groups needing automatic scaling and failover | Workers/jobs with externally controlled assignments |

Choose `subscribe()` when you need Kafka to manage partition distribution and rebalancing. Choose `assign()` when the application has a clear reason to own assignments and has mechanisms for lifecycle, failover, and ownership management.

## 14. Pre-deployment checklist

- [ ] Clearly identified why manual assignment is needed instead of `subscribe()`.
- [ ] Topic/partition list per instance is explicitly managed.
- [ ] No two workers unintentionally own the same partition.
- [ ] `group.id` is chosen properly for offset storage.
- [ ] Replay jobs use a separate group ID to avoid affecting production offsets.
- [ ] `initialOffset` and `auto.offset.reset` are properly understood.
- [ ] Manual assignment is distinguished from manual acknowledgment/commit.
- [ ] Listener/container has an appropriate acknowledgment mode.
- [ ] Listener bean is thread-safe when concurrency is greater than one.
- [ ] Ownership transfer procedure exists when a worker fails or restarts.
- [ ] Fencing or lease mechanism exists when needed to stop old workers from continuing to process.
- [ ] Tested duplicates, offset commits, partition increases, and assignment transfers.
- [ ] Logs/metrics exist for assignments, lag, and ownership.

## Conclusion

Manual partition assignment lets an application specify exactly which partitions a consumer reads via `KafkaConsumer.assign()` or Spring Kafka's `@KafkaListener` `topicPartitions`. This approach does not participate in consumer group automatic distribution and rebalancing; the application must manage ownership, scaling, failover, and partition changes itself. `group.id` can still be used to store committed offsets, but it does not guarantee manually assigned consumers share partitions exclusively. Distinguish assignment from acknowledgment/commit, use idempotent handlers, and choose manual assignment only when the system has a clear partition coordination mechanism.

