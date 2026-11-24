# What Information Does ConsumerRecord Contain

When Spring Kafka invokes a `@KafkaListener` method, the application can receive the deserialized value directly or receive the full `ConsumerRecord<K, V>`. Use `ConsumerRecord` when you need both the payload and the metadata Kafka attaches to the record: topic, partition, offset, timestamp, key, value, headers, serialized data sizes, and leader epoch.

This information helps the application locate the record in the log, trace the event's origin, write correlatable logs, handle tombstones, and diagnose consumers. However, `ConsumerRecord` describes a single read record; it does not contain the full state of the consumer group, such as committed offsets or the group ID.

## 1. What is ConsumerRecord?

`ConsumerRecord<K, V>` is the Kafka client object representing a record received by a consumer. The two generic parameters `K` and `V` are the key and value types after the deserializer converts the data from bytes into the Java types used by the application.

For example, with `StringDeserializer` for both key and value, the listener can receive `ConsumerRecord<String, String>`. If the value is deserialized into `OrderEvent`, the listener can receive `ConsumerRecord<String, OrderEvent>`.

```text
Kafka partition
      |
      |  record at offset 42
      v
+-----------------------------------------------+
| ConsumerRecord<String, String>                |
|                                               |
| topic, partition, offset                      |
| timestamp, timestampType, leaderEpoch         |
| key, value                                    |
| headers                                      |
| serializedKeySize, serializedValueSize        |
+-----------------------------------------------+
      |
      v
Spring Kafka @KafkaListener
```

A record can have a `null` key or value. For instance, a record with a key and a `null` value is commonly used as a tombstone in a compacted topic. Therefore, you should not assume every record has a non-null payload.

## 2. Fields that locate a record in Kafka

The three fields `topic()`, `partition()`, and `offset()` identify a record's position in the Kafka log.

| Method | Return type | Meaning |
|---|---|---|
| `topic()` | `String` | Name of the topic containing the record |
| `partition()` | `int` | Partition number containing the record |
| `offset()` | `long` | Position of the record within that partition |

For example, a record with `topic=orders.events`, `partition=2`, `offset=42` is located at offset 42 of partition 2 in the `orders.events` topic.

Use this triplet when logging, correlating errors, storing processing traces, or communicating with operators. An offset is only meaningful within a single partition; offset 42 in partition 0 is not the same position as offset 42 in partition 2.

Kafka guarantees record ordering within the same partition. If a topic has multiple partitions, the location triplet does not establish a global order across them. When ordering per order is required, producers typically use `orderId` as the key so events for the same order go to the same partition according to the configured partitioner.

### Record offset vs. committed offset

`record.offset()` is the position of the record currently being processed. It is not the consumer group's committed offset.

Kafka stores committed progress per consumer group and topic-partition pair. The committed value represents the next position to read. For example, after successfully processing the record at offset `42`, the consumer typically commits offset `43` to indicate the next read position.

| Value | Example | Meaning |
|---|---:|---|
| `record.offset()` | `42` | Offset of the current record |
| Committed offset | `43` | Next position the consumer group will read |

Committing is managed by the Kafka consumer or Spring Kafka listener container according to the acknowledgment mode. You cannot infer commit state from `ConsumerRecord` alone.

## 3. Timestamp and timestamp type

The following two methods provide record timing information:

| Method | Return type | Meaning |
|---|---|---|
| `timestamp()` | `long` | Timestamp in epoch milliseconds |
| `timestampType()` | `TimestampType` | Timestamp type used by the record |

The timestamp can represent either when the producer created the record (`CreateTime`) or when the broker appended the record to the log (`LogAppendTime`), depending on the topic's `message.timestamp.type` configuration. Therefore, when using the timestamp to measure latency or aggregate by business time, check both `timestamp()` and `timestampType()`.

If the record has no valid timestamp, the Kafka client may return a negative sentinel value (`ConsumerRecord.NO_TIMESTAMP`). Do not convert that value to a date-time before checking it.

Example converting the timestamp to `Instant`:

```java
long timestamp = record.timestamp();

if (timestamp >= 0) {
    Instant occurredAt = Instant.ofEpochMilli(timestamp);
    System.out.println("record time=" + occurredAt);
}

System.out.println("timestamp type=" + record.timestampType());
```

A timestamp does not replace an offset. A record with an earlier timestamp can still appear at a higher offset if the event arrives late; Kafka does not reorder the log by timestamp.

