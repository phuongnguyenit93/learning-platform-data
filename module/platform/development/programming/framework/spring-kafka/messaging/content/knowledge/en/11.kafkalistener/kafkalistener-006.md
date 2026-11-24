# Reading key, topic, partition, and offset

In Spring Kafka, a listener often needs more than just the event payload. When processing a record, the application may need the key to identify the business entity, the topic to know the data source, the partition to understand parallel processing flow, and the offset to track reading progress. `@KafkaListener` exposes these details through `ConsumerRecord`, `@Header` parameters, or a `Message<?>` object.

These four pieces of information serve distinct roles. The key usually supports routing and entity identification; the topic identifies the log the record belongs to; the partition identifies the ordered sub-log; and the offset identifies the record's position within that partition. Reading each field accurately makes logging, tracing, and business processing more reliable.

## 1. Looking Inside a Kafka Record

A Kafka record can be represented by the following fields:

| Field | Meaning | Example |
|---|---|---|
| Key | Identifier or partitioning key sent by the producer | `order-1024` |
| Value | Event payload | `OrderCreated` |
| Topic | Name of the topic containing the record | `orders` |
| Partition | Partition containing the record | `2` |
| Offset | Position of the record within the partition | `184` |
| Timestamp | Timestamp attached to the record | `1730000000000` |
| Headers | Additional key/value metadata | `trace-id`, `event-type` |

An example record can be described as follows:

```text
topic      = orders
partition  = 2
offset     = 184
key        = order-1024
value      = {"orderId":"order-1024","total":250000}
timestamp  = 1730000000000
headers    = trace-id=abc-123, event-type=OrderCreated
```

Key and value are data sent by the producer; the application chooses the destination topic. The producer partitioner chooses the partition based on the key and topic metadata, or the application can specify a partition explicitly. Kafka assigns the offset when the record is written to that partition's log. The timestamp may be supplied by the producer or assigned by the broker depending on configuration. Headers hold extra metadata, commonly used to carry correlation IDs, trace IDs, event types, or schema version info.

## 2. Reading All Metadata with ConsumerRecord

The most direct way when both payload and metadata are needed is to accept `ConsumerRecord<K, V>` in the listener. `K` is the deserialized key type and `V` is the deserialized value type.

```java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
class OrderListener {

    @KafkaListener(
            topics = "orders",
            groupId = "order-reader"
    )
    public void onOrder(ConsumerRecord<String, OrderCreated> record) {
        String key = record.key();
        OrderCreated event = record.value();

        String topic = record.topic();
        int partition = record.partition();
        long offset = record.offset();
        long timestamp = record.timestamp();

        log.info(
                "Received order event: key={}, topic={}, partition={}, offset={}, timestamp={}",
                key,
                topic,
                partition,
                offset,
                timestamp
        );

        orderService.process(event);
    }
}
```

Commonly used accessors:

| Method | Return value | Notes |
|---|---|---|
| `key()` | Deserialized key | May be `null` |
| `value()` | Deserialized payload | May be `null`, e.g., tombstone |
| `topic()` | Topic name | Not the consumer group name |
| `partition()` | Partition number | Type `int` |
| `offset()` | Offset of the current record | Type `long`, meaningful within the partition |
| `timestamp()` | Record timestamp | Milliseconds since epoch or invalid sentinel if absent |
| `timestampType()` | Timestamp type | `CreateTime`, `LogAppendTime`, or `NO_TIMESTAMP_TYPE` if the record has no timestamp |
| `headers()` | Native Kafka headers | Each header has a name and a byte-array value |
| `serializedKeySize()` | Serialized key size | Not the string length after deserialization |
| `serializedValueSize()` | Serialized value size | May have no size if value is null |

`ConsumerRecord` is the right choice when cross-referencing data with the Kafka CLI, logging metadata, reading raw headers, or feeding partition/offset details into business flows.

Do not retain the entire `ConsumerRecord` or Kafka headers long-term as a business object. Extract only the required fields into a dedicated command or context, avoiding tight coupling to the Kafka API in the domain layer.

## 3. Reading key, topic, partition, and offset with @Header

If the listener only needs the payload plus a few metadata fields, you can declare separate parameters and use `@Header`. Spring Kafka maps record metadata into the corresponding message headers.

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.stereotype.Component;

@Component
class OrderHeaderListener {

