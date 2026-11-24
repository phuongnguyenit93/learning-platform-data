# Ordering by partition

Apache Kafka guarantees record ordering **within each partition**. When a broker appends records to a partition, each record receives a monotonically increasing offset; consumers read that partition in offset order. However, Kafka does not establish a total order across multiple partitions. A record in partition 0 can be processed before or after a record in partition 3, depending on scheduling, assignment, load, retries, and processing time.

With Spring Kafka, understanding partition-level ordering is essential for maintaining correctness in flows such as order state updates, account balances, inventory, projections, and event sourcing. A sound design typically chooses a **business aggregate key** as the Kafka record key so events for the same aggregate land in the same partition. The producer must then preserve publish order, the consumer must avoid parallel execution that reorders side effects, and retries/replays must align with the ordering contract.

This lesson belongs to the **Correctness and Idempotency** chapter of **Spring Kafka Reliability Operations**. It covers ordering guarantees, keys and partitioners, producer retries/idempotence, consumer concurrency, batch/async processing, retry topics/DLTs, changing partition counts, per-key sequencing, idempotency, and testing in production-like environments.

## 1. Where does Kafka guarantee ordering?

A Kafka topic is divided into multiple partitions. Each partition is an append-only log with its own offsets.

~~~text
Topic: orders

Partition 0:  offset 0 -> A1 -> offset 1 -> A2 -> offset 2 -> A3
Partition 1:  offset 0 -> B1 -> offset 1 -> B2
Partition 2:  offset 0 -> C1 -> offset 1 -> C2
~~~

Kafka guarantees records in each partition are read in offset order:

- Partition 0: A1 before A2 before A3.
- Partition 1: B1 before B2.
- Partition 2: C1 before C2.

However, Kafka guarantees no temporal relationship among A1, B1, and C1. Partitions can be fetched and processed concurrently.

### 1.1 Offsets are meaningful only within a partition

A record is located by the triple:

~~~text
topic + partition + offset
~~~

Offset 15 in partition 0 has no ordering relationship with offset 15 in partition 1. You cannot compare two offsets across partitions to conclude which record occurred earlier across the topic.

Example:

| Record | Partition | Offset | What can be concluded |
|---|---:|---:|---|
| Order A created | 0 | 10 | Precedes offset 11 of partition 0 |
| Order A confirmed | 0 | 11 | Follows offset 10 of the same partition |
| Order B created | 1 | 8 | No global order relative to the two partition 0 records |
| Order C created | 2 | 4 | No global order relative to other partitions |

### 1.2 Kafka append order differs from business event time

A producer may create an event at 10:00:05 yet send it after an event created at 10:00:07. Brokers append in the order produce requests arrive and are processed, rather than sorting by business timestamps.

Therefore:

- Offset reflects append order within the partition.
- Event timestamp reflects the time attached by the producer/application.
- Business sequence number reflects business order if managed by the application.
- Consumer completion time reflects when the side effect finished.

These are four distinct concepts. Never use record timestamps to infer Kafka append order or business causal order without an explicit contract.

## 2. Keys determine the ordering domain

To place events of the same business entity into the same partition, producers typically set the **record key** to a stable entity/aggregate identifier.

Example with orders:

~~~java
kafkaTemplate.send(
    "orders.events",
    order.getId(),
    event
);
~~~

If the same order ID is sent with the same key serializer, partitioner, and partition count, events normally route to the same partition.

~~~text
key=order-1001
  OrderCreated
  OrderPaid
  OrderPacked
  OrderShipped
        |
        v
    partition 2
        |
        v
    offsets 40, 41, 42, 43
~~~

Events for order-1002 can go to another partition and be processed in parallel.

### 2.1 Choose keys by the aggregate needing ordering

| Use case | Typical key | Ordering preserved |
|---|---|---|
| Order lifecycle | orderId | Changes for one order |
| Account ledger | accountId | Transactions for one account |
| Inventory | sku or inventoryAggregateId | Stock updates for the same item |
| Shipment | shipmentId | States of one shipment |
| User profile | userId | Profile changes for one user |
| Device telemetry | deviceId | Sequential events from one device |

The key should represent **the unit requiring sequential processing**. Choosing customerId when only orderId ordering is needed can concentrate too much traffic onto one partition. Choosing eventId as the key typically sends each event to a different partition and loses per-aggregate ordering.

### 2.2 Key is not a partition ID

The key is routing data. The partitioner determines the target partition from the key and topic metadata. Although `ProducerRecord` can specify a partition number directly, hardcoding partition IDs couples the application to topology and makes scaling difficult.

### 2.3 Null keys create no per-entity ordering

If a record has no key, the partitioner may distribute records via sticky/round-robin behavior depending on Kafka client version and configuration. There is no guarantee records for the same business entity land in one partition.

If ordering is a business requirement, supply a stable key and test partition routing.

## 3. Default partitioner and identical keys

For keyed records, default Kafka partitioning typically hashes the serialized key to pick a partition. Conceptually:

~~~text
partition = positiveHash(serializedKey) % partitionCount
~~~

