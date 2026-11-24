# Reading headers in a listener

A Kafka record does not only have a key and a value. Each record can also carry headers to pass auxiliary information such as trace ID, correlation ID, tenant ID, schema version, or origin source. Spring Kafka provides multiple ways to read these values in `@KafkaListener`: using `@Header`, `@Headers`, `Message<?>`, or directly accessing `ConsumerRecord.headers()`.

Choosing the right reading approach helps the listener receive the expected data type, avoid errors when a header is absent, and preserve the metadata needed for tracing. You must distinguish **Kafka record headers sent by the producer** from **metadata headers created by Spring Kafka upon receiving a record**.

## 1. Where do headers reside in a Kafka record?

A Kafka record has the following main components:

- **Key**: used to route the record to a partition and support entity-ordered processing.
- **Value**: payload containing business data.
- **Headers**: a collection of name and byte array pairs to carry additional metadata.
- **Record metadata**: topic, partition, offset, and timestamp managed by Kafka.

A Kafka header has a simple API:

```java
public interface Header {
    String key();
    byte[] value();
}
```

The header name is a String, while the value on the wire is always `byte[]`. Kafka does not inherently understand whether a header is a String, Integer, UUID, or JSON. Producer and consumer must agree on how to encode and decode it.

For example, a record can carry:

| Component | Example value |
|---|---|
| Key | `order-42` |
| Value | JSON of `OrderCreated` |
| `trace-id` | `trace-9f31` UTF-8 encoded |
| `tenant-id` | `tenant-7` UTF-8 encoded |
| `schema-version` | `2` encoded as bytes |

Headers do not replace the payload. You should not put all business data into headers; keep headers small, stable, and dedicated to necessary metadata.

## 2. Distinguishing custom headers and KafkaHeaders

There are two common groups of headers in a listener:

1. **Custom headers** are headers sent by the application or producer, such as `trace-id`, `tenant-id`, `event-version`.
2. **KafkaHeaders** are headers created by Spring Kafka to represent information about the received record, such as topic, key, partition, offset, and timestamp.

Common constants in Spring Kafka 3.x:

| Constant | Meaning |
|---|---|
| `KafkaHeaders.RECEIVED_TOPIC` | Topic that received the record |
| `KafkaHeaders.RECEIVED_KEY` | Key of the received record |
| `KafkaHeaders.RECEIVED_PARTITION` | Partition containing the record |
| `KafkaHeaders.OFFSET` | Offset of the record |
| `KafkaHeaders.RECEIVED_TIMESTAMP` | Timestamp of the record |
| `KafkaHeaders.TIMESTAMP_TYPE` | Timestamp type provided by Kafka |
| `KafkaHeaders.NATIVE_HEADERS` | Original Kafka `Headers` when there is no header mapper |
| `KafkaHeaders.BATCH_CONVERTED_HEADERS` | List of converted headers in a batch listener |

Use `KafkaHeaders` constants instead of writing internal strings like `kafka_receivedTopic` manually. Constants make code intent clear and reduce typos.

`RECEIVED_KEY` may not exist when the record has a null key. Since Spring Kafka 2.5, the framework does not put this header into `MessageHeaders` if the record's key is null. Therefore, the parameter receiving the key should be declared as optional.

## 3. Reading metadata with @Header

For payload-style listeners, metadata can be retrieved using the `@Header` annotation:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;

@KafkaListener(
    topics = "order-events",
    groupId = "billing-service"
)
public void handle(
        @Payload OrderCreated event,
        @Header(value = KafkaHeaders.RECEIVED_KEY, required = false) String orderKey,
        @Header(KafkaHeaders.RECEIVED_TOPIC) String topic,
        @Header(KafkaHeaders.RECEIVED_PARTITION) int partition,
        @Header(KafkaHeaders.OFFSET) long offset,
        @Header(KafkaHeaders.RECEIVED_TIMESTAMP) long timestamp) {

    // Process the event and use metadata for tracing.
}
```

Spring Kafka maps `ConsumerRecord` metadata into message headers so the method argument resolver can bind them to parameters.

Some notes:

- `@Payload` marks the parameter containing the deserialized/converted value.
- `@Header` retrieves a header by name.
- The parameter type must be compatible with the header value after mapping.
- `partition` and `offset` are Kafka metadata, not custom headers set by the producer.
- If you do not need the timestamp, you do not have to declare that parameter.

You can receive the timestamp type if you need to distinguish producer-created timestamps from broker-appended timestamps:

```java
import org.apache.kafka.common.record.TimestampType;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;