## 4. Key and value

The two fields `key()` and `value()` return data after conversion by the consumer deserializer:

| Method | Return type | Meaning |
|---|---|---|
| `key()` | `K` | Record key after deserialization |
| `value()` | `V` | Record value after deserialization |

The key is typically used to route the record to a partition and identify a business entity. For example, `order-1001` is the key for all events belonging to that order. The value holds the payload, such as JSON representing `OrderCreated` or `OrderPaid`.

Key and value can be `null`:

- A record without a key can be partitioned according to the producer's partitioner strategy.
- A record with a key and a `null` value is typically a tombstone, meaning deletion of the key in a compacted topic.
- If the application cannot handle null, check before accessing properties or deserializing into a business object.

Example listener receiving a string payload:

```java
String orderId = record.key();
String payload = record.value();

if (payload == null) {
    // Handle tombstone or application null rules.
    return;
}

process(orderId, payload);
```

When using a JSON deserializer, the listener's generic type must match the object type configured on the consumer factory. `ConsumerRecord<String, OrderEvent>` lets the application work with `OrderEvent` after deserialization, without changing the bytes stored in Kafka.

## 5. Headers: extensible record metadata

`headers()` returns the record's collection of headers. A header is a name and byte-value pair, commonly used to pass small metadata across the processing pipeline without embedding everything into the payload.

Common use cases:

- `trace-id` or `correlation-id` to link logs across the producer, Kafka, and consumer.
- `event-type` to identify the event kind.
- `schema-version` to determine the payload structure version.
- Routing metadata or event-source metadata when the architecture requires it.

Kafka allows multiple headers with the same name on a single record. You can use `lastHeader(name)` to get the last header with that name, or `headers(name)` to iterate over all values with the same name.

Example reading `trace-id`:

```java
import java.nio.charset.StandardCharsets;
import org.apache.kafka.common.header.Header;

Header traceHeader = record.headers().lastHeader("trace-id");
String traceId = null;

if (traceHeader != null && traceHeader.value() != null) {
    traceId = new String(traceHeader.value(), StandardCharsets.UTF_8);
}
```

If you need to read multiple headers with the same name:

```java
for (Header header : record.headers().headers("tag")) {
    byte[] bytes = header.value();
    String tag = bytes == null
            ? null
            : new String(bytes, StandardCharsets.UTF_8);

    System.out.println("tag=" + tag);
}
```

Header values are bytes, so producer and consumer must agree on encoding or format. Do not assume every header is UTF-8. Avoid putting passwords, access tokens, sensitive personal data, or large payloads in headers; headers should contain only necessary metadata with clear conventions.

## 6. Serialized key and value sizes

`ConsumerRecord` provides two methods to observe the byte size of the key and value:

| Method | Return type | Meaning |
|---|---|---|
| `serializedKeySize()` | `int` | Size of the key in serialized form, in bytes |
| `serializedValueSize()` | `int` | Size of the value in serialized form, in bytes |

If the key or value is `null`, the corresponding size may be `-1`. This is the serialized data size, not the Java heap object size and not the total size of the record over the network. It does not fully include protocol, batch, header, and other storage structure overhead.

These two values are useful when investigating abnormally growing payloads or analyzing message size distribution. For example:

```java
int keyBytes = record.serializedKeySize();
int valueBytes = record.serializedValueSize();

if (valueBytes >= 0 && valueBytes > 256 * 1024) {
    log.warn(
            "Large Kafka value: topic={}, partition={}, offset={}, bytes={}",
            record.topic(), record.partition(), record.offset(), valueBytes
    );
}
```

The `256 KiB` threshold is only an illustrative example, not a Kafka default limit. The system should determine thresholds based on allowed message size, broker capacity, fetch configuration, and business requirements.

## 7. Leader epoch

`leaderEpoch()` provides the leader epoch attached to the record as an `Optional<Integer>` in Kafka client versions that support this API. Leader epoch is the generation number of the partition leader, incremented when the partition transitions to a new leader epoch. Kafka uses this information in log consistency mechanisms and to detect log truncation during leader changes.

Leader epoch is not an offset, timestamp, or consumer group generation. Normal applications rarely need to use this field directly in business logic, but it is useful when diagnosing failover scenarios or reconciling metadata at the Kafka client level.

Example:

```java
record.leaderEpoch().ifPresent(epoch ->
        log.debug(
                "Kafka record leader epoch: topic={}, partition={}, epoch={}",
                record.topic(), record.partition(), epoch
        )
);
```

