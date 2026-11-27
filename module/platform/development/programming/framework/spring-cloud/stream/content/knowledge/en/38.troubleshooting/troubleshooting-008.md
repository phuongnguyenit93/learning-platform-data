# Duplicate Messages, Out-of-Order Processing, or Hot Partition Skew

## Objectives

In an event-driven system built with **Spring Cloud Stream**, the same event may be received multiple times, a newer update may be processed before an older one, or most of the load may pile onto a single Kafka partition while other consumers sit nearly idle. These three symptoms commonly relate to **delivery semantics, partition keys, concurrency, and ACK/commit timing**, yet they do not share the same root cause or fix.

An application with a `Supplier` emitting events, a `Function` transforming data, and a `Consumer` updating a database can run into all three failures. Kafka, RabbitMQ, and Pulsar all support delivery and retries, but their notions of partitions, consumer groups, queues, and subscriptions carry different guarantees. During diagnosis, you must find the exact boundary where duplication, reordering, or skew occurs; you cannot fix every case by raising `concurrency`, changing `group`, or deleting the backlog.

This lesson belongs to the **Troubleshooting** chapter of the **SPRING_CLOUD_STREAM** module. It walks through verifying symptoms, picking stable keys, preserving idempotent processing, evaluating per-key ordering, spotting hot partitions, and testing retries/redeliveries before changing deployment settings.

After this lesson, you will be able to:

- Distinguish duplicate records, redeliveries, and duplicate business side effects.
- Read producer, broker, consumer, and ACK/offset timelines to pinpoint where duplicates arise.
- Explain ordering boundaries in Kafka by partition, RabbitMQ by queue, and Pulsar by subscription type.
- Use event IDs, aggregate IDs, and sequence/versions to detect and control duplicate or stale events.
- Apply the inbox/idempotent consumer pattern inside a database transaction.
- Inspect key/partition assignments and spot hot keys or hot partitions from metrics.
- Tune `concurrency`, prefetch, consumer groups, and partitioning without breaking ordering requirements.
- Distinguish Kafka Streams repartitioning, state stores, and late event-time arrivals.
- Run broker integration tests for redelivery, out-of-order events, and partition skew.
- Build a runbook and choose safe load-mitigation and rollback actions.

## 1. Three Symptoms Easily Confused

| Symptom | Observation | Always a Broker Bug? | First Question |
|---|---|---|---|
| **Duplicate messages** | Same event ID appears in handler twice | No | Did producer send twice or broker redeliver? |
| **Out-of-order** | Version 12 processed before version 11 | No | Ordering within the same partition or handler completion order? |
| **Hot partition skew** | Partition 3 has high traffic/lag while others are low | No | Is key distribution skewed or is one key too hot? |

Example order event stream:

~~~text
Producer (business order):
  O-21 / version=1 / CREATED
  O-21 / version=2 / PAID
  O-21 / version=3 / SHIPPED

Consumer observes:
  O-21 / version=1 / CREATED
  O-21 / version=2 / PAID
  O-21 / version=2 / PAID      <-- duplicate
  O-21 / version=3 / SHIPPED
~~~

Another variant:

~~~text
Consumer log records completion timestamps:
  O-21 / version=3 / SHIPPED
  O-21 / version=2 / PAID     <-- processing completion out of order
~~~

This does not prove the broker stored records out of order. Version 2 may have arrived first but processed slowly, while version 3 finished first because the application ran tasks asynchronously.

Partition skew, by contrast, is a load-distribution issue—for example, most order events share `customerId="VIP"`, so they constantly route to a single partition.

**Do not start by resetting offsets or increasing partition counts.** First record event identity, key, partition, offset, timestamps, and processing outcomes.

## 2. Observability Model: Event Identity, Delivery, and Side Effects

An event must be distinguished from a delivery attempt.

- **Event identity:** `eventId` generated at the business source, stable across retries/replays.
- **Aggregate identity:** `orderId` or `accountId` grouping events that require ordering.
- **Sequence/version:** monotonically increasing number per aggregate showing which update is newer.
- **Delivery metadata:** Kafka topic, partition, offset; or the corresponding broker's message ID and delivery/redelivery metadata.
- **Processing attempt:** number of times the handler actually executed.
- **Side effect:** database update, API call, or outbound emission.

Structured log entry example:

~~~json
{
  "eventId": "evt-702",
  "aggregateId": "order-21",
  "aggregateVersion": 12,
  "binding": "processOrders-in-0",
  "group": "order-projection",
  "broker": "kafka",
  "topic": "orders.events",
  "partition": 3,
  "offset": 481920,
  "attempt": 2,
  "outcome": "ALREADY_PROCESSED"
}
~~~

`eventId`, `aggregateId`, and `aggregateVersion` are application-defined fields or headers; Kafka does not provide business identity automatically. Exact names for `partition`, `offset`, and delivery headers depend on the binder/version. In Spring Kafka, `KafkaHeaders.RECEIVED_TOPIC`, `KafkaHeaders.RECEIVED_PARTITION`, and `KafkaHeaders.OFFSET` commonly expose receive metadata; verify header mapping in your release.

### Why Looking Only at Identical Payloads Is Insufficient

Two orders with identical payloads can be two distinct valid events. Conversely, the same `eventId` with different bodies indicates a contract bug or inconsistent emitter. Do not deduplicate by hashing the entire payload when an event ID is guaranteed by the producer.

| Evidence | Possible Explanation |
|---|---|
| Same event ID, same topic/partition/offset | Likely redelivery or handler re-invoked for the same broker record |
| Same event ID, different offset | Producer published two records, or a replay/forward created a new record |
| Different event ID, same aggregate/version | Producer recreated a business event with a new ID; check aggregate-version contract |
| Offsets advance sequentially but DB logs invert order | Concurrency, async processing, or side-effect completion timing |
| One partition's lag spikes abnormally | Hot partition or slow consumer on that partition |

An offset locates a record within **a single Kafka partition**. It is not a topic-wide or system-wide global sequence number.

## 3. Duplicate Messages: Why Can the Broker Redeliver?

