# Processing Orders in Key-Ordered Sequence Across Multiple Instances

An order system typically receives multiple events for the same order: order creation, payment confirmation, inventory reservation, packing, shipping, and cancellation. Events for a single order must be applied in their proper business sequence. At the same time, the system needs multiple consumer instances to scale throughput and continue operating if one instance stops.

The challenge is **parallelism across orders combined with sequential execution within each order**. If two instances process events for the same `orderId` concurrently, a newer state update can complete before an older event. Simply adding more consumers or configuring a single consumer group does not automatically preserve business ordering.

This exercise builds a Spring Cloud Stream pipeline using Kafka as the primary example: the producer attaches `orderId` as the record key, Kafka distributes keys across partitions, multiple instances in the same consumer group process distinct partitions, and the database checks `eventId` and `sequence` to prevent duplicates and detect out-of-order events. The final sections compare equivalent designs for RabbitMQ and Pulsar.

## 1. Objectives and Completion Criteria

After completing this exercise, the system must satisfy:

- Events for the same `orderId` land in the same Kafka partition.
- Different partitions are processed in parallel by multiple consumer instances.
- Within a partition, the handler processes sequentially and does not run asynchronous side effects that reorder completion.
- Each order carries a monotonically increasing sequence; the consumer detects missing, duplicate, or out-of-order events.
- Restarts, rebalances, and redeliveries do not lose events; duplicates never execute business side effects a second time.
- Retry/DLQ does not silently allow a later event for the same order to jump ahead of an unprocessed earlier event.
- Tests demonstrate ordering across multiple instances, multiple partitions, and failure scenarios.

### 1.1. Scope of Guarantees

In Kafka, ordering is guaranteed within a single partition. If all events for the same order are written to the same partition, consumers can process them in broker-stored order. Kafka does not guarantee global ordering across partitions.

This ordering is the partition append order, not automatically the event creation timestamp across multiple independent producers. If two services both emit events for the same order, the system must have an authoritative sequence/serialization source to decide which event comes first.

~~~mermaid
flowchart LR
    A[Order A events] --> K1[Partition 0]
    B[Order B events] --> K1
    C[Order C events] --> K2[Partition 1]
    D[Order D events] --> K3[Partition 2]
    K1 --> W1[Consumer instance 1]
    K2 --> W2[Consumer instance 2]
    K3 --> W3[Consumer instance 3]
    W1 --> DB[(Order state)]
    W2 --> DB
    W3 --> DB
~~~

In the diagram, orders A and B may share a partition and therefore be processed sequentially within that partition. Orders C and D reside on different partitions and can be processed concurrently. There is no ordering guarantee between A and C because they belong to different partitions.

## 2. Data Model and Ordering Rules

Each event needs at least four fields:

| Field | Purpose |
|---|---|
| `eventId` | Unique ID for identification and deduplication. |
| `orderId` | Business key; used as the Kafka record key. |
| `sequence` | Monotonically increasing sequence number within a single order. |
| `eventType` | Type of business state change such as `ORDER_CREATED`, `PAYMENT_CONFIRMED`. |

Example Java record:

~~~java
package com.acme.orders;

import java.time.Instant;
import java.util.UUID;

public record OrderEvent(
    UUID eventId,
    String orderId,
    long sequence,
    String eventType,
    Instant occurredAt,
    long amountInMinorUnit
) {}
~~~

An order's event stream:

| orderId | sequence | eventType |
|---|---:|---|
| `ORD-1001` | 1 | `ORDER_CREATED` |
| `ORD-1001` | 2 | `PAYMENT_CONFIRMED` |
| `ORD-1001` | 3 | `STOCK_RESERVED` |
| `ORD-1001` | 4 | `ORDER_PACKED` |
| `ORD-1001` | 5 | `ORDER_SHIPPED` |

Order `ORD-2002` has its own sequence starting from 1. Never compare sequence numbers across different orders.

