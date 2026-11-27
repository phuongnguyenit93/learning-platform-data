# Preserving Ordering While Increasing Parallelism

In an event-driven **Spring Cloud Stream** application, increasing consumers, threads, or replicas usually improves throughput. In return, concurrent processing can cause events to complete out of their published order, especially when events mutate the same business entity. An order flow might emit `CREATED`, `PAID`, and then `CANCELLED`; if `CANCELLED` completes before `PAID`, the final state can be wrong even though the broker stored the messages in the right order.

This lesson belongs to the **Performance** chapter of the `SPRING_CLOUD_STREAM` module and uses the `Supplier`/`Function`/`Consumer` functional model, bindings, and binders for Kafka, RabbitMQ, or Pulsar. The goal is to define the **unit of ordering** (entire topic, partition, queue, or business key), choose an appropriate parallelism level, and verify that the ordering of **business effects** holds under higher load, retries, or instance handoffs.

## 1. Define the exact ordering guarantee

"Preserving order" has multiple meanings. State explicitly what the system must guarantee before picking `concurrency` or partition counts.

| Ordering type | Example | Guarantee scope |
|---|---|---|
| Publish order | Producer sends `E1`, then `E2` | Within the producer's send sequence; can depend on retries and client settings |
| Log/queue order | `E1` appears before `E2` in a partition | Broker append or ordering within a storage unit |
| Delivery order | Consumer receives `E1` then `E2` | Depends on broker, subscription, redelivery, and consumption model |
| Processing start order | Handler starts `E1` before `E2` | Depends on listener/executor scheduling |
| Completion order | `E1` finishes writing to the database before `E2` | Depends on completion time of business operations |
| Effective state order | Version 10 is applied before version 11 | Depends on version/transaction checks at the target store |

The broker can guarantee **log** order, yet it cannot automatically guarantee **database commit** order if code uses `CompletableFuture`, hands messages off to a thread pool, or executes operations of varying durations. Protect ordering from receipt all the way until business effects complete.

## 2. Global ordering vs. per-key ordering

These two requirements have vastly different costs:

- **Global ordering:** every event across all orders must complete in a single sequence. A single sequential processing lane is the easiest design to verify; parallelism is strictly constrained.
- **Per-business-key ordering:** only events for the **same `orderId`** must stay ordered; different orders can be processed in parallel. This is usually the best scaling choice for event-driven applications.

Example:

```text
Order A: A-1 -> A-2 -> A-3  (must preserve order)
Order B: B-1 -> B-2         (must preserve order)

Valid processing schedule:
  A-1, B-1, B-2, A-2, A-3

Invalid processing schedule for Order A:
  A-1, A-3, B-1, A-2, B-2
```

Two independent keys A and B can run on different workers. For the same key, two state-updating tasks should not run concurrently unless storage enforces versioning or compare-and-set to stop stale updates from overwriting newer ones.

## 3. Why can raising concurrency reorder events?

Suppose a consumer receives two events for the same order:

```text
Time            Worker 1                     Worker 2
-------------------------------------------------------------
t0              receives Order#42 version=1
t1                                           receives version=2
t2                                           processes fast
t3                                           writes DB version=2
t4              slow processing finishes
t5              writes DB version=1   <-- overwrites newer state
```

If all records for `Order#42` are genuinely processed sequentially inside a synchronous listener, this scenario does not occur on that path. It can happen when messages with the same key are routed to different consumers, when a listener offloads work to a thread pool, when messages from multiple topics are merged without coordination, or when retries/replays run out of band.

**Design rule:** scale lanes **across keys**; keep a single sequential lane **within each key** when per-key ordering is required.

## 4. Business keys are the scheduling boundary

Pick a key matching the entity whose invariant must be protected:

| Business domain | Suggested key | Why |
|---|---|---|
| Order status updates | `orderId` | All changes to one order must be sequential |
| Wallet balance adjustments | `walletId` | Prevents concurrent updates to the same balance |
| Inventory per item/warehouse | `warehouseId + productId` | Sequential per warehouse-product pair |
| Customer profile | `customerId` | Ensures ordered updates to one profile |
| Independent telemetry | `deviceId` if per-device order is needed | Allows many devices to run in parallel |

Do not pick a random key (`eventId`, a fresh UUID per message) when related events must stay in the same stream. A key that changes per message destroys partition consistency. Equally, do not collapse all events onto one constant key like `all-orders`: that creates a **hot partition** and negates adding partitions.

Some flows span multiple keys (such as transferring funds between two wallets). Routing by a single key cannot solve invariants involving two keys simultaneously. Those require transactions, coordinated locks, sagas, or concurrency control at the data store; never claim a Kafka partition key alone guarantees multi-entity atomicity.

## 5. Broker order differs from business event time

Kafka guarantees offset order within **each partition**. Kafka does not guarantee order across partitions; independent producers can emit events whose business timestamps differ from broker arrival order.

