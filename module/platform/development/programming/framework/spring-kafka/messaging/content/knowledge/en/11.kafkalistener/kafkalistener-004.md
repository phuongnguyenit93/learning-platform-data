# Reading ConsumerRecord in Listeners

When a `@KafkaListener` method accepts only a `String` or a DTO parameter, the application typically sees only the message value. In many situations, the listener also needs to know which topic and partition the record came from, what its offset is, what the key is, when it was created, and which headers it carries. Spring Kafka allows receiving `ConsumerRecord<K, V>` directly to access all of that information.

`ConsumerRecord` is an Apache Kafka client type. Spring Kafka passes the record fetched by the consumer into the listener method; the key and value have already passed through the configured deserializers. Thus, `ConsumerRecord` lets business code combine the payload with Kafka metadata without manually creating a consumer or calling `poll()`.

## 1. What Is ConsumerRecord?

`ConsumerRecord<K, V>` represents a single record read by a consumer from Kafka. The two generic parameters represent the key type (`K`) and value type (`V`) after deserialization.

Example:

```java
ConsumerRecord<String, String> record;
```

In this example, both the key and value seen by the listener are `String`. If the consumer uses a JSON deserializer to turn the value into `OrderCreatedEvent`, the type can be:

```java
ConsumerRecord<String, OrderCreatedEvent> record;
```

Key pieces of information in a record:

| Member | Meaning |
| --- | --- |
| `topic()` | Name of the topic containing the record |
| `partition()` | Partition number containing the record |
| `offset()` | Position of the record within that partition |
| `key()` | Deserialized key |
| `value()` | Deserialized value |
| `timestamp()` | Timestamp attached to the record |
| `timestampType()` | Timestamp type, e.g., producer creation time or broker append time |
| `headers()` | Collection of record headers |
| `serializedKeySize()` | Size of the serialized key in bytes |
| `serializedValueSize()` | Size of the serialized value in bytes |

An offset is meaningful only within a single partition. For example, `(orders.created, partition 1, offset 25)` pinpoints the record in partition 1 of topic `orders.created`; offset 25 in another partition is a different position.

## 2. Receiving ConsumerRecord with @KafkaListener

Declare a `ConsumerRecord<K, V>` parameter in the listener method:

```java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderCreatedListener {

    @KafkaListener(
            topics = "orders.created",
            groupId = "order-projection")
    public void onMessage(ConsumerRecord<String, String> record) {
        String key = record.key();
        String payload = record.value();

        System.out.printf(
                "topic=%s partition=%d offset=%d key=%s payload=%s%n",
                record.topic(),
                record.partition(),
                record.offset(),
                key,
                payload);

        // Convert payload into business data and process.
    }
}
```

Spring Kafka's listener container still manages the consumer and poll loop. When a record arrives, the container invokes `onMessage` and passes the `ConsumerRecord` object. The application does not need to call `KafkaConsumer.poll()` manually.

If the method only declares a `String payload` parameter, Spring Kafka can pass the value into that parameter. Use `ConsumerRecord` when you also need the key, offset, partition, timestamp, or headers.

## 3. Reading topic, partition, and offset

These three properties are commonly used to trace a record:

```java
String topic = record.topic();
int partition = record.partition();
long offset = record.offset();

log.info("Received Kafka record: topic={}, partition={}, offset={}",
        topic, partition, offset);
```

When investigating failures, the `(topic, partition, offset)` triplet pinpoints the record for cross-referencing broker logs or re-reading via Kafka CLI. Example:

```text
topic=orders.created
partition=2
offset=184
```

The offset is the record's position in the partition log, not a global sequence number and not the consumer group's committed offset. A consumer group tracks commit progress separately per partition. Receiving offset 184 does not by itself prove the group has committed past that record.

Do not increment offsets manually inside a listener to infer how many records were processed. Log compaction, transaction markers, and other conditions can cause visible offsets to be non-contiguous. To measure group progress, inspect committed offsets and log end offsets using administrative tooling or consumer lag metrics.

## 4. Reading key and value

`key()` and `value()` return the generic types declared on `ConsumerRecord`:

```java
String orderId = record.key();
String eventJson = record.value();
```

Keys are typically used to identify the business entity and preserve partition affinity. For example, events sharing the same `orderId` are normally routed by the producer to the same partition when using the same key serializer, partitioner, and partition count.

The value is the payload converted into a Java type by the deserializer. With JSON, consumer configuration can use `JsonDeserializer` to convert bytes into a DTO:

```yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        "[spring.json.value.default.type]": com.example.messaging.OrderCreatedEvent
        "[spring.json.trusted.packages]": com.example.messaging
```