Consumer rules:

1. If `eventId` was already processed, ignore as a duplicate.
2. If sequence equals `lastSequence + 1`, apply the event and update state.
3. If sequence is greater than `lastSequence + 1`, detect a gap: one or more prior events are missing.
4. If sequence is less than or equal to `lastSequence` with a different `eventId`, detect a stale/conflicting event; inspect data and replay policy.

Sequence acts as an extra business guard. The Kafka key ensures the same key enters the same partition, while sequence catches upstream bugs, out-of-order replays, or partitioning changes.

## 3. Choosing `orderId` as the Partition Key

Kafka routes records to partitions based on the record key and partitioner. With the default partitioner, the same key consistently maps to the same partition as long as the partition count remains unchanged. Thus, every event with `orderId=ORD-1001` goes to the same partition when the producer consistently sets the key.

Do not use `eventId` as the key for flows requiring per-order ordering. Because `eventId` changes on every message, events for the same order would scatter across multiple partitions.

### 3.1. Configuring the Producer Key in the Kafka Binder

Declare the output binding and use the `orderId` header as the Kafka message key:

~~~yaml
spring:
  cloud:
    stream:
      output-bindings: orders-out-0
      bindings:
        orders-out-0:
          destination: orders.events
      kafka:
        bindings:
          orders-out-0:
            producer:
              message-key-expression: headers['orderId']
              configuration:
                enable.idempotence: true
                acks: all
                max.in.flight.requests.per.connection: 5
~~~

`message-key-expression` is a Kafka binder expression for extracting the key from the message. This example requires the producer to set the `orderId` header before sending. `enable.idempotence`, `acks`, and `max.in.flight.requests.per.connection` are Kafka producer settings; they improve producer retry reliability and preserve batch order within Kafka's supported bounds.

The publisher sends a `Message` via `StreamBridge`:

~~~java
package com.acme.orders;

import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Component;

@Component
public class OrderEventPublisher {

    private final StreamBridge streamBridge;

    public OrderEventPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    public boolean publish(OrderEvent event) {
        Message<OrderEvent> message = MessageBuilder
            .withPayload(event)
            .setHeader("orderId", event.orderId())
            .build();

        return streamBridge.send("orders-out-0", message);
    }
}
~~~

The return value of `send` indicates that the message was accepted by the framework's message channel layer. It does not by itself prove the broker durably persisted the message or that consumers finished processing it.

### 3.2. Producers Must Emit Events in Sequence Order

The partition key only selects the partition; it does not sort two independent producers by business timestamp. For example:

- Producer A creates sequence 2 but experiences network delay.
- Producer B sends sequence 3 and reaches Kafka first.
- Kafka appends sequence 3 before sequence 2 despite sharing the same key.

The consumer sees the append order and cannot reliably infer that sequence 2 should precede sequence 3 purely from timestamps.

To prevent this, the event source must:

- Allocate sequence numbers inside the transaction updating the order aggregate.
- Write events to a transactional outbox within the same transaction as order state.
- Have the dispatcher publish outbox records strictly in sequence order for each `orderId`.
- Optionally run multiple dispatchers in parallel sharded by key, provided a single dispatcher stream serializes any given key.
- Mark outbox records as published after a successful send; if a crash occurs after publishing but before marking, the event may be resent, so consumers still need idempotency.

Do not rely on `occurredAt` for strict ordering: clocks across instances can drift, timestamps can collide, and recording time does not necessarily match business commit order.

## 4. Designing the Topic and Partition Count

In this exercise, create topic `orders.events` with 12 partitions. This illustrates multiple consumers; production systems must choose partition counts based on throughput, cluster capacity, active key count, and operational manageability.

With three application instances, each running concurrency 4:

\[
3\ \text{instances} \times 4\ \text{consumer threads} = 12
\]

Total consumer threads equal the partition count, allowing all 12 partitions in one group to be utilized if all threads are healthy and the broker balances assignments normally.