This is a high-level description; exact implementation depends on Kafka client version and partitioner configuration.

Given the same key, same partitioner, and same partition count, routing remains stable under normal conditions. Thus, events of an aggregate can be appended to the same partition.

### 3.1 Key serialization must be deterministic

If a key serializer produces different byte sequences for the same logical ID, the hashes can also differ. Example:

~~~text
"order-1001"
"ORDER-1001"
"order-1001 "
~~~

These are three distinct key values if the serializer preserves those raw bytes.

Standardize keys by contract:

- Identical format and charset.
- No unintended casing changes.
- No extra whitespace.
- No unstable object serialization.
- No switching serializers across producers without migration.
- Do not let one producer use orderId while another uses customerId on the same stream if the ordering contract requires orderId.

### 3.2 Custom partitioners can break routing assumptions

A custom Partitioner can route the same key to different partitions based on tenant, region, time, or metadata. When using a custom partitioner, verify:

- Does the same key always map to the same partition?
- Can the mapping change across deployments?
- Is there a fallback when the key is null?
- Does increasing partition count alter the mapping?
- Do all producers share the exact same algorithm and configuration?

Key-based ordering holds only when the routing policy is consistent across all producers.

## 4. Producers sending records in the right order

Even when identical keys route to the same partition, the producer application must still preserve send order.

Example:

~~~java
kafkaTemplate.send("orders.events", orderId, createdEvent);
kafkaTemplate.send("orders.events", orderId, paidEvent);
kafkaTemplate.send("orders.events", orderId, shippedEvent);
~~~

These calls initiate sends in code order, yet send is asynchronous. Understand producer batching, in-flight requests, retries, and multithreading to ensure broker append order.

### 4.1 Producer retries and in-flight requests

A Kafka producer can have multiple requests in flight simultaneously. If an earlier request fails and retries while a later request succeeds, ordering can be disturbed when idempotence is disabled or configuration violates ordering prerequisites.

In modern Kafka producers, **enable.idempotence** is supported to prevent retry duplicates and preserve ordering under compatible configurations. When idempotence is enabled, max.in.flight.requests.per.connection is bounded per Kafka version; in modern clients, values up to 5 are supported while preserving ordering with idempotence.

Illustrative explicit configuration:

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        enable.idempotence: true
        max.in.flight.requests.per.connection: 5
        retries: 2147483647
~~~

This is an example policy for Kafka clients supporting these settings. Spring Boot property binding and Kafka client versions must be compatible. Producer idempotence may require acks=all, retries greater than 0, and max.in.flight within permitted bounds.

### 4.2 Idempotence does not replace business ordering

An idempotent producer protects producer sequences inside the Kafka protocol, avoiding duplicate writes from retries per producer semantics. It does not know that OrderCreated must precede OrderPaid at the business layer.

If two application threads call send with the same key and thread B sends before thread A due to a race, the producer appends requests in the order it received them, even if the intended business order is reversed.

### 4.3 Multiple producers writing to the same key

Suppose Service A and Service B both publish events for order-1001. Each producer preserves its internal order, yet the broker has no automatic business sequence coordinator across two producers.

~~~text
Producer A: OrderAddressChanged
Producer B: OrderCancelled
        \       /
         \     /
       same key / partition
             |
             v
        broker append order
~~~

The broker establishes an append order, but that order need not match business causality between the two producers.

If an aggregate has multiple writers, you need an owner/sequencer or versioning strategy. Using the same key alone is insufficient to define business order across multiple producer processes.

## 5. Serializing sends for the same aggregate

When a service has multiple threads, events for the same aggregate can be generated concurrently. Options include:

- An aggregate owner processing commands sequentially.
- A partitioned executor keyed by aggregate key.
- An outbox relay ordered by aggregate sequence.
- Optimistic concurrency/version checks in the database.
- A sequencer issuing sequence numbers.

Avoid a single application-wide synchronized block if it serializes all aggregates and destroys throughput. The goal is **serializing per key**, letting different keys proceed in parallel.

### 5.1 Business sequence numbers

An event can carry aggregateVersion:

~~~json
{
  "orderId": "order-1001",
  "aggregateVersion": 42,
  "eventType": "OrderPaid"
}
~~~

The consumer can validate that version 42 follows version 41. If version 43 arrives before 42, the consumer can buffer, retry, reject, or reconcile per policy.

Sequence numbers detect gaps/reordering; they do not automatically prevent brokers from appending out of order.

### 5.2 Where are sequence numbers issued?

Sequences must be issued by the authority that owns aggregate ordering. If two producers independently increment local counters, they can create duplicate or inverted versions.

A common approach stores the aggregate version in the same database transaction that updates state and inserts the outbox event. When the transaction commits, the event carries the new version. The outbox relay must publish in aggregate order.

## 6. Partition count affects key mapping

An easily overlooked operational detail: with hash partitioning, increasing partition count can route the same key to a different partition.

Illustrative example:

~~~text
Before:
  partitionCount = 4
  key order-1001 -> partition 2

