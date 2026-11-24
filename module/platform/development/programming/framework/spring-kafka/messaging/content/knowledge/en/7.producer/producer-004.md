# Selecting a Partition Using a Key

When sending a record to a Kafka topic with multiple partitions, the producer needs to determine which partition the record will be written to. How the partition is selected directly affects parallelism, load distribution, and event ordering. With Spring Kafka, applications usually pass a **key** when calling `KafkaTemplate.send(...)`; the Kafka producer uses that key to route the record via the partitioner.

The key should represent the business entity for which the system needs to preserve order, such as `orderId`, `accountId`, or `customerId`. When events of the same entity use the same key and the same partitioning rules, they are usually written to the same partition. Kafka guarantees record order within each partition, so consumers can process that entity's sequence of events in log order.

## 1. Multi-partition topics and the routing problem

A topic is split into multiple partitions so Kafka can distribute data and allow consumers to process in parallel. For example, topic `orders.events` has three partitions:

```text
orders.events
  ├── Partition 0: offset 0, 1, 2, ...
  ├── Partition 1: offset 0, 1, 2, ...
  └── Partition 2: offset 0, 1, 2, ...
```

The producer must decide which partition each record goes into. It can specify a partition directly, or let the partitioner choose automatically based on the key and topic metadata.

Kafka only guarantees ordering within the scope of a single partition. There is no total ordering across Partition 0, Partition 1, and Partition 2. If `OrderCreated`, `OrderPaid`, and `OrderShipped` events for the same order are written to different partitions, a consumer may receive them in an undesirable order.

Therefore, key design is a decision about ordering boundaries. The key defines the group of records that must be routed together; the partition is the unit of ordered storage and processing.

## 2. How does Kafka choose a partition from a key?

When no specific partition is provided, Kafka's default partitioner operates according to the following principles:

1. The producer serializes the key and value into byte arrays.
2. If the key has a value, the partitioner computes a hash from the key's bytes.
3. The hash is converted to a non-negative value and used to select one of the available partitions.
4. If the key is `null`, the default partitioner uses sticky partitioning to group keyless records into one partition over an interval/batch, and may then switch to another partition to improve batching and load distribution.

With the traditional default partitioner, the calculation for a key can be expressed broadly as:

```text
partition = positive(hash(serializedKey)) % partitionCount
```

By default, the Kafka client uses a hash algorithm on the serialized key bytes (Murmur2 in the default partitioner). Applications normally do not need to compute the partition themselves; simply choose a stable key and let the producer perform the routing. If a custom partitioner is configured or a partition is specified explicitly, the rules may differ.

Example with a three-partition topic:

| Key | Illustrative routing result |
| --- | --- |
| `order-1001` | Partition 2 |
| `order-1002` | Partition 0 |
| `order-1003` | Partition 1 |
| `order-1001` (next send) | Partition 2 |

The partition numbers in the table are illustrative only. You cannot infer which partition a particular key always belongs to without knowing the partition count, serializer, and partitioner in use. Multiple distinct keys can also hash to the same partition; Kafka does not create a separate partition for each key.

## 3. Choosing a key by business entity

Choose the key by asking: **Which records need Kafka to preserve relative order with respect to each other?**

| Domain | Usually suitable key | Reason |
| --- | --- | --- |
| Order lifecycle | `orderId` | Changes for the same order are routed to the same partition |
| Account transactions | `accountId` | Balance changes for one account share the same ordered stream |
| Customer profile | `customerId` | Updates for the same customer share the same partition |
| IoT device state | `deviceId` | Events from the same device are grouped by key |
| Product inventory events | `productId` | Updates for the same product can be processed in order |

For example, an order has the events:

```text
OrderCreated(orderId=ORD-42)
OrderPaid(orderId=ORD-42)
OrderPacked(orderId=ORD-42)
OrderShipped(orderId=ORD-42)
```

If all four records are sent to the same topic with key `ORD-42`, the default partitioner will choose the same partition (given the same partition count and the same key serialization). A consumer reading that partition will see the records in offset order.

Do not use a new UUID for each event as the key if the goal is to group events by order. Each distinct UUID will scatter events and lose `orderId` affinity. An event UUID is still useful, but it should live in the payload or header to uniquely identify each event; the key remains `orderId`.

## 4. Sending keyed records with `KafkaTemplate`

Spring Kafka provides the `send(topic, key, data)` overload to pass the key directly. The example below uses `orderId` as the key and a JSON event as the value.

```java
import java.time.Instant;
import java.util.concurrent.CompletableFuture;

import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Service;

record OrderEvent(
        String eventId,
        String orderId,
        String eventType,
        Instant occurredAt) {
}

@Service
public class OrderEventPublisher {

    private static final String TOPIC = "orders.events";

    private final KafkaTemplate<String, OrderEvent> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderEvent>> publish(
            OrderEvent event) {
        return kafkaTemplate.send(TOPIC, event.orderId(), event);
    }
}
```