Spring Cloud Stream does not default to guaranteeing that every business event invokes the handler strictly once. **At-least-once** delivery naturally allows duplicates whenever a failure occurs between processing and acknowledgment.

Common timeline:

~~~mermaid
sequenceDiagram
    participant K as Kafka / broker
    participant C as Consumer
    participant D as Database
    K->>C: Deliver event evt-702
    C->>D: UPDATE succeeds
    D-->>C: Commit OK
    Note over C,K: Process crashes before ACK/offset commit
    K->>C: Redeliver evt-702
    C->>D: UPDATE runs again if not idempotent
~~~

Common causes:

1. Handler completes side effects, then the process crashes before ACK/commit.
2. ACK or offset commit fails or times out.
3. Consumer rebalances or drops connection, causing the partition/queue to be reassigned.
4. Handler throws an exception, triggering binder/container retries or broker redelivery.
5. Producer retries when unsure whether the broker received the message.
6. Outbox publisher re-emits an event after failing to mark it published.
7. DLT replay, offset reset, or spinning up a new consumer group/`applicationId`.
8. An event crosses multiple functions/bindings and is published twice due to misrouting.
9. Autoscaling, rolling deployments, or health restarts widen uncommitted in-flight windows.

You cannot determine the cause merely because a handler logged twice. Compare `eventId`, Kafka topic/partition/offset or broker message ID, and business persistence timestamps.

### Duplicate Delivery Differs from Duplicate Side Effects

Duplicate delivery does not have to multiply business writes. An idempotent consumer can receive the event again, return `ALREADY_PROCESSED`, and leave the database untouched. The goal is not to hide every duplicate from logs, but to **make repeated processing safe**.

## 4. Idempotent Processing via an Inbox in the Same DB Transaction

A common pattern stores `(consumer_name, event_id)` in an inbox table with a unique constraint. The consumer executes side effects only if the event ID has not yet been processed for that logical consumer.

PostgreSQL example:

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(120) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

In a Spring service:

~~~java
@Service
public class OrderProjectionService {
    private final JdbcTemplate jdbc;

    public OrderProjectionService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void apply(OrderPaid event) {
        int inserted = jdbc.update("""
            INSERT INTO processed_events (consumer_name, event_id)
            VALUES (?, ?)
            ON CONFLICT DO NOTHING
            """,
            "order-projection",
            event.eventId()
        );

        if (inserted == 0) {
            return; // Already committed this event previously
        }

        int updated = jdbc.update("""
            UPDATE order_projection
               SET paid_amount_minor = paid_amount_minor + ?
             WHERE order_id = ?
            """,
            event.amountMinor(),
            event.orderId()
        );
        if (updated != 1) {
            throw new IllegalStateException(
                    "Expected one order projection for " + event.orderId()
            );
        }
    }
}
~~~

Function binding:

~~~java
@Bean
Consumer<OrderPaid> projectPaidOrders(OrderProjectionService service) {
    return service::apply;
}
~~~

**Core requirement:** inserting into the inbox and updating business tables must execute inside the **same database transaction**. The example checks the updated row count so an event is not marked processed when the target projection does not exist yet. If the update fails or that check throws, the transaction rolls back the inbox row too, allowing redelivery to retry. If the DB commit succeeds while the broker ACK fails, the next delivery hits the unique constraint and skips the side effect.

The example uses PostgreSQL's `ON CONFLICT DO NOTHING`, which is not universal SQL across every database. On other engines, use an equivalent insert-if-absent and unique-constraint mechanism.

### Limitations to Know

- An event ID must be stable and never reused for a different event.
- `consumer_name` must identify the logical subscriber; independent projections must not share the same idempotency key if each needs to process the event.
- External side effects outside the database (email/HTTP/payments) do **not** automatically become atomic with the inbox transaction; use outbox, target-side idempotency keys, or sagas/compensation.
- Inbox retention must exceed the maximum window in which events can be replayed; otherwise pruned records can be reprocessed.
- If one event triggers multiple side effects, design idempotency per operation's semantics.
- When updating balances, inventory, or monetary totals, duplicate side effects can cause severe corruption; always test DB commit → process crash → redelivery.

## 5. Producer Duplicates: Not Every Duplicate Comes from the Consumer

If **the same event ID appears at different Kafka offsets**, the cause likely lies in the producer or an upstream forwarding step.

Scenarios:

- Producer misses an ACK timeout and re-sends at the application level.
- An outbox job polls the same record twice due to missing locking/leasing or failing to mark it published.
- An HTTP request is retried where event creation lacks an idempotency key.
- Two services both publish an event for the same business transition.
- Restarting a `Supplier` replays old data because its cursor/state is not durable.
- A consumer reads the DLT and republishes to the source topic, creating a new record with the same ID.

### Kafka Producer Idempotence and Its Limits

Kafka supports an idempotent producer (e.g., `enable.idempotence=true` with compatible settings). It lets the broker deduplicate retries of **the same record within a producer client session** using sequence numbers. It does **not** deduplicate two separate application publish calls, two different producers, or database side effects.

Kafka transactions and `read_committed` help provide read-process-write guarantees across Kafka topics within transaction scope; they do not create distributed atomic transactions across Kafka and external databases/HTTP APIs. For external side effects, rely on inbox/outbox and idempotency.

### Distinguishing via Record Identity

For Kafka:

| Same Event ID | Topic/Partition/Offset | Likelihood |
|---|---|---|
| Identical | Same triple | One broker record delivered multiple times |
| Identical | Different offset | Producer or topology wrote multiple records |
| Identical | Different topic | Forward/retry/DLT/replay; inspect routing |
| Similar body, different ID | Any | Business event generated twice; inspect emitter |

For RabbitMQ and Pulsar, inspect message IDs and delivery metadata supported by the binder; never assume broker-native IDs stay unchanged when a message is republished to a retry/DLT topic or queue.

## 6. Out-of-Order Has Multiple Meanings

Separate four kinds of ordering:

1. **Business event order:** the sequence in which real-world changes happened, e.g., version 1 → 2 → 3.
2. **Publish/append order:** the order records are accepted by the broker inside a partition or queue.
3. **Delivery order:** the order in which a consumer receives records.
4. **Side-effect completion order:** the order in which DB transactions or HTTP requests actually finish.