@KafkaListener(topics = "order-events")
public void handle(
        @Payload OrderCreated event,
        @Header(KafkaHeaders.TIMESTAMP_TYPE) TimestampType timestampType) {

    // CREATE_TIME or LOG_APPEND_TIME depending on topic/broker configuration.
}
```

`TimestampType` is a Kafka enum. Check the actual parameter type instead of defaulting to converting every header to a String.

## 4. Handling optional headers

Not every record has all headers present. For instance, a producer might omit the key or a legacy system might not send `trace-id`.

If a header may be absent, use `required = false`:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;

@KafkaListener(topics = "order-events")
public void handle(
        @Payload OrderCreated event,
        @Header(
            value = KafkaHeaders.RECEIVED_KEY,
            required = false
        ) String orderKey,
        @Header(
            value = "trace-id",
            required = false
        ) byte[] traceIdBytes) {

    if (traceIdBytes == null || traceIdBytes.length == 0) {
        // Create an internal correlation context if policy allows.
    }

    // Process the event.
}
```

You can use `defaultValue` when a default value is genuinely valid:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;

@KafkaListener(topics = "order-events")
public void handle(
        @Payload OrderCreated event,
        @Header(
            value = "source-system",
            defaultValue = "legacy"
        ) String sourceSystem) {

    // Process according to sourceSystem.
}
```

When `defaultValue` is declared, Spring treats the header as optional. Only use a default value if it carries business meaning. Do not use a dummy default string like `unknown` for a security- or tenant-required header, because that can allow invalid-data records to be processed as valid.

For critical headers, validate them at the very start of the listener or in the request conversion layer.

## 5. How does a producer send custom headers?

A Kafka producer can add headers to a `ProducerRecord` before sending:

```java
import java.nio.charset.StandardCharsets;

import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.header.internals.RecordHeader;

ProducerRecord<String, String> record =
    new ProducerRecord<>(
        "order-events",
        "order-42",
        "{\"orderId\":\"order-42\"}"
    );

record.headers().add(
    new RecordHeader(
        "trace-id",
        "trace-9f31".getBytes(StandardCharsets.UTF_8)
    )
);

record.headers().add(
    new RecordHeader(
        "tenant-id",
        "tenant-7".getBytes(StandardCharsets.UTF_8)
    )
);

kafkaTemplate.send(record);
```

The producer creates a `RecordHeader` with a byte array value. The consumer must know that `trace-id` and `tenant-id` use UTF-8 to decode them properly.

If using Spring `Message<?>` to send via `KafkaTemplate`, Spring Messaging headers can be converted into Kafka headers by `KafkaHeaderMapper`. How mapping works depends on the configured mapper; section 9 explains this in detail.

## 6. Reading custom headers with @Header

If a header has been converted to an appropriate Java type by the Spring Kafka header mapper, it can be received directly with `@Header`:

```java
import java.nio.charset.StandardCharsets;

import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;

@KafkaListener(topics = "order-events")
public void handle(
        @Payload OrderCreated event,
        @Header(value = "trace-id", required = false) byte[] traceIdBytes) {

    String traceId = traceIdBytes == null
        ? null
        : new String(traceIdBytes, StandardCharsets.UTF_8);

    // Attach traceId to logs or tracing context.
}
```

The example above receives a byte array to clearly illustrate the case where headers arrive from a plain Kafka producer without Spring type metadata. If the application configures a mapper to convert raw headers to String, the parameter can be declared as `String`.

Do not cast blindly:

```java
String traceId = (String) message.getHeaders().get("trace-id");
```

The header could currently be `byte[]`, `String`, `Integer`, or another type depending on the mapper and producer. Define the wire format and configure mappers consistently across services.

## 7. Reading all headers with @Headers

When a listener needs multiple custom headers or flexible metadata handling, use `@Headers` to receive a map:

```java
import java.util.Map;

import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.messaging.handler.annotation.Headers;
import org.springframework.messaging.handler.annotation.Payload;