After increasing:
  partitionCount = 8
  key order-1001 -> partition 6
~~~

Old records for order-1001 still sit in partition 2. New records may be appended to partition 6. Both partitions can be processed concurrently by consumers.

When that happens, a newer event can complete before an older backlogged event. Kafka still preserves order within each partition, yet order for orderId has been split in two.

### 6.1 Increasing partitions alters the ordering contract

Before increasing the partition count of an aggregate-keyed topic:

1. Identify the ordering domain and key distribution.
2. Measure current backlog per partition.
3. Evaluate the producer partitioner and key hash mapping.
4. Assess the impact of keys shifting partitions.
5. Check whether consumer side effects can overlap between old and new partitions.
6. Choose a migration strategy.
7. Increase partitions only after accepting the semantics and testing.

Never treat increasing partitions as a pure capacity change with zero correctness impact.

### 6.2 Risk mitigation strategies

- Keep partition count fixed if strict per-key ordering is a hard requirement.
- Use stable logical shards/virtual partition mappings managed by the application.
- Migrate to a new topic version with controlled cutover/draining.
- Pause/drain the old stream before starting new routing, if SLAs permit.
- Use aggregate sequence/version checks to detect and handle gaps.
- Build an epoch-aware routing layer so consumers know which mapping applies.

Each strategy carries cost and operational complexity. No simple partition-increase command automatically migrates history and restores per-key ordering.

## 7. Consumer groups and ordering

Within a consumer group, a partition is assigned to at most one consumer member at a time. That consumer processes the partition's records in offset order.

~~~text
Topic orders, 6 partitions
        |
        v
Consumer group orders-projection
  consumer-0 -> partitions 0, 3
  consumer-1 -> partitions 1, 4
  consumer-2 -> partitions 2, 5
~~~

Consumer members process partitions in parallel. Inside each partition, the consumer preserves delivery order by offset. There is no global order between consumer-0 and consumer-1.

### 7.1 Spring Kafka concurrency

Example:

~~~java
factory.setConcurrency(3);
~~~

If the topic has 6 partitions, three child consumers may receive roughly two partitions each depending on the assignor. If concurrency exceeds partition count, some consumers sit idle.

Concurrency increases throughput by processing multiple partitions in parallel. It does not introduce independent concurrency within a single partition.

### 7.2 One partition is never processed concurrently by two members of the same group

Kafka group assignment guarantees one partition belongs to one consumer member in the group at a time. However, an application can still create internal parallelism inside a member via executors or async processing. That is where side-effect order can invert.

### 7.3 Two independent consumer groups

If two groups subscribe to the same topic, each reads all partitions in its own offset order. However, completion timing between the two groups is unsynchronized.

Do not rely on consumer groups A and B to create global ordering across two processing pipelines. If downstream needs coordination, explicit coordination or sequence/version checks are required.

## 8. Async processing can invert ordering

A synchronous listener:

~~~java
@KafkaListener(topics = "orders.events")
public void handle(OrderEvent event) {
    orderService.apply(event);
}
~~~

The container invokes the listener for a record and waits for the method to finish per its processing model. For records in the same partition, this is the simplest way to preserve side-effect order.

However, if the listener offloads work:

~~~java
@KafkaListener(topics = "orders.events")
public void handle(OrderEvent event) {
    executor.submit(() -> orderService.apply(event));
}
~~~

the method can return immediately. Tasks for offsets 41 and 42 run concurrently; task 42 may commit to the database before task 41. Kafka delivery order does not equal business completion order.

### 8.1 Reordering example

~~~text
Kafka delivery:
  offset 41 -> OrderAddressChanged
  offset 42 -> OrderShipped

Async execution:
  task 41: slow DB call 800 ms
  task 42: fast DB call 100 ms

Completion:
  offset 42 side effect finishes first
  offset 41 side effect finishes later
~~~

The final outcome could apply an address update after the order is already shipped, or overwrite newer state with older state.

### 8.2 Preserving per-key order with async work

- Use an executor with a serial queue per aggregate key.
- Use a keyed mailbox/actor model: at most one active task per key.
- Use partition-aligned workers with sequential processing.
- Enforce optimistic version checks in the database.
- Do not acknowledge/commit before business tasks complete per contract.
- Bound queues to prevent unbounded memory growth.

Do not use a single application-wide single-threaded executor if high throughput across partitions is required. Serializing by partition or aggregate key retains parallelism across distinct keys.

### 8.3 KafkaConsumer is not thread-safe

Never pass the KafkaConsumer object to executor threads to poll, commit, seek, or pause directly. The Spring Kafka container manages the consumer thread and lifecycle. Async business processing must use framework-supported APIs/acknowledgment patterns.

## 9. Batch listeners and ordering

A batch listener can receive records from multiple partitions in one poll. Overall batch order does not imply global ordering across partitions.

Example batch:

~~~text
Partition 0: offset 10, 11
Partition 1: offset 20, 21
Partition 2: offset 30
~~~

A batch can contain records fetched from multiple partitions. Within each partition, offset order still matters; between partitions 0 and 1, there is no total order.