Example where two records arrive in order 11 then 12, but the handler runs asynchronously:

~~~text
10:00:00.000  receive version=11
10:00:00.001  receive version=12
10:00:00.030  complete version=12
10:00:00.150  complete version=11
~~~

This is a **completion-order** bug, not necessarily a Kafka ordering bug. If a business projection uses last-write-wins based on commit timestamp, the older update overwrites the newer one.

Also distinguish:

- **Out-of-order event:** business versions go backward.
- **Late event:** an event with an older event-time arrives later; may be valid in stream processing.
- **Duplicate event:** the same event identity is processed again.
- **Gap:** a sequence/version is missing from the stream.

A single system can experience all four simultaneously.

## 7. Kafka Guarantees Order Only Within a Partition

Kafka stores records in strictly increasing offset order **within a single partition**. A consumer reads that partition in offset order, but Kafka provides no total ordering across partitions.

~~~text
orders.events partition 0:  offset 80, 81, 82, 83
orders.events partition 1:  offset 41, 42, 43
orders.events partition 2:  offset 77, 78
~~~

It is meaningless to claim that offset 83 on partition 0 "happened after" offset 78 on partition 2.

### Conditions for Per-Aggregate Ordering to Hold

To preserve order for events sharing the same `orderId` over Kafka:

1. Producers use the same canonical key for every event of that order.
2. Events with the same key are routed by the partitioner to the same partition under a stable strategy.
3. Producers emit events for the same aggregate in coordinated order; do not rely on wall-clock time across multiple producers.
4. Consumers process sequentially or enforce version checks when using async work.
5. No replay/forward path breaks the key/ordering rule.
6. Changes to partition count, partitioner, key serializer, or hashing strategy are evaluated before rollout.

**Sharing a key does not create business order if multiple producers race on the same aggregate without source sequencing.** The broker only knows the order it received records, not which domain transition happened first.

### How Can Producer Retries Cause Reordering?

With certain non-idempotent settings and multiple in-flight requests, if batch A fails and is retried after batch B succeeds, append order can diverge from send-call order. An idempotent producer with compatible settings preserves ordering on retries within the producer protocol, though it still cannot substitute for source-side sequencing.

When investigating, record producer config (`enable.idempotence`, `acks`, `retries`, `max.in.flight.requests.per.connection`), producer IDs if visible, keys, partitions, and offsets. Never try to fix ordering by increasing concurrency.

## 8. Out-of-Order Due to Async Processing and Consumer Concurrency

In Spring Cloud Stream, `consumer.concurrency` spins up multiple consumer threads. With the regular Kafka binder, a single partition in a consumer group is normally assigned to one consumer member at a time, yet the application itself can introduce async execution.

Dangerous example:

~~~java
@Bean
Consumer<OrderEvent> processOrders(Executor executor, OrderService service) {
    return event -> executor.execute(() -> service.apply(event));
}
~~~

The function returns as soon as the task is queued, without waiting for `service.apply` to finish. From the binder's viewpoint, the handler has completed and can commit/ACK the message before business work finishes. Tasks can also finish out of order.

A safer pattern when per-partition or per-key sequentiality is required is synchronous handling inside the consumer:

~~~java
@Bean
Consumer<OrderEvent> processOrders(OrderService service) {
    return service::apply;
}
~~~

If higher concurrency is needed:

- Preserve **serialized execution per aggregate key** via worker partitioning/striped executors and acknowledge only after completion.
- Use version/sequence checks before updating state.
- Avoid unbounded queues; maintain backpressure.
- If offloading work from the consumer, persist work to a **durable queue** before ACKing.
- Test crashes between task submission and completion.
- Do not expect raising `concurrency` to make a single Kafka partition process in parallel while preserving strict ordering.

### An Older Update Overwrites a Newer One

Suppose a consumer receives version 8 then version 9, but version 9 commits first. If SQL runs `UPDATE ... SET status=?` without a version check, version 8 overwrites version 9. For "latest state wins" projections, add a version guard.

## 9. Guard State with an Aggregate Version

Include an `aggregateVersion` or `sequence` generated by the business source:

~~~java
public record OrderEvent(
        String eventId,
        String orderId,
        long aggregateVersion,
        String status,
        Instant occurredAt
) {}
~~~

PostgreSQL example that applies an update only if the event is newer than stored state:

~~~sql
UPDATE order_projection
   SET status = :status,
       aggregate_version = :incoming_version
 WHERE order_id = :order_id
   AND aggregate_version < :incoming_version;
~~~

Semantics:

- Currently at version 9 → events with version 8 or 9 do not overwrite.
- Currently at version 7 → event with version 9 can be applied.
- Versions must be generated monotonically by the source with a clear contract.

**Note:** `current_version < incoming_version` fits "latest state wins" projections where each event carries **full state** or intermediate versions can be skipped. It is **unsafe** for delta events like "subtract 10," "add 5," or strict step-by-step state transitions. For deltas/transitions, you must:

- Enforce `incoming_version == current_version + 1`.
- Hold early arrivals in a bounded buffer/store or route to durable retry.
- Detect missing events and provide reconciliation.
- Handle expired gaps according to business policy rather than buffering forever in heap.
- Use locks, optimistic concurrency, or conditional updates inside a database transaction.

Never use the consumer JVM's clock as the primary sequence. Clock skew and variable transit delays mean `occurredAt` does not guarantee causal order. An aggregate-owner version is far stronger than timestamps for causal ordering.

## 10. Event Time, Late Arrivals, and Kafka Streams

In Kafka Streams, records carry timestamps used for windowing. An event created at 09:59 may arrive after a 10:01 record due to network delays or retries. That is a **late arrival**, not necessarily Kafka breaking offset order.

Example time-windowed aggregation:

~~~java
KTable<Windowed<String>, Long> counts = events
    .groupByKey(Grouped.with(Serdes.String(), orderEventSerde))
    .windowedBy(TimeWindows.ofSizeAndGrace(
            Duration.ofMinutes(5),
            Duration.ofMinutes(2)))
    .count();
~~~