    @KafkaListener(
            topics = "orders",
            groupId = "order-header-reader"
    )
    public void onOrder(
            OrderCreated event,
            @Header(KafkaHeaders.RECEIVED_KEY) String key,
            @Header(KafkaHeaders.RECEIVED_TOPIC) String topic,
            @Header(KafkaHeaders.RECEIVED_PARTITION) int partition,
            @Header(KafkaHeaders.OFFSET) long offset) {

        log.info(
                "Received key={}, topic={}, partition={}, offset={}",
                key,
                topic,
                partition,
                offset
        );

        orderService.process(event);
    }
}
```

Important constants:

| Constant | Contents |
|---|---|
| `KafkaHeaders.RECEIVED_KEY` | Key of the received record |
| `KafkaHeaders.RECEIVED_TOPIC` | Topic name |
| `KafkaHeaders.RECEIVED_PARTITION` | Partition number |
| `KafkaHeaders.OFFSET` | Record offset |
| `KafkaHeaders.RECEIVED_TIMESTAMP` | Record timestamp |
| `KafkaHeaders.TIMESTAMP_TYPE` | Timestamp type |
| `KafkaHeaders.NATIVE_HEADERS` | Native Kafka headers |

Using `@Header` keeps the listener concise when only a few metadata fields are needed. When many fields, native headers, or Kafka consumer APIs are needed, `ConsumerRecord` is usually easier to read with fewer parameters.

### Handling Potentially Null Keys

Kafka allows records without a key in many scenarios. If a listener declares the key as a required parameter while an actual record has a null key, the application must consider binding and null handling. You can mark the header as optional:

```java
@KafkaListener(topics = "orders", groupId = "order-header-reader")
public void onOrder(
        OrderCreated event,
        @Header(value = KafkaHeaders.RECEIVED_KEY, required = false)
        String key,
        @Header(KafkaHeaders.RECEIVED_TOPIC) String topic,
        @Header(KafkaHeaders.RECEIVED_PARTITION) int partition,
        @Header(KafkaHeaders.OFFSET) long offset) {

    if (key == null) {
        log.warn(
                "Received an order event without key: topic={}, partition={}, offset={}",
                topic,
                partition,
                offset
        );
    }

    orderService.process(event);
}
```

For listeners that must handle null keys or tombstones precisely, accepting `ConsumerRecord` is usually clearer because you can inspect `record.key()` and `record.value()` directly.

## 4. Reading Metadata via Message<?> and Message Headers

Spring Kafka can convert a record into a Spring Messaging `Message<?>`. The payload lives in `getPayload()`, and metadata lives in `getHeaders()`:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component
class OrderMessageListener {

    @KafkaListener(
            topics = "orders",
            groupId = "order-message-reader"
    )
    public void onOrder(Message<OrderCreated> message) {
        OrderCreated event = message.getPayload();

        Object key = message.getHeaders().get(KafkaHeaders.RECEIVED_KEY);
        String topic = message.getHeaders()
                .get(KafkaHeaders.RECEIVED_TOPIC, String.class);
        Integer partition = message.getHeaders()
                .get(KafkaHeaders.RECEIVED_PARTITION, Integer.class);
        Long offset = message.getHeaders()
                .get(KafkaHeaders.OFFSET, Long.class);

        log.info(
                "Received key={}, topic={}, partition={}, offset={}",
                key,
                topic,
                partition,
                offset
        );

        orderService.process(event);
    }
}
```

This approach is useful when the application already uses Spring Messaging or wants to pass payload and headers as a unified message. Header values are objects; read them with the appropriate type and check for null if a header is not guaranteed to be present.

Do not confuse Spring message headers with native Kafka headers. Fields like `RECEIVED_TOPIC`, `RECEIVED_PARTITION`, and `OFFSET` are metadata mapped by Spring. Headers sent by the producer live in native Kafka headers and are read differently.

## 5. Distinguishing Key from Topic, Partition, and Offset

These four fields frequently appear side by side in logs, yet have distinct meanings:

| Field | Who decides? | Globally unique across cluster? | Used for? |
|---|---|---|---|
| Key | Producer | No | Identification, partitioning, per-entity processing |
| Topic | Producer or application config | No | Selecting the data stream |
| Partition | Producer partitioner or explicit producer choice | No | Splitting the log and parallel processing |
| Offset | Assigned by Kafka within the partition | No | Pinpointing the record's position in the log |

### How Does the Key Affect the Partition?

With the default partitioner, the producer typically hashes the key to select a partition. Records with the same key are usually sent to the same partition as long as the partition count and partitioning strategy stay constant. This helps preserve record order for an entity, e.g., all events for `order-1024` go to the same partition.

However:

- A key is not a partition number.
- A key is not an offset.
- The same key does not guarantee the same partition if the partition count or partitioner changes.
- If the key is null, the partitioner may pick a partition using a different distribution mechanism.
- A producer can specify a partition explicitly, in which case that partition is chosen directly.

Example sending a record with a key:

```java
kafkaTemplate.send(
        "orders",
        order.getOrderId(),
        new OrderCreated(order.getOrderId(), order.getTotal())
);
```