Example:

```text
Service A creates E1 at 10:00:00, but network is slow.
Service B creates E2 at 10:00:01, but reaches broker first.

Broker appends: E2 then E1.
```

Even when `E1` and `E2` share the same key, a partition preserves **observed append order**, not `occurredAt` order. When you must prove E1 precedes E2 in business terms, include a **sequence number** or **entity version** issued by a single source of truth (such as the aggregate-updating transaction), rather than relying on clocks across multiple services as the sole ordering authority.

An event envelope should include:

```json
{
  "eventId": "evt-873",
  "aggregateId": "order-42",
  "aggregateVersion": 17,
  "type": "OrderPaid",
  "occurredAt": "2026-11-24T04:20:11Z",
  "payload": { "paymentId": "pay-91" }
}
```

`aggregateId` guides partition selection; `aggregateVersion` checks state ordering; `eventId` supports deduplication; `occurredAt` helps with time analysis but does not replace version. These fields require explicit schemas and version-increment rules.

## 6. Kafka: preserving order with the same record key

With the Kafka Binder, records sharing the same key are normally routed to the same partition by the Kafka producer's partitioner. Within a consumer group, a partition is assigned to one consumer in the group at a time. You can therefore process multiple partitions in parallel while preserving **per-partition record order**, provided handlers execute synchronously and do not reorder downstream.

```text
Topic orders.events (4 partitions)

order-11: v1, v2, v3 ----> P1 ----> Consumer A (sequential)
order-22: v1, v2 --------> P3 ----> Consumer B (sequential)
order-33: v1, v2 --------> P0 ----> Consumer C (sequential)

P2 holds other keys; processed independently.
```

If the producer omits a key, the client can spread records across partitions without keeping one order's events in the same partition. Therefore, verify the **actual record key sent to Kafka**, rather than seeing `orderId` inside the JSON payload and assuming the broker will hash that field.

## 7. Setting the Kafka record key from Spring Cloud Stream

In Spring Cloud Stream's functional model, an output can return `Message<T>` with the Kafka record key set via `KafkaHeaders.KEY`. Example function normalizing the key before publishing:

```java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

record OrderEvent(String eventId, String orderId, long version, String status) {}

@Bean
Function<OrderEvent, Message<OrderEvent>> keyByOrder() {
    return event -> MessageBuilder
        .withPayload(event)
        .setHeader(KafkaHeaders.KEY, event.orderId())
        .build();
}
```

Input/output configuration:

```yaml
spring:
  cloud:
    function:
      definition: keyByOrder
    stream:
      bindings:
        keyByOrder-in-0:
          destination: orders.raw
        keyByOrder-out-0:
          destination: orders.keyed
```

The function reads `OrderEvent` from input and returns `Message<OrderEvent>` with Kafka key `orderId`. If there is only one upstream producer, you can also set the key directly at the upstream producer or via `StreamBridge` with `MessageBuilder`. If the binder uses custom partitioning (`partition-key-expression`), compare the binder's algorithm against the native Kafka partitioner because they can pick different partitions for the same key.

**Note:** this example focuses on keys and bindings. The application still needs the Kafka Binder dependency, compatible serializer/content type for `OrderEvent`, and properly provisioned topics. `KafkaHeaders.KEY` is how you set the native Kafka record key; do not set an arbitrary header `orderId` and assume the broker treats it as the key.

## 8. Configuring concurrency for a Kafka consumer

Example consumer function processing events sequentially inside the listener:

```java
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.messaging.Message;

@Bean
Consumer<Message<OrderEvent>> applyOrder(OrderStateService service) {
    return message -> service.applyInTransaction(message.getPayload());
}
```

`OrderStateService` is an application business component; in this example, `applyInTransaction` **waits for the write to finish before returning**, while checking event version and event ID. Do not offload this operation to an executor and return early if ordering is required.

```yaml
spring:
  cloud:
    function:
      definition: applyOrder
    stream:
      bindings:
        applyOrder-in-0:
          destination: orders.keyed
          group: order-state-projector
          consumer:
            concurrency: 3
      kafka:
        binder:
          brokers: localhost:9092
```

`concurrency: 3` configures the number of consumer threads/containers per binder for **one instance**. Running two replicas, each configured with three, can create up to six consumers joining **the same group**. With a six-partition topic, Kafka can distribute the partitions across them. With only three partitions, some consumers get no partitions; raising concurrency further adds neither ordering nor throughput.

This is **cross-partition** parallelism. The same partition is not processed concurrently by two consumers in one group under normal assignment. Still, correctness also depends on synchronous handling, retry/rebalance behavior, and storage-side version checks.

## 9. Basic sizing formula

For a single Kafka topic and one consumer group, useful consumer threads that can be assigned partitions are capped by the partition count:

\[
T_{useful} \leq \min(P, I \times C)
\]

