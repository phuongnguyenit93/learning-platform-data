# When a single partition is needed

Kafka guarantees record order within the scope of a single partition. If every record in a topic is written to one exact partition, that topic has a single append sequence for consumers to read in offset order. This is the simplest way to obtain a shared order for all records in a topic, though it also imposes a clear limit on parallel writes and consumption.

In the `SPRING_KAFKA_MESSAGING` module, producers send events with `KafkaTemplate` and consumers receive events with `@KafkaListener`. Deciding to use a single partition must be based on actual ordering requirements, data volume, consumer processing capacity, and scaling plans. Many use cases only need per-entity ordering such as by `orderId`; in those cases, using a key to route to the same partition is usually better than forcing the entire topic into one partition.

## 1. What does a single partition mean?

A Kafka topic can have one or more partitions. Each partition is an independent log with offsets increasing in the order records are appended to that log.

With a single-partition topic:

```text
Topic: system-events

Partition 0
  offset 0 -> ServiceStarted
  offset 1 -> ConfigurationLoaded
  offset 2 -> UserSignedIn
  offset 3 -> ServiceStopped
```

The consumer reads partition `0` in offset order. Because there is no second partition, every record in the topic resides in one log stream. This is the basis for an application to observe a shared append order across the topic's events.

That order is the order in which the broker appends records to the partition, not automatically business chronological order. If two producers emit events concurrently, the broker establishes append order as it receives the records. Kafka cannot infer which event occurred earlier in an external system. If business logic requires causal ordering, the application must still coordinate producers or carry a sequence/version in events to validate business order.

A single partition only creates ordering within that topic. It does not establish a shared order across multiple topics, nor does it guarantee global order across independent systems.

## 2. When is a single partition needed?

Choose a single partition when the application truly needs every record in the topic to pass through one append sequence and traffic is low enough for a single partition to handle.

Some suitable use cases include:

- **Low-volume control streams:** commands or configuration changes that must be read in the exact same append order.
- **Simple audit logs:** a controlled write source emits small state milestones and consumers need to read a single event stream.
- **Sequential workflows:** a small workflow that must be processed step by step in sequence within the same topic.
- **Exercises, demos, or development environments:** observing offsets and ordering without needing parallel partitioning yet.
- **Legacy integrations:** an older system requires a single sequential stream and throughput has been measured to stay within a single partition's limits.

For example, a service managing a single device may emit state events like `DeviceRegistered`, `DeviceActivated`, `DeviceDisabled`. If the entire state stream has low volume and requires consumers to read in one shared append order, a single partition can be a simple design.

However, if the topic holds events for thousands of independent devices or orders, packing every event into one partition usually hurts scalability. In that case, identify which entity requires ordering and choose the corresponding key.

## 3. Distinguishing topic-wide order from per-key order

These are two distinct requirements:

| Requirement | Typically suitable design | Ordering scope |
|---|---|---|
| Every record in the topic must share one append order | Single-partition topic | All records in the topic |
| Events of the same order must be ordered | Use `orderId` as key on a multi-partition topic | Events with the same key, when routing stays stable |
| Events per account must be ordered, while different accounts run in parallel | Use `accountId` as key | Within each partition holding that account |
| Parallel processing of independent events | Multiple partitions and evenly distributed keys | No topic-wide ordering |

For example, topic `orders` has eight partitions. The producer uses `orderId` as the key; all events of the same order are routed to the same partition by the default partitioner as long as key serialization, partitioner, and partition count stay unchanged. Different orders can sit in different partitions and be processed in parallel.

```text
Topic orders (8 partitions)

order-1001: OrderCreated -> PaymentAccepted -> OrderShipped  -> partition 2
order-1002: OrderCreated -> PaymentRejected                  -> partition 5
order-1003: OrderCreated -> PaymentAccepted -> OrderShipped  -> partition 7
```

Consumers still read in offset order within each partition. Thus, `order-1001` events have their own order in partition `2`, and `order-1002` events have their own order in partition `5`. Kafka provides no ordering guarantee between events of two orders in different partitions.

If only per-aggregate ordering is needed, do not sacrifice parallelism for the entire topic by creating just one partition. Use the aggregate ID as the key and design consumers per partition.

## 4. Trade-offs of having only one partition

One partition keeps ordering simple, yet routes all write traffic to a single leader and caps active parallel consumers per group.

| Aspect | Single-partition topic | Multi-partition topic |
|---|---|---|
| Ordering | Single append order across the topic | Local order within each partition only |
| Parallel writes | One partition leader handles appends | Multiple leaders can handle different partitions |
| Parallel consumers in one group | At most one consumer assigned the partition | Multiple active consumers, up to assigned partition count |
| Throughput | Bounded by one partition/leader's capacity | Can scale by spreading load across partitions and brokers |
| Load distribution | All records funnel into one partition | Can distribute by key/partitioner |
| Operations | Easy to visualize and trace order | Requires observing multiple partitions and handling per-key ordering |

