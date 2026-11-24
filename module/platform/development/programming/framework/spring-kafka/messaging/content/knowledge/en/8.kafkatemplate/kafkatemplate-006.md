# Sending ProducerRecord Directly

`KafkaTemplate` provides several `send(...)` overloads to send data to Kafka. When only topic, key, and value are needed, a short overload is enough. When full control over record metadata such as partition, timestamp, and headers is needed, you can construct a `ProducerRecord<K, V>` and pass it directly to `KafkaTemplate.send(record)`.

In the `SPRING_KAFKA_MESSAGING` module, producers emit events using Spring Kafka and consumers receive events using `@KafkaListener`. `ProducerRecord` is the object describing a message on the producer side: it gathers the required details before serializers convert key/value into bytes and the Kafka producer sends the record to the broker.

## 1. What is `ProducerRecord`?

`ProducerRecord<K, V>` is a type from the Kafka Java client (`org.apache.kafka.clients.producer.ProducerRecord`). It represents a record that the producer is preparing to send. `K` is the Java type of the key and `V` is the Java type of the value prior to serialization.

A record has the following core fields:

| Field | Type/value | Meaning |
|---|---|---|
| `topic` | `String` | Target topic name |
| `partition` | `Integer`, nullable | Explicit partition; `null` lets the partitioner choose |
| `timestamp` | `Long`, nullable | Timestamp in milliseconds since Unix epoch |
| `key` | `K`, nullable | Routing or record-identification key |
| `value` | `V`, nullable | Record payload |
| `headers` | Collection of `Header` | Additional metadata as names and byte values |

The send flow can be visualized as follows:

```mermaid
flowchart LR
    A[Application event] --> B[Create ProducerRecord]
    B --> C[KafkaTemplate.send record]
    C --> D[Key/value serializers]
    D --> E[Kafka producer and partitioner]
    E --> F[(Kafka broker/topic)]
    F --> G[SendResult and RecordMetadata]
```

`ProducerRecord` is not yet data written to Kafka. It is an application-side description of the record. The actual send takes place when calling `KafkaTemplate.send(...)`; the result is typically returned asynchronously.

## 2. Creating `ProducerRecord` via constructors

The Kafka client provides multiple constructors to build a record with minimal or full metadata. Common forms:

```java
new ProducerRecord<>(topic, value);
new ProducerRecord<>(topic, key, value);
new ProducerRecord<>(topic, partition, key, value);
new ProducerRecord<>(topic, partition, timestamp, key, value);
new ProducerRecord<>(topic, partition, timestamp, key, value, headers);
```

The full constructor lets the producer explicitly declare all required metadata. For example:

```java
ProducerRecord<String, OrderCreatedEvent> record =
        new ProducerRecord<>(
                "orders",                       // topic
                null,                            // partition: let the partitioner choose
                event.occurredAt().toEpochMilli(), // timestamp
                event.orderId(),                 // key
                event,                            // value
                headers                           // headers
        );
```

When `partition` is `null`, the producer uses the configured partitioner. When a concrete partition is passed, the record is sent to that partition if it exists. The key is still stored in the record, though it is not used to select the partition when a partition is explicitly specified.

If `timestamp` is `null`, the Kafka producer assigns the send time according to client behavior. If an explicit timestamp is supplied, it is used according to topic/broker timestamp settings. With `CreateTime`, the broker keeps the producer-provided timestamp; with `LogAppendTime`, the broker replaces it with the log-append time.

## 3. Sending directly with `KafkaTemplate.send(record)`

The following example creates an `OrderCreatedEvent`, wraps it in a `ProducerRecord`, and sends it directly:

```java
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.List;
import java.util.concurrent.CompletableFuture;

import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.header.Header;
import org.apache.kafka.common.header.internals.RecordHeader;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Service;

public record OrderCreatedEvent(
        String eventId,
        String orderId,
        BigDecimal total,
        Instant occurredAt
) {}

@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderCreatedEvent>> publish(
            OrderCreatedEvent event) {

        List<Header> headers = List.of(
                new RecordHeader(
                        "event-type",
                        "OrderCreated".getBytes(StandardCharsets.UTF_8)
                ),
                new RecordHeader(
                        "event-id",
                        event.eventId().getBytes(StandardCharsets.UTF_8)
                )
        );

        ProducerRecord<String, OrderCreatedEvent> record =
                new ProducerRecord<>(
                        "orders",
                        null,
                        event.occurredAt().toEpochMilli(),
                        event.orderId(),
                        event,
                        headers
                );

        return kafkaTemplate.send(record);
    }
}
```