Where \(P\) is partition count, \(I\) is instance count, and \(C\) is concurrency per instance. This formula approximates an upper bound on concurrent consumers with partitions, not an absolute throughput forecast. CPU, hot-key share, database latency, and retry duration also cap capacity.

| Partitions | Instances | Concurrency/instance | Configured threads | Max threads with partitions |
|---:|---:|---:|---:|---:|
| 4 | 1 | 1 | 1 | 1 |
| 4 | 2 | 2 | 4 | 4 |
| 4 | 4 | 2 | 8 | 4 |
| 12 | 3 | 2 | 6 | 6 |
| 12 | 6 | 2 | 12 | 12 |

When one key accounts for 70% of traffic, a single partition can become the bottleneck even with spare total CPU. Adding partitions or instances only helps if keys are distributed evenly enough, and it still does not make a **single key** safely parallelizable.

## 10. Kafka producer: retries can affect order

Kafka records order within each partition, yet producers have retries and multiple in-flight requests. Without idempotence enabled, an earlier request retried while a later request succeeds can produce unexpected append ordering under certain `max.in.flight.requests.per.connection` settings.

An idempotent producer lets the broker recognize resends from the producer session, prevent retry duplicates, and preserve ordering per Kafka producer guarantees. Example Kafka Binder configuration on an output:

```yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          keyByOrder-out-0:
            producer:
              configuration:
                enable.idempotence: true
                acks: all
                max.in.flight.requests.per.connection: 5
```

When `enable.idempotence=true`, the Kafka producer enforces compatible values (including `acks=all`, retries, and in-flight request limits). Conflicting values can cause producer configuration errors. Verify against your Kafka client version. If an ultra-conservative setting is needed for an experiment, you can lower `max.in.flight.requests.per.connection` to 1, though that lowers throughput and does not solve ordering across **independent producers**.

An idempotent producer does not replace `eventId`/version checks in the database, does not provide global business ordering, and does not eliminate duplicates when the application replays messages from a separate business transaction.

## 11. Do not use arbitrary asynchronous processing inside a listener

Pattern prone to reordering:

```java
@Bean
Consumer<OrderEvent> unsafeOrderProcessor(Executor executor,
                                          OrderStateService service) {
    return event -> executor.execute(() -> service.applyInTransaction(event));
}
```

The listener returns immediately after `execute`. The consumer can advance to the next message in the same partition and finish/ack as configured while the earlier task is still running. If the version-2 task finishes faster than version 1, the system can overwrite state incorrectly. If the process crashes after the listener treated the message as succeeded, the data may not even be persisted yet.

Simple safe pattern for sequential requirements:

```java
@Bean
Consumer<OrderEvent> orderedProcessor(OrderStateService service) {
    return service::applyInTransaction;
}
```

If asynchronous processing is mandatory, build a **per-key or per-partition serial executor**, preserve backpressure, and ack/commit only after related work completes. That is a custom coordination mechanism requiring thorough testing; do not assume any `Flux.flatMap` or thread pool preserves order. With Reactor, `concatMap` preserves order within **a single input sequence**, but watch partition boundaries, ack behavior, and external side effects; concurrent `flatMap` can emit results in completion order rather than input order.

When per-key async processing is needed, you can shard an input stream into lanes by key hash, run `concatMap` inside each lane, and scale multiple lanes concurrently. Verify backpressure, lane lifecycle management, queue bounds, and crash/retry handling. Keep lane counts fixed when state exists or plan key-mapping migrations carefully.

## 12. Kafka Streams: tasks and stream threads

The Kafka Streams Binder processes topologies using stream tasks; each task reads assigned partitions of a subtopology. `num.stream.threads` sets the number of stream threads per instance. Adding threads/replicas distributes **independent tasks**; it never makes two threads execute the same active task at the same time.

Example:

```yaml
spring:
  cloud:
    function:
      definition: aggregateOrders
    stream:
      bindings:
        aggregateOrders-in-0:
          destination: orders.events
      kafka:
        streams:
          binder:
            applicationId: order-aggregator-v1
            configuration:
              num.stream.threads: 2
```

If a function uses `KStream` with stateful operators like `groupByKey`, `aggregate`, `join`, or `selectKey` followed by repartitioning, Kafka Streams can create **repartition topics** and new subtopologies. Ensure keys and partitioning after repartitioning still match ordering boundaries. A join across independent sources does not invent business ordering that did not exist between topics.

`applicationId` must remain stable and shared across replicas of the same topology. Replicas with different application IDs run as independent applications, potentially processing the same data and emitting duplicate outputs. Standby tasks primarily accelerate state recovery; they do not increase active tasks for a key.

## 13. RabbitMQ: one queue and multiple consumers

A RabbitMQ queue preserves message order at enqueue time, yet **multiple consumers** reading the same queue can finish processing out of order due to varying load or execution times. Large prefetch also lets one consumer hold many unacked messages. Requeues/redeliveries can alter observed order after failures.