### 9.1 Using ConsumerRecord to preserve metadata

~~~java
@KafkaListener(topics = "orders.events")
public void handleBatch(
        List<ConsumerRecord<String, OrderEvent>> records) {

    Map<TopicPartition, List<ConsumerRecord<String, OrderEvent>>> byPartition =
        records.stream().collect(
            Collectors.groupingBy(
                record -> new TopicPartition(
                    record.topic(),
                    record.partition()
                )
            )
        );

    byPartition.values().forEach(partitionRecords ->
        partitionRecords.sort(
            Comparator.comparingLong(ConsumerRecord::offset)
        )
    );

    // Process sequentially within each partition by offset.
}
~~~

This example illustrates grouping/sorting. Kafka already delivers records in fetch order per partition; grouping makes the ordering domain explicit when batch business logic spans multiple partitions. Preserve batch listener acknowledgment and exception semantics.

### 9.2 Parallelize across partitions, not across records in the same partition

A batch can be split into partition groups. Different groups can process in parallel if business effects are independent; within each group, process sequentially by offset.

However, if the database or downstream shares state across keys/partitions, additional concurrency control is required. Partition boundaries alone do not guarantee business entities are completely independent.

### 9.3 Batch retries can reprocess multiple records

A batch listener exception can cause the framework to redeliver/recover a batch or subset of records depending on error handler semantics and version. Do not assume only the final record is retried.

If a batch holds multiple aggregate keys, one failure can reprocess multiple records. Business operations must be idempotent and batch retry behavior must be tested.

## 10. Blocking retries preserve order but can stall a partition

With DefaultErrorHandler and blocking retries, a failed record can be sought/redelivered after a BackOff. The consumer cannot advance normally past the failed record until it is processed or recovered per policy.

~~~text
Partition 0:
  offset 100 -> success
  offset 101 -> failure, retry
  offset 102 -> waiting behind
  offset 103 -> waiting behind
~~~

This is a trade-off: preserving in-partition order by preventing later records from overtaking a failed record, at the risk of a poison record stalling partition progress.

### 10.1 Head-of-line blocking

If offset 101 retries for 30 seconds, offsets 102 and 103 may have to wait. Partition consumer lag rises even though subsequent records could process quickly.

To reduce impact:

- Classify non-retryable exceptions.
- Use bounded BackOff.
- Configure DLT/recovery for poison records.
- Separate workloads with differing SLAs into appropriate topics/partitions.
- Monitor per-partition lag and retry duration.

Do not bypass a failed record if business ordering forbids later offsets from overtaking it.

### 10.2 Recovery and offset progression

When a record is recovered to a DLT, the container can advance per error handler/acknowledgment semantics. That means the record was quarantined, not that its business effect succeeded.

If replay is needed after fixing data, design the replay procedure so it does not create out-of-order side effects against newer already-processed events.

## 11. Non-blocking retries can invert ordering

With @RetryableTopic, failed records route to retry topics while the main topic continues processing later records.

~~~text
Main topic:
  offset 100 -> OrderCreated -> success
  offset 101 -> OrderPaid -> failure, routed to retry
  offset 102 -> OrderShipped -> success

Retry topic later:
  OrderPaid -> success
~~~

In this example, OrderShipped can be processed before OrderPaid. This is intentional behavior of non-blocking retries, yet it can break strict per-aggregate ordering.

### 11.1 When are retry topics appropriate?

Non-blocking retries are useful when:

- Records are independent or eventual ordering is acceptable.
- One failing record must not block an entire partition.
- Downstream outages require long delays.
- Business logic has version checks/idempotency to tolerate reordering.
- Retry topics are designed with matching retention, partitioning, and ACLs.

Do not apply @RetryableTopic mechanically to event streams requiring strict per-key sequencing.

### 11.2 Ways to preserve correctness when using retry topics

- Each event carries an aggregate sequence/version.
- Consumers reject or buffer events whose version exceeds the expected version.
- Side effects are idempotent.
- Retry handlers do not overwrite newer state with older state.
- Reconciliation jobs resolve gaps.
- DLT/replay workflows preserve source metadata.

If strict total order is mandatory, blocking retries or a sequencing layer may be more suitable.

## 12. DLT and replay can introduce reordering

When an old record goes to a DLT, newer records can continue processing. When replaying the DLT hours later, the old event can arrive after newer state.

Example:

~~~text
10:00 OrderAddressChanged v12 -> DLT
10:01 OrderShipped v13 -> main consumer success
11:00 Replay v12 -> consumer sees stale event
~~~

If the consumer applies v12 after v13 without checking version, state can regress.

### 12.1 Replay requires an ordering policy

Before replaying:

1. Identify the record's aggregate key and sequence/version.
2. Inspect the current state of the aggregate.
3. Check whether the event was already applied.
4. Decide whether to skip, reconcile, replay in order, or rebuild the projection.
5. Ensure replay does not dangerously overtake newer events.
6. Record an audit trail of the replay operation.