If total consumer threads exceed the partition count, extra consumers receive no partitions and stay idle. If fewer than the partition count, one consumer handles multiple partitions.

### 4.1. Do Not Increase Partition Count Arbitrarily

With a partitioner based on `hash(key) % partitionCount`, changing the partition count can remap a key to a different partition. When that happens:

- Older events for `ORD-1001` remain on the old partition.
- Newer events for the same order may be written to a new partition.
- Two partitions can be processed concurrently by consumers.
- Single-stream ordering between old history and new events for that order is broken.

If you must increase partitions, plan a migration: pause or fence producers, drain or migrate data by key, switch to a new topic version, or use versioned stable routing. Never treat increasing partitions as a throughput-only change.

## 5. Configuring Multiple Consumer Instances in the Same Group

Consumers must share the same `group` so Kafka distributes partitions among instances. If each instance uses a distinct group, every instance receives the full stream and can trigger duplicate side effects.

~~~yaml
spring:
  cloud:
    function:
      definition: processOrders
    stream:
      bindings:
        processOrders-in-0:
          destination: orders.events
          group: orders-processor
          consumer:
            concurrency: 4
            max-attempts: 3
      kafka:
        bindings:
          processOrders-in-0:
            consumer:
              configuration:
                max.poll.records: 1
                max.poll.interval.ms: 300000
~~~

`concurrency: 4` instructs each application instance to spawn four consumer threads for the binding. With three instances, there are up to 12 group members in total. Kafka distributes partitions across members automatically.

`max.poll.records: 1` is used in this exercise to highlight per-record ordering and simplify observation. It is not optimal for throughput in every system; when switching to batching, verify processing time and batch error-handling semantics.

There is no need to set `instanceCount`/`instanceIndex` for a Kafka consumer group to divide partitions. Those instance properties belong to Spring Cloud Stream's partitioned producer/consumer mechanism and do not replace Kafka's consumer group assignment.

### 5.1. One Partition Has Only One Consumer in a Group at a Time

Within a single consumer group, a partition is assigned to at most one consumer member at any given time. Consequently, multiple instances can process multiple partitions concurrently, but they never process the same partition in parallel within the same group.

This forms the basis for key-based ordering:

1. The producer sets `orderId` as the key.
2. Kafka writes every event with the same key to the same partition.
3. A single consumer member owns that partition.
4. The consumer processes records in poll/listener order.
5. During a rebalance, ownership of the partition may move to another member; the committed offset determines where processing resumes.

Do not spawn `@Async`, `parallelStream()`, or uncontrolled executors inside the handler if side effects must stay ordered. If the listener receives record 1 and offloads it asynchronously, record 2 can finish before record 1 even though Kafka delivered them in order.

## 6. Sequential Consumer Function

Imperative function receiving each event:

~~~java
package com.acme.orders;

import java.util.function.Consumer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderFunctions {

    @Bean
    Consumer<OrderEvent> processOrders(OrderService orderService) {
        return orderService::applyInOrder;
    }
}
~~~

This function invokes the service synchronously. While a consumer thread is processing the current event, it must finish before returning rather than offloading side effects to a background thread and returning success early.

If using a reactive function, preserve order with sequential operators such as `concatMap` per partition stream. Using `flatMap` with concurrency can allow multiple events to execute concurrently and finish out of source order. Preserving output emission order is also insufficient if side effects inside inner publishers execute concurrently.

## 7. Sequence Guard and Idempotency in the Database

Kafka's at-least-once delivery can redeliver a record if a consumer crashes after executing business logic but before committing the offset. Therefore, the service must enforce deduplication at the business layer.

A simple table design:

| Table | Key | Main columns |
|---|---|---|
| `orders` | `order_id` | order status, `last_sequence`, version |
| `processed_events` | `event_id` | processed timestamp, `order_id`, sequence |