To preserve **queue-wide** processing order, the clear choice is a single active consumer with a sequential listener. RabbitMQ supports **Single Active Consumer (SAC)**: multiple consumers can register, but the broker delivers messages to only one active consumer at a time and fails over to a standby consumer if the active one disconnects.

```yaml
spring:
  cloud:
    function:
      definition: applyOrder
    stream:
      bindings:
        applyOrder-in-0:
          destination: orders.events
          group: ordered-processors
          consumer:
            concurrency: 1
      rabbit:
        bindings:
          applyOrder-in-0:
            consumer:
              singleActiveConsumer: true
              prefetch: 1
```

`singleActiveConsumer` sets the queue argument `x-single-active-consumer=true` when the binder declares the queue; verify provisioning behavior for your release. An existing queue declared with different arguments cannot be redeclared under the same name; provision/migrate queues carefully. `prefetch: 1` minimizes unacked messages held by a consumer, making ordering easier to control on errors, though it can reduce throughput.

**Important limitation:** SAC ensures only one active consumer per queue; it does not fix reordering caused by a listener spawning threads or by retries/requeues. To process independent orders in parallel while keeping per-`orderId` order, consistently hash keys across multiple queues, enable SAC on each queue, and scale queues/consumers to match capacity. RabbitMQ mentions the `x-modulus-hash` exchange for this routing pattern; plan the required plugin/topology and queue-count migration strategy accordingly.

## 14. Pulsar: choosing the right subscription type

Pulsar has multiple subscription types with distinct ordering semantics. Do not add consumers on `Shared` and assume messages with the same key remain ordered.

| Subscription | Parallelism | Ordering notes |
|---|---|---|
| `Exclusive` | One active consumer for the subscription | Simple sequential model; cannot scale across multiple consumers on the same subscription |
| `Failover` | Active/standby; can distribute partitions across consumers | Preserves per-partition order when configured properly |
| `Shared` | Multiple consumers receive messages | No ordering guarantee; suited for independent workloads |
| `Key_Shared` | Multiple consumers, key-based distribution | Messages with the same key stick to a consumer per `Key_Shared` semantics |

With `Key_Shared`, producers **must** set consistent keys/ordering keys and must **disable standard batching or use key-based batching** (`BatcherBuilder.KEY_BASED` in the Pulsar Java client). Default batching can mix multiple keys in one batch, and the broker uses the first message's key to dispatch the entire batch, breaking expected per-key routing.

The Spring Cloud Stream Pulsar Binder supports Spring Pulsar consumer/producer properties at binder or binding scope; verify subscription-type and batching properties against your bundled Spring Pulsar release before configuring. Illustrative example (consumer binding name must match the function bean):

```yaml
spring:
  cloud:
    function:
      definition: applyOrder
    stream:
      bindings:
        applyOrder-in-0:
          destination: persistent://acme/orders/orders.events
          group: order-processing
      pulsar:
        bindings:
          applyOrder-in-0:
            consumer:
              subscription-type: key-shared
```

Enum values and binding formats can differ between versions (`Key_Shared` in the Pulsar API); verify configuration metadata and run integration tests. Do not simply set the subscription type and stop there: verify producer keys, batching strategy, subscription name, ack/redelivery, and actual scaling behavior. Messages with the same key can still run out of order if the application dispatches them concurrently outside the consumer.

## 15. Retries and redeliveries can break business order

Retries affect more than latency; they decide whether subsequent events are allowed to bypass a failed event. Suppose one `orderId` emits three events:

```text
order-42: v10 CREATED -> v11 PAID -> v12 SHIPPED

v11 fails at the database.
Should v12 be processed right away?
```

The answer depends on the **ordering contract**:

| Policy | Implementation | Trade-off |
|---|---|---|
| Stop-on-error | Hold the partition/key waiting for v11 to recover | Preserves sequential progress but causes head-of-line blocking |
| Bounded in-place retry | Retry v11 before advancing | Fits transient failures; adds latency to trailing events |
| Route v11 to DLQ and process v12 | Main stream continues | Higher throughput, yet state may miss v11 |
| Let v12 run, check version at storage | Hold v12 in pending state if v11 is missing | Requires buffer/version coordinator and gap handling |

With the Kafka Binder, check `maxAttempts`, backoff, error handler, ack mode, and DLQ settings for your release. A message sent to a DLQ usually stops blocking the main stream; records behind it can proceed. With RabbitMQ, `requeueRejected`, retries, and DLX queues also move messages back or out per specific semantics. With Pulsar, negative acknowledgements and redeliveries can change observed processing order.

**No single retry/DLQ setting simultaneously preserves absolute order, never blocks the stream, and always maximizes throughput.** Your design must select a policy matching event coupling and provide a verified recovery path.

## 16. Example error-handling policy for orders