@KafkaListener(topics = "order-events")
public void handle(
        @Payload OrderCreated event,
        @Headers Map<String, Object> headers) {

    Object traceId = headers.get("trace-id");
    Object tenantId = headers.get("tenant-id");
    Object source = headers.get("source-system");

    // Check types and values before using.
}
```

The map contains headers converted by the Spring header mapper. It is useful when the number of custom headers varies by event type or when passing metadata down to a processing layer.

Do not assume every key in the map exists. Use `containsKey`, check for null, and check the type before casting.

If only one or two fixed headers are needed, `@Header` is usually easier to read. If you need to access many headers, `@Headers` helps reduce the number of method parameters.

## 8. Reading headers via Message<?> and MessageHeaders

A listener can also receive a Spring `Message<T>`. Both payload and metadata reside in the same object:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;

@KafkaListener(topics = "order-events")
public void handle(Message<OrderCreated> message) {
    OrderCreated event = message.getPayload();

    MessageHeaders headers = message.getHeaders();

    String topic = headers.get(
        KafkaHeaders.RECEIVED_TOPIC,
        String.class
    );

    Integer partition = headers.get(
        KafkaHeaders.RECEIVED_PARTITION,
        Integer.class
    );

    Long offset = headers.get(
        KafkaHeaders.OFFSET,
        Long.class
    );

    Object traceId = headers.get("trace-id");

    // Pass the event and needed metadata to the business layer.
}
```

This approach is useful when you need to pass both payload and metadata through an adapter layer or a Spring Messaging pipeline. `MessageHeaders` is Spring's header structure, not the native Kafka `Headers`.

`MessageHeaders` is designed to be immutable. Do not modify the header map directly; if you need to create a new message with added or modified headers, use `MessageBuilder`.

## 9. How does KafkaHeaderMapper convert headers?

Kafka native headers only store `byte[]`, whereas Spring `MessageHeaders` can hold many Java types. `KafkaHeaderMapper` is the bridge between these two structures.

Two common mappers in Spring Kafka 3.x:

| Mapper | Behavior |
|---|---|
| `DefaultKafkaHeaderMapper` | Converts rich headers using JSON and stores type metadata to restore Java types |
| `SimpleKafkaHeaderMapper` | Maps raw headers as `byte[]`, with an option to convert selected headers to String |

With `DefaultKafkaHeaderMapper`, Spring uses a special header `spring_json_header_types` to store type information for serialized headers. When a consumer reads a record sent by a compatible Spring application, the mapper can restore the original Java type.

With non-Spring producers or producers that only add `RecordHeader` as byte arrays, headers may be received as byte arrays because Spring type metadata is absent. That is why header formats should be agreed upon at the inter-service communication level.

In Spring Kafka 3.x, `DefaultKafkaHeaderMapper` is typically used by default in `MessagingMessageConverter` and `BatchMessagingMessageConverter` when Jackson is on the classpath. In Spring Kafka 4.x, the JSON mapper API is renamed to `JsonKafkaHeaderMapper`; choose the right class for the version in use.

### Explicit mapper configuration

You can configure a mapper to only send allowed headers:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.support.DefaultKafkaHeaderMapper;
import org.springframework.kafka.support.KafkaHeaderMapper;
import org.springframework.kafka.support.converter.MessagingMessageConverter;
import org.springframework.kafka.support.converter.RecordMessageConverter;

@Configuration
public class KafkaHeaderConfiguration {

    @Bean
    KafkaHeaderMapper kafkaHeaderMapper() {
        return new DefaultKafkaHeaderMapper(
            "!id",
            "!timestamp",
            "trace-*",
            "tenant-id",
            "source-system"
        );
    }