This creates 5-minute windows with a 2-minute grace period for late records under stream-time semantics. Events arriving after the window closes may be dropped depending on topology/operators. Window grace handles late event-time arrivals; it does **not** automatically fix duplicate business events or aggregate causal ordering.

When using Kafka Streams:

- Define timestamp extractors and time units/timezones explicitly.
- Inspect stream-time, grace, and retention when records arrive late.
- Check key/value Serdes across repartitions and materializations.
- Avoid `groupBy` on hot keys that bottleneck a single task/state store.
- Check changelog/state restoration and processing guarantees for stateful topologies.
- Use event IDs/versions or a dedup state store if business rules forbid double counting.

## 11. What Is Kafka Partition Skew?

**Partition skew** happens when workload is unevenly distributed across partitions or tasks. One partition may have:

- A higher inbound record rate than other partitions.
- More bytes despite similar record counts.
- Most of the expensive messages.
- One aggregate/key generating the bulk of traffic.
- Steadily rising lag while other partitions stay near 0.

Example:

| Partition | Input msg/s | Consumer msg/s | Lag Growing? |
|---|---:|---:|---|
| 0 | 120 | 130 | No |
| 1 | 110 | 125 | No |
| 2 | 900 | 250 | Yes |
| 3 | 130 | 140 | No |

Partition 2 receives 900 msg/s but processes 250 msg/s, so lag grows by roughly 650 msg/s. Adding replicas does not add concurrent consumers for **the same partition** within the same group.

### A Hot Partition Is Not Always a Hot Key

- **Hot key:** one key like `customerId=VIP` accounts for most records and hashes to one partition.
- **Low-cardinality key skew:** only a few distinct values like `country=VN/US` or `status=NEW/PAID` across many partitions.
- **Null/constant key skew:** producer emits the same key for every message or uses fixed routing.
- **Heavy-record skew:** few messages, but each takes longer to process or carries huge payloads.
- **Consumer-side skew:** one partition hits failing messages or slow DB queries, raising lag despite balanced input.
- **Assignment skew:** one consumer holds several heavy partitions; partition assignment or task placement is unbalanced.

Distinguish **input rate per partition**, **processing rate per partition**, and **lag per partition**. Lag alone is never enough to blame the partitioner.

## 12. Inspecting Hot Partitions with Kafka CLI and Metrics

Inspect the consumer group and per-partition lag:

~~~bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server kafka-1:9092 \
  --group order-projection \
  --describe
~~~

Illustrative output:

~~~text
TOPIC          PARTITION  CURRENT-OFFSET  LOG-END-OFFSET  LAG
orders.events  0          50000           50010           10
orders.events  1          52000           52008           8
orders.events  2          19000           90000           71000
orders.events  3          49000           49005           5
~~~

Here partition 2 has a far larger backlog. You still need per-partition incoming record/byte rates and processing latency to separate key skew from a slow consumer.

Inspect topic partition count and metadata:

~~~bash
bin/kafka-topics.sh \
  --bootstrap-server kafka-1:9092 \
  --describe --topic orders.events
~~~

Check further:

1. How many active consumer members are in the group?
2. Which consumer/pod owns partition 2?
3. What are the most frequent event keys in partition 2?
4. Does a single key dominate traffic?
5. Are p95/p99 message sizes or processing durations abnormal?
6. Are retries or poison events looping in partition 2?
7. After a rebalance, does the lag follow the partition or the pod?
8. Does the broker/controller have I/O or network issues specific to that partition's leader?

Never put sensitive keys into metric labels. When identifying hot keys, use cardinality-bounded top-K sampling or approved hashes to keep PII out of monitoring.

## 13. Choose Partition Keys by the Unit Requiring Ordering

A good partition key reflects **the business unit requiring ordered processing** while having enough cardinality to avoid hot partitions.

Examples:

| Use Case | Suggested Key | Why |
|---|---|---|
| Per-order state | `orderId` | Events for the same order share a partition |
| Account balance | `accountId` | Sequential per account when required |
| Inventory per SKU and warehouse | `warehouseId:sku` | State per stock record |
| Session clickstream | `sessionId` | Preserves ordering within a session |
| Customer-wide state | `customerId` | Orders per customer, but risks hot customers |
| Country-wide stats | `country` | **Unsuitable for load distribution** if only a few keys exist |

Using `eventId` as the partition key gives great distribution, but events for the same order scatter across partitions, losing per-order ordering. Using `customerId` risks concentrating many orders from one high-volume customer onto a single partition.

Key selection is a **trade-off** between ordering and load distribution. No single key satisfies every goal simultaneously; identify the exact scope where ordering is truly needed.

### Canonical Key Representation

String keys emitted by producers in different languages must use identical normalization and serialization:

- Unicode normalization and casing.
- Whitespace, prefixes, and tenant codes.
- UUID or numeric formatting.
- Charset and byte serialization.
- Partitioner/hash strategy and partition count.

The same business value with different key bytes can hash to a different partition. Changing serializers or partitioners during a rolling deployment can break key affinity even though values look identical to the eye.

## 14. Configuring Partition Keys in Spring Cloud Stream

For producer bindings using Spring Cloud Stream partitioning, declare a partition key expression:

~~~yaml
spring:
  cloud:
    function:
      definition: publishOrders
    stream:
      bindings:
        publishOrders-out-0:
          destination: orders.events
          producer:
            partition-key-expression: payload.orderId
            partition-count: 12
~~~

This applies when the payload at expression-evaluation time exposes `orderId`. With Java records, expression/property access and mappers depend on how the function/binder represents the payload; write an integration test to confirm the key resolved before conversion matches expectations.

Points to distinguish:

- `partition-key-expression` determines the key used by **Spring Cloud Stream's partitioning mechanism** per effective configuration.
- `partition-count` specifies the partition count used for partitioning/provisioning algorithms; keep it aligned with the actual partition count on the broker.
- Declaring a partition key expression or key extractor enables producer-side partitioning in the framework; do not assume a shared boolean `partitioned` property exists across all producer binders/versions.
- Native Kafka producers also have `ProducerRecord.key`, key serializers, and partitioners. Do not assume a binding property and native Kafka partitioner share the exact same API across every binder version.
- For RabbitMQ/Pulsar, key/routing/subscription semantics differ from Kafka; never copy Kafka YAML blindly as Rabbit or Pulsar ordering rules.