In this example:

- `KafkaTemplate<String, OrderCreatedEvent>` specifies the key and value types handled by the template.
- The topic is `orders`.
- Partition is `null`, so the partitioner determines the partition based on the key and producer configuration.
- `orderId` serves as the key so events of the same order can be routed to the same partition under the default partitioner and stable configuration.
- `occurredAt` is used as the timestamp to represent when the business event occurred.
- Headers add the event type and event ID for consumers or observability tools to read.

`ProducerRecord` consolidates metadata into a single object. The publisher method does not have to pass each parameter separately into a `KafkaTemplate` overload and can pass the record through layers of a producer adapter before sending.

## 4. Key, partition, and timestamp in the record

### 4.1. Key and partition

The key usually represents a business entity, such as `orderId` or `accountId`. If no partition is specified, the default partitioner uses the serialized key to select a partition. Records with the same key typically go to the same partition as long as partition count, serializer, and partitioner stay unchanged.

If you need to specify a partition explicitly, pass the partition index to the constructor:

```java
ProducerRecord<String, OrderCreatedEvent> record =
        new ProducerRecord<>(
                "orders",
                2,
                event.orderId(),
                event
        );
```

Partition indices start at `0`. The topic must have partition `2`; the producer does not automatically expand a topic if the partition does not exist. Kafka guarantees order within each partition, not across partitions. If events of an order must be processed in sequence, maintain consistent routing for every event of that order.

### 4.2. Timestamp

Record timestamps are measured in milliseconds from the Unix epoch. Applications can pass the event occurrence time (`event time`) or let the producer assign the send timestamp. The broker may keep the producer timestamp or overwrite it with the log-append time depending on `message.timestamp.type`.

If business logic requires both event time and ingestion time, keep a field such as `occurredAt` in the payload or a header, and clarify which milestone the Kafka timestamp represents. Do not use timestamps for global ordering; offsets define record order within a partition.

## 5. Headers: additional metadata for the record

Kafka headers are name and byte-array pairs. They are suitable for transport or observability metadata, for example:

- `event-type`: event classification, such as `OrderCreated`.
- `event-id`: unique identifier of the event.
- `correlation-id`: links steps within the same request or workflow.
- `traceparent`: trace context following the tracing convention in use.

Example creating a header:

```java
Header correlationHeader = new RecordHeader(
        "correlation-id",
        correlationId.getBytes(StandardCharsets.UTF_8)
);
```

Header values are byte arrays, so producer and consumer must agree on encoding. For strings, UTF-8 is the common choice. Do not put large payloads or core business data into headers; the value should hold the event content. Nor should you place secrets into headers, as headers may be logged or inspected by operational tools.

Kafka allows multiple headers with the same name. Consumers need an appropriate reading strategy, such as `lastHeader("correlation-id")` if the contract specifies using the last value. Do not assume a header name always appears once if producers or interceptors might append duplicate headers.

## 6. Serialization and generic types of `KafkaTemplate`

`ProducerRecord<K, V>` holds the key/value as Java types. Before sending, the Kafka producer uses matching serializers to convert them into bytes. Therefore, the generic types of `KafkaTemplate` must align with the configured serializers.

Example configuration for string keys and JSON values in Spring Boot:

```yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
```

In the configuration above, `String` keys are serialized with `StringSerializer`; `OrderCreatedEvent` objects are serialized to JSON with `JsonSerializer`. Consumers need a compatible deserializer and target type matching the event schema.

Declaring `KafkaTemplate<String, OrderCreatedEvent>` does not magically teach Kafka JSON. Generic types help the compiler and Spring wiring enforce types in Java; serializers decide the byte representation on the wire. If a serializer is incompatible with the actual object, the send future may complete with a serialization error.

When multiple independent services exchange events, manage schemas and compatibility policies. Do not rely on Java class names or internal producer packages as the sole integration contract.

## 7. Receiving send results and reading metadata

In Spring Kafka 3.x, `KafkaTemplate.send(record)` returns `CompletableFuture<SendResult<K, V>>`. The future completes when the producer receives a success or failure result. `SendResult` contains the `RecordMetadata` returned by Kafka.