Suppose `OrderPaid(v11)` fails due to a transient database disconnect. If v12 depends on v11, continuing with v12 can violate the `CREATED -> PAID -> SHIPPED` invariant.

Safe per-key workflow:

1. Receive v11 and check the current version of `order-42`.
2. For transient errors, retry with bounded backoff, without marking v11 complete.
3. If v11 must move to the DLQ, flag key `order-42` as having an **ordering gap** and do not apply v12 to the target projection.
4. Investigate/recover v11 or make a valid business decision to skip v11.
5. Once the gap is resolved, apply v12 and subsequent events in version order.

This is application logic, not default DLQ behavior. A DLQ only holds failed messages for investigation/replay and generally does not automatically coordinate with aggregate versions. If you choose best-effort processing without requiring every intermediate state, proceeding may be acceptable, provided you document the contract and test the consequences.

## 17. Idempotency and version checks at the target data store

Receiving in order is not enough to handle redeliveries safely. Kafka, RabbitMQ, and Pulsar can all redeliver messages after crashes, timeouts, or incomplete acks. Consumers must therefore be **idempotent** and, for ordered data, enforce **version checks**.

Example projection tables:

```sql
CREATE TABLE order_projection (
    order_id         VARCHAR(100) PRIMARY KEY,
    applied_version  BIGINT NOT NULL,
    status           VARCHAR(32) NOT NULL
);

CREATE TABLE consumed_event (
    event_id VARCHAR(100) PRIMARY KEY
);
```

Each event carries `eventId`, `orderId`, and `aggregateVersion`. Within **a single database transaction**, the consumer verifies the event was not already recorded, checks the next expected version, updates the projection, and inserts the processed `eventId`. A conditional update on an existing record might look like:

```sql
UPDATE order_projection
SET applied_version = :incomingVersion,
    status = :incomingStatus
WHERE order_id = :orderId
  AND applied_version = :incomingVersion - 1;
```

If `rowCount = 0`, distinguish three cases: duplicate/stale message (`incomingVersion <= appliedVersion`), gap (`incomingVersion > appliedVersion + 1`), or projection not yet created. For initial inserts, use appropriate upsert/transaction logic; never treat `rowCount = 0` as blanket success. A unique constraint on `eventId` detects duplicates, but only when checking/inserting and updating state happen in the **same transaction** do you avoid updating state without recording the processed marker.

**Example decision algorithm:**

```text
On receiving event (aggregateId, eventId, version):
  1. If eventId already processed: ack duplicate, do not reapply.
  2. Read/lock or conditionally update current projection.
  3. If version == currentVersion + 1:
       apply change and persist eventId in the same transaction.
  4. If version <= currentVersion:
       audit log; ignore or alert stale/conflict.
  5. If version > currentVersion + 1:
       record gap, defer processing / route to recovery mechanism.
  6. Acknowledge the message per policy only after the decision above is durable.
```

This algorithm protects data under errors or competing producers; it is not an automatic binder feature. "Acking a gapped event" is valid only if the system has **durably persisted** that event in a recovery store/queue with a drain process.

## 18. Ack/commit must follow durable business effects

On the consumer side, acking/committing offsets before finishing state updates means a crash can drop the event from the stream before the business change executes. Conversely, updating the database and crashing before ack causes redelivery: this is why idempotency is mandatory.

```text
Safe choice under at-least-once:
  receive -> validate version -> DB transaction commit -> ack/offset commit
                                                     |
                                                     +-- crash before ack -> redelivery
                                                         -> idempotency skips duplicate
```

Never claim Kafka transactions or exactly-once processing automatically cover an external database. Kafka Streams exactly-once semantics cover Kafka transactions/state/changelogs; HTTP calls, emails, or databases outside that transaction require separate guarantees (outbox, idempotency, or appropriate transaction coordination).

If using Kafka Binder `ackMode`, use syntax/semantics matching your Spring Kafka version. For RabbitMQ/Pulsar, ack timing depends on listener/container and binder settings. Test crashing **after DB commit but before ack** to prove replay neither regresses versions nor duplicates effects.

## 19. Batches, reactive pipelines, and side effects

Batching boosts throughput by cutting round trips, yet the order of **applying effects** must still be protected. A batch containing same-key events `[v20, v21, v22]` must not be written concurrently across three independent transactions if sequential state is required.

With Reactor, consider two operators:

```java
// Can process elements concurrently; results may arrive out of order:
Flux<OrderEvent> parallel = source.flatMap(this::asyncProcess);

// Processes elements sequentially within the same sequence:
Flux<OrderEvent> sequential = source.concatMap(this::asyncProcess);
```

API illustration; `asyncProcess` here is an application-supplied method returning `Publisher<OrderEvent>`. `concatMap` preserves order within **the sequence it receives**, but does not merge sequences from multiple consumers or partitions into global business order. `flatMapSequential` can preserve **emission order** within a stream while inner side effects still run concurrently: do not rely on output emission order to assert the database was updated in order.