The database needs a unique constraint on `processed_events.event_id`. Recording the processed event and updating order state must execute within the same DB transaction.

~~~java
@Service
public class OrderService {

    private final ProcessedEventRepository processedEvents;
    private final OrderRepository orders;

    public OrderService(
            ProcessedEventRepository processedEvents,
            OrderRepository orders) {
        this.processedEvents = processedEvents;
        this.orders = orders;
    }

    @Transactional
    public void applyInOrder(OrderEvent event) {
        boolean firstDelivery = processedEvents.insertIfAbsent(
            event.eventId(), event.orderId(), event.sequence()
        );

        if (!firstDelivery) {
            return; // Event ID has already been applied.
        }

        OrderState state = orders.findForUpdate(event.orderId())
            .orElseGet(() -> {
                if (event.sequence() != 1 ||
                        !"ORDER_CREATED".equals(event.eventType())) {
                    throw new IllegalStateException(
                        "First event for an order must be ORDER_CREATED"
                    );
                }
                return OrderState.newOrder(event.orderId());
            });

        long expected = state.lastSequence() + 1;
        if (event.sequence() != expected) {
            throw new SequenceGapException(
                event.orderId(), expected, event.sequence()
            );
        }

        state.apply(event);
        state.setLastSequence(event.sequence());
        orders.save(state);
    }
}
~~~

`insertIfAbsent` must be implemented with an atomic unique constraint or upsert, not an unlocked `SELECT` followed by `INSERT`. If the sequence guard throws an exception, the DB transaction rolls back the `processed_events` insert too, allowing the event to be retried once the gap is resolved.

If an event arrives with a sequence lower than expected but a new `eventId`, do not automatically treat it as a valid duplicate. It could be a replayed old event, a misallocated sequence, or a logically duplicated emission from the producer. Route it to an investigation/quarantine flow per contract.

### 7.1. Why Both Key and Sequence Are Needed

| Mechanism | What it protects | What it cannot solve |
|---|---|---|
| Kafka key = `orderId` | Routes same order to same partition. | Two independent producers emitting out of order before append. |
| Partition ordering | Records in one partition are read in append order. | Ordering across partitions or async side effects. |
| Unique `eventId` | Prevents reapplying the exact same event. | Detecting missing sequence events. |
| Per-order `sequence` | Detects gaps or stale events. | Automatically recovering missing events. |
| DB transaction/lock | Protects concurrent state updates. | Atomic commit with Kafka without a proper transactional design. |

## 8. Handling Sequence Gaps Without Breaking Ordering

Suppose an order's state has `lastSequence=2`, and the consumer receives sequence 4. Sequence 3 is missing or delayed.

Do not apply event 4 and wait for event 3 to arrive later. That moves business state backward out of order. Also do not send event 4 to a DLQ, commit the offset, and let event 5 update the same order if strict ordering is required.

There are three strategies:

1. **Block partition:** halt processing on that partition at the failing record until the missing event is recovered. Simple and preserves order, though other keys on the same partition are also blocked.
2. **Per-key parking/sequencer:** store later events in a pending store keyed by `orderId`, hold across the sequence gap, and apply only after the missing event arrives. Requires transactional design and recovery for the pending store.
3. **Quarantine + controlled replay:** move failing records into quarantine, keep checkpoints/offsets from crossing unsafe boundaries, fix the root cause, and replay in proper sequence order. Do not simply republish one record to the tail of the topic if later events have already been applied.

In this exercise, choose the block-partition strategy for sequence gaps so behavior is easy to verify. In production with many keys sharing a partition, evaluate head-of-line blocking impact and consider per-key parking if high availability is required.

## 9. Retry and DLQ Must Preserve Key Invariants

Retries can hold a partition at the failing record, though long backoffs reduce partition throughput. A DLQ typically lets the consumer advance to the next record after recovering the failed one; that can violate per-key business ordering if subsequent events still get processed.

Example:

| Offset | orderId | sequence | Outcome |
|---:|---|---:|---|
| 100 | `ORD-1001` | 1 | Succeeded |
| 101 | `ORD-1001` | 2 | Failed, moved to DLQ and committed |
| 102 | `ORD-1001` | 3 | Succeeded |

The order state applied sequence 3 while sequence 2 was never processed. Kafka preserved offset order, yet the DLQ workflow allowed skipping an event in the business stream.

For strict ordering:

- Distinguish transient retryable errors from poison messages needing intervention.
- Never commit past a gap if the partition must maintain strict ordering.
- If using a DLQ, capture original topic, partition, offset, key, sequence, `eventId`, and exception metadata.
- Replay in proper key/sequence order; never replay behind newer events already applied.
- Alert whenever a partition pauses or an order remains pending too long.
- Rely on idempotency so replays do not repeat already-committed side effects.

Example bounded retry configuration for record mode:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrders-in-0:
          consumer:
            max-attempts: 3
~~~

This only caps attempts at the Spring Cloud Stream layer. Configure the Kafka binder error handler/DLQ appropriately and verify exact offset recovery behavior. If strict ordering requires blocking the partition, do not enable automatic DLQ-and-continue recovery without a sequencer or mechanism to hold subsequent events.

## 10. Rebalances, Restarts, and Multiple Instances

Kafka can trigger a rebalance when an instance starts or stops, a consumer misses heartbeats or fails to poll in time, partition counts change, or consumer group membership changes.

During a rebalance, partitions may move from instance A to instance B. This is normal behavior. To preserve ordering:

1. Use the same group name across all instances.
2. Ensure consumer processing never exceeds `max.poll.interval.ms`.
3. Use graceful shutdown so in-flight work completes and commits when possible.
4. Never commit offsets before the required business transaction completes.
5. Expect at-least-once redelivery after crashes and protect with idempotency.
6. Keep keys and partitioning strategies stable throughout rollouts.

A partition is assigned to only one group member at a time, though a brief pause can occur during rebalances. Never design the application assuming the same instance will always own a given `orderId`.

### 10.1. Running Three Instances in a Test Environment

Launch three processes with identical configuration:

| Instance | Consumer concurrency | Group |
|---|---:|---|
| `orders-1` | 4 | `orders-processor` |
| `orders-2` | 4 | `orders-processor` |
| `orders-3` | 4 | `orders-processor` |

The topic has 12 partitions. All 12 consumer threads can receive partitions. Inspect assignment logs to verify actual distribution; do not assume each instance always gets exactly four partitions because assignment strategies and membership timing can distribute them differently.

## 11. End-to-End Testing

Tests must use a real Kafka broker or equivalent integration environment. The Test Binder checks function/binding wiring but does not verify partition assignments, consumer groups, producer keys, rebalances, or broker-committed offsets.

### 11.1. Test Data

Publish concurrently:

- `ORD-A`: sequences 1 through 100.
- `ORD-B`: sequences 1 through 100.
- `ORD-C`: sequences 1 through 100.
- Emit events for each order rapidly to generate load.

Each event carries a unique `eventId`. Record input fixtures and expected sequences per `orderId`.

### 11.2. Verifying Same Key Lands in Same Partition

Use a Kafka consumer to inspect record metadata or observe partitions in a test harness:

1. Publish 100 events for `ORD-A`.
2. Record the partition of each record.
3. Assert only a single partition appears for key `ORD-A`.
4. Repeat for `ORD-B` and `ORD-C`.
5. Assert sequences increase monotonically with offset inside each order's partition.

Do not assert that different orders must always land on different partitions. Hash collisions are normal; what matters is that a single order is never split across partitions.

### 11.3. Verifying Parallel Processing Across Multiple Instances

Start three instances in the same group and enable logging for:

- `orderId`.
- `sequence`.
- Kafka partition/offset.
- Consumer client/instance ID.
- Processing start and end timestamps.

Expected results:

- Different partitions can be processed concurrently.
- Each order's sequences are applied in order 1, 2, 3…100.
- No two instances process the same partition concurrently within the same group.
- An order may migrate to another instance after a rebalance while its sequence continues accurately.

### 11.4. Verifying Duplicates and Idempotency

Resend the same `eventId` twice, including cases where the producer times out without knowing whether the broker persisted it. Assert:

- The `processed_events` table contains only one row for that `eventId`.
- The order state increments sequence only once.
- Business side effects do not repeat.
- Duplicate metrics increment if the application instruments them.

### 11.5. Verifying Sequence Gaps

Create an order with `lastSequence=2`, then publish sequence 4 without sequence 3.

Assert:

- The service detects `expected=3, actual=4`.
- The order state does not jump to sequence 4.
- The event is not marked as successfully processed.
- The partition/key is held or the event is parked according to the chosen strategy.
- Logs/metrics/alerts capture `orderId`, `sequence`, and partition/offset for investigation.

Then inject/replay sequences 3 and 4 in order; assert the state reaches sequence 4.

### 11.6. Verifying Rebalances Under Backlog

1. Publish enough events to build a backlog.
2. Gracefully stop one instance.
3. Verify its partitions transfer to remaining instances.
4. Keep publishing new events for the same orders.
5. Reconcile sequences and event IDs in the database.
6. Restart the stopped instance and verify it rejoins the group without resetting offsets.

Repeat by abruptly killing a process mid-handling. Some events may be redelivered; business outcomes must remain accurate thanks to DB transactions and idempotency.

### 11.7. Test Matrix

| Test case | Scenario | Expected result |
|---|---|---|
| KEY-01 | 100 events with same `orderId` | All land on the same partition. |
| KEY-02 | Two distinct `orderId` values | Can process concurrently on different partitions. |
| SEQ-01 | Continuous sequence 1..N | State advances in exact order. |
| SEQ-02 | Missing sequence mid-stream | Gap detected; later event is not applied. |
| DUP-01 | Same `eventId` sent twice | Side effect executes only once. |
| PROD-01 | Producer retries on flaky network | Order preserved within idempotent producer bounds; duplicates guarded by consumer. |
| CON-01 | Three instances in same group | Partitions distributed across members. |
| CON-02 | One instance stops | Rebalance occurs with zero event loss. |
| CON-03 | One instance crashes mid-processing | Redelivery handled idempotently. |
| DLQ-01 | Poison event for an order | Later events for same order do not jump past the gap. |
| PART-01 | Partition count changed | Test demonstrates key remapping and need for migration. |
| LOAD-01 | Many concurrent orders | Throughput scales while per-order sequence holds. |

## 12. Checking Hot Keys and Load Distribution

Partitioning by `orderId` preserves order but can create hot partitions if a single order or key group dominates traffic.

For instance, 90% of messages might belong to one massive order. That order always hits one partition while the other 11 partitions sit lightly loaded. Adding consumer instances cannot parallelize that single order if strict ordering is required.

Considerations:

- Optimize processing for hot keys.
- Reduce payload sizes and DB/API overhead.
- Split business logic into independent steps while preserving sequencing at the aggregate boundary.
- Increase partitions only when routing/migration preserves historical order.
- Measure skew by partition and key group, not just aggregate throughput.

Never split a single `orderId` across multiple keys purely to balance load if events still depend on whole-order ordering. Doing so trades a simple model for complex cross-key synchronization.

## 13. When Using RabbitMQ

RabbitMQ queues generally preserve enqueue order, yet multiple consumers, prefetch, redeliveries, and asynchronous processing can cause side-effect completion order to diverge from delivery order.

### 13.1. Single Consumer per Queue

- Use one active consumer with concurrency 1.
- Set prefetch to 1 if only one unacknowledged delivery is allowed at a time.
- Process synchronously and ACK only after the DB transaction commits.
- Optionally use Single Active Consumer to keep a standby consumer ready if the active consumer drops.