    @Bean
    RecordMessageConverter kafkaRecordMessageConverter(
            KafkaHeaderMapper kafkaHeaderMapper) {
        MessagingMessageConverter converter = new MessagingMessageConverter();
        converter.setHeaderMapper(kafkaHeaderMapper);
        return converter;
    }
}
```

Patterns are evaluated in order; the first matching pattern decides whether a header is mapped. When configuring patterns manually, exclude Spring Messaging's `id` and `timestamp` because these are internal headers, not business metadata to send to Kafka. The mapper bean must be attached to `MessagingMessageConverter`; this converter must then be used by the listener container factory. For record listeners, call `factory.setRecordMessageConverter(kafkaRecordMessageConverter)`. For batch listeners, wrap it with `new BatchMessagingMessageConverter(kafkaRecordMessageConverter)` and pass it to `factory.setBatchMessageConverter(...)`. Merely declaring a mapper bean without attaching it to the converter will not change the mapping flow.

`DefaultKafkaHeaderMapper` only deserializes types belonging to trusted packages. If you need to restore custom header types, add the exact packages using `addTrustedPackages(...)`. Avoid trusting all packages with `*` when receiving records from uncontrolled sources.

If using Spring Kafka 4.x, replace `DefaultKafkaHeaderMapper` with `JsonKafkaHeaderMapper` accordingly.

Do not indiscriminately enable mapping for all headers if messages might contain tokens, personal information, or internal metadata. Only map headers that need to cross Kafka.

## 10. Reading native Kafka Headers via ConsumerRecord

When you need exact access to original Kafka headers, receive `ConsumerRecord<K,V>` in the listener:

```java
import java.nio.charset.StandardCharsets;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.header.Header;
import org.springframework.kafka.annotation.KafkaListener;

@KafkaListener(topics = "order-events")
public void handle(ConsumerRecord<String, OrderCreated> record) {
    Header traceHeader = record.headers().lastHeader("trace-id");

    String traceId = traceHeader == null || traceHeader.value() == null
        ? null
        : new String(traceHeader.value(), StandardCharsets.UTF_8);

    String topic = record.topic();
    int partition = record.partition();
    long offset = record.offset();

    OrderCreated event = record.value();

    // Use raw headers and record metadata.
}
```

`ConsumerRecord.headers()` returns the native Kafka `Headers`. This approach is suitable when:

- You need to read the exact byte array sent by the producer.
- You need to handle headers produced by non-Spring systems.
- You need to handle multiple headers with the same name.
- You need to access native metadata without depending on `KafkaHeaderMapper`.

If a listener only needs the payload and a few metadata fields, `@Header` is usually more concise. `ConsumerRecord` is useful when full control over the record is required.

## 11. Duplicate header names and multiple values

Kafka allows a record to have multiple headers with the same name. For example, a producer can send two `route-tag` values:

```java
record.headers()
    .add(new RecordHeader("route-tag", "blue".getBytes(StandardCharsets.UTF_8)))
    .add(new RecordHeader("route-tag", "priority".getBytes(StandardCharsets.UTF_8)));
```

When reading native Kafka Headers:

```java
Iterable<Header> routeHeaders =
    record.headers().headers("route-tag");

for (Header header : routeHeaders) {
    String value = new String(
        header.value(),
        StandardCharsets.UTF_8
    );
}
```

`lastHeader("route-tag")` only returns the last header with that name. Use `headers("route-tag")` if you need to read all values.

Mapping multiple headers with the same name into Spring `MessageHeaders` depends on the version and mapper configuration. Multi-value mapping support was added in Spring Kafka 4.0 via multi-value patterns of the JSON header mapper. In earlier versions, do not assume `@Header` or `Map<String,Object>` will preserve all duplicate headers; use `ConsumerRecord.headers()` when each occurrence must be preserved.

## 12. When there is no header mapper: NATIVE_HEADERS

If there is no header mapper, Spring Kafka can place the native Kafka `Headers` into `KafkaHeaders.NATIVE_HEADERS` instead of converting each header into Spring `MessageHeaders`.

Example:

```java
import org.apache.kafka.common.header.Headers;
import org.apache.kafka.common.header.Header;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;

@KafkaListener(topics = "order-events")
public void handle(
        @Payload OrderCreated event,
        @Header(KafkaHeaders.NATIVE_HEADERS) Headers nativeHeaders) {

    Header traceHeader = nativeHeaders.lastHeader("trace-id");

    // Decode byte[] according to the application's wire format.
}
```

`NATIVE_HEADERS` is an option when you need all unmapped Kafka headers. In a batch listener, the native headers structure can be a list of `Headers`, corresponding to each payload's position in the batch.

If a mapper is active, prefer `@Header`, `@Headers`, or `MessageHeaders` with the mapped data types. Do not assume `NATIVE_HEADERS` is always present in every configuration.

## 13. ConsumerRecordMetadata when only metadata is needed

If a method needs topic, partition, offset, and timestamp without needing key, value, or raw headers, Spring Kafka provides `ConsumerRecordMetadata`:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.listener.adapter.ConsumerRecordMetadata;

@KafkaListener(topics = "order-events")
public void handle(
        OrderCreated event,
        ConsumerRecordMetadata metadata) {

    String topic = metadata.topic();
    int partition = metadata.partition();
    long offset = metadata.offset();
    long timestamp = metadata.timestamp();

    // Process the event along with metadata.
}
```