The producer uses `order.getOrderId()` as the key for routing via the partitioner. The listener retrieves the key via `record.key()` or `KafkaHeaders.RECEIVED_KEY`.

## 6. Understanding Offsets in the Right Scope

An offset is a record's position within a single partition, not a topic-wide sequence number. For example:

```text
orders-0: offset 0, 1, 2, 3, 4, ...
orders-1: offset 0, 1, 2, 3, 4, ...
orders-2: offset 0, 1, 2, 3, 4, ...
```

Record `orders-0` at offset `15` and record `orders-2` at offset `15` are two completely different records. Therefore, when logging or storing checkpoints, always pair the offset with both topic and partition.

Characteristics of offsets:

- Kafka assigns offsets sequentially as records are written to each partition.
- The current record's offset comes from `record.offset()`.
- An offset is not a timestamp; use `record.timestamp()` if timing is needed.
- Observed offsets may be non-contiguous from a consumer's perspective, such as in compacted topics or with aborted transactions.
- Offsets should not be used as business IDs or system-wide unique keys.

If you need to persist processing progress, a checkpoint must minimally bind to the consumer group, topic, and partition; the committed offset represents the next position to read, whereas `record.offset()` is the offset of the current record.

## 7. Reading Native Headers of a Kafka Record

Kafka headers are a collection of name and byte-array pairs. A single record can contain multiple headers with the same name, so do not assume each name appears only once.

```java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.header.Header;
import org.apache.kafka.common.header.Headers;

void logHeaders(ConsumerRecord<String, OrderCreated> record) {
    Headers headers = record.headers();

    for (Header header : headers) {
        String name = header.key();
        byte[] value = header.value();

        String decoded = value == null
                ? null
                : new String(value, java.nio.charset.StandardCharsets.UTF_8);

        log.debug("Kafka header: name={}, value={}", name, decoded);
    }
}
```

If only a specific header is needed, use `headers().lastHeader("trace-id")`. This method returns the last header with that name or null if none exists. Header values remain byte arrays and must be decoded with the encoding used by the producer.

Do not blindly convert every header to a UTF-8 string: headers may hold binary payloads or different encodings. Define the encoding and schema for custom headers standardized within your system.

### Retrieving Trace ID or Event Type

A producer can attach extra metadata:

```java
import org.apache.kafka.common.header.internals.RecordHeader;
import org.apache.kafka.clients.producer.ProducerRecord;
import java.nio.charset.StandardCharsets;

ProducerRecord<String, OrderCreated> record =
        new ProducerRecord<>("orders", orderId, event);

record.headers().add(
        new RecordHeader(
                "trace-id",
                traceId.getBytes(StandardCharsets.UTF_8)
        )
);

record.headers().add(
        new RecordHeader(
                "event-type",
                "OrderCreated".getBytes(StandardCharsets.UTF_8)
        )
);

kafkaTemplate.send(record);
```

Consumer reading it back:

```java
Header traceHeader = record.headers().lastHeader("trace-id");

String traceId = traceHeader == null
        ? null
        : new String(
                traceHeader.value(),
                StandardCharsets.UTF_8
        );
```

For production tracing, prefer standard context propagation already used by your platform (such as OpenTelemetry instrumentation) rather than inventing ad-hoc headers. Never put tokens or sensitive data in headers.

## 8. Reading Metadata in Batch Listeners

Default listeners process one record at a time. When a container factory is configured in batch mode, a listener can receive a list of records. Each record has its own key, topic, partition, and offset:

```java
import java.util.List;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
class OrderBatchListener {

    @KafkaListener(
            topics = "orders",
            groupId = "order-batch-reader",
            containerFactory = "batchFactory"
    )
    public void onOrders(
            List<ConsumerRecord<String, OrderCreated>> records) {

        for (ConsumerRecord<String, OrderCreated> record : records) {
            log.info(
                    "Batch record key={}, topic={}, partition={}, offset={}",
                    record.key(),
                    record.topic(),
                    record.partition(),
                    record.offset()
            );
        }

        orderService.processBatch(
                records.stream()
                        .map(ConsumerRecord::value)
                        .toList()
        );
    }
}
```

A batch listener must use a container factory configured with batch listener mode enabled:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.boot.autoconfigure.kafka.ConcurrentKafkaListenerContainerFactoryConfigurer;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;

@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated> batchFactory(
        ConcurrentKafkaListenerContainerFactoryConfigurer configurer,
        ConsumerFactory<String, OrderCreated> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    configurer.configure(factory, consumerFactory);
    factory.setBatchListener(true);
    return factory;
}
```

When a batch contains records from multiple partitions, do not assume contiguous offsets or that all records share the same partition. Read metadata from each individual record. If a batch listener must handle partial failures, explicitly design tracking of processed records along with matching acknowledgment/retry semantics.

## 9. Deserializers Determine Key and Value Types

The generic types on `ConsumerRecord<K, V>` must match the key deserializer and value deserializer. For instance, with string keys and JSON object values:

```yaml
spring:
  kafka:
    consumer:
      group-id: order-reader
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.value.default.type: com.example.orders.OrderCreated
        spring.json.trusted.packages: com.example.orders