This approach is simple for strict queue ordering but bounds queue throughput.

### 13.2. Sharding by Key Across Multiple Queues

To process multiple orders in parallel, route the same `orderId` to the same queue or partition queue. Different queues can be consumed concurrently. Routing must stay stable by key, and shard counts must not change arbitrarily while history is in flight.

With the RabbitMQ binder, you can use Spring Cloud Stream's partitioned producer/consumer support if topology and binder configuration fit. Verify the actual queue/partition mapping and ensure each partition queue has only a single sequential consumer when strict order is needed.

Prefetch values greater than 1 can improve throughput, but holding multiple unacknowledged deliveries increases out-of-order completion risk if processed concurrently. Retries and requeues can also place an older message behind newer ones. Therefore, never infer strict ordering merely because a queue is FIFO.

## 14. When Using Apache Pulsar

Pulsar offers multiple subscription types with distinct semantics:

| Subscription type | Characteristics | Fit for requirements |
|---|---|---|
| `Exclusive` | One active consumer on the subscription. | Simple ordering, limited throughput. |
| `Failover` | One active consumer, others on standby. | Preserves sequential processing with failover. |
| `Shared` | Multiple consumers receive messages from the subscription. | High throughput; no global or per-key ordering by default. |
| `Key_Shared` | Messages with the same key go to the same consumer per key-shared rules. | Parallelism across keys with per-key ordering when producer/batching are compatibly configured. |

For multiple instances with per-`orderId` ordering, `Key_Shared` is the primary option to evaluate. Producers must set the message key to `orderId`. When batching is enabled, use key-based batching compatible with `Key_Shared`; batches mixing multiple keys and dispatched as one unit can break key-level distribution.

Consumers processing messages of the same key must process them sequentially. If a consumer receives distinct keys, it may process across keys concurrently in a controlled way, but never run two events of the same key concurrently.

Do not use `Shared` while assuming messages for the same order will always finish in order. Also inspect ACK timeouts, redeliveries, and dead-letter policies because redelivered messages can disrupt the processing sequence.

## 15. Observability and Operations

Structured logs should include:

- `eventId`, `orderId`, `sequence`, `eventType`.
- `topic`, `partition`, `offset` (Kafka) or the corresponding broker queue/subscription/message ID.
- Consumer group, instance ID, and start/end timestamps.
- Outcome: `APPLIED`, `DUPLICATE`, `GAP`, `STALE`, `RETRY`, or `DLQ`.

Metrics should use bounded-cardinality tags:

| Metric | Appropriate tags |
|---|---|
| `orders.events.processed` | binder, binding, outcome |
| `orders.events.sequence_gap` | binding, error_category |
| `orders.events.duplicate` | binding |
| `orders.consumer.lag` | topic, bounded partition, group |
| `orders.partition.processing.time` | binding, outcome |

Never use `orderId`, `eventId`, or `correlationId` as metric labels because cardinality grows unboundedly with orders/events. Keep those IDs in logs and traces for targeted debugging.

Key alerts:

- Consumer lag climbing continuously.
- Partitions left unassigned or frequent unexpected assignment churn.
- Sequence gaps detected.
- Spikes in redeliveries or retries.
- New messages arriving in DLQ.
- One partition showing starkly different throughput or lag than peers.
- An order/key remaining pending past SLA thresholds.

## 16. Common Design Pitfalls