When per-key async processing is needed, you can split an input stream into lanes hashed by key, apply `concatMap` per lane, and run multiple lanes concurrently. Verify backpressure, lane lifecycle management, queue bounds, and crash/retry behavior. Keep lane count fixed once state exists, or plan key-mapping migrations.

## 20. Increasing partitions can relocate the same key

Adding partitions in Kafka/Pulsar increases capacity across keys, yet it can cause the same key to hash to a new partition because partitioning depends on partition count. Older records remain on the old partition while newer records land on the new one.

```text
Before: topic has 4 partitions; order-42 -> P1
After:  topic has 8 partitions; order-42 -> P5 (possibly)

E10 is waiting in P1, E11 arrives at P5.
The two partitions can be processed independently.
```

As a result, completion order for a key can break during the transition. If the topic already holds backlog, never add partitions solely to scale consumers without a migration plan.

Options include: draining the backlog before changing partition counts, creating a versioned topic and cutting producers/consumers over cleanly, or protecting via storage-side version/gap handling. Each option has distinct downtime, backlog, and replay trade-offs. Similarly, changing the hash algorithm, key serializer, or routing lane count can alter key-to-worker mapping.

## 21. Multiple topics and multiple producers lack global order

Suppose `OrderCreated` comes from `orders.events`, while `PaymentConfirmed` comes from `payments.events`. Even if each topic is ordered by `orderId`, a consumer joining both topics has no guarantee the payment message arrives after the order message in wall-clock time.

```text
orders.events:       OrderCreated(order-42, v1)
payments.events:     PaymentConfirmed(order-42, v2)

Due to network delay or scheduling, v2 may reach the consumer before v1.
```

With Kafka Streams joins, understand record-time/stream-time, windows, grace periods, and state stores. Kafka Streams does not invent absolute business ordering across two independent topics. If strict ordering for an aggregate across sources is required, use reliable versions with buffering/waiting, or merge events through a single canonical keyed log.

If one service both updates its database and emits events in a business transaction, consider the **transactional outbox** pattern to avoid losing events. Still, CDC/outbox does not eliminate the need for proper keys and coordination across multiple producers or parallel publishing paths.

## 22. Safe horizontal scaling: step by step

A plan to scale from one replica to multiple replicas should follow this sequence:

1. Define the contract: global or per-key; write at least one concrete business ordering example.
2. Confirm keys are actually sent to the broker and related events share the same key.
3. Confirm topics/queues/subscriptions have enough parallel units to split load.
4. Keep consumer `group` (Kafka) or subscription name (Pulsar) stable when adding replicas.
5. Never vary Kafka Streams `applicationId` by pod/replica name.
6. Ensure handlers never ack before durable side effects finish.
7. Use event IDs, versions, and transactions/conditional updates to deduplicate and block stale events.
8. Decide whether retry/DLQ allows trailing events to advance or blocks the key.
9. Test rebalances, restarts, failovers, and replays before raising production load.
10. Increase concurrency/replicas gradually while monitoring throughput, lag, and out-of-order/version-gap counts.

Do not judge scaling success by throughput alone. A system can process messages faster while ending up with wrong projections. Acceptance criteria must include preserving invariants and recovering cleanly from failures.

## 23. What to monitor to detect broken ordering?

For ordering investigations, logs should include `eventId`, `aggregateId`, `aggregateVersion`, destination, partition/queue/subscription, consumer instance, and attempt count. Avoid logging sensitive payloads, tokens, or unnecessary private data.

| Signal | Purpose |
|---|---|
| `out_of_order_events_total` | Counts higher versions arriving before prior versions are processed |
| `stale_events_total` | Tracks old/duplicate events arriving after newer state |
| `duplicate_events_total` | Verifies idempotency and redeliveries |
| `ordering_gap_oldest_age` | Measures how long a key waits due to a missing version |
| Per-partition lag/backlog | Detects hot partitions or stuck keys |
| Processing latency by key/partition | Finds slow tasks holding back a key |
| Retry/DLQ count | Assesses failure impact on continuity |
| Rebalance/task reassignment | Correlates consumer changes with disruption windows |
| End-to-end event age | Evaluates projection freshness |

Avoid using a single topic-wide average to assess ordering. One hot partition can lag by minutes while all other partitions run near real-time. Dashboards should show latency percentiles, backlog histograms, and per-partition breakdowns; attaching `orderId` directly to every metric causes cardinality explosions, so keep specific IDs in controlled logs/traces.

## 24. Ordering test suite scenarios

Integration tests with a real broker or Testcontainers should cover at least these cases:

| Scenario | Execution | What to verify |
|---|---|---|
| Same key | Publish 100 sequential events for one `orderId` | Audit log for that key climbs 1..100 with zero inversions |
| Multiple keys | Interleave 100 keys | Parallelism occurs across keys while each key climbs sequentially |
| Higher concurrency | Scale from 1 to 3 consumer threads | Same-key version never regresses |
| Higher replicas | Scale from 1 to 3 instances in same group | Tasks/partitions rebalance while invariants hold |
| Hot key | One key carries 70% of traffic | Measure bottleneck and p95/p99 for that key |
| Mid-sequence retry | Force v11 transient failure, send v12 | Enforces documented stop/skip/gap policy |
| DLQ and replay | Send v11 to DLQ, v12 arrives later | Replay does not overwrite newer state; gap resolves cleanly |
| Crash before ack | Commit DB then kill consumer before ack | Redelivery is deduped with no duplicate side effects |
| Rebalance | Stop a replica owning partitions | New consumer resumes at valid version |
| Partition increase | Scale 4 to 8 partitions with active backlog | Detects or prevents out-of-order via migration/version checks |
| Concurrent producers | Two producers emit for the same key | Authoritative version dictates business order |
| RabbitMQ SAC | Two consumers on the same queue | Only one active; failover preserves rules |
| Pulsar `Key_Shared` | Enable key-based batching and multiple consumers | Same-key messages follow subscription semantics; side effects sequential |

`spring-cloud-stream-test-binder` is helpful for testing functions, yet it does not fully simulate Kafka partition assignment, RabbitMQ queues/SAC, or Pulsar `Key_Shared`. Proving ordering under scale requires integration tests against the actual binder/broker and multiple real instances or an equivalent environment.

## 25. Verify version history, not just final state

Simply checking `status = SHIPPED` after 100 messages is insufficient: an app could write v100, then v99, then overwrite with v100 and still pass. Record an **audit of durable applications**, capturing version and storage sequence, and verify:

```text
expected: 1, 2, 3, 4, ..., 100
actual:   1, 2, 4, 3, ..., 100   --> fail
```

For instance, an audit table with `audit_id` monotonically increasing in commit order inside the transaction and `aggregate_version`. A test query can be:

```sql
SELECT aggregate_id, aggregate_version
FROM order_projection_audit
WHERE aggregate_id = 'order-42'
ORDER BY audit_id;
```

The audit table must be written **in the same transaction** as the projection so it reflects events actually applied. Client-generated timestamps can lack clock accuracy and resolution; prefer storage-generated sequence/commit order and do not confuse it with event occurrence time.

If policy permits skipping stale events, the applied history may omit some versions, provided an audit explains why and business state remains valid. Do not require a strict `1..N` sequence when the contract allows coalescing or snapshots superseding intermediate events.

## 26. Architecture selection table by requirement

| Requirement | Suggested design | Additional controls needed |
|---|---|---|
| Strict global ordering | Single stream/partition or single active queue consumer | Low throughput, head-of-line blocking |
| Per-`orderId` ordering with Kafka | Record key `orderId`, multiple partitions, unified consumer group | No async side effects per key; retries and version checks |
| Stateful aggregation with Kafka Streams | Keyed `KStream`/state store, enough tasks/threads | Repartitioning, task restore, application ID, state migration |
| RabbitMQ queue needing ordered consumption | Single active consumer/SAC, sequential listener | Prefetch, requeue, queue arguments, and failover |
| Per-key RabbitMQ at high load | Hash routing key across multiple queues, SAC per queue | Hash choice, queue count, migration/replay |
| Pulsar with multiple consumers preserving per-key order | `Key_Shared`, stable keys, key-based batching or batching disabled | Subscription semantics, redelivery, app side effects |
| Fast processing of independent events only | Multiple consumers/`Shared`, competing consumption | Idempotency and duplicate handling |
| Multi-source producers / multiple topics | Authoritative version/sequence + state gate | Gap buffering, replay, and conflict resolution |

The best design is one that is **just strict enough** for the ordering requirement. If business rules only require idempotent at-least-once processing without order sensitivity, do not force the entire pipeline through a single worker.

## 27. Lab: accelerating an order system

Suppose an application starts with a six-partition Kafka topic `orders.events`, one replica, and `concurrency: 1`, averaging 60 ms/event. The system needs higher speed while ensuring events with the same `orderId` are applied in `aggregateVersion` order.

Design it as follows:

1. Producer sets `KafkaHeaders.KEY = orderId` and configures an idempotent producer.
2. Consumer keeps group `order-projection` and raises `concurrency` from 1 to 3 per replica.
3. Deploy two replicas in the same group, creating six consumer threads across six partitions.
4. Handler updates the projection synchronously in a transaction, checking `eventId` and `aggregateVersion`.
5. For transient errors, retry per key/partition per policy. For persistent errors, store the event in a recovery mechanism with explicit gap tracking.
6. Publish 100 events each across 1,000 interleaved `orderId`s, then verify the version audit of **every** order.
7. Kill one replica mid-processing; verify no lower version overwrites a higher version, and retries/redeliveries produce zero duplicate side effects.