A single partition can become a bottleneck when producers send many records or consumers process heavy payloads. Increasing listener `concurrency` does not create more partitions and does not enable multiple consumers in the same group to read the same partition in parallel.

## 5. Replication does not replace partitioning

Partition count and replication factor address two different goals:

- **Partitioning** splits data into independent logs to increase load distribution and parallel processing.
- **Replication** creates copies of partitions across brokers to improve fault tolerance and availability.

A topic with one partition and a replication factor of three still has only one partition leader accepting writes. Two follower replicas copy that partition's data; they do not become two parallel write partitions.

Example on a three-broker cluster:

```text
Topic system-events, partition count = 1, replication factor = 3

Broker 1: partition 0 (leader)
Broker 2: partition 0 (replica)
Broker 3: partition 0 (replica)
```

A replication factor of 3 requires enough brokers in the cluster to place replicas. In production, also examine producer `acks`, `min.insync.replicas`, and ISR health to pick the right durability level. Raising the replication factor can improve fault tolerance, but does not increase write parallelism for a single partition.

## 6. Creating a single-partition topic with Spring Kafka

You can declare a topic using `KafkaAdmin` and `TopicBuilder`:

```java
import org.apache.kafka.clients.admin.NewTopic;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.TopicBuilder;

@Configuration
public class KafkaTopicConfiguration {

    @Bean
    public NewTopic systemEventsTopic() {
        return TopicBuilder.name("system-events")
                .partitions(1)
                .replicas(3)
                .build();
    }
}
```

The example uses replication factor 3, so the cluster needs at least three eligible brokers. For local single-broker Kafka, change it to `.replicas(1)`. `KafkaAdmin` uses `NewTopic` declarations to request topic creation at application startup; the topic must be provisioned with suitable settings before producers/consumers use it.

If the topic already exists with multiple partitions, changing `.partitions(1)` in the `NewTopic` bean does not make Kafka reduce the partition count. Kafka does not support reducing the partition count of an existing topic. To move from multiple partitions to one partition, create a new topic, define a data migration strategy, and switch producers/consumers in a controlled manner.

After creation, verify the actual partition count using the Admin API or Kafka admin tools. Do not rely solely on values in source code to conclude broker settings are right.

## 7. Sending records to the single partition

For a topic with only partition `0`, the default partitioner selects that partition whether a key is present or not, barring custom partitioners or unusual configuration. The application can also specify partition `0` explicitly.

Example using `KafkaTemplate`:

```java
import java.time.Instant;
import java.util.concurrent.CompletableFuture;

import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Service;

public record SystemEvent(
        String eventId,
        String eventType,
        Instant occurredAt
) {}

public interface SystemEventHandler {
    void handle(SystemEvent event);
}

@Service
public class SystemEventPublisher {

    private final KafkaTemplate<String, SystemEvent> kafkaTemplate;

    public SystemEventPublisher(
            KafkaTemplate<String, SystemEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, SystemEvent>> publish(
            SystemEvent event) {
        return kafkaTemplate.send(
                "system-events",
                0,
                event.eventId(),
                event
        );
    }
}
```

Here the producer specifies partition `0` while still retaining `eventId` as the key. The key can be useful for correlation or if the topic later uses compaction, though in a single-partition topic it does not distribute records to other partitions.

If explicit specification is unnecessary, use `kafkaTemplate.send("system-events", event.eventId(), event)`. When the topic truly has one partition, the partitioner selects partition `0`.

Sending is asynchronous. In real applications, inspect `CompletableFuture<SendResult<K, V>>` to know whether sending succeeded or failed, and inspect `RecordMetadata.partition()`/`offset()` when tracing is needed. Never ignore send failures just because the topic has one partition.

## 8. Reading a single-partition topic with `@KafkaListener`

One listener in a consumer group can read the topic's sole partition:

```java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class SystemEventListener {

    private final SystemEventHandler handler;

    public SystemEventListener(SystemEventHandler handler) {
        this.handler = handler;
    }

    @KafkaListener(
            id = "systemEventsListener",
            topics = "system-events",
            groupId = "system-events-reader",
            concurrency = "1"
    )
    public void listen(ConsumerRecord<String, SystemEvent> record) {
        System.out.printf(
                "partition=%d offset=%d key=%s type=%s%n",
                record.partition(),
                record.offset(),
                record.key(),
                record.value().eventType()
        );

        handler.handle(record.value());
    }
}
```

With one partition and one consumer group, at most one consumer member is assigned that partition at a time. Setting `concurrency = "1"` states the design clearly. Raising concurrency above one leaves the remaining child consumers with no partitions to read in this group.