### When Using StreamBridge

`StreamBridge` sends to the specified output binding and can leverage that binding's key expression/partitioning config. When sending a Spring `Message<?>`, you can attach the Kafka key header per the Kafka binder contract; check header names and serializers in your Spring Kafka version. Never generate partition keys from random UUIDs when business logic requires ordering by `orderId`.

Verify the real producer with an independent client: emit a sequence of events with the same `orderId`, read the topic, and confirm they land in the same partition in ascending offset order under stable configuration.

## 15. Does Increasing Partition Count Fix a Hot Partition?

Not necessarily.

- If one key generates 80% of traffic, scaling from 8 to 32 partitions can still send 80% of records to **a single partition**.
- If many keys are evenly distributed yet there are too few partitions to feed enough consumers, adding partitions improves parallelism.
- If the bottleneck is a database or slow handler, adding partitions will not raise real throughput.
- If lag is caused by repeated poison messages, adding partitions will not fix data errors.

**Ordering warning when increasing partition count:** hash-modulo partitioning can route the same key to a different partition once the partition count changes. Old records for that key stay on the old partition while new records go to the new partition. During transition, both partitions are read independently, so **per-key ordering across the change boundary can break**.

When strict ordering is needed:

1. Evaluate whether partition count is part of the wire/routing contract.
2. If expanding partitions, design a coordinated drain/cutover or a new versioned topic.
3. Re-partition data in a controlled manner when required.
4. Use aggregate versions to guard against old/new records arriving out of order.
5. Test concurrent old/new producers and stateful consumers.
6. Prepare rollback/reconciliation; you cannot simply shrink partition counts back down because Kafka does not support reducing partitions as a normal operation.

## 16. Targeted Mitigations Matched to Root Cause

| Root Cause | Appropriate Mitigation | Risks / Conditions |
|---|---|---|
| One key is too hot | Split aggregate if domain allows; salt/shard key then re-aggregate | Loses whole-key ordering; requires re-aggregation |
| Low-cardinality key | Choose a more granular key | Must preserve business ordering contract |
| Too few partitions, keys balanced | Increase partitions with a migration plan | Key → partition mapping changes |
| Consumer on that partition is slow | Profile handler/DB/external dependencies | Not a partitioner bug |
| One consumer holds multiple heavy partitions | Scale or rebalance task assignment | Total capacity must still suffice |
| Poison events / retry storm | Fix handler, bounded retries, DLT | Guard against duplicate side effects |
| Oversized events | Cap payloads, optimize serializer | Schema / backward compatibility |
| Kafka Streams stateful hotspot | Change aggregation key or two-stage aggregation if associative | State-store/changelog migration |
| CPU/heap limits | Tune batching, GC, memory, I/O | Must not break ACK/ordering |

### Key Salting Fits Only Associative Operations

For counting or summing, two-stage aggregation works:

~~~text
Hot key = region-VN
  -> region-VN:shard-0 -> partial count
  -> region-VN:shard-1 -> partial count
  -> region-VN:shard-2 -> partial count
  -> combine partial results -> region-VN total
~~~

Splitting keys increases parallelism but **breaks strict ordering** across events of the original key. Do not salt keys for account balance updates or strictly sequential state transitions unless explicit concurrency control exists.

For a single aggregate that genuinely must be processed sequentially, the bottleneck may be an inherent business constraint. The solution is reducing per-event processing cost, minimizing synchronous work, or redesigning the domain model—not simply adding consumers.

## 17. Consumer Groups and Concurrency Cannot Exceed Partition Limits

The regular Kafka binder lets you configure consumer concurrency:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrders
    stream:
      bindings:
        processOrders-in-0:
          destination: orders.events
          group: order-projection
          consumer:
            concurrency: 4
~~~

Example with a 6-partition topic:

| Deployment | Consumer Members in Group | Max Consumers Actively Receiving Partitions |
|---|---:|---:|
| 1 replica × concurrency 2 | 2 | 2 |
| 2 replicas × concurrency 3 | 6 | 6 |
| 3 replicas × concurrency 4 | 12 | 6 |

Within the same group, each Kafka partition is assigned to one consumer at a time; consumers beyond the partition count remain idle. Multiple input topics or assignment policies can cause exact partition counts to differ from this simple math.

Scaling replicas from 2 to 4 when all partitions already have consumers will not add parallelism to **one hot partition**. Before scaling:

- Check the partition count.
- Measure load per partition and per pod.
- Check downstream connection pools.
- Check how many consumers actually hold partition assignments.
- Monitor rebalance duration and processing lag.
- Confirm ACK/commit semantics stay intact as concurrency rises.

Never change `group` just to make lag drop; a new group has its own offsets and may replay or skip history depending on configuration.

## 18. Kafka Streams: Repartitioning and Task Skew

In the Kafka Streams binder, keys and partitioning play a central role for `KStream`, `KTable`, aggregations, and joins.

Example re-keying by `orderId`:

~~~java
@Bean
Function<KStream<String, OrderEvent>, KStream<String, OrderEvent>>
normalizeOrderKey() {
    return input -> input.selectKey(
            (oldKey, event) -> event.orderId()
    );
}
~~~

`selectKey` changes the record's logical key in the topology. Kafka Streams marks the stream for repartitioning when downstream key-dependent operators require it; calling `selectKey` alone does not always materialize a repartition topic immediately. When grouping, joining, or aggregating, examine `Grouped.with(...)`, key/value Serdes, partition counts, and task assignments.

A hot key can force one task and its local state store to bear most of the work. When diagnosing, inspect:

- Record rate/latency per task or thread.
- Changelog/repartition topic sizes.
- State store size and restore duration.
- Aggregation/join key distribution.
- RocksDB/cache/GC and disk I/O.
- Rebalances and task migrations.
- `applicationId` and state schemas before changing topology.

Changing keys, store names, Serdes, or repartitioning strategies may require rebuilding state. Never run application resets or delete changelogs in production to "rebalance load" without a replay, migration, and downstream idempotency plan.