Because there are six partitions, six total consumer threads represent only the **partition-bounded ceiling of parallelism**, not a guarantee of 6x throughput. If one `orderId` carries most messages, the partition holding that key remains slow. Never add partitions while backlog is unprocessed without a key-migration plan.

## 28. Common misconceptions to avoid

| Misconception | Reality |
|---|---|
| "Because the broker is ordered, the database stays ordered too" | Async handlers, retries, and external side effects can invert completion order |
| "Adding consumers makes a single key run faster" | Under strict ordering, one key must be serialized or guarded by a version gate |
| "Records have `orderId` in JSON, so Kafka partitions by it automatically" | You must explicitly set the record key or partitioning configuration |
| "Kafka with one producer always yields business order" | App threads, retries, transactions, and event creation timing still matter |
| "Pulsar `Shared` preserves per-key order" | `Shared` does not guarantee order; inspect `Key_Shared` and producer batching |
| "Multiple RabbitMQ consumers preserve completion order" | Queue dispatch order differs from completion order; use SAC/partitioned queues if needed |
| "DLQs do not affect ordering" | Skipping a failed event can create gaps and alter state |
| "Idempotency alone preserves ordering" | Deduplication does not stop an old version from overwriting a newer version without version checks |
| "Exactly-once automatically covers databases outside Kafka" | External side effects require their own transactional/idempotent strategy |
| "Adding partitions is always safe" | Changing key-to-partition mapping can introduce ordering gaps during backlogs |

## 29. Pre-production scaling checklist

- [ ] Documented definition of the ordering unit (global, per-key, per-partition/queue).
- [ ] All related events include stable keys, event IDs, and versions where needed.
- [ ] Producers actually set record keys/routing keys, not just fields inside the payload.
- [ ] Producer retries/idempotence and batching do not break ordering guarantees.
- [ ] Consumer group/subscription name/application ID stays stable when scaling replicas.
- [ ] Concurrency matches partitions/tasks/queues without spawning idle workers.
- [ ] Handlers do not return success before required side effects finish.
- [ ] Storage-side idempotency and version/gap handling are implemented.
- [ ] Retry/DLQ/replay defines clear policies for trailing events on the same key.
- [ ] Any repartitioning or partition-count increase has a migration plan.
- [ ] Integration tests cover multiple replicas, rebalances, failures, and redeliveries.
- [ ] Metrics track out-of-order events, lag, hot partitions, and gap duration.

## 30. Self-check questions

1. Does Kafka guarantee order per topic or per partition? What must be configured so two events with the same `orderId` land in the same partition?
2. Why does setting `concurrency: 8` on a four-partition topic not result in eight consumers independently processing eight partitions?
3. If a listener receives v10 then v11 and offloads to a thread pool, what can happen in the database?
4. What does RabbitMQ `singleActiveConsumer` solve, and what does it not solve?
5. Why does Pulsar `Key_Shared` require key-based batching or disabling standard batching?
6. When v11 goes to the DLQ while v12 proceeds, what mechanism does the application need to detect/recover the gap?
7. Why can idempotency not replace version checks when out-of-order events occur?
8. How can increasing Kafka partition count from four to eight change key-to-partition mapping?
9. Which test catches an intermediate state being corrupted even when the final state ends up right?
10. When should you accept per-key ordering instead of global ordering for higher throughput?

## Conclusion

Preserving order while scaling parallelism begins with choosing the **smallest unit of serialization your business requires**. With Kafka, use stable record keys to group an entity's events into one partition, then scale concurrency/replicas across partitions. With Kafka Streams, scale tasks/threads while protecting keys and repartition boundaries. With RabbitMQ, Single Active Consumer keeps one active consumer per queue; to scale by key, route across multiple queues. With Pulsar, pick an appropriate subscription such as `Key_Shared` and configure key-based batching. In every case, retries/DLQ, async processing, redeliveries, and partition changes can alter effective order; rely on idempotency, version gates, gap policies, and real integration tests to guarantee data correctness after scaling.

## References

- Spring Cloud Stream — Partitioning with Kafka Binder: https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/partitions.html
- Spring Cloud Stream — Kafka Binder Configuration: https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html
- Spring Cloud Stream — Kafka Streams Binder Configuration: https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/configuration-options.html
- Spring Cloud Stream — RabbitMQ Consumer Properties: https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview/rabbitmq-consumer-properties.html
- Spring Cloud Stream — Pulsar Binder: https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html
- Apache Kafka — Partition Ordering and Consumer Groups: https://kafka.apache.org/documentation/
- RabbitMQ — Consumers and Single Active Consumer: https://www.rabbitmq.com/docs/consumers
- RabbitMQ — Queue Ordering: https://www.rabbitmq.com/docs/queues
- Apache Pulsar — Messaging and Key_Shared: https://pulsar.apache.org/docs/5.0.x/concepts-messaging/