Another consumer group can still read the same partition independently. For example, group `system-events-audit` and group `system-events-dashboard` both receive all records from the topic at their own pace. This does not increase parallelism inside one group; it provides independent read streams for different applications.

## 9. A single partition does not automatically guarantee business order

Kafka guarantees append order within the partition, but does not automatically understand business before/after relationships. Keep these scenarios in mind:

- **Multiple producers:** record order is the order the leader appends them, not necessarily the order events happened in source systems.
- **Asynchronous producer sends:** send calls from multiple threads or multiple producers need coordination rules if business order is mandatory.
- **Retries and errors:** producer settings should be reviewed together with idempotence, retries, and in-flight requests to avoid unexpected reordering under legacy or misconfigured settings.
- **Parallel consumer processing:** if the listener pushes records to an executor and tasks finish out of order, business side effects can invert even though records were polled in offset order.
- **Timestamps:** timestamps can collide, suffer clock skew, or reflect late events; they do not replace offset order.

If strict causal ordering is needed, designate one authoritative emitter, serialize event emission, or attach sequence numbers/versions to each event for consumer validation. A single partition creates a shared append order, yet does not resolve every business-layer ordering conflict on its own.

## 10. When should you avoid using a single partition?

Avoid choosing a single partition if:

- The topic has high write/read throughput or large payloads.
- Consumers need horizontal scaling to process many records in parallel within the same group.
- Events belong to many independent aggregates and only require per-aggregate ordering.
- One partition leader could become a bottleneck or limit load recovery capacity.
- Multiple business workers need work distributed across multiple consumers in the same group.

For example, topic `orders.events` carries events for millions of orders. Using a single partition forces all load into one log. Using `orderId` as the key with a properly sized partition count lets events of the same order preserve sequence in one partition while different orders process in parallel.

Do not use a single partition as a distributed lock or a mechanism to guarantee only one producer exists. Multiple producers can still write to the same partition; multiple consumer groups can still read independently. If single-writer or leader election is needed at the business layer, implement a dedicated coordination mechanism.

## 11. Future scaling and changing partition counts

Partition count is an architectural decision with long-term impact:

- Kafka allows increasing partition count, but does not support reducing the partition count of an existing topic.
- When increasing partitions, a key-based partitioner may map the same key to a different partition because the modulus denominator changes.
- Old records stay in the old partition while new records may land in a new partition; ordering for a key across the transition window no longer sits in one continuous offset stream.
- For a topic currently using one partition, scaling out to multiple partitions requires re-evaluating ordering requirements, consumer groups, and how historical data is handled.

If scaling needs are expected soon, start with multiple partitions and use keys to preserve per-aggregate order. If topic-wide order is genuinely required, accept the throughput limit and maintain a clear migration plan for when requirements change.

## 12. Testing ordering on a single-partition topic

Integration tests should verify both the actual partition and the read record sequence:

1. Create a test topic with exactly one partition and a replication factor matching the test broker.
2. Send a sequence of events with explicit sequences, such as `1`, `2`, `3`, `4`.
3. Wait for send futures to complete and assert `RecordMetadata.partition()` equals `0`.
4. Read the topic using a dedicated consumer group and inspect partitions/offsets.
5. Verify sequences are read in the expected append order in a single-producer test.
6. If multiple producers or multiple threads exist, separately test ordering coordination rules; do not assume timestamps dictate order.
7. Verify that consumer concurrency greater than one does not increase active consumers reading the sole partition in the same group.

Embedded Kafka or Testcontainers can both be used for integration tests. With a single-broker test setup, the topic's replication factor must be `1`; `.replicas(3)` only works when the test cluster has enough brokers.

## 13. Checklist for deciding on a single partition

- [ ] The real requirement is one shared append order for every record in the topic.
- [ ] Throughput and payload sizes have been measured and are low enough for one partition.
- [ ] Compared against key-based per-aggregate ordering.
- [ ] Accepted at most one active consumer for the partition in each group.
- [ ] Replication factor is chosen separately for durability, not confused with parallelism.
- [ ] Producers have coordination rules if multiple emitters need business ordering.
- [ ] Consumers do not process asynchronously in ways that invert side-effect order unintentionally.
- [ ] Verified the actual topic has exactly one partition.
- [ ] Migration plan exists if partition count ever needs to increase later.
- [ ] Integration tests verify partition, offsets, and append order.

A single partition is a sensible choice when a topic needs one shared append stream, traffic is low, and consumers can process sequentially. If ordering is only needed per entity, using keys on a multi-partition topic generally strikes a better balance between ordering and scalability. Base the decision on business requirements and load metrics, then verify with integration tests before running the topic in production.