```

With this configuration, the listener can accept `ConsumerRecord<String, OrderCreated>`. If the deserializer does not match actual data, the listener may encounter deserialization errors before the method is even invoked. In that case, you cannot rely on `record.value()` to handle malformed payloads manually; configure proper deserialization error handling instead.

Some applications use `ErrorHandlingDeserializer` to route deserialization errors into Spring Kafka's error-handling pipeline. Deserializer selection must stay consistent between producer and consumer, especially when multiple services write to and read from the same topic.

## 10. Tombstones and Null Values in Compacted Topics

In compacted topics, a record with a key and a null value is commonly used as a tombstone indicating deletion of the key's state. Listeners must distinguish this case from a valid payload:

```java
@KafkaListener(topics = "customer-state", groupId = "customer-projection")
public void onCustomerState(
        ConsumerRecord<String, CustomerState> record) {

    String customerId = record.key();

    if (record.value() == null) {
        customerProjection.delete(customerId);
        return;
    }

    customerProjection.upsert(record.value());
}
```

A tombstone still carries a topic, partition, offset, and key; only the value is null. If code directly calls `record.value().get...()` without checking for null, the listener can throw a `NullPointerException` and endlessly retry the same record.

Null keys also require deliberate handling. For business data requiring entity-based routing, define clearly whether a key is mandatory and reject or route records missing a key per the data contract.

## 11. Using Metadata for Logging, Tracing, and Troubleshooting

A useful log line should contain enough fields to locate the record in Kafka:

```java
log.info(
        "Consumed event: topic={}, partition={}, offset={}, key={}, eventType={}",
        record.topic(),
        record.partition(),
        record.offset(),
        record.key(),
        record.value() == null
                ? "tombstone"
                : record.value().getClass().getSimpleName()
);
```

When locating a record, use the three fields `topic`, `partition`, and `offset` as its coordinates. The key helps identify the business entity; the timestamp places the event on a timeline. Never use offset alone, because an offset is unique only within a single partition.

Avoid logging full payloads or headers if they contain personal data, tokens, or confidential information. Also avoid putting high-cardinality keys into metric labels; logs or traces are usually better suited than metrics for recording specific values.

## 12. Common Pitfalls

| Symptom | Cause | Resolution |
|---|---|---|
| `record.key()` returns null | Producer sent a keyless record or serializer/deserializer behaved unexpectedly | Check whether the event contract requires a key; inspect producer |
| `record.value()` returns null | Tombstone or null-value record | Check key and handle tombstones before accessing payload |
| Duplicate offsets across records | Comparing offsets while ignoring topic/partition | Always compare `topic + partition + offset` |
| Non-contiguous offsets | Compaction, aborted transactions, or control records unseen by consumers | Do not assume adjacent offsets |
| Unexpected partition | Key, partitioner, or partition count changed | Inspect producer key, partitioner, and topic metadata |
| Unreadable header | Header is a byte array, wrong encoding, or missing | Check for null and decode with the right encoding |
| Listener receives wrong payload type | Deserializer or default type mismatch | Check consumer properties and schema |
| Batch spans multiple partitions | Poll returned records across assigned partitions | Read metadata per record; do not assume a single partition |
| Log cannot identify which client read the record | `ConsumerRecord` does not directly expose client ID | Log client ID from config or separate logging context |

## 13. Checklist for Writing @KafkaListener

1. Use `ConsumerRecord<K, V>` when full key, payload, topic, partition, offset, timestamp, and native headers are needed.
2. Use `@Header` when only a few metadata fields are needed.
3. Use `Message<T>` when the application wants payload and Spring message headers in a single abstraction.
4. Match generic types to the key/value deserializers.
5. Handle null keys and null values if allowed by the data contract.
6. Always pair offsets with topic and partition when logging or saving checkpoints.
7. Never assume a batch contains records from only one partition.
8. Read native headers as byte arrays and decode according to convention.
9. Never treat the key as an offset or partition; the key only influences partitioning via the partitioner.
10. Inspect metadata alongside deserialization errors, retries, and rebalances when troubleshooting listeners.

When a listener reads key, topic, partition, and offset accurately, the application can identify events, understand data provenance, and pinpoint exact record coordinates in Kafka. `ConsumerRecord` is the most complete choice for metadata-heavy processing; `@Header` and `Message<?>` keep listeners concise when only partial metadata is needed.