The listener can then accept the concrete type:

```java
@KafkaListener(topics = "orders.created", groupId = "order-projection")
public void onMessage(
        ConsumerRecord<String, OrderCreatedEvent> record) {
    String orderId = record.key();
    OrderCreatedEvent event = record.value();

    // Process deserialized event.
}
```

Class names in the configuration are illustrative and must be replaced with actual classes from your application. Trust only packages containing event DTOs controlled by your application; do not open trusted packages wider than needed.

If deserialization fails, the listener may not be invoked at all because the error happens before a valid Java value can be constructed. For applications that need to route deserialization errors to an error handler or dead-letter topic, configure `ErrorHandlingDeserializer` and a corresponding handling strategy.

## 5. Reading timestamp and timestamp type

`timestamp()` returns the record's timestamp from Kafka metadata. Its meaning depends on the topic/broker `message.timestamp.type` setting:

- `CreateTime`: typically the timestamp attached by the producer when creating the record.
- `LogAppendTime`: timestamp attached by the broker when appending the record to the log.
- `NO_TIMESTAMP_TYPE`: no valid timestamp is present in metadata.

Reading both value and timestamp type:

```java
long timestamp = record.timestamp();
var timestampType = record.timestampType();

log.info("Record timestamp={}, type={}", timestamp, timestampType);
```

Timestamps are typically represented in epoch milliseconds. Do not assume the timestamp always represents the business occurrence time: producers may supply custom timestamps, clocks may drift, or brokers may use `LogAppendTime`. When exact business timing matters, store `occurredAt` inside the event payload with a clear timezone convention.

## 6. Reading headers

A Kafka record can carry multiple headers. Each header consists of a name and a byte-array value. Headers are commonly used for metadata such as event type, correlation ID, trace ID, or source service.

Reading a single header:

```java
import java.nio.charset.StandardCharsets;

var header = record.headers().lastHeader("correlation-id");
String correlationId = header == null || header.value() == null
        ? null
        : new String(header.value(), StandardCharsets.UTF_8);
```

The same header name can appear multiple times. `lastHeader(name)` returns the last header with that name; if all values are needed, iterate over the collection:

```java
import org.apache.kafka.common.header.Header;

for (Header header : record.headers().headers("trace-tag")) {
    byte[] bytes = header.value();
    String value = bytes == null
            ? null
            : new String(bytes, StandardCharsets.UTF_8);
    log.debug("trace-tag={}", value);
}
```

Convert headers to UTF-8 only when producer and consumer agree on that encoding. Some headers may contain binary data or custom formats; do not blindly coerce every header into a string.

Example producer creating a header:

```java
import java.nio.charset.StandardCharsets;

import org.apache.kafka.clients.producer.ProducerRecord;

ProducerRecord<String, String> outgoing = new ProducerRecord<>(
        "orders.created", orderId, eventJson);

outgoing.headers().add(
        "correlation-id",
        correlationId.getBytes(StandardCharsets.UTF_8));

kafkaTemplate.send(outgoing);
```

Consumers can extract the correlation ID from headers to correlate logs across services. Never put passwords, access tokens, or secrets into Kafka headers.

## 7. Reading serialized key and value sizes

`serializedKeySize()` and `serializedValueSize()` return the serialized sizes of key and value in bytes:

```java
int keySize = record.serializedKeySize();
int valueSize = record.serializedValueSize();

log.debug("Record sizes: key={} bytes, value={} bytes",
        keySize, valueSize);
```

If the key or value is `null`, the corresponding size may be `-1`. This is metadata about serialized size, not the Java object's heap footprint. You can use these fields to spot large payloads, but do not treat them as the total wire size of the record since headers and record batch/protocol overhead are excluded.

## 8. ConsumerRecord vs. Spring Message

Spring Kafka supports both reception styles:

1. Accept `ConsumerRecord<K, V>` when direct access to Kafka's metadata API is required.
2. Accept Spring `Message<?>` and read metadata through Spring Kafka headers.

Example receiving Spring `Message`:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.stereotype.Component;

@Component
public class OrderMessageListener {