DLT replay is not merely pushing a record back to the main topic. It is an operation altering processing history that requires idempotency and sequencing.

### 12.2 Never strip original metadata when routing to DLT

Preserve source topic, partition, offset, timestamp, and exception headers per policy for investigation. This metadata traces the original location, even though the DLT topic assigns its own new offset.

## 13. Consumer rebalances and partition ownership handoff

During a consumer group rebalance, partitions can be revoked from an old consumer and assigned to a new consumer.

~~~text
Before:
  consumer-0 owns partition 0

Rebalance:
  partition 0 revoked from consumer-0

After:
  consumer-1 owns partition 0
~~~

Kafka enforces group assignment ownership via generation/epoch semantics. Yet if the old consumer offloaded business tasks to an executor, those tasks may keep running after the partition is assigned to the new consumer.

Two tasks for the same key can then overlap even though Kafka assigns a partition to only one consumer member at a time.

### 13.1 Graceful shutdown and in-flight work

On revoke/stop:

- Stop accepting new work for the partition.
- Drain or cancel tasks per policy.
- Wait for business tasks to finish within a bounded timeout.
- Do not commit offsets before side effects complete.
- Ensure old tasks cannot overwrite newer state from the new consumer.
- Use fencing/version checks where possible.

If draining cannot finish within the timeout, database optimistic locking and aggregate sequence checks prevent stale writes.

### 13.2 Cooperative rebalancing does not guarantee end-to-end business order

Cooperative sticky assignment shrinks the set of partitions revoked during a rebalance, but does not automatically solve async tasks, retries, or side effects already running outside the consumer thread.

## 14. Key skew and hot partitions

Key-based partitioning preserves per-key order, yet can create hot partitions if one key or group of keys dominates traffic.

Example:

~~~text
partition 0: 90,000 records/s
partition 1:  3,000 records/s
partition 2:  3,500 records/s
partition 3:  3,500 records/s
~~~

If one tenant or account generates massive event volume, all events for that key must flow through one partition to keep order. You cannot split a single strict ordering domain across multiple partitions without adding a sequencing mechanism.

### 14.1 Measuring skew

Track:

- Records in/out per partition.
- Bytes in/out per partition.
- Consumer lag per partition.
- Processing duration per key/category if safely aggregated.
- Retry rate and DLT rate per partition.
- Partition assignment distribution.

Never put raw keys into metric tags. Use key classes/tenant tiers or privacy-controlled offline top-key analysis instead.

### 14.2 When a hot key cannot scale horizontally

Options:

- Optimize business work for that key.
- Split the aggregate into sub-aggregates if business rules allow.
- Use per-subkey ordering if invariants permit.
- Reduce event chatter/coalesce updates.
- Increase consumer capacity for that partition and downstream.
- Design a sequencer/reorder buffer if a single key must be fanned out.

Do not increase partition count hoping a hot key will automatically spread out; identical keys still route to a single partition.

## 15. Global ordering requires a dedicated architecture

If business rules require every event across the entire system to share one total order, multiple partitions cannot provide that guarantee automatically.

A single-partition topic establishes one global log order for that topic, but caps throughput and parallelism. Only one consumer in a consumer group can actively read that partition at a time.

Alternatives:

- Central sequencer issuing global sequence numbers.
- Single-writer log/service.
- Database transaction log/outbox with a sequence.
- Event time + watermark/reorder buffer for use cases tolerating bounded delay.
- Explicit causal dependencies across aggregates.

### 15.1 Global order has a cost

A global sequence requires coordination. If every service must wait on the same sequencer, throughput, availability, and latency depend on that component.

Most business domains only need per-aggregate ordering—such as per order or per account—rather than ordering across every order in the system.

## 16. Idempotency and ordering complement each other

Ordering ensures events arrive sequentially within a partition. Idempotency ensures reprocessing an event creates no duplicate side effects. Both are needed in at-least-once systems.

Example:

~~~text
OrderCreated v1
OrderPaid v2
OrderShipped v3
~~~

The consumer processes v1 and v2, then crashes before offset commit. On restart, v2 may be redelivered. Without idempotency, the consumer could charge or apply side effects twice.

### 16.1 Inbox table

A consumer can store processed event IDs in the same database transaction as business state:

~~~sql
CREATE TABLE processed_events (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Pseudo flow:

~~~text
BEGIN DB TRANSACTION
  INSERT event_id into processed_events
  if duplicate:
      skip business side effect
  else:
      apply state transition
COMMIT
ACK/commit Kafka offset according to listener policy
~~~

Handle duplicate key conflicts safely and keep the idempotency record in the same transaction as the side effect. If the inbox insert and business update sit in two separate transactions, a crash can leave inconsistent state.

### 16.2 Version guard

With aggregateVersion:

~~~sql
UPDATE orders
SET status = :newStatus,
    version = :incomingVersion
WHERE order_id = :orderId
  AND version = :incomingVersion - 1;
~~~

If the update affects zero rows, the event may be a duplicate, stale, or a gap. The application must distinguish all three cases and decide whether to retry, reconcile, or skip.

A version guard stops stale events from overwriting newer state; it does not automatically ensure events process in order if business logic lacks a gap-recovery path.

### 16.3 Kafka exactly-once does not cover every database side effect

Kafka transactions can atomically commit consumed offsets and produced Kafka records within a properly configured transaction boundary. They do not automatically atomically commit a standard PostgreSQL transaction alongside the Kafka transaction.

If the consumer writes to a DB, use idempotency/inbox/outbox or proper transaction coordination. Never infer EOS means every external side effect is exactly once.

## 17. Transactional outbox and per-aggregate order

Transactional outbox is commonly used when a service updates a database and must consistently publish a Kafka event:

~~~text
DB transaction:
  update orders
  insert outbox event with aggregate_id + aggregate_version
COMMIT

Outbox relay:
  read unpublished rows
  publish to Kafka with key=aggregate_id
  mark published
~~~

Sharing an aggregate key sends events into the same Kafka partition. Yet the relay must still read and publish in aggregate sequence order.

### 17.1 Multiple relay workers

If multiple relay workers claim outbox rows concurrently, worker A might publish version 11 slowly while worker B publishes version 12 first. Using the same key cannot fix producer send ordering already inverted before reaching the broker.

Requirements:

- Claim rows by aggregate with locking/partitioning.
- Allow only one active worker per aggregate/shard.
- Publish in ascending sequence order.
- Do not mark published before broker acknowledgment per policy.
- Make the relay idempotent against crashes after publishing before marking.
- Validate duplicates and version gaps at the consumer.

### 17.2 Outbox key and Kafka key must align

If outbox aggregate_id is orderId yet the relay publishes with customerId, the ordering domain changes. Contracts must align across database, event schema, producer, and consumer.

## 18. Sample Spring Kafka configuration

A consumer record listener configuration with appropriate concurrency:

~~~java
@Configuration
public class OrdersKafkaConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    ordersListenerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory,
            CommonErrorHandler ordersErrorHandler) {

        var factory =
            new ConcurrentKafkaListenerContainerFactory<
                String, OrderEvent>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(4);
        factory.setCommonErrorHandler(ordersErrorHandler);

        factory.getContainerProperties()
               .setAckMode(ContainerProperties.AckMode.RECORD);

        return factory;
    }
}
~~~

Producer:

~~~java
@Bean
KafkaTemplate<String, OrderEvent> ordersKafkaTemplate(
        ProducerFactory<String, OrderEvent> producerFactory) {

    return new KafkaTemplate<>(producerFactory);
}
~~~

Publishing by aggregate key:

~~~java
public CompletableFuture<SendResult<String, OrderEvent>> publish(
        OrderEvent event) {

    return kafkaTemplate.send(
        "orders.events",
        event.orderId(),
        event
    );
}
~~~

API return types may vary by Spring Kafka version. This sample illustrates key-based routing; producer properties such as idempotence/acks/retries must be configured and verified separately.

### 18.1 Concurrency does not create cross-partition order

Concurrency=4 allows processing up to multiple partitions in parallel if the topic has enough partitions. If all events for the same orderId always land in the same partition and the listener is synchronous, those records are processed sequentially within that partition.

If the listener offloads async tasks, concurrency=4 does not protect side-effect order within a partition. Handle it as outlined in the async processing section.

## 19. Producer send order and future completion

KafkaTemplate.send returns a future. If an application sends multiple events without waiting for results, understand send order and failure handling.

~~~java
CompletableFuture<SendResult<String, OrderEvent>> first =
    kafkaTemplate.send("orders.events", orderId, created);

CompletableFuture<SendResult<String, OrderEvent>> second =
    kafkaTemplate.send("orders.events", orderId, paid);
~~~

Calling send in sequence creates invocation order on that thread. However, multiple threads can interleave calls; futures complete at different times; completion callbacks do not guarantee broker append order.

If business rules require guaranteeing OrderCreated is published before OrderPaid, serialize command/event creation per aggregate and handle send failures before emitting dependent events.

### 19.1 Do not block all keys while awaiting futures

You can chain sends for the same aggregate:

~~~java
kafkaTemplate.send("orders.events", orderId, created)
    .thenCompose(result ->
        kafkaTemplate.send("orders.events", orderId, paid)
    );
~~~

This illustrates sequencing within a single flow; handle exceptions and avoid unbounded chains. You do not need to serialize sends across different order IDs when they are independent.

## 20. Repartitioning and topic migration

When partition count must increase, one migration approach creates a new topic with the new topology:

~~~text
orders.v1 (4 partitions)
        |
        v
drain / snapshot / migration
        |
        v
orders.v2 (8 partitions)
        |
        v
new producers and consumers
~~~

A safe migration defines a cutover boundary so the same aggregate is never emitted concurrently to two topics with two different mappings.

### 20.1 Questions to answer

- Who owns the producer cutover?
- How do we confirm all pre-cutover events have drained?
- Where do new consumers start?
- How do aggregate versions continue incrementing?
- Could duplicates occur between v1 and v2?
- How are consumer side effects deduplicated?
- To which topic do old DLT records replay?
- Could rolling back producer routing invert sequences?

