# ProducerRecord and Its Data Fields

In the Kafka Producer API, `ProducerRecord<K, V>` is the object that describes a record a producer wants to send to a topic. It contains the topic name, optional partition, optional timestamp, key, value, and headers. Spring Kafka uses this exact object when calling `KafkaTemplate.send(...)`.

Understanding each field helps you decide where a record will go, how it is routed, what data it carries, and what metadata consumers can read to process it. In many cases, you only need to send the topic, key, and value; when you need control over the partition, timestamp, or metadata, you can construct a `ProducerRecord` explicitly.

## 1. What is ProducerRecord?

`ProducerRecord<K, V>` is a producer-side data structure, where `K` is the key type and `V` is the value type. For example:

```java
ProducerRecord<String, OrderCreatedEvent> record =
        new ProducerRecord<>("orders.events", "O100", event);
```

This record describes data sent to the `orders.events` topic, using the string `O100` as the key and the `event` object as the value. The producer serializes the key and value into bytes before sending them to the broker. `ProducerRecord` is an application-side object; it is not the byte format stored directly in Kafka.

Key fields of `ProducerRecord`:

| Field | Type | Role |
|---|---|---|
| `topic` | `String` | Target topic name. This is a required field. |
| `partition` | `Integer` | Target partition specified by the application; `null` to let the producer partitioner choose. |
| `timestamp` | `Long` | Record timestamp in Unix epoch milliseconds; `null` to let the producer/broker apply the default. |
| `key` | `K` | Key used for partitioning and helping consumers identify groups of related records; can be `null`. |
| `value` | `V` | Main payload of the record; can be `null`. |
| `headers` | `Headers` | Metadata as key/value headers, where the value is a byte array. |

Fields can be accessed via `topic()`, `partition()`, `timestamp()`, `key()`, `value()`, and `headers()`.

## 2. Topic — where the record is sent

`topic` identifies the data stream to which the record belongs. For example:

```java
private static final String ORDER_TOPIC = "orders.events";

ProducerRecord<String, OrderCreatedEvent> record =
        new ProducerRecord<>(ORDER_TOPIC, event.orderId(), event);
```

The topic name must match a topic that the cluster allows the producer to write to. A topic can be created in advance with administrative tools or created automatically if the cluster and application allow auto topic creation. In production, it is generally best to manage topics explicitly in terms of partition count, replication factor, and retention/compaction configuration.

A producer sends records to a specific topic; a consumer group subscribes to that topic to receive records. The topic name is routing metadata, not part of the business payload.

## 3. Partition — where the record is appended

The `partition` field allows the producer to specify a particular partition. The partition index starts at 0 and must exist in the topic. If an invalid partition is specified, the send operation will fail.

Normally, you should leave `partition` as `null` so the partitioner chooses based on the key or the producer's distribution strategy:

```java
// Let the partitioner decide the partition based on the key.
ProducerRecord<String, OrderCreatedEvent> byKey =
        new ProducerRecord<>("orders.events", event.orderId(), event);

// Explicitly specify partition 2 (0-based index).
ProducerRecord<String, OrderCreatedEvent> fixedPartition =
        new ProducerRecord<>("orders.events", 2, event.orderId(), event);
```

When the application specifies a partition, the producer uses that partition instead of asking the partitioner to choose. This is useful in special cases such as partitioning according to controlled custom rules, but it can easily create load skew or break ordering strategies if used arbitrarily.

If no partition is specified:

- When the key is not `null`, the default partitioner typically uses the serialized key to route records with the same key to the same partition, provided the partition count and serialization/partitioning remain stable.
- When the key is `null`, the producer uses the client's keyless distribution strategy. Details may depend on the Kafka client version and partitioner configuration; you should not rely on it to preserve ordering for a business entity.

Kafka guarantees append ordering within a single partition. If events for the same order need to be processed in order, use `orderId` as the key and keep the partitioning strategy stable.

## 4. Timestamp — the time associated with the record

`timestamp` is the time in milliseconds since the Unix epoch (UTC). You can specify the timestamp when creating a record:

```java
long eventTime = event.occurredAt().toEpochMilli();

ProducerRecord<String, OrderCreatedEvent> record =
        new ProducerRecord<>(
                "orders.events",
                null,       // partition: let the partitioner choose
                eventTime,  // timestamp in milliseconds
                event.orderId(),
                event
        );
```

If no timestamp is provided, the producer usually attaches the current time when sending the record. The actual timestamp observed by the consumer also depends on the topic's `message.timestamp.type` configuration:

- `CreateTime`: uses the timestamp provided by the producer; if the producer does not provide one, the client generates the current timestamp.
- `LogAppendTime`: the broker overwrites the timestamp with the time the broker appends the record to the log.

Timestamps are useful for time-based processing, measuring latency, or analyzing event streams. They do not replace offsets and are not an ordering guarantee mechanism. Producer clocks can drift from one another; two records in different partitions also have no total order simply because their timestamps differ.

## 5. Key — routing key and record association

`key` is data serialized by the key serializer. With the default partitioner, the key is an important basis for choosing a partition. For example, `orderId` helps changes for the same order go to the same partition:

```java
ProducerRecord<String, OrderCreatedEvent> record =
        new ProducerRecord<>("orders.events", event.orderId(), event);
```

A key can be used to:

- Route related records to the same partition.
- Preserve the order of changes for the same aggregate within that partition.
- Allow consumers or stream processors to group data by entity.
- Serve as the key for compaction if the topic uses `cleanup.policy=compact`.

A key does not have to be a unique ID for each individual event. For example, `eventId` identifies a single event occurrence, whereas `orderId` groups multiple events belonging to the same order. Choose the key according to partitioning and business processing requirements.

A key can be `null`. In that case, the producer can still send the record, but there is no key for the partitioner to route consistently by entity. If a compacted topic needs to update or delete state by key, records must have an appropriate key.

## 6. Value — the record payload

`value` is the main content the producer sends to Kafka. This is usually an event or message modeled as a DTO, Java class, or Java `record`:

```java
import java.math.BigDecimal;
import java.time.Instant;

public record OrderCreatedEvent(
        String eventId,
        String orderId,
        Instant occurredAt,
        BigDecimal total
) {}
```

When sending this object, the producer needs a compatible value serializer. For example, `StringSerializer` is suitable for `String` values; a JSON serializer is suitable for objects if the consumer has a corresponding deserializer or message converter. Producer and consumer must agree on the schema, encoding, and data version.

`value` can also be `null`. In a compacted topic, a record with a non-`null` key and a `null` value is called a **tombstone**, used to mark the state for that key for deletion. In a non-compacted topic, a null value is simply a record without a payload; deletion semantics do not arise automatically unless the application defines that convention.

Do not confuse a Kafka null value with the JSON string `"null"` or a JSON document whose content is `null`. The latter two are normal byte payloads after serialization, not a Kafka null value.

## 7. Headers — metadata accompanying the record

`headers` contains pairs of header names and byte values. Headers are suitable for metadata used for transport or processing, such as:

- `event-type`: event type, e.g. `OrderCreated`.
- `correlation-id`: links messages belonging to the same processing flow.
- `trace-id`: links logs and traces across services.
- `schema-version`: data contract version.

Example of adding headers:

```java
import java.nio.charset.StandardCharsets;
import org.apache.kafka.clients.producer.ProducerRecord;

ProducerRecord<String, OrderCreatedEvent> record =
        new ProducerRecord<>("orders.events", event.orderId(), event);

record.headers().add(
        "event-type",
        "OrderCreated".getBytes(StandardCharsets.UTF_8)
);
record.headers().add(
        "schema-version",
        "1".getBytes(StandardCharsets.UTF_8)
);
```

Header values are `byte[]`, so producer and consumer must agree on the encoding. For ordinary strings, UTF-8 is the common choice. Headers do not replace the payload: do not put entire business data into headers or use headers to carry large content.

Consumers can read headers from `ConsumerRecord`:

```java
import java.nio.charset.StandardCharsets;

import org.apache.kafka.common.header.Header;

Header eventTypeHeader = record.headers().lastHeader("event-type");

if (eventTypeHeader != null) {
    String eventType = new String(
            eventTypeHeader.value(),
            StandardCharsets.UTF_8
    );
}
```

Kafka headers can contain multiple headers with the same name. `lastHeader(name)` returns the last header with that name; if you need to process all values, you can iterate over `headers().headers(name)`.

## 8. Common constructors

`ProducerRecord` provides multiple constructors to create a record with the needed level of information. Some common forms:

```java
// Topic and value; key is null.
new ProducerRecord<String, OrderCreatedEvent>("orders.events", event);

// Topic, key, and value.
new ProducerRecord<String, OrderCreatedEvent>(
        "orders.events", event.orderId(), event);

// Topic, partition, key, and value.
new ProducerRecord<String, OrderCreatedEvent>(
        "orders.events", 2, event.orderId(), event);

// Topic, partition, timestamp, key, and value.
new ProducerRecord<String, OrderCreatedEvent>(
        "orders.events", 2, System.currentTimeMillis(), event.orderId(), event);
```