1. Using `eventId` as the Kafka key, scattering events of the same order across partitions.
2. Using `orderId` as the key while multiple producers send concurrently without authoritative sequencing or source serialization.
3. Assuming Kafka guarantees ordering across partitions.
4. Increasing partition counts without accounting for key remapping.
5. Giving each instance a separate consumer group so all instances receive duplicate data.
6. Raising concurrency and using `@Async`/`parallelStream()`, causing out-of-order side effects.
7. Using a retry topic or DLQ and committing offsets, letting later events for the same order bypass a failed event.
8. Sorting solely by event timestamp while ignoring business sequence numbers.
9. Omitting a unique constraint on `eventId`, allowing duplicates to update the DB twice.
10. Committing offsets before the business transaction completes.
11. Using Pulsar `Shared` when `Key_Shared` ordering is required.
12. Setting high RabbitMQ prefetch with parallel handlers while expecting FIFO completion.
13. Putting `orderId` into metric tags, causing cardinality explosion per order.
14. Skipping tests for rebalances, crashes, and replays.

## 17. Lab Execution Workflow

1. Create topic `orders.events` with 12 partitions and confirm it is ready.
2. Create the producer output binding, attach `orderId` as a header, and configure `message-key-expression`.
3. Configure appropriate producer idempotence and reliability settings.
4. Create the `processOrders` function consuming each `OrderEvent`.
5. Configure fixed consumer group `orders-processor` with concurrency 4.
6. Start three instances; verify 12 consumer threads total and inspect partition assignments.
7. Emit 100 consecutive events per `orderId`; confirm all share one partition and sequence increments cleanly.
8. Persist `eventId` and `lastSequence` inside a DB transaction to block duplicates and detect gaps.
9. Inject duplicates, out-of-order sequences, and poison events; verify order state remains uncorrupted.
10. Stop/crash one instance under backlog; inspect rebalances and redeliveries.
11. Measure lag, throughput, processing latency, and partition skew.
12. Test changing partition count on a separate scratch topic to observe key remapping; never alter the live pipeline topic.
13. Record configurations, results, event IDs, and checkpoints for reproducibility.

### Acceptance Checklist

- [ ] `orderId` is used as the Kafka record key across all producer paths.
- [ ] The source allocates monotonically increasing sequences and publishes in order per order.
- [ ] Outbox/dispatcher never publishes a later event before an earlier event of the same order.
- [ ] Topic partition counts are managed with an explicit migration plan.
- [ ] All consumer instances share the same group.
- [ ] Consumer concurrency does not exceed partition and downstream capacity.
- [ ] Handlers execute synchronously per partition or use a per-key sequencer.
- [ ] DB transactions update order state and processed-event records atomically.
- [ ] Sequence gaps are never silently skipped.
- [ ] Retry/DLQ never lets a later event of the same key jump past an unprocessed event.
- [ ] Rebalances, graceful restarts, and crashes have been tested.
- [ ] Duplicates never trigger a second side effect.
- [ ] Metrics do not use `orderId`/`eventId` as labels.
- [ ] Dashboards monitor lag, partition skew, sequence gaps, duplicates, and DLQ.

## References

- [Spring Cloud Stream – Kafka Binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/index.html)
- [Spring Cloud Stream – Kafka Binder Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html)
- [Spring Kafka – Message Listener Containers and Offset Management](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html)
- [Apache Kafka – Producer Configuration](https://kafka.apache.org/documentation/#producerconfigs)
- [Apache Kafka – Consumer Configuration](https://kafka.apache.org/documentation/#consumerconfigs)
- [RabbitMQ – Consumer Prefetch](https://www.rabbitmq.com/docs/consumer-prefetch)
- [RabbitMQ – Single Active Consumer](https://www.rabbitmq.com/docs/consumers#single-active-consumer)
- [Spring Cloud Stream – Rabbit Binder](https://docs.spring.io/spring-cloud-stream-binder-rabbit/docs/current/reference/html/)
- [Apache Pulsar – Messaging Concepts and Subscriptions](https://pulsar.apache.org/docs/concepts-messaging/)
- [Apache Pulsar – Key_Shared Subscription](https://pulsar.apache.org/docs/concepts-messaging/#key_shared)
- [Spring for Apache Pulsar – Message Consumption](https://docs.spring.io/spring-pulsar/reference/reference/pulsar/message-consumption.html)