`KafkaTemplate<String, OrderEvent>` expresses the producer's key and value types. The `send` call passes `event.orderId()` as the key, while the entire event is the value. `StringSerializer` serializes the key into bytes; the value serializer (for example `JsonSerializer`) handles converting the event into bytes.

A minimal producer configuration might look like this:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
```

After sending, you can inspect the partition confirmed by the broker in the metadata:

```java
publisher.publish(event)
        .thenAccept(result -> {
            int partition = result.getRecordMetadata().partition();
            long offset = result.getRecordMetadata().offset();
            log.info("Order event sent to partition={}, offset={}",
                    partition, offset);
        })
        .exceptionally(exception -> {
            log.error("Cannot publish order event", exception);
            return null;
        });
```

The callback snippet assumes the class has a logger `log`. Calling `send` is asynchronous; only when the future completes successfully is there metadata confirming that the broker received the record. Do not log success right after the `send` call line.

## 5. Keys must be serialized consistently

The partitioner operates on the serialized bytes of the key. Therefore, the same logical value serialized into different bytes may be routed to different partitions.

For example, if producer A serializes numeric ID `42` as the UTF-8 string `"42"`, while producer B serializes the same ID as a different binary representation, the two producers may compute different hashes. To maintain partition affinity across multiple producers, standardize:

- The data type of the key.
- The key serializer.
- Normalization rules before serialization, such as upper/lower case or whitespace.
- An ID representation that remains compatible across application versions.

For string business IDs, `StringSerializer` is usually a simple choice. Do not change the serializer or key format arbitrarily while the topic is still actively used by multiple producers/consumers.

## 6. Keys, explicit partitions, and custom partitioners

Normally, let Kafka choose the partition from the key. However, `KafkaTemplate` also has overloads that allow specifying a partition:

```java
kafkaTemplate.send("orders.events", 1, orderId, event);
```

This call sends the record to partition `1`, regardless of which partition the default partitioner would select from the key. The partition index must exist in the topic. When specifying a partition manually, the application is responsible for load distribution and ensuring all events requiring the same order are sent to the same partition.

In some systems, routing rules are more complex than the default hash. The Kafka producer lets you install a custom partitioner to map keys to partitions using a custom algorithm. Weigh this carefully before using it, because a custom partitioner increases the burden of keeping logic synchronized across producers and application versions. Every producer writing to the same topic must apply compatible rules.

Do not simultaneously specify an explicit partition and expect the key to guarantee affinity on its own. When a partition is supplied, that partition is the routing choice.

## 7. Keys and processing order

A key does not create topic-wide ordering on its own. It only helps route records with the same key to the same partition according to partitioning rules.

Example:

```text
Producer
  OrderCreated(ORD-42) ─┐
  OrderPaid(ORD-42) ────┼── key=ORD-42 ──> Partition 1
  OrderShipped(ORD-42) ─┘

  OrderCreated(ORD-99) ───── key=ORD-99 ──> Partition 0
```

Within a consumer group, each partition is assigned to at most one consumer at a time. Therefore, the consumer group can process multiple partitions in parallel while order within each partition is preserved. If you need ordered processing by `orderId`, ensure the listener does not dispatch records from the same partition to uncontrolled asynchronous threads that cause business logic to complete out of order.

The producer also needs proper configuration for retries. With an idempotent producer enabled, Kafka preserves the order of batches sent by the producer under retry scenarios supported by the configuration. If idempotence is disabled and multiple in-flight requests are allowed, retries can change the append order of batches. When business order matters, keep idempotence at the Kafka client's appropriate default and do not disable it arbitrarily.

If multiple instances or multiple producers emit events for the same key concurrently, Kafka still writes them to the same partition and creates a unique offset order based on broker append order. However, that order is not necessarily the business order desired by the producers if there is no coordination at the emission source.

## 8. What happens when you increase the partition count?

With the default partitioner, the partition is typically calculated as the key's hash modulo the partition count. Because the denominator changes when increasing the partition count, a key may map to a new partition after the topic is expanded.

Example:

```text
Before: hash(key) % 3 = 1  -> Partition 1
After:  hash(key) % 4 = 3  -> Partition 3
```

This is purely an arithmetic example. The practical consequence is that older events for `ORD-42` may reside in partition 1, while newer events after expanding the topic land in partition 3. The two partitions are processed independently by consumers, so there is no longer a single order across that key's entire history.

If business logic strictly depends on ordering by key, treat the partition count as an architectural decision that must be planned upfront. Before increasing partitions, assess the impact on ordering, consumer concurrency, data distribution, and how state is rebuilt. Consider creating a new versioned topic and migrating in a controlled manner if historical ordering must be preserved.

## 9. Avoiding hot partitions and load skew

Choosing a key preserves order, but it also dictates how load is distributed. If one key accounts for most of the traffic, all records for that key go to the same partition and that partition becomes a **hot partition**. Adding partitions cannot split a single key while using the same hash rule.

Common causes:

- Using a fixed value such as `"ORDER"` for every record.
- Using `tenantId` when one tenant generates most of the traffic.
- Using keys with a skewed distribution, such as some devices emitting far more data than others.
- Using a `null` key for every record and expecting per-entity ordering, when a null key cannot represent the entity to be grouped.

Possible approaches:

1. Choose a key with good distribution while still preserving the right business ordering boundary.
2. If business rules allow sharding an entity, use a composite key like `accountId:shardId`; do this only when accepting that global ordering for the whole account is no longer guaranteed across shards.
3. Monitor record rate, bytes in/out, and consumer lag per partition to detect load skew.
4. Avoid a constant key or an overly broad key purely for implementation convenience.

You cannot both scatter a stream for the same entity across multiple partitions and rely on Kafka to preserve a natural total order for that stream. This is a trade-off between ordering and parallelism that must be decided by business needs.

## 10. Keys in compacted topics and in consumers

Keys also play a special role in topics using `cleanup.policy=compact`. Kafka compaction retains the latest state per key within each partition. If the producer uses `customerId` as the key, the topic can represent the most recent state of each customer.

For compacted topics, the key must be stable and non-null if compaction is to group versions of the same entity. Sending a tombstone (a key with a `null` value) is how key deletion is represented in compacted state; tombstones must be understood alongside compaction retention rules.

On the consumer side, the key can be read from `ConsumerRecord.key()`:

```java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;

