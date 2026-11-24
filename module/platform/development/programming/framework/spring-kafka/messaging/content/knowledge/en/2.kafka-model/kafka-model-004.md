# Record key, value, and timestamp

Kafka stores and transmits data as **records**. A record carries `key`, `value`, and `timestamp` data alongside metadata such as topic, partition, offset, and headers. Understanding these three components—key, value, and timestamp—helps design stable event streams: events for the same entity can go to the same partition, consumers read the right payload, and applications distinguish when an event occurred from when Kafka received it.

In the `SPRING_KAFKA_MESSAGING` module, we typically construct records with `KafkaTemplate` or `ProducerRecord`, and read records with `@KafkaListener` and `ConsumerRecord`. Spring Kafka provides convenient Java types, yet the underlying rules for keys, values, and timestamps remain Kafka's rules.

## 1. Structure of a Kafka record

You can picture a record after it is written to Kafka as follows:

```text
Topic: orders
  Partition: 3
    Offset: 182
    Timestamp: 1731741000000
    Timestamp type: CreateTime
    Key: order-8421
    Value: {"orderId":"order-8421","status":"PAID"}
    Headers: event-type=OrderPaid
```

This is a logical representation for reading metadata. Kafka does not store `key` and `value` as Java objects or JSON objects; the producer converts them to bytes before sending. The consumer uses corresponding deserializers to convert those bytes back into types the application uses.

| Component | Meaning | Who provides or determines it? |
|---|---|---|
| `topic` | Logical stream containing the record, e.g., `orders` | Producer chooses the topic when sending |
| `partition` | Physical partition of the topic; order is guaranteed within each partition | Producer partitioner or explicit partition; broker stores record in that partition |
| `offset` | Position of the record within a partition | Assigned by the broker when writing the record |
| `key` | Identifier or partitioning key of the record | Provided by the producer; may be `null` |
| `value` | Main payload, usually an event or state data | Provided by the producer; may be `null` |
| `timestamp` | Time associated with the record, in milliseconds since Unix epoch | Producer or broker, depending on timestamp type |
| `headers` | Metadata as name and byte-value pairs | Producer can attach; consumer can read |

In the Java Kafka client, two key types are:

- `ProducerRecord<K, V>` describes a record the producer is preparing to send. `K` is the Java type of the key before serialization on the producer and after deserialization on the consumer; `V` is the corresponding value type.
- `ConsumerRecord<K, V>` is the record the consumer receives, containing both data and metadata such as topic, partition, offset, timestamp, and headers.

Offsets are only meaningful within a single partition. Two records in different partitions can have the same offset, so never use offset as a topic-wide global sequence number.

## 2. Key: identification and partition selection

A key typically represents the business entity described by a sequence of events, such as `orderId`, `accountId`, or `customerId`. The key plays two important roles:

1. **Record routing:** the partitioner uses the key to select a partition when the producer does not specify an explicit partition.
2. **Identity during compaction:** for topics with log compaction enabled, Kafka uses the key to identify records belonging to the same logical entity.

### 2.1. How does the key affect partitioning?

With the default partitioner and a non-`null` key, Kafka hashes the serialized bytes of the key and selects a partition. Therefore, the same key is typically routed to the same partition as long as the partition count, key serialization, and partitioner configuration remain unchanged.

```text
order-1001 ──┐
order-1001 ──┼──> partitioner ──> orders-2
order-1001 ──┘

order-1002 ─────> partitioner ──> orders-5
```

This directly affects processing order. Kafka guarantees record order within a single partition. If all events for `order-1001` are written to the same partition, a consumer can read that order's event sequence in partition offset order. Kafka does not guarantee total order across partitions.

For example, if an order produces `OrderCreated`, `PaymentAuthorized`, and `OrderShipped`, using `orderId` as the key keeps these events in the same partition under stable partitioning. If a new UUID were used for each event, events of the same order could scatter and the application could no longer rely on single-partition ordering to process them.