The full constructor also lets you pass an `Iterable<Header>` to create a record with a set of headers from the start. If you only need to add a few headers after creation, you can use `record.headers().add(...)` as shown in the example above.

| Construction form | When to use |
|---|---|
| `topic, value` | Payload does not need a key and the partitioner can distribute the record. |
| `topic, key, value` | Common case, requiring key-based routing. |
| `topic, partition, key, value` | Need to specify a concrete partition according to a designed strategy. |
| `topic, partition, timestamp, key, value` | Need to control timestamp along with partition. |
| Constructor with headers | Want to initialize full metadata when creating the record. |

If there are no special requirements, the `topic, key, value` constructor is usually the clearest and easiest-to-maintain choice.

## 9. Sending ProducerRecord with KafkaTemplate

Spring Kafka provides `KafkaTemplate` to send `ProducerRecord`:

```java
import java.nio.charset.StandardCharsets;

import org.apache.kafka.clients.producer.ProducerRecord;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private static final String TOPIC = "orders.events";

    private final KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(OrderCreatedEvent event) {
        ProducerRecord<String, OrderCreatedEvent> record =
                new ProducerRecord<>(TOPIC, event.orderId(), event);

        record.headers().add(
                "event-type",
                "OrderCreated".getBytes(StandardCharsets.UTF_8)
        );

        kafkaTemplate.send(record);
    }
}
```

`KafkaTemplate.send(record)` is an asynchronous operation. In real applications, observe the future/callback to know whether the send succeeded or failed and record the returned metadata when needed. Calling `send` does not mean the broker has already acknowledged a successful write.

Example of tracking the send result in modern Spring Kafka versions that return `CompletableFuture`:

```java
kafkaTemplate.send(record).whenComplete((result, exception) -> {
    if (exception != null) {
        // Log, retry, or route to error handling per application policy.
        return;
    }

    var metadata = result.getRecordMetadata();
    System.out.printf(
            "topic=%s partition=%d offset=%d%n",
            metadata.topic(),
            metadata.partition(),
            metadata.offset()
    );
});
```

The result metadata helps determine which partition and offset the broker wrote the record to. This is operational information; you should not use the offset in place of the event's business ID.

## 10. Common mistakes

| Mistake | Consequence | Resolution |
|---|---|---|
| Sending to the wrong topic name | Record does not reach the stream the consumer expects or is sent to an unintended topic. | Use centralized constants/configuration and verify the topic in the target environment. |
| Specifying a non-existent partition | Broker rejects the send. | Check partition count; specify a partition only when truly needed. |
| Using an unstable key | Events for the same entity may go to different partitions. | Standardize keys and key serializers across all producers. |
| Key/value serializer mismatch with data type | Serialization errors or consumer cannot decode the payload. | Configure compatible serializers/deserializers and schemas. |
| Sending the string `"null"` instead of a `null` value | Kafka stores a literal payload, not a tombstone. | Pass Java `null` if a tombstone is needed on a compacted topic. |
| Putting large payloads into headers | Increases overhead and makes metadata hard to manage. | Keep headers for small metadata, with payloads in the value. |
| Not tracking the `send` result | Asynchronous send failures go undetected. | Handle the future/callback and observe producer errors. |

## 11. Key takeaways

- `ProducerRecord<K, V>` describes a producer-side record with topic, partition, timestamp, key, value, and headers.
- `topic` determines the target stream; `partition` can be explicitly specified or left for the partitioner to choose.
- `key` is commonly used for routing and keeping records of the same entity in a single partition.
- `value` is the serialized payload; a null value on a compacted topic with a key is a tombstone.
- `timestamp` is in epoch milliseconds and is affected by `message.timestamp.type`.
- `headers` carry byte-format metadata and do not replace the business payload.
- `KafkaTemplate.send(ProducerRecord)` sends records asynchronously; handle the result to detect errors and retrieve broker metadata.

When creating a `ProducerRecord`, clearly determine which topic receives the data, which key protects partitioning requirements, which value serves as the payload contract, what the timestamp means, and which metadata the headers need. When these fields are designed consistently, producers and consumers will coordinate more easily, and the Kafka stream can be operated and monitored reliably.