@KafkaListener(topics = "orders.events", groupId = "order-projection")
public void consume(ConsumerRecord<String, OrderEvent> record) {
    String orderId = record.key();
    OrderEvent event = record.value();

    // Process changes for the corresponding order.
}
```

Consumers can use the key to update read models, validate business ordering, or select records for deduplication. A key does not replace an event ID: the event ID uniquely identifies a single event emission, whereas the key identifies the group of data related for partitioning.

## 11. Testing partition affinity

A straightforward integration test can send two records with the same key and verify that the metadata returns the same partition. Avoid hard-coding a specific partition index because the result depends on partition count and the partitioner.

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
        "spring.kafka.producer.key-serializer=org.apache.kafka.common.serialization.StringSerializer",
        "spring.kafka.producer.value-serializer=org.apache.kafka.common.serialization.StringSerializer"
})
@EmbeddedKafka(
        partitions = 3,
        topics = "orders.partition-test",
        bootstrapServersProperty = "spring.kafka.bootstrap-servers")
class OrderPartitioningTest {

    @Autowired
    private KafkaTemplate<String, String> kafkaTemplate;

    @Test
    void recordsWithSameKeyUseSamePartition() throws Exception {
        SendResult<String, String> first = kafkaTemplate
                .send("orders.partition-test", "ORD-42", "OrderCreated")
                .get(10, TimeUnit.SECONDS);

        SendResult<String, String> second = kafkaTemplate
                .send("orders.partition-test", "ORD-42", "OrderPaid")
                .get(10, TimeUnit.SECONDS);

        assertThat(second.getRecordMetadata().partition())
                .isEqualTo(first.getRecordMetadata().partition());
    }
}
```

This test demonstrates partition affinity for the same key in the same topic and under the same test configuration. You can add an offset assertion to verify that the second record is appended after the first record in the partition. It does not test load distribution across many keys, ordering across multiple concurrent producers, or behavior after changing the partition count.

## 12. Common misconceptions

| Misconception | Correct understanding |
| --- | --- |
| Every key gets its own dedicated partition | Multiple keys can hash to the same partition |
| The same key always stays on the same partition even if the topic changes | This holds when partition count, serializer, and partitioner stay unchanged |
| Kafka guarantees topic-wide ordering | Kafka only guarantees ordering within each partition |
| Passing no key still preserves entity ordering | A null key does not identify an entity; the default partitioner uses sticky partitioning |
| Increasing partitions is always safe for ordering | A key may map to a different partition after increasing the partition count |
| Event ID should always be the key | Choose the key based on the entity that needs ordering; event ID can live in the payload/header |
| Just sharing a key guarantees exact business order across all producers | The broker establishes append order; the emitting system still has to coordinate business order if multiple producers run concurrently |

## 13. Conclusion

The key is a central mechanism for routing records to partitions. With the default partitioner, Kafka uses the serialized bytes of the key to select a partition; records with the same key typically go to the same partition as long as the topic keeps the same partition count and serialization/partitioning rules. Thanks to offset ordering within a partition, applications can preserve processing order for a business entity such as an order or an account.

In Spring Kafka, pass the key explicitly via `KafkaTemplate.send(topic, key, value)`, choose a stable serializer, and observe the partition from metadata during testing. Key design must balance ordering against load distribution; at the same time, assess the impact of hot partitions and partition count increases before modifying a live topic.