If the `Optional` is empty, leader epoch metadata is not available for that record. You should not try to infer the epoch from the offset or the consumer group's rebalance count.

## 8. Example reading ConsumerRecord in Spring Kafka

The following example combines commonly used fields in a listener. Assume producer and consumer have configured `StringSerializer`/`StringDeserializer` for key and value.

```java
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.header.Header;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
class OrderConsumer {

    private static final Logger log = LoggerFactory.getLogger(OrderConsumer.class);

    @KafkaListener(
            topics = "orders.events",
            groupId = "order-projection"
    )
    public void consume(ConsumerRecord<String, String> record) {
        String topic = record.topic();
        int partition = record.partition();
        long offset = record.offset();
        String orderId = record.key();
        String payload = record.value();

        long timestamp = record.timestamp();
        String eventTime = timestamp < 0
                ? "unknown"
                : Instant.ofEpochMilli(timestamp).toString();

        Header traceHeader = record.headers().lastHeader("trace-id");
        String traceId = traceHeader == null || traceHeader.value() == null
                ? "missing"
                : new String(traceHeader.value(), StandardCharsets.UTF_8);

        log.info(
                "Consume Kafka record: topic={}, partition={}, offset={}, "
                        + "key={}, timestamp={}, timestampType={}, "
                        + "keyBytes={}, valueBytes={}, traceId={}",
                topic,
                partition,
                offset,
                orderId,
                eventTime,
                record.timestampType(),
                record.serializedKeySize(),
                record.serializedValueSize(),
                traceId
        );

        if (payload == null) {
            handleTombstone(orderId);
            return;
        }

        processOrderEvent(orderId, payload);
    }

    private void handleTombstone(String orderId) {
        // Handle deletion signal according to application rules.
    }

    private void processOrderEvent(String orderId, String payload) {
        // Deserialize business payload if needed and process the event.
    }
}
```

The code focuses on reading metadata. In a real application, `log` needs to be declared using the project's logger, such as SLF4J. You should also consider log levels and data masking policies: do not write full payloads, sensitive keys, or headers containing secret information into production logs.

If you want to read the leader epoch, you can add:

```java
record.leaderEpoch().ifPresent(epoch ->
        log.debug("leaderEpoch={}", epoch)
);
```

## 9. What information does ConsumerRecord NOT contain?

Some data is often mistaken for record properties, when in reality it resides in the consumer, listener container, or consumer group:

| Information | Appropriate place to obtain it |
|---|---|
| Consumer group ID | `group.id` configuration, `@KafkaListener(groupId = ...)`, or container configuration |
| Group's committed offset | Kafka consumer group offsets or appropriate admin/consumer API |
| List of partitions currently assigned to the consumer | `KafkaConsumer.assignment()` or listener container assignment events |
| Time when the application started processing | Recorded using a clock inside the listener |
| Spring Kafka retry/delivery attempt count | Retry mechanism and metadata/headers provided by Spring Kafka, depending on configuration and version |
| Producer transaction state | Transaction configuration and state, not inside `ConsumerRecord` |

In particular, `record.offset()` does not indicate whether the record has been committed. Successful processing and committing the offset are two related but distinct steps. With Spring Kafka's acknowledgment mode, the listener container decides when to commit according to configuration. If manual acknowledgment is needed, acknowledge after business logic completes and clearly understand how the container handles batches, errors, and retries.

## 10. Using metadata for the right purpose

| Need | Field to inspect |
|---|---|
| Identify a record in the log | `topic()`, `partition()`, `offset()` |
| Know the timestamp attached to the record | `timestamp()`, `timestampType()` |
| Identify an entity or business routing | `key()` |
| Read event content | `value()` |
| Pass trace ID, correlation ID, schema version | `headers()` |
| Investigate large payloads | `serializedKeySize()`, `serializedValueSize()` |
| Analyze partition leader generation metadata | `leaderEpoch()` |

When logging to support operations, the topic-partition-offset triplet is usually the first piece of information needed to trace a record. Key, timestamp type, and trace ID can be added if they help with investigation. Keep logs structured, bound their size, and avoid logging sensitive data.

Understanding `ConsumerRecord` properly helps a Spring Kafka listener know where a record came from, where it sits in the log, and what metadata it carries. Separating record metadata from consumer group commit state makes event processing, retrying, observability, and recovery more accurate.