`ConsumerRecordMetadata` has been available since Spring Kafka 2.5 and holds record metadata, excluding key and value. If you need to read custom headers, you still need `@Header`, `@Headers`, `Message<?>`, or `ConsumerRecord`.

This keeps the listener signature clean when only technical metadata is needed without declaring multiple `@Header` parameters.

## 14. Header validation and handling

Headers are input data from producers. You should not trust them just because the header name looks valid.

Example validating tenant ID and trace ID:

This snippet assumes the producer sends both headers as raw UTF-8 byte arrays, as in the section 5 example.

```java
import java.nio.charset.StandardCharsets;

import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;

@KafkaListener(topics = "order-events")
public void handle(
        @Payload OrderCreated event,
        @Header(value = "tenant-id", required = false) byte[] tenantIdBytes,
        @Header(value = "trace-id", required = false) byte[] traceIdBytes) {

    String tenantId = tenantIdBytes == null
        ? null
        : new String(tenantIdBytes, StandardCharsets.UTF_8);

    if (tenantId == null || tenantId.isBlank()) {
        throw new IllegalArgumentException("Missing tenant-id header");
    }

    if (tenantId.length() > 80) {
        throw new IllegalArgumentException("Invalid tenant-id header");
    }

    String traceId = traceIdBytes == null
        ? null
        : new String(traceIdBytes, StandardCharsets.UTF_8);

    // Continue processing after validating metadata.
}
```

Principles to apply:

- Validate required headers before using them for routing or authorization.
- Restrict length and character sets if headers are used in logs, URLs, or queries.
- Do not use `tenant-id` from a header as grounds for granting permissions unless verified against an authenticated identity.
- Do not write tokens, passwords, or sensitive personal data into logs.
- Handle cases where headers are null, wrongly encoded, or of the wrong type.
- Keep header names and wire formats stable across service versions.

If a header is invalid, throw an appropriate exception so the listener error handler applies retry, recoverer, or DLT according to policy. Permanent malformed-data errors usually do not benefit from infinite retries.

## 15. Testing reading custom headers

You can use Embedded Kafka to verify that a producer sends raw headers and a listener reads the byte arrays properly. Example listener capturing records into a queue:

```java
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class HeaderCaptureListener {

    private final BlockingQueue<ConsumerRecord<String, String>> records =
        new LinkedBlockingQueue<>();

    @KafkaListener(
        id = "header-capture",
        topics = "audit-events",
        groupId = "header-capture-test"
    )
    public void capture(ConsumerRecord<String, String> record) {
        records.add(record);
    }

    public ConsumerRecord<String, String> poll(
            long timeout,
            TimeUnit unit) throws InterruptedException {
        return records.poll(timeout, unit);
    }
}
```

Test sending a record with headers:

```java
import java.nio.charset.StandardCharsets;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.header.internals.RecordHeader;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.kafka.test.utils.ContainerTestUtils;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(properties = {
    "spring.kafka.consumer.key-deserializer=org.apache.kafka.common.serialization.StringDeserializer",
    "spring.kafka.consumer.value-deserializer=org.apache.kafka.common.serialization.StringDeserializer",
    "spring.kafka.producer.key-serializer=org.apache.kafka.common.serialization.StringSerializer",
    "spring.kafka.producer.value-serializer=org.apache.kafka.common.serialization.StringSerializer"
})
@EmbeddedKafka(
    partitions = 1,
    topics = "audit-events",
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
class KafkaHeaderListenerTest {

    @Autowired
    private KafkaTemplate<String, String> kafkaTemplate;

    @Autowired
    private HeaderCaptureListener capture;

    @Autowired
    private KafkaListenerEndpointRegistry registry;

    @BeforeEach
    void waitForAssignment() {
        ContainerTestUtils.waitForAssignment(
            registry.getListenerContainer("header-capture"),
            1
        );
    }

    @Test
    void readsTraceIdFromNativeHeader() throws Exception {
        ProducerRecord<String, String> record =
            new ProducerRecord<>(
                "audit-events",
                "order-42",
                "{\"orderId\":\"order-42\"}"
            );

        record.headers().add(
            new RecordHeader(
                "trace-id",
                "trace-9f31".getBytes(StandardCharsets.UTF_8)
            )
        );

        kafkaTemplate.send(record).get(10, TimeUnit.SECONDS);

        ConsumerRecord<String, String> received =
            capture.poll(10, TimeUnit.SECONDS);

        assertThat(received).isNotNull();

        String traceId = new String(
            received.headers().lastHeader("trace-id").value(),
            StandardCharsets.UTF_8
        );

        assertThat(traceId).isEqualTo("trace-9f31");
    }
}
```