```java
import java.util.concurrent.CompletableFuture;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Service;

@Service
public class AuditedEventPublisher {

    private static final Logger log =
            LoggerFactory.getLogger(AuditedEventPublisher.class);

    private final KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate;

    public AuditedEventPublisher(
            KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderCreatedEvent>> publish(
            ProducerRecord<String, OrderCreatedEvent> record) {

        return kafkaTemplate.send(record).whenComplete((result, exception) -> {
            if (exception != null) {
                log.error("Kafka send failed for event {}", record.key(), exception);
                return;
            }

            var metadata = result.getRecordMetadata();
            log.info(
                    "Sent topic={} partition={} offset={} timestamp={}",
                    metadata.topic(),
                    metadata.partition(),
                    metadata.offset(),
                    metadata.timestamp()
            );
        });
    }
}
```

Commonly used metadata fields:

| Field | Meaning |
|---|---|
| `topic()` | Topic where the broker wrote the record |
| `partition()` | Actual partition |
| `offset()` | Offset assigned in the partition |
| `timestamp()` | Timestamp recorded by the broker |
| `serializedKeySize()` | Key size after serialization |
| `serializedValueSize()` | Value size after serialization |

Do not ignore the future if business logic needs to know whether sending succeeded or failed. You can return the future to the caller, use `whenComplete` to record logs/metrics, or transform the outcome into an application-layer result type. Avoid blocking threads with `get()` or `join()` on request threads without a clear reason.

In older Spring Kafka versions, the send API may return `ListenableFuture` instead of `CompletableFuture`. Check your project's dependency version before copying examples.

## 8. When should you use `ProducerRecord` directly?

| Need | Appropriate approach |
|---|---|
| Only topic, key, and value | `kafkaTemplate.send(topic, key, value)` |
| Need to specify partition | `kafkaTemplate.send(topic, partition, key, value)` or `ProducerRecord` |
| Need custom timestamp | Build a `ProducerRecord` |
| Need multiple headers | Build a `ProducerRecord` |
| Want to package metadata into one object passed across layers | Build a `ProducerRecord` |
| Sending multiple event types via templates with matching generics/serializers | Create typed records and send via the appropriate template |

`ProducerRecord` is helpful when a record carries substantial metadata or when a producer adapter constructs the record in one step and sends it in another. For simple cases, the shorter `KafkaTemplate` overloads are usually easier to read.

## 9. Common mistakes

- **Generic types not matching serializers:** `KafkaTemplate<String, OrderCreatedEvent>` while the value serializer only supports another type. Check the producer factory and serializers.
- **Thinking `ProducerRecord` sends data by itself:** you must call `kafkaTemplate.send(record)` to initiate sending.
- **Confusing partition `null` with partition `0`:** `null` lets the partitioner choose; `0` explicitly targets the first partition.
- **Passing timestamps in the wrong unit:** Kafka uses milliseconds since the Unix epoch, not seconds or `Instant` directly.
- **Using event time without aligning timestamp type:** the broker may overwrite the timestamp when `LogAppendTime` is configured.
- **Headers using mismatched encodings:** producer and consumer must agree on UTF-8 or the designated encoding.
- **Putting large payloads or sensitive data in headers:** headers should hold small, non-secret metadata.
- **Ignoring asynchronous failures:** sending can fail after the publisher method returns; observe the future/callback.
- **Assuming key determines partition when partition is explicitly set:** the explicit partition takes precedence, leaving the key purely as record data.
- **Neglecting schema evolution:** producers and consumers may run different versions; contracts need compatibility policies.

## 10. Checklist before sending `ProducerRecord`

- [ ] The topic already exists and the producer has write permissions.
- [ ] Generic types of `ProducerRecord` match `KafkaTemplate<K, V>`.
- [ ] Key/value serializers are compatible with actual Java types.
- [ ] Partition is `null` for partitioner selection or a verified valid index.
- [ ] Timestamp is in milliseconds and matches event-time/ingestion-time semantics.
- [ ] Headers follow consistent naming, encoding, and reading conventions.
- [ ] Payloads are not stuffed into headers, nor is sensitive data included.
- [ ] The send future is observed and errors are handled per application policy.
- [ ] Actual metadata such as topic, partition, and offset are logged when tracing is needed.
- [ ] Event schemas have compatibility conventions between producers and consumers.

Sending `ProducerRecord` directly gives producers full control over per-record metadata and keeps sending uniform within a Spring Kafka adapter. When combined with matching serializers, routing, timestamps, headers, and asynchronous result handling, `KafkaTemplate` can emit clear, traceable events aligned with the application's messaging contract.