No single Kafka command automatically migrates an ordering contract when partition counts change.

## 21. Monitoring ordering and correctness

Standard Kafka metrics measure throughput, lag, and latency; they do not prove business events are in order.

Additional instrumentation:

| Metric/log | Purpose |
|---|---|
| consumer_lag per partition | Detect partition backlog |
| records_processed_total per listener | Throughput |
| retry_attempts_total | Retry behavior |
| dlt_records_total | Quarantine volume |
| aggregate_version_gap_total | Event version gaps |
| stale_event_rejected_total | Stale events blocked |
| duplicate_event_total | Duplicates detected |
| processing_completion_duration | Business completion duration |
| rebalance_total | Ownership changes |

Never use aggregate ID, event ID, or offset as Prometheus tags. Aggregate by listener, topic, error category, and other low-cardinality dimensions.

### 21.1 Detecting out-of-order via sequence

If events carry aggregateVersion, consumers can detect:

~~~text
current version = 12
incoming version = 14
expected version = 13
~~~

This is a gap. Event 13 may be retrying, the producer may have published out of order, or the consumer may have skipped an event. Never automatically skip past version 14 if business invariants require complete transitions.

### 21.2 Per-partition dashboards

A useful dashboard shows:

- Lag per partition.
- Records consumed rate.
- Processing duration.
- Retry/DLT counts.
- Assignment/consumer members.
- Hot partitions/skew.
- Business sequence gaps and stale event counts.

Topic-wide aggregate lag can hide one hot partition blocking all events for an aggregate.

## 22. Integration tests for ordering

Ordering must be tested against a real Kafka broker or appropriate Testcontainers/Embedded Kafka, not merely a mocked KafkaTemplate.

### 22.1 Same key must land in the same partition

1. Create a topic with multiple partitions.
2. Send multiple events with the same aggregate key.
3. Use ProducerRecord or SendResult metadata to read the partition.
4. Assert all events for the key land in the same partition under the same topology.
5. Assert offsets increment in publish order.
6. Send additional distinct keys and confirm they distribute across multiple partitions.

Do not assert a key must land in a specific hardcoded partition number unless the test fixes the partitioner/hash implementation.

### 22.2 Consumer processes sequentially within a partition

1. Send events with the same key and sequences 1..N.
2. Listener records sequences in business processing completion order.
3. Assert outcome 1..N.
4. Enable concurrency greater than 1 to verify other partitions can process in parallel.
5. Do not offload async in the baseline test.

### 22.3 Testing async reordering

1. Listener offloads records to an executor.
2. Make the earlier event slower than the later event.
3. Observe completion order.
4. Confirm the test reproduces reordering.
5. Add a per-key serial executor/version guard.
6. Re-run and verify the invariant holds.

### 22.4 Testing producer retries/idempotence

- Simulate controlled broker/network retries if the test environment supports it.
- Send multiple records with the same key.
- Verify ordering and duplicates.
- Confirm producer properties are compatible with idempotence.
- Do not rely on a mocked future to conclude broker append order.

### 22.5 Testing blocking retries

- Send sequences 1, 2, 3 with the same key.
- Cause sequence 2 to fail temporarily.
- Verify sequence 3 does not complete before 2 when policy requires strict partition order.
- Allow sequence 2 to succeed or recover.
- Verify offset progression.

### 22.6 Testing non-blocking retries

- Send sequences 1, 2, 3 with the same key.
- Cause sequence 2 to route to a retry topic.
- Verify the main topic can process sequence 3 first.
- Verify version guards/buffers/reconciliation preserve business correctness.
- Test the retried event replaying after the newer sequence.

### 22.7 Testing partition expansion

- Create a topic initially with a small partition count.
- Send events for the same key.
- Increase partition count.
- Send new events for the same key.
- Observe that the mapping can change.
- Verify migration/version policies prevent stale side effects.

### 22.8 Testing rebalances and in-flight work

- Use an async listener or executor.
- Trigger consumer rebalance/stop.
- Check whether old tasks still run after the partition is assigned to a new consumer.
- Verify draining/cancellation/version guards.
- Confirm offsets do not commit before completion per policy.

## 23. Runbook when out-of-order events are detected

1. Identify the aggregate key and event sequence/version.
2. Collect source topic/partition/offset for each event.
3. Compare Kafka offset order within each partition.
4. Verify whether the events share the same partition.
5. Check producer partitioner, key serializer, and partition count at publish time.
6. Inspect producer threads, multiple producers, and send futures.
7. Check consumer concurrency and partition assignment.
8. Check listener async/executor completion order.
9. Inspect blocking retries, @RetryableTopic, and DLT replays.
10. Inspect rebalances/in-flight tasks.
11. Determine which events already wrote side effects to the database.
12. Use aggregate version/inbox state to classify stale, duplicate, and gap events.
13. Block stale writes or pause the flow per incident policy.
14. Reconcile/replay in sequence order.
15. Document partition topology and producer/consumer versions.
16. Add a regression test reproducing the root cause before resuming rollout.