## 19. RabbitMQ: Duplicates and Ordering Have Different Semantics

RabbitMQ does not distribute records by Kafka partitions; messages route through exchanges/bindings to queues, and queues deliver to consumers.

Duplicate causes include:

- Consumer ACK did not reach the broker before connection closed.
- Consumer threw an error and nacked/requeued.
- Publisher retried because it was unsure the broker received the publish.
- Message was republished to retry/DLQ and replayed.
- Handler side effect succeeded before delivery was ACKed.

RabbitMQ can provide FIFO-like delivery from a queue under specific conditions, but **processing completion order is not guaranteed with multiple consumers**, prefetch, priorities, or redeliveries/requeues.

Example of one queue with two consumers:

~~~text
Queue head: M1, M2, M3
Consumer A receives M1 -> processes 500ms
Consumer B receives M2 -> processes 20ms, ACK
Consumer B receives M3 -> processes 30ms, ACK
Consumer A ACKs M1
Completion order: M2, M3, M1
~~~

If strict queue-wide ordering is required, consider a single active consumer, low prefetch, and synchronous processing; this limits throughput. RabbitMQ offers single-active-consumer at the broker and queue sharding by routing key if ordering is only needed per business key. Verify queue types, features, and binder/broker versions before deploying.

### Configuring Prefetch and Concurrency

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrders-in-0:
          destination: orders.exchange
          group: order-projection
          consumer:
            concurrency: 2
      rabbit:
        bindings:
          processOrders-in-0:
            consumer:
              prefetch: 5
              requeueRejected: false
~~~

This illustrates bounded in-flight delivery. `prefetch` caps unacknowledged deliveries under RabbitMQ/Spring AMQP semantics; `concurrency` adds consumer threads. `requeueRejected: false` does not create a DLT automatically: properly configured DLX/DLQ on the broker/binder is still required. Where ordering matters, multiple consumers can cause completion order to diverge from delivery order.

Never set `requeueRejected=true` for poison messages without backoff or caps; a redelivery storm can make a queue appear "stuck" while looping the same message endlessly.

## 20. Pulsar: Shared, Key_Shared, and Redelivery

Pulsar uses subscriptions to define how messages distribute across consumers:

| Subscription Type | General Behavior | Ordering Impact |
|---|---|---|
| Exclusive | One active consumer on the subscription | Easier to reason about ordering, though async/retries still apply |
| Failover | One active consumer, standby backups | Redeliveries on failover and lifecycle boundaries |
| Shared | Messages distributed across consumers | No per-key completion ordering guarantee |
| Key_Shared | Messages with the same key coordinated to the same consumer | Useful for per-key processing; still test retry/batching/concurrency |

With Pulsar `Key_Shared`, messages with the same key are typically delivered to the assigned consumer per key-distribution policy; per-key ordering depends on configuration, batching, and runtime conditions. If producer batching mixes different keys into one batch, `Key_Shared` distribution may behave unexpectedly; consider key-based batching or disabling batching per your client version docs.

Negative acknowledgments/redeliveries and retry/DLT flows can also affect observed ordering. Pulsar documentation notes that redelivery upon nack can produce out-of-order deliveries under some subscription semantics. Never conclude "`Key_Shared` means side effects always finish in order" if handlers spawn async tasks or retry.

If messages repeat:

1. Check message ID, key, and redelivery count.
2. Check ACK timeout, negative ack delay, retry topic, and DLT policy.
3. Check subscription type and receiver queue.
4. Check consumer restarts, broker unloads, or rebalances.
5. Re-test via integration tests on the exact Pulsar broker/client/binder version.

Do not copy Kafka `enableDlq` or Kafka `partitionKeyExpression` config assuming it works identically on the Pulsar binder.

## 21. Distinguish Broker Redeliveries from Framework Retries

Spring Cloud Stream provides function-handler-level retry/error handling in many binders. Example:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrders-in-0:
          consumer:
            max-attempts: 3
            back-off-initial-interval: 1000
            back-off-max-interval: 10000
~~~

In supported imperative framework retry paths, `max-attempts: 3` usually includes the initial attempt. That is not the same as three broker redeliveries. One record can invoke the handler multiple times before the broker ever receives an ACK/nack. In addition, native deserialization, Kafka Streams, and reactive functions have distinct error-handling models.

When diagnosing, track separately:

- Broker delivery/redelivery attempts.
- Handler invocations per event ID.
- DB/API calls per event ID.
- Published output records.
- DLT records.
- Final commit/ACK outcome.

Enforce a bounded total retry budget. Retries stacked across framework, HTTP clients, broker, and DLT replay can amplify load onto a hot partition.

## 22. Error Handling Does Not Automatically Guarantee Order or Dedup

When an event fails:

- Synchronous in-place retry can block the partition/queue, preserving order at the cost of growing lag.
- Skip/continue preserves throughput at the cost of business gaps.
- Routing to DLT isolates poison messages from the main flow, yet replaying later may arrive **late or causally out of order**.
- Pushing failed events to a retry topic unblocks the main consumer, yet newer events can overtake older failing events.

Example:

~~~text
Main topic:
  order-21/version=10   -> failed -> retry topic
  order-21/version=11   -> processed successfully
Retry topic later:
  order-21/version=10   -> processed after 11
~~~

If the handler enforces a contract-compliant version guard, event 10 may be flagged as stale. But if version 10 is a mandatory delta, gap detection/replay is required instead of skipping it.

Define a clear **policy balancing correctness and liveness**:

| Policy | Pros | Cons |
|---|---|---|
| Block/retry in place | Easy to preserve per-partition order | One poison event stalls the entire partition |
| DLT then continue | Partition keeps moving | Aggregate may miss a version |
| Async retry topic | Avoids blocking workers | Can invert business order |
| Version guard / latest-wins | Prevents stale overwrites | Unsuitable for mandatory deltas/gaps |
| Ordered inbox/buffer per key | Protects causal order | Adds state, timeouts, and operational complexity |

There is no single universal answer: snapshot events and delta events carry different requirements.

## 23. Metrics and Facts to Collect

Good diagnostics require visibility across three layers.

### Broker