The test must use serializers/deserializers compatible with `KafkaTemplate<String,String>` and the consumer. If the project uses a shared Spring Boot configuration, ensure the test listener uses a dedicated group ID and a dedicated test topic. `waitForAssignment` prevents sending records before the consumer has received partition assignments.

Additional cases that should be tested:

- Missing header.
- Header with an empty byte array value or wrong encoding.
- Duplicate header names.
- Header with a value not matching the wire format.
- `@Header(required = false)` working properly when a header is missing.
- Mapper restoring Java types properly when both producer and consumer use a Spring mapper.

## 16. Common pitfalls

| Symptom | Possible cause | How to handle |
|---|---|---|
| `@Header` reports missing header | Producer did not send it or header name is wrong | Check header name and use `required=false` if optional |
| Receiving `byte[]` instead of String | Raw Kafka header lacks type metadata or mapper returns raw bytes | Decode UTF-8 or configure mapper |
| `RECEIVED_KEY` does not exist | Record was sent with a null key | Mark parameter as optional |
| Custom header does not appear in `MessageHeaders` | Mapper pattern excludes header or mapper is not attached to converter | Check `KafkaHeaderMapper` and patterns |
| Casting header throws `ClassCastException` | Producer and consumer do not agree on type/wire format | Clearly define byte type and mapping rules |
| Only reads one duplicate header | `lastHeader()` only gets the last occurrence or mapper merges values | Use `headers(name)` on `ConsumerRecord` |
| `KafkaHeaders.NATIVE_HEADERS` is absent | Header mapper is converting native headers to Spring headers | Use `@Header`/`@Headers` or configure mapper |
| Type metadata is not restored | Producer did not send `spring_json_header_types` or package is not trusted | Use simple wire format or configure specific trusted packages |

## 17. Header design checklist

- Distinguish custom headers from metadata created by Kafka/Spring Kafka.
- Use `KafkaHeaders` constants for topic, key, partition, offset, and timestamp.
- Agree on encoding, typically UTF-8 for text headers.
- Use `required=false` when a header can genuinely be absent.
- Choose `@Header`, `@Headers`, `Message<?>`, or `ConsumerRecord` according to need.
- Understand clearly whether the mapper converts headers to String, byte array, or other Java types.
- Use native `Headers` when duplicate headers must be preserved.
- Restrict mapping patterns and trusted packages.
- Validate headers before using them for tenant, routing, or security.
- Do not store secrets or large payloads in headers.
- Test missing, mistyped, duplicate, and cross-version headers.

## 18. Takeaways

- Kafka headers store names and byte array values; Kafka does not inherently enforce Java types for values.
- `@Header` retrieves one header; `@Headers` retrieves a header map; `Message<?>` holds both payload and metadata.
- `KafkaHeaders.RECEIVED_*` represents metadata of the received record.
- `ConsumerRecord.headers()` allows reading native Kafka headers and handling multiple occurrences with the same name.
- `KafkaHeaderMapper` determines how native Kafka headers are converted into Spring `MessageHeaders`.
- `DefaultKafkaHeaderMapper` is commonly used in Spring Kafka 3.x; Spring Kafka 4.x uses `JsonKafkaHeaderMapper`.
- Headers are not guaranteed to be present; null, wrong types, and invalid encodings must be handled.
- Headers are input data, requiring validation and security policies just like the payload.

By understanding the wire format, header mappers, and parameter binding options, a listener can safely read metadata and custom headers. This allows passing trace IDs, tenant IDs, and routing information through Kafka while maintaining clear boundaries between payload, application headers, and broker metadata.