Never reset all consumer offsets to fix an ordering bug without knowing the impact. A reset can replay large volumes of records and create further duplicates/out-of-order effects.

## 24. Common misconceptions

**"Kafka preserves order across the whole topic."** False. The default guarantee is within each partition.

**"The same key always maps to the same partition forever."** Not if partition count or partitioner mapping changes.

**"Producer calling send in order means business events are guaranteed to append in order."** Only under compatible producer flow, concurrency, and retry settings; multiple writers can race.

**"Idempotent producer guarantees business event ordering."** No. It protects protocol-layer producer retry/duplicate semantics, not business sequences.

**"Concurrency greater than 1 inverts order within a partition."** Not automatically if the container processes sequentially; async offloading or custom parallelism is what can invert side effects.

**"A batch listener has one total order across all records."** No. A batch can span multiple partitions; only ordering within each partition is meaningful.

**"Retry topics always preserve strict per-key order."** No. Non-blocking retries allow newer records to process ahead of retrying records.

**"DLT replay is just resending an old record."** No. Replays can deliver stale events after newer state; sequence/idempotency policies are required.

**"Consumer rebalance guarantees all old async tasks finished."** No. The application must manage in-flight work.

**"Exactly-once solves all duplicates and ordering."** No. Kafka transactions have their own scope; external DB side effects need idempotency/coordination.

**"Increasing partitions only increases throughput."** No. It can alter key-to-partition mapping and affect per-key order.

**"A higher offset in another partition means a newer event."** No. Offsets compare only within the same partition.

## 25. Ordering design checklist

**Producer**

- [ ] Identify aggregates/keys requiring ordering.
- [ ] All producers share the same key contract and serializer.
- [ ] Non-null keys for records requiring per-entity ordering.
- [ ] Partitioner mapping is stable and tested.
- [ ] enable.idempotence and producer retry settings are appropriate.
- [ ] Multiple producer writers have a sequencer/versioning strategy.
- [ ] Outbox relay publishes in aggregate sequence order.
- [ ] Partition count changes have a migration plan.

**Consumer**

- [ ] Each partition has a sequential processing flow by design.
- [ ] Concurrency is chosen based on partition count and workload.
- [ ] Async work does not complete out of order or has version guards.
- [ ] Batch processing preserves order within each partition.
- [ ] Rebalance drains/cancels in-flight tasks properly.
- [ ] Offset acknowledgment aligns with business completion semantics.
- [ ] Blocking vs non-blocking retries are chosen per ordering contract.
- [ ] DLT replay has a sequence/reconciliation policy.

**Correctness**

- [ ] Events include aggregate ID and sequence/version when needed.
- [ ] Consumer is idempotent against duplicate delivery.
- [ ] Inbox/unique event ID is stored alongside the business side effect.
- [ ] Stale events and version gaps are distinguished.
- [ ] Kafka EOS is not mistaken for DB exactly-once.
- [ ] Business ordering domain is documented in the contract.

**Operations and verification**

- [ ] Lag is monitored per partition.
- [ ] Hot keys/partition skew are observed.
- [ ] Dashboards exist for retry/DLT/rebalance metrics.
- [ ] Integration tests cover same key, multiple keys, retries, and rebalances.
- [ ] Tests cover partition expansion and replays.
- [ ] Runbook exists for handling out-of-order events.
- [ ] Keys/offsets/event IDs are not used as metric labels.

## 26. References

- Apache Kafka Documentation — Introduction and topics/partitions: https://kafka.apache.org/documentation/
- Apache Kafka Producer Configuration: https://kafka.apache.org/documentation/#producerconfigs
- Apache Kafka Consumer Configuration: https://kafka.apache.org/documentation/#consumerconfigs
- Spring for Apache Kafka — Message Listener Containers: https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html
- Spring for Apache Kafka — Handling Exceptions: https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html
- Spring for Apache Kafka — Retry Topic: https://docs.spring.io/spring-kafka/reference/retrytopic.html
- Spring for Apache Kafka — Transactions: https://docs.spring.io/spring-kafka/reference/kafka/transactions.html

Verify producer defaults, idempotence, retry semantics, and listener APIs against the exact Kafka client/Spring Kafka version you run in production.

## 27. Conclusion

Kafka guarantees record ordering **within a partition**, not a global order across multiple partitions. To preserve ordering by business aggregate, producers need stable keys, consistent partitioners, and sequenced send flows; consumers must process sequentially per partition and prevent async side effects from completing out of order. Producer idempotence handles retries/duplicates at the protocol layer, but does not replace business sequence numbers or idempotency.

Ordering can also be affected by partition count increases, multiple producers, blocking/non-blocking retries, DLT replays, batch processing, and consumer rebalances. A reliable production design combines per-key routing, aggregate versions, inbox/outbox patterns, suitable retry policies, lag/sequence monitoring, and integration tests. Define your ordering domain clearly before choosing partition keys, concurrency, or retry strategies; those choices directly govern data correctness.