- Kafka: per-partition input bytes/records, log end offsets, group committed offsets, lag, assignments, rebalances.
- RabbitMQ: ready/unacked counts, consumer counts, prefetch, redeliveries, rejects, DLX/DLQ.
- Pulsar: backlog, unacked counts, redeliveries, subscription type, consumer assignments, retry/DLT.
- Broker/network: connection errors, throttling, disk I/O, and leader elections.

### Application

- Invocation counts by event ID or bounded-cardinality sampling.
- `ALREADY_PROCESSED` rate per logical consumer.
- Handler processing duration and DB/HTTP p95/p99 latency.
- Active workers, executor queue depth, rejected tasks.
- Offset/ACK failures, retries/backoff, DLT ingress.
- Processing time vs `occurredAt` and `aggregateVersion`.
- State-store restore/repartition metrics for Kafka Streams.

### Contract

- Producer key bytes/format, null-key ratio, distinct key count.
- Top-K key frequency under data-protection rules.
- Event ID uniqueness and aggregate version gaps.
- Topic/queue/subscription routing.
- Producer and consumer versions when errors started.
- Recent partition expansions or serializer changes.

Never use raw `eventId` or `orderId` as Prometheus metric labels due to unbounded cardinality. Log IDs with sampling/redaction, and keep metric labels bounded to binding/topic/partition/error-class.

## 24. Runbook A — Duplicate Messages

Follow in order:

1. Determine whether `eventId` and business side effects actually duplicated or only handler logs repeated.
2. Compare broker record identities: Kafka topic/partition/offset, Rabbit delivery metadata, or Pulsar message ID.
3. If the same record was redelivered, look for restarts, rebalances, ACK timeouts, exceptions, or commit failures.
4. If they are distinct records, investigate app-level producer retries, outbox, dual-publishing, or DLT replays.
5. Measure framework handler attempts separately from broker redelivery attempts.
6. Inspect inbox/unique constraints and DB transaction boundaries.
7. Check whether ACKs occur before side effects finish.
8. If duplicate side effects already happened, perform business reconciliation/compensation.
9. After fixing, test crashing right after DB commit and before ACK.
10. Track duplicate delivery rate and duplicate side-effect rate as separate metrics.

**Never delete consumer group offsets or DLTs to "clear duplicates."** That can trigger even more replays and destroy investigative evidence.

## 25. Runbook B — Out-of-Order Events

1. Determine whether the events share the same aggregate key.
2. Check event `aggregateVersion`/sequence and `occurredAt`, not merely log timestamps.
3. For Kafka, inspect topic/partition/offset of the events.
4. If same partition and sequential offsets, investigate async processing, thread pools, retries, and DB commit order.
5. If different partitions, inspect producer keys, partitioner, serializers, and partition-count changes.
6. If multiple producers emit for the same aggregate, identify the sequencing owner.
7. If events arrived late via retry/DLT, apply business policy for late/gapped events.
8. Choose latest-wins snapshots or ordered delta processing per semantics.
9. Test processing version `N+1` before `N` in an integration test.
10. Verify outputs/state do not regress when older records replay.

**Never treat Kafka offsets as event versions.** Offsets are scoped to a single partition; business versions must be managed at the aggregate level.

## 26. Runbook C — Hot Partition Skew

1. Verify per-partition lag and input rates via CLI/metrics.
2. Identify hot keys, null keys, constant keys, or low-cardinality keys.
3. Check partition assignments and the consumer/pod handling the hot partition.
4. Compare processing latency on the hot partition vs other partitions.
5. Check whether retry loops or poison messages are stalling that partition.
6. Check DB bottlenecks, CPU, heap, producer throttling, and state stores.
7. If keys are evenly distributed but partition count is low, plan a controlled partition expansion.
8. If one key is genuinely hot, optimize per-key work or shard/re-aggregate only if the domain allows.
9. If changing partitioners/keys/partition counts, execute an order-preserving migration.
10. Monitor lag, throughput, duplicates, and ordering violations after rollout.

**Do not raise consumer concurrency indefinitely:** one partition still has at most one active consumer member in a standard group. Extra threads waste CPU and connections without speeding up a hot partition.

## 27. Integration Tests Reproducing All Three Failures

Test Binder is helpful for testing function logic and validation, but it does not faithfully reproduce broker offsets, partition assignments, ACK/redelivery, or nack/requeue. These failures require broker integration tests using Testcontainers or a real Kafka/RabbitMQ/Pulsar environment matching production.

### Test Duplicates and Idempotency

~~~text
Given:
  eventId = evt-702
  DB projection does not yet contain this eventId

When:
  publish event
  consumer commits DB but is killed before ACK
  broker redelivers the same event

Then:
  handler may run again
  business side effect commits only once
  inbox has exactly one row (consumer_name, event_id)
  consumer advances after successful handling
~~~

Test producer duplicates separately: publish **two broker records** with the same event ID at different offsets/message IDs and verify the DB still updates only once.

### Test Out-of-Order and Gaps

~~~text
Given:
  Order order-21 already processed version 9

When:
  version 11 arrives before version 10

Then (snapshot latest-wins):
  version 11 may become current state
  version 10 arriving later does not overwrite

Then (ordered delta):
  version 11 is held/retried in a durable buffer
  version 10 applies first
  version 11 applies afterward
  gap timeout triggers alert/reconciliation
~~~

Add tests for: same key across multiple producers; async tasks with varying latencies; DLT replay; restarts between events; and partition count increases.

### Test Hot Partitions

~~~text
Scenario A: 95% of messages share the same key
  Expected: one partition/task absorbs most load
  Assertion: adding consumers does not split a single key across partitions

Scenario B: 10,000 evenly distributed keys
  Expected: roughly balanced across key hashes with minor variance
  Assertion: scaling concurrency helps up to the partition count limit

Scenario C: evenly distributed keys, but partition 2 hits DB timeouts
  Expected: partition 2 lag grows despite balanced producer distribution
  Assertion: root cause is consumer/dependency, not the key
~~~

During benchmarks, record per-partition throughput/bytes/lag, CPU, heap, GC, DB pool usage, retries, and p99 processing latency. Use an event fixture whose key distribution mirrors production.

