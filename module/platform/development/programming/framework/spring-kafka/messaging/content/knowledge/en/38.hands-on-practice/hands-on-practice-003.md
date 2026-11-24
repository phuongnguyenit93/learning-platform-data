# Designing Topics and Keys for Orders

In an order processing system, multiple services need to receive events such as `OrderCreated`, `OrderPaid`, `OrderShipped`, and `OrderCancelled`. Topic and key design determines where events are stored, which consumers receive them, partition-based scalability, and ordering preservation for each order.

This hands-on lab asks you to design a Kafka topology for the order flow using Spring Kafka. You will select topics by data purpose, choose keys by the aggregate requiring ordering, determine partitions/replication/retention, configure the producer, and verify actual send metadata. The goal is to produce a design that can be explained and tested, rather than choosing partitions or keys by guesswork.

## 1. Context and Business Requirements

Assume the e-commerce system has the following components:

- `order-service` receives order placement requests and publishes order lifecycle events.
- `order-projection` reads events to update the read model for queries.
- `notification-service` reads events to send emails or notifications.
- `analytics-service` reads events to aggregate metrics.
- An operations screen needs to read the latest status of each order.

Core requirements:

1. Events for the same order must be processed in business order.
2. Multiple independent services must all receive the same event stream.
3. Services can scale their consumers independently without causing other services to lose records.
4. The latest status of an order can be read as a current record.
5. Failed records have an isolation area for investigation and replay.
6. The design must support scaling partitions while clearly stating the impact of changing the partition count.

Key distinction: Kafka guarantees ordering within a partition. To preserve ordering for an order's events, the producer must route them to the same partition, and the consumer must not reorder them during asynchronous processing.

## 2. Choosing Topics by Data Purpose

You should neither create a separate topic for every record type nor lump all unrelated data into a single topic. Group data by lifecycle, consumption pattern, retention, and operational policy.

Proposed design for the lab:

| Topic | Purpose | Cleanup policy | Key | Retention/notes |
|---|---|---|---|---|
| `orders.events` | Immutable event stream of the order lifecycle | `delete` | `orderId` | For example, 7 days retention; adjust based on replay and storage needs. |
| `orders.status` | Changelog of each order's latest status | `compact` | `orderId` | Kafka retains the latest value per key after compaction; suitable for state snapshots. |
| `orders.dlt` | Unprocessable records after retry/recovery | `delete` | Preserves original key, usually `orderId` | For example, 30 days retention for investigation; requires replay procedures and access control. |

`orders.events` is an event stream. Every business change is appended as a new record; old events are never updated or overwritten. `orders.status` is a compacted changelog: for the same key, older values may be cleaned up after broker compaction runs. This is not a mechanism for keeping full change history.

`orders.dlt` is an operational isolation zone. If `DeadLetterPublishingRecoverer` preserves the source partition when publishing to the DLT, the DLT topic needs at least as many matching partitions. Do not mix failed records back into `orders.events` as if they were new business events.

Only add `orders.commands` if the system has an asynchronous command flow with separate write permissions, consumers, and retry lifecycle. A command expresses a request to perform an action; an event expresses something that has already happened. Do not create a command topic if the application only publishes domain events.

## 3. Choosing the Key: Why Use `orderId`?

The key determines the partition when the producer does not specify a partition directly. With the default partitioner, the same key is typically mapped to the same partition as long as the topic partition count and partitioner do not change.

In this lab, choose `orderId` as the key for `orders.events`:

| Candidate key | Suitable when | Limitations |
|---|---|---|
| `orderId` | Events within the same order need ordering | Orders distribute by hash; a very hot order still concentrates on a single partition. |
| `customerId` | All changes for a customer must be processed in a shared order | A customer with many orders concentrates on the same partition, potentially creating a hot key. |
| `eventId` | Each event needs independent routing | Events for the same order may land in different partitions, losing per-order ordering. |
| `null` | There is no identifier to partition by aggregate | No guarantee that events for the same order go to the same partition. |

For the order lifecycle, `orderId` is the natural choice because `Created`, `Paid`, `Shipped`, and `Cancelled` events all describe one aggregate. Do not use `eventId` as the key just because each record has a unique ID; doing so breaks the partition affinity between events of the same order.

The producer sends a stable key:

```java
kafkaTemplate.send("orders.events", event.orderId(), event);
```

When publishing the current status to `orders.status`, also use `orderId` as the key so every update for the same order replaces the right logical entry in the compacted topic:

```java
kafkaTemplate.send("orders.status", status.orderId(), status);
```

Do not manually compute `hash(orderId) % partitionCount` in the business service. Let the Kafka producer partitioner handle mapping and verify the actual partition via `RecordMetadata`. Manual calculation easily diverges from the partitioner algorithm, null-key handling, or topic metadata.

## 4. Determining Partition Count and Replication Factor

Partition count determines the maximum parallelism of a consumer group. If `orders.events` has 6 partitions, a group has at most 6 active consumers assigned partitions at the same time. Increasing replicas beyond the partition count does not automatically increase group throughput.

In this lab, choose 6 partitions as a starting point to practice consumer scaling. This is an illustrative number, not a production default. In a real design, you need to estimate:

- Input throughput and the throughput a single consumer can process.
- Expected consumer/concurrency count per service.
- Maximum replica count and autoscaling plan.
- Number of topics/partitions the brokers must manage.
- Hot key ratio and order distribution.
- Ordering requirements and the ability to change partition count later.

Replication factor is the number of partition replicas in the cluster. For a production environment with at least three brokers, you can start evaluating a replication factor of 3 and configure `min.insync.replicas` to pair with `acks=all`. For an embedded broker or local development with only one broker, you must use replication factor 1; you cannot create an RF=3 topic on a single broker.

| Environment | Suggested partitions for lab | Replication factor | Purpose |
|---|---:|---:|---|
| Local/Embedded Kafka single broker | 6 | 1 | Testing routing, keys, and consumer assignment. |
| Production cluster of three or more brokers | Based on throughput and scale plan | Typically evaluate RF=3 | Broker fault tolerance and higher data durability. |

Before increasing the partition count of a topic that already has data, evaluate key mapping. The same `orderId` may map to a different partition after the partition count changes; older records remain on the old partition. If continuous per-aggregate ordering is a hard requirement, you need a migration plan or sequence/version numbers to detect late events.

## 5. Choosing Retention and Cleanup Policy

`orders.events` needs to retain event history long enough for consumer recovery, replay, or projection rebuilding. For example, the lab uses 7 days:

```text
cleanup.policy=delete
retention.ms=604800000
```

This value equals 7 days. Production should be based on maximum acceptable outage duration, replay window, traffic volume, broker disk capacity, and audit requirements. If long-term history is needed, consider archiving to object storage or a dedicated storage system rather than increasing broker retention indefinitely.

`orders.status` uses `cleanup.policy=compact`. Compaction keeps the latest value per key after the log cleaner runs; it happens asynchronously, so older values do not disappear immediately when the producer sends a new update. Sending a tombstone (null value) for a key marks that key for removal from the compacted view according to tombstone retention rules.

`orders.dlt` usually uses `delete` with retention long enough for investigation. The DLT must have an owner, dashboard, alerts, and a replay procedure. Do not let the DLT become an unbounded dumping ground without storage limits or access controls.

## 6. Creating Topics for the Lab

With a single-broker local Kafka, create the three topics with replication factor 1:

```bash
bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --create \
  --topic orders.events \
  --partitions 6 \
  --replication-factor 1 \
  --config cleanup.policy=delete \
  --config retention.ms=604800000

bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --create \
  --topic orders.status \
  --partitions 6 \
  --replication-factor 1 \
  --config cleanup.policy=compact

bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --create \
  --topic orders.dlt \
  --partitions 6 \
  --replication-factor 1 \
  --config cleanup.policy=delete \
  --config retention.ms=2592000000
```

In a three-broker production cluster, evaluate replication factor 3 and an appropriate `min.insync.replicas`. Do not copy the local RF=1 command into production configuration when durability requires replication.

Verify the topology after creation:

```bash
bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --topic orders.events

bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --topic orders.status
```

Verify the partition count, leader, replicas, and topic configs. If a topic already exists with different settings, `--create` may report that the topic exists; describe it and adjust via an explicit governance process rather than deleting a topic that holds data.

## 7. Defining a Stable Event Envelope

An event should carry enough metadata for consumers to identify the event type, identity, aggregate, and version. For example:

```java
public record OrderEvent(
        String eventId,
        String orderId,
        long aggregateVersion,
        String eventType,
        Instant occurredAt,
        Map<String, Object> data) {
}
```

Example payload:

```json
{
  "eventId": "evt-1001",
  "orderId": "order-42",
  "aggregateVersion": 1,
  "eventType": "OrderCreated",
  "occurredAt": "2026-11-17T05:00:00Z",
  "data": {
    "currency": "VND",
    "totalAmount": 1250000
  }
}
```

`eventId` identifies a single event emission and is useful for idempotency. `orderId` is the Kafka key and aggregate identity. `aggregateVersion` helps consumers detect duplicate or out-of-order events. `eventType` conveys business meaning; `occurredAt` aids tracing and does not replace offset for determining append order within a partition.

When schemas change, a clear compatibility strategy is required. Do not change the meaning of an existing field or reuse an event type for an incompatible payload. In larger systems, consider a schema registry and controlled schema formats rather than relying solely on `Map<String, Object>`.

## 8. Configuring the Spring Kafka Producer

Example Spring Boot configuration using `StringSerializer` for the key and `JsonSerializer` for the event value:

```yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      acks: all
      properties:
        "[enable.idempotence]": true
```

The producer service sends events using `orderId` as the key:

```java
@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderEvent> kafkaTemplate;

    public OrderEventPublisher(KafkaTemplate<String, OrderEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderEvent>> publish(
            OrderEvent event) {

        return kafkaTemplate.send(
                "orders.events",
                event.orderId(),
                event);
    }
}
```

The example uses the `CompletableFuture` API of modern Spring Kafka versions. If your project uses an older version, the future type may be `ListenableFuture`; use the API matching your project's dependencies. In the send-success callback, record `topic`, `partition`, `offset`, `eventId`, and `orderId` to verify routing.

`acks=all` requires broker acknowledgment according to the current ISR. Combining it with an idempotent producer increases record delivery reliability; it does not replace consumer-side idempotency for business side effects.

## 9. Designing Consumer Groups for Services

Each independent service that needs the full event stream should use its own consumer group:

| Service | `group.id` | Role |
|---|---|---|
| `order-projection` | `order-projection` | Updates the read model and status. |
| `notification-service` | `notification-service` | Sends notifications to customers. |
| `analytics-service` | `analytics-service` | Aggregates metrics. |

Replicas of the same service share a group ID to split partitions. Do not use the same group ID for the three services above if each service must receive every event; Kafka distributes records among consumers in the same group rather than broadcasting to each service.

Example projection listener:

```java
@KafkaListener(topics = "orders.events", groupId = "order-projection")
public void project(OrderEvent event) {
    projectionService.apply(event);
}
```

A consumer of `orders.status` can use a separate group to build a cache or restore current state. The consumer needs to understand that a compacted topic can contain multiple versions per key before compaction runs; if building state, apply records in offset order and handle tombstones.

## 10. Verifying Partitions and Ordering

Send at least three events for the same order and one event for another order. In tests, wait for each send to be acknowledged by the broker so you can compare metadata and avoid finishing the test before the producer completes:

```java
publisher.publish(new OrderEvent(
        "evt-1", "order-42", 1, "OrderCreated", Instant.now(), Map.of()))
        .get(10, TimeUnit.SECONDS);
publisher.publish(new OrderEvent(
        "evt-2", "order-42", 2, "OrderPaid", Instant.now(), Map.of()))
        .get(10, TimeUnit.SECONDS);
publisher.publish(new OrderEvent(
        "evt-3", "order-42", 3, "OrderShipped", Instant.now(), Map.of()))
        .get(10, TimeUnit.SECONDS);
publisher.publish(new OrderEvent(
        "evt-4", "order-99", 1, "OrderCreated", Instant.now(), Map.of()))
        .get(10, TimeUnit.SECONDS);
```

After the broker acknowledges the sends, check the metadata:

- The three events for `order-42` must have the same partition if the topic partition count and partitioner have not changed.
- The offsets of those three events must increase in the send order confirmed by the producer.
- `order-99` may go to the same or a different partition; do not assert that two orders must go to different partitions.
- The projection, notification, and analytics consumer groups must independently receive the same event stream.

You can verify using the console consumer command or an integration test with `EmbeddedKafka`:

```bash
bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic orders.events \
  --from-beginning \
  --property print.key=true \
  --property print.partition=true \
  --property print.offset=true
```

Do not claim global ordering across partitions 0, 1, and 2. Kafka only guarantees ordering within each partition. If a listener offloads work to a thread pool, completion order may differ from delivery order; in that case, check sequence/version and keyed processing.

## 11. Analyzing a Partition Count Change Scenario

Suppose `orders.events` initially has 6 partitions and the producer uses `orderId` as the key. Over time, the operations team increases it to 12 partitions to increase parallelism. Existing records remain in their original partitions, but keys may map to different partitions under the new partition count.

This can spread a single order's history across multiple partitions. A consumer group has no automatic way to globally sort those records by aggregate. If continuous ordering is required, consider:

- Choosing a partition count large enough for planned growth from the start.
- Using `aggregateVersion` and only applying events with valid versions.
- Creating a new versioned topic and migrating data through a controlled process.
- Using a stable application-managed partitioning strategy, while evaluating scalability and hot partitions.

Do not increase partition count simply because consumer lag rises. First determine whether lag comes from too few consumers, slow processing, key skew, downstream saturation, or fetch configuration.

## 12. Hands-On Exercises

Follow these steps in order in a local or embedded Kafka environment:

1. Create `orders.events` with 6 partitions, `delete` cleanup, and 7-day retention.
2. Create `orders.status` with 6 partitions and `compact` cleanup.
3. Create `orders.dlt` with 6 partitions and retention sufficient for investigation.
4. Define `OrderEvent` with `eventId`, `orderId`, `aggregateVersion`, `eventType`, `occurredAt`, and `data`.
5. Write a publisher using `orderId` as the key for `orders.events`.
6. Send three consecutive events for `order-42` and at least one event for `order-99`.
7. Record send metadata: topic, partition, and offset.
8. Create two independent consumer groups and verify both receive the events.
9. Create a listener that updates `orders.status` keyed by `orderId`.
10. Try sending events with `eventId` as the key and explain why per-order ordering is no longer guaranteed.
11. Simulate changing the partition count in a separate test environment and analyze key remapping behavior.
12. Write sizing notes: target throughput, consumer count, concurrency, partition count, replication, and retention.

### Deliverables

- A table describing the three topics, purpose, partitions, replication factor, cleanup policy, and retention.
- An explanation of why `orderId` is the key for the event stream and status topic.
- Spring Kafka publisher code sending to the right topic/key.
- Metadata results for at least three events of the same order.
- Verification results for two independent consumer groups.
- Risk analysis of increasing partition count and a strategy to preserve ordering.

## 13. Acceptance Criteria

| Criterion | Passing condition |
|---|---|
| Topic design | Clearly distinguishes event stream, compacted state, and DLT by purpose. |
| Key design | Events of the same order use the same `orderId` as key. |
| Partitions | Partition count is justified by throughput/concurrency, not chosen arbitrarily. |
| Replication | Local RF=1 and production RF chosen according to broker count and durability requirements. |
| Retention | Event and DLT topics have appropriate retention; status topic uses compaction. |
| Producer | Sends to the right topic/key and captures broker-returned metadata. |
| Consumer group | Independent services use separate group IDs; replicas of the same service share a group ID. |
| Ordering | Guarantees ordering only within a partition and identifies risks of increasing partition count. |
| Operations | Includes a plan to monitor lag, hot partitions, DLT, and replay. |

## 14. Self-Assessment Questions

1. Why is `eventId` not an appropriate key when lifecycle ordering of an order must be preserved?
2. If `order-42` and `order-99` hash to the same partition, is that a design flaw? Why or why not?
3. Why must three services that each need to process the same events use three different consumer groups?
4. How does a compacted topic differ from an event stream with `delete` retention?
5. Why can increasing the partition count send new events of the same order to a different partition than older events?
6. If records have the right partition and offset but database state is updated out of order, which layer should be investigated?

Good topic and key design starts from the aggregate and how the data is consumed. For the order flow, `orders.events` uses `orderId` as the key to preserve per-partition ordering, `orders.status` uses the same key for the latest state, and `orders.dlt` isolates records needing investigation. When partition count, retention, replication, and consumer groups are chosen against explicit requirements, a Spring Kafka system can scale while preserving traceability and correctness of the order flow.