When the producer specifies an explicit `partition`, that partition is used instead of deriving one from the key. A custom partitioner can also override the default rule. Thus, key-based hashing is the behavior of the default partitioner, not an immutable guarantee across every configuration.

### 2.2. What happens when the key is `null`?

A record can omit a key. With the default partitioner in modern Kafka versions, producers typically use sticky partitioning for keyless records: one partition is retained for a send/batch window to batch data efficiently, then it may switch to another partition. Exact distribution behavior depends on producer version and configuration.

When the key is `null`, the application has no guarantee that records for the same entity will go to the same partition. Omit the key only when business logic does not require entity-based routing or per-key ordering.

### 2.3. Choosing a stable key

A good key usually has these characteristics:

- Represents the entity whose order must be preserved, such as `orderId` for an order lifecycle.
- Remains stable across events for the same entity.
- Uses consistent serialization across producers and application versions.
- Distributes evenly enough to avoid concentrating most traffic in a single partition.

If using a composite key, standardize the format and component order. For example, `tenant-17:order-1001` is clearer and more stable than concatenating values without a delimiter. Key serialization matters greatly: the partitioner hashes the serialized bytes of the key, so the same business value encoded into two different byte representations can land in different partitions.

Do not assume increasing the partition count is a no-op for keys. With hash-and-partition-count routing, changing the partition count can map a key to a different partition. Old records stay in the old partition while new records may enter a new partition; at that point, there is no longer one offset stream representing the entity's entire history. If strict per-entity ordering is needed, plan a partition scaling strategy and how consumers handle the transition period ahead of time.

Keys can also create hot partitions. For example, if `countryCode` is used as the key and most traffic comes from one country, one partition may receive too many records. Choosing a key is a balance between business ordering and load distribution.

## 3. Value: the record payload

The value holds the data the consumer needs to process. In event-driven systems, the value is usually a clearly named and structured event, such as `OrderCreated`, `PaymentCaptured`, or `InventoryAdjusted`. In state-storage topics, the value may be the latest snapshot of an entity.

Key and value are serialized independently. A common setup uses `StringSerializer` for the key and a JSON serializer for the value. Systems using Avro, Protobuf, or other formats follow the same principle: producers and consumers must agree on schema, serializers, deserializers, and schema compatibility policies.

Example value of an `OrderCreated` event:

```json
{
  "orderId": "order-1001",
  "customerId": "customer-42",
  "total": 1250000,
  "currency": "VND",
  "occurredAt": "2026-11-17T02:15:30Z"
}
```

In this example, `orderId` can simultaneously act as the key to route the order's events; the full object serves as the value for business processing. There is no need to repeat every field in the key: the key should be small, stable, and serve routing or identification; the value serves processing content.

### 3.1. Distinguishing an empty value from a `null` value

These three cases are not the same:

| Case | Meaning at the record layer |
|---|---|
| Value is an empty JSON object `{}` | Payload is still JSON data representing content |
| Value is an empty byte array | Payload exists but has length 0 |
| Value is `null` | Record has no value payload |

On topics with **log compaction** enabled, a record with a non-`null` key and a `null` value is called a *tombstone*. A tombstone signifies deleting the current value for that key. When compacting the log, Kafka retains the latest state per key and uses tombstones to propagate deletion signals; a tombstone is only removed after the configured tombstone retention window, not immediately when the producer sends it.

For example, suppose topic `customer-state` holds `customer-42 -> {"name":"An"}`. When the application sends `customer-42 -> null`, a consumer rebuilding state can interpret that this customer's data was deleted. A record with a `null` key cannot act as a tombstone for a specific entity because there is no key to identify that entity.

On non-compacted topics, a `null` value is simply a record with no payload; business meaning is defined by the application. Therefore, avoid arbitrary `null` values unless consumers share an explicit handling convention.

## 4. Timestamp: the time of the record

A Kafka record's timestamp is the number of milliseconds since the Unix epoch (`1970-01-01T00:00:00Z`). Timestamps let applications attach time context to data, but you must know where the timestamp is set and what moment it represents.

Kafka supports two common timestamp types:

| Timestamp type | Who sets the timestamp? | Meaning |
|---|---|---|
| `CreateTime` | Producer | Time attached by the producer. If the producer does not pass a timestamp, it typically uses the sending machine's current clock. |
| `LogAppendTime` | Broker | Time the broker writes the record into the log; the broker overwrites any producer-supplied timestamp with the broker's receipt time. |

The timestamp type is controlled by the broker's `message.timestamp.type` setting or the corresponding topic-level configuration. `CreateTime` is the common default. Consumers can inspect both the timestamp value and the timestamp type to interpret it accurately.

### 4.1. Event time and ingestion time

Two timestamps often need to be distinguished:

- **Event time:** when the event actually occurred in business reality, such as when a customer completed payment.
- **Ingestion time:** when the Kafka broker received and wrote the record.

If a producer sends an event after a delay using `CreateTime`, the timestamp can reflect event time if the application explicitly supplies when the event happened. With `LogAppendTime`, the timestamp reflects when the broker accepted the record. For time-windowed processing, picking the wrong timestamp can skew analytics away from business reality.

If both timestamps are needed, keep `occurredAt` inside the payload or headers and use the Kafka timestamp for ingestion time (or vice versa per system convention). Document this convention clearly in the event contract so all consumers interpret it identically.

### 4.2. Timestamps are not a global order

Timestamps are not unique sequence numbers. Multiple records can share the same timestamp; producer clocks can skew; late-arriving records can carry an older event time than previously written records. Even if timestamps appear monotonic in a test run, applications must not rely on that as a Kafka guarantee.

When you need order within a partition, use that partition's offset order. When you need business order per entity, design the key so the entity's events share a partition and ensure the producer emits them in the desired order. Timestamps are useful for time-based analysis and event-time processing, but they do not replace offsets or business versioning mechanisms.

## 5. Sending and receiving records with Spring Kafka

### 5.1. Sending records with explicit key, value, and timestamp

The following example uses `orderId` as the key, the `OrderCreated` object as the value, and `occurredAt` as the timestamp. The `event-type` header adds the event kind so consumers or observability tools can read it without inferring from class names.

```java
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.List;

import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.header.Header;
import org.apache.kafka.common.header.internals.RecordHeader;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

public record OrderCreated(
        String orderId,
        BigDecimal total,
        Instant occurredAt
) {}

@Service
public class OrderPublisher {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public OrderPublisher(KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(OrderCreated event) {
        List<Header> headers = List.of(
                new RecordHeader(
                        "event-type",
                        "OrderCreated".getBytes(StandardCharsets.UTF_8)
                )
        );

        ProducerRecord<String, OrderCreated> record = new ProducerRecord<>(
                "orders",
                null, // Let the partitioner choose the partition from the key
                event.occurredAt().toEpochMilli(),
                event.orderId(),
                event,
                headers
        );

        kafkaTemplate.send(record);
    }
}
```

The second parameter is `partition`; passing `null` lets the producer choose the partition automatically. The third parameter is the timestamp in milliseconds. The fourth and fifth parameters are the key and value, respectively. If you do not need a custom timestamp or headers, you can use the shorter `kafkaTemplate.send("orders", event.orderId(), event)`.

This example assumes `occurredAt` is always non-null. In real applications, validate inputs and standardize time zones/time formats in the domain layer. The return type of `KafkaTemplate.send` has changed across Spring Kafka versions; in modern versions, it returns `CompletableFuture<SendResult<K, V>>`, allowing asynchronous handling of send results.

Key and value serializers must match the generic types of `KafkaTemplate`. For instance, a `String` key needs a string serializer/deserializer; an `OrderCreated` value needs a suitable JSON serializer and the consumer needs a deserializer capable of converting the payload back to the right type. Mismatched serializer configurations commonly cause send failures, deserialization errors, or unreadable consumer data.

### 5.2. Reading metadata with `ConsumerRecord`

If a listener accepts only an `OrderCreated` parameter, Spring Kafka conveniently passes the payload to the listener method. When you need to inspect the key, timestamp, partition, or offset, accept a `ConsumerRecord`:

```java
import java.time.Instant;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderCreatedListener {

    @KafkaListener(topics = "orders", groupId = "order-projection")
    public void onMessage(ConsumerRecord<String, OrderCreated> record) {
        long timestamp = record.timestamp();
        String recordTime = timestamp >= 0
                ? Instant.ofEpochMilli(timestamp).toString()
                : "unknown";

        System.out.printf(
                "topic=%s partition=%d offset=%d key=%s timestamp=%s type=%s%n",
                record.topic(),
                record.partition(),
                record.offset(),
                record.key(),
                recordTime,
                record.timestampType()
        );

        OrderCreated event = record.value();
        // Process the event according to business rules.
    }
}
```

`record.key()` returns the deserialized key; `record.value()` returns the deserialized payload. `record.timestamp()` returns the timestamp in milliseconds and `record.timestampType()` tells whether it is `CreateTime` or `LogAppendTime`. The `topic`, `partition`, and `offset` fields are useful for logging, error tracing, and reconciling consumer progress.

When logging in production environments, avoid printing the full value if the payload contains personal data or sensitive information. Usually logging the permitted key, topic, partition, offset, event type, and correlation id is sufficient.

## 6. Choosing key, value, and timestamp by scenario

| Scenario | Recommended key | Recommended value | What timestamp should represent |
|---|---|---|---|
| Order lifecycle events | `orderId` | Events such as `OrderCreated`, `OrderPaid` | When the event occurred if doing event-time processing |
| Account events | `accountId` | Transactions or balance changes | When the business action occurred |
| Compacted topic storing latest state | Stable entity ID | Current snapshot; `null` to emit a tombstone on delete | Update time or broker receipt time, per convention |
| Independent event log without entity affinity | May be `null` | Event payload | Business time or ingestion time |

Before finalizing the design, answer three questions:

1. Which entity must consumers preserve order for? Use that entity's identifier as the key.
2. What data do consumers need to process? Put that content in the value and manage compatible schemas.
3. Does the system analyze by event time or ingestion time? Pick the corresponding timestamp type and time field.

## 7. Common design mistakes

- **Using a unique per-event ID as the key when aggregate ordering is required:** events for the same entity can scatter across partitions. Consider using `orderId`, `accountId`, or the aggregate ID.
- **Assuming the same key stays on the same partition forever:** increasing partitions, changing the partitioner, or changing key serialization can alter routing results.
- **Using a skewed key:** a hot partition reduces the topic's parallel processing capacity. Measure key distribution with realistic data.
- **Treating timestamps as a global order:** timestamps can collide, suffer clock skew, or arrive late. Use offsets within a partition when log order is needed.
- **Confusing `value = null` with an empty object:** in compacted topics, a non-`null` key with a `null` value carries tombstone semantics.
- **Not aligning serializers and deserializers:** the producer might succeed in sending while the consumer fails to decode the key or value. Manage configuration and schemas as part of the event contract.
- **Failing to distinguish event time from ingestion time:** reports grouped by broker receipt time can differ from reports grouped by when business events occurred.

## 8. Pre-release topic checklist

- [ ] The key represents the exact entity needed for routing or compaction.
- [ ] Producers use consistent key serialization.
- [ ] Key distribution does not create unexpected hot partitions.
- [ ] Values have a clear schema and consumers have compatible deserializers.
- [ ] Handling conventions for `null` values and tombstones are defined if compaction is enabled.
- [ ] Timestamps are clearly defined as event time or ingestion time.
- [ ] Consumers needing metadata use `ConsumerRecord` or appropriate header extraction mechanisms.
- [ ] Any plan to increase partitions accounts for impacts on routing and per-key ordering.

When keys, values, and timestamps are designed as a data contract, producers can publish events via `KafkaTemplate` and consumers can use `@KafkaListener` to process them with consistent semantics. This lays the foundation for subsequent topics such as serialization, consumer groups, retries, dead-letter handling, and messaging flow testing.