## 28. Configurations and Quick Fixes Never to Apply Blindly

| Hasty Fix | Why It Is Dangerous | Alternative |
|---|---|---|
| Change `group` to fix duplicates | New group gets separate offsets and can replay even more | Keep group; fix ACK/idempotency |
| Use random keys to spread load | Breaks per-aggregate ordering | Pick domain keys; shard only where allowed |
| Increase partition count immediately | Keys can move partitions, breaking per-key order during cutover | Controlled migration/rollout |
| Raise concurrency on a hot partition | Still only one active consumer per partition in the same group | Find hot keys and optimize tasks |
| Enable infinite retries | Poison events and slow dependencies cause storms | Backoff, budgets, DLQ, and reconciliation |
| Use `logAndContinue` for all errors | Silently drops critical records | Classify errors and define gap policy |
| Return normally after catching all exceptions | Can ACK despite failed side effects | Route errors to the proper error handler |
| Submit async task then ACK immediately | In-heap tasks are lost on process crash | Await completion or durable handoff |
| Count events by topic-wide Kafka offsets | Offsets lack total order across partitions | Use aggregate sequence/version |
| Delete DLT to clear errors | Destroys data needed for diagnosis/replay | Manage DLTs and fix root causes |
| Raise prefetch when seeing lag | Moves backlog into heap without increasing service rate | Find the real bottleneck |
| Treat Kafka exactly-once as DB exactly-once | Kafka transactions do not cover DB side effects | Inbox/outbox and idempotent operations |

## 29. Production Deployment Checklist

### Event Contract

- [ ] `eventId` is stable across retries and replays.
- [ ] `aggregateId` identifies the unit requiring ordering.
- [ ] `aggregateVersion` or sequence is present when business rules require causal order.
- [ ] Key serializer/partitioner and partition count are managed as a contract.
- [ ] Snapshot, delta, or transition semantics are clearly defined.
- [ ] Duplicate/gap/late-event policies are established.

### Delivery and Error Handling

- [ ] ACK/commit occurs only after required work has durably completed.
- [ ] Tested crash after DB commit and before ACK.
- [ ] Unique constraint/inbox or equivalent idempotency mechanism is in place.
- [ ] Retry budget, backoff, DLT, and replay procedure are defined.
- [ ] Exceptions are never swallowed in ways that cause false ACKs.
- [ ] Non-DB side effects are protected when retried.

### Ordering and Load Distribution

- [ ] Verified per-partition input rates, bytes, lag, and assignments.
- [ ] Measured hot-key ratio and null-key ratio.
- [ ] Concurrency is bounded by partition/subscription counts and downstream capacity.
- [ ] Async processing does not break ACKs or ordering.
- [ ] Changes to partition count, key, or serializer follow a migration plan.
- [ ] For Kafka Streams, checked repartitioning, Serdes, and state stores.
- [ ] For RabbitMQ/Pulsar, verified queue/subscription ordering and redelivery behavior.

### Testing and Operations

- [ ] Broker integration tests cover duplicates, out-of-order events, and hot partitions.
- [ ] Tested DLT replays and broker/consumer restarts.
- [ ] Separate metrics track duplicate deliveries, duplicate side effects, ordering violations, and hot partition lag.
- [ ] Dashboards never use high-cardinality event IDs as labels.
- [ ] Runbook defines owners, rollback triggers, and reconciliation procedures.

## Conclusion

**Duplicate messages** are primarily a delivery/retry and ACK/commit-boundary problem; **out-of-order processing** is a causal-version, key/partition, async-processing, and replay problem; **hot partitions** are a key-distribution, processing-cost, and parallelism-limit problem. All three symptoms can appear together, yet each must be diagnosed with evidence at the right layer.

In Kafka, ordering is guaranteed by **offset within each partition**, not across the whole topic or across all business events. In RabbitMQ, multiple consumers, prefetch, and requeues can make completion order diverge from delivery order. In Pulsar, subscription types (especially `Shared`/`Key_Shared`), batching, and redeliveries govern distribution and ordering. In Kafka Streams, `groupBy`, repartitioning, and state stores introduce additional factors to inspect.

Do not hunt for a magic setting guaranteeing "no duplicates, no reordering, perfectly balanced partitions." Design stable event IDs and aggregate versions, build idempotent consumers via transactions/inbox tables, pick partition keys matching your ordering scope, defer ACKs until completion, separate hot keys from slow consumers, and test replays, redeliveries, and cutovers against real brokers. That is the foundation for reliable Spring Cloud Stream event processing under scale, retries, and multi-instance deployments.

## References

- [Spring Cloud Stream — Consumer Groups](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/consumer-groups.html) and [Partitioning](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-partitioning.html): groups, concurrency, producer partitioning, and binder constraints.
- [Spring Cloud Stream — Kafka Binder Configuration](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html): Kafka consumer/producer configuration and error/DLT options.
- [Apache Kafka — Consumer Groups](https://kafka.apache.org/documentation/#consumerconfigs) and [Producer Configs](https://kafka.apache.org/documentation/#producerconfigs): partition assignment, polling, idempotence, and ordering in Kafka clients.
- [Apache Kafka — Semantics](https://kafka.apache.org/documentation/#semantics): at-least-once, at-most-once, idempotent producers, and transaction scopes.
- [Spring Cloud Stream — Kafka Streams Binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/configuration-options.html): Kafka Streams topologies, Serdes, and runtime properties.
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms), [Consumer Prefetch](https://www.rabbitmq.com/docs/consumer-prefetch), and [Queues](https://www.rabbitmq.com/docs/queues): redelivery, prefetch, requeue, and ordering limitations.
- [Apache Pulsar — Messaging Concepts](https://pulsar.apache.org/docs/concepts-messaging/) and [Key_Shared Subscriptions](https://pulsar.apache.org/docs/concepts-messaging/#key_shared): subscription semantics and per-key ordering.

These examples are illustrative and may require adjustments for your specific Spring Cloud Stream, Kafka/RabbitMQ/Pulsar binder, broker, and client versions. In production, consult the reference guide for your exact release, inspect real data, and write integration tests covering the guarantees your domain requires.