    @KafkaListener(topics = "orders.created", groupId = "order-message-view")
    public void onMessage(
            Message<String> message,
            @Header(KafkaHeaders.RECEIVED_PARTITION) int partition) {
        String payload = message.getPayload();
        Object offset = message.getHeaders().get(KafkaHeaders.OFFSET);

        log.info("Received partition={}, offset={}, payloadSize={}",
                partition, offset, payload.length());
    }
}
```

`ConsumerRecord` fits best when APIs like `headers()`, `timestampType()`, or serialized sizes are needed. Spring `Message` fits when the application already uses Spring's message abstraction and wants the payload alongside mapped headers. Choose the parameter type based on the information the listener genuinely needs.

## 9. Using Metadata for Tracing and Business Processing

Metadata supports a variety of use cases:

| Need | Commonly used field |
| --- | --- |
| Identify where the record came from | `topic()`, `partition()`, `offset()` |
| Correlate logs across services | `correlation-id` or `trace-id` header |
| Identify event type | Event type header or payload field |
| Inspect routing key | `key()` |
| Analyze ingestion latency | `timestamp()` and `timestampType()` |
| Detect oversized payloads | `serializedKeySize()`, `serializedValueSize()` |

Example of selective metadata logging:

```java
log.info(
        "Kafka event received: topic={}, partition={}, offset={}, key={}, timestampType={}",
        record.topic(),
        record.partition(),
        record.offset(),
        record.key(),
        record.timestampType());
```

Avoid logging full values or all headers by default. Payloads may contain personal data, order details, or internal data. Log permitted identifiers, correlation IDs, and record coordinates; mask or omit sensitive fields.

## 10. ConsumerRecord Does Not Control Offset Commits

`record.offset()` only reports the record's position within the partition. It does not commit the offset, nor does it confirm that business processing succeeded.

Spring Kafka's listener container manages commits according to `AckMode` and acknowledgment configuration. If the listener finishes processing but the application stops before the offset is committed, the record may be redelivered. If commits happen too early, the application may skip records that have not finished processing. Therefore:

- Do not treat `record.offset()` as the committed offset.
- Do not increment offsets manually to track group progress.
- Rely on the container's acknowledgment and error handler according to your configured policy.
- Make business processing idempotent whenever redelivery is possible.

If manual commits are required, use Spring Kafka's `Acknowledgment` and `AckMode`; never assume a commit occurred simply because a `ConsumerRecord` was read.

## 11. Batch Listeners Receiving a List of ConsumerRecord

When a listener is configured in batch mode, a single invocation can receive a list of `ConsumerRecord` instances:

```java
import java.util.List;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderBatchListener {

    @KafkaListener(
            topics = "orders.created",
            groupId = "order-batch-view",
            containerFactory = "batchKafkaListenerContainerFactory")
    public void onMessages(List<ConsumerRecord<String, String>> records) {
        for (ConsumerRecord<String, String> record : records) {
            log.info("topic={}, partition={}, offset={}",
                    record.topic(), record.partition(), record.offset());
            // Process each record or aggregate into a business batch.
        }
    }
}
```

`batchKafkaListenerContainerFactory` must be configured with `setBatchListener(true)`. You cannot simply change the method parameter from a single `ConsumerRecord` to `List<ConsumerRecord>` without configuring the listener container accordingly.

## 12. Common Pitfalls

| Pitfall | Consequence | Resolution |
| --- | --- | --- |
| Confusing record offset with committed offset | Misjudging consumer group progress | Use consumer group tooling/metrics to read committed offsets |
| Assuming `ConsumerRecord` value is always `byte[]` | Incorrect casting or double deserialization | Use the generic type produced by the deserializer |
| Skipping null checks on key/value | `NullPointerException` or business bugs | Check for null, especially for tombstones or keyless records |
| Assuming a header only has one value | Ignoring duplicate-named metadata | Use `headers(name)` when all values are needed |
| Treating timestamp as business event time | Wrong latency or business ordering calculations | Inspect `timestampType()` and use `occurredAt` in payload if needed |
| Logging entire payloads and headers | Sensitive data exposure and log bloat | Log only needed metadata and mask sensitive data |
| Assuming listener is called even on deserialization errors | Errors occur before a listener object exists | Configure `ErrorHandlingDeserializer` and an error handler |

## 13. Conclusion

`ConsumerRecord<K, V>` lets `@KafkaListener` access both the deserialized key/value and Kafka metadata such as topic, partition, offset, timestamp, headers, and serialized sizes. It is the right choice when a listener needs record traceability, key-based processing, correlation ID extraction, or data provenance inspection.

Keep record offsets distinct from consumer group committed offsets, interpret timestamps according to the Kafka timestamp type, decode headers using the agreed encoding, and check for nulls before using payloads. When only the payload is needed, a DTO or `Message<?>` parameter may be cleaner; when full record details are required, `ConsumerRecord` provides a direct and explicit interface.

## References

- [Apache Kafka — ConsumerRecord API](https://kafka.apache.org/documentation/#consumerapi)
- [Spring for Apache Kafka — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/annotation-driven.html)
- [Spring for Apache Kafka — Message Listener Containers](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html)
