# Converters when sending Message<?>

Spring Kafka allows sending a Spring `Message<?>` directly with `KafkaTemplate.send(message)`. This approach is useful when the application already builds messages using `MessageBuilder` and wants to package the payload together with metadata such as topic, key, partition, timestamp, and custom headers into a single object.

In the `SPRING_KAFKA_MESSAGING` module, producers send events with `KafkaTemplate`, and consumers receive events with `@KafkaListener`. When sending `Message<?>`, Spring Kafka uses `RecordMessageConverter` to convert the Spring Message into a Kafka `ProducerRecord`. The Kafka producer then uses serializers to convert key and value into bytes. These two steps have distinct responsibilities and must be configured compatibly.

## 1. Sending Spring `Message<?>` instead of calling `send(...)` overloads

With standard sending, the producer passes topic, key, and value directly:

```java
kafkaTemplate.send("orders.created", event.orderId(), event);
```

If you also need to pass partition, timestamp, or headers, you can use `ProducerRecord`. Spring Kafka also supports Spring Messaging's `Message<?>`:

```java
Message<OrderCreatedEvent> message = MessageBuilder
        .withPayload(event)
        .setHeader(KafkaHeaders.TOPIC, "orders.created")
        .setHeader(KafkaHeaders.MESSAGE_KEY, event.orderId())
        .build();

kafkaTemplate.send(message);
```

`Message<?>` bundles payload and headers into one object following Spring's abstraction. The converter reads this message, extracts the required Kafka metadata, and builds the corresponding `ProducerRecord`.

```mermaid
flowchart LR
    A[Domain event] --> B[MessageBuilder]
    B --> C[Spring Message payload + headers]
    C --> D[RecordMessageConverter]
    D --> E[Kafka ProducerRecord]
    E --> F[Key/value serializers]
    F --> G[(Kafka topic / partition)]
    G --> H[SendResult / RecordMetadata]
```

## 2. Building `Message<?>` with `MessageBuilder`

Spring Messaging provides `MessageBuilder` to create a message with payload and headers. Example event:

```java
import java.math.BigDecimal;
import java.time.Instant;

public record OrderCreatedEvent(
        String eventId,
        String orderId,
        BigDecimal total,
        Instant occurredAt
) {}
```

The producer builds a message with Kafka metadata:

```java
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public Message<OrderCreatedEvent> toMessage(
        OrderCreatedEvent event,
        String correlationId) {

    return MessageBuilder
            .withPayload(event)
            .setHeader(KafkaHeaders.TOPIC, "orders.created")
            .setHeader(KafkaHeaders.MESSAGE_KEY, event.orderId())
            .setHeader(KafkaHeaders.TIMESTAMP, event.occurredAt().toEpochMilli())
            .setHeader("correlation-id", correlationId)
            .setHeader("event-type", "OrderCreated")
            .build();
}
```

Important headers:

| Header | Typical value | Role when sending |
|---|---|---|
| `KafkaHeaders.TOPIC` | `String` | Target topic; required if template has no default topic |
| `KafkaHeaders.MESSAGE_KEY` | Key matching `K` | Key of the Kafka record |
| `KafkaHeaders.PARTITION` | `Integer` | Explicit partition; if omitted, the partitioner chooses |
| `KafkaHeaders.TIMESTAMP` | `Long` | Record timestamp in milliseconds since Unix epoch |
| Custom header | e.g., `correlation-id` | Additional metadata mapped by the header mapper |

`MessageHeaders` also has standard Spring headers such as `id` and `timestamp`. Do not confuse `MessageHeaders.TIMESTAMP` with the Kafka record timestamp; when specifying a timestamp for Kafka, use `KafkaHeaders.TIMESTAMP`.

## 3. Sending messages with `KafkaTemplate.send(Message<?>)`

Complete publisher example:

```java
import java.util.concurrent.CompletableFuture;

import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderCreatedEvent>> publish(
            OrderCreatedEvent event,
            String correlationId) {

        Message<OrderCreatedEvent> message = MessageBuilder
                .withPayload(event)
                .setHeader(KafkaHeaders.TOPIC, "orders.created")
                .setHeader(KafkaHeaders.MESSAGE_KEY, event.orderId())
                .setHeader(KafkaHeaders.TIMESTAMP,
                        event.occurredAt().toEpochMilli())
                .setHeader("correlation-id", correlationId)
                .build();

        return kafkaTemplate.send(message);
    }
}
```

In Spring Kafka 3.x, `send(...)` returns `CompletableFuture<SendResult<K, V>>`. In older versions, the API may return `ListenableFuture`; check your project's dependency version.

If you want to send to a specific partition, add the `KafkaHeaders.PARTITION` header with a valid partition index. Without a partition header, the converter creates a record without an explicit partition and the Kafka partitioner decides based on the key and producer configuration.

## 4. What does `RecordMessageConverter` do?

`RecordMessageConverter` is Spring Kafka's abstraction for converting between Spring `Message<?>` and Kafka records. On the outbound side, the converter takes a Spring Message and builds a `ProducerRecord`; on the inbound side, it can convert a `ConsumerRecord` into a Spring Message for listeners.

`MessagingMessageConverter` is the standard implementation. It maps:

- `Message.getPayload()` to the `ProducerRecord` value.
- `KafkaHeaders.TOPIC` to topic.
- `KafkaHeaders.MESSAGE_KEY` to key.
- `KafkaHeaders.PARTITION` to partition if specified.
- `KafkaHeaders.TIMESTAMP` to timestamp if specified.
- Custom headers through `KafkaHeaderMapper`.

Crucially: `MessagingMessageConverter` does not implicitly turn every POJO into a JSON byte array. It converts the Spring Message structure into a Kafka record and lets the Kafka key/value serializers handle the corresponding data types.

In many Spring Kafka setups, `KafkaTemplate` already comes with a default message converter. Configure a custom converter only when you need to change how payloads or headers are mapped.

## 5. Distinguishing message converter and Kafka serializer

The two components sit at different steps:

| Component | Input | Output | Example responsibility |
|---|---|---|---|
| `RecordMessageConverter` | Spring `Message<?>` | Kafka `ProducerRecord<K, V>` | Reads topic/key/partition/timestamp from headers and extracts payload |
| Key serializer | Java key `K` | `byte[]` | Converts `String` key to bytes |
| Value serializer | Java value `V` | `byte[]` | Converts POJO to JSON or byte array |
| Header mapper | Spring Message headers | Kafka record headers | Converts custom metadata into Kafka headers |

For example, if using `KafkaTemplate<String, OrderCreatedEvent>` with `JsonSerializer`, `MessagingMessageConverter` puts the event payload into `ProducerRecord`; `JsonSerializer` is what turns `OrderCreatedEvent` into a JSON byte array.

If the serializer is configured as `StringSerializer` while the payload remains `OrderCreatedEvent`, the producer will fail with a data type/serialization error. Wrapping with `MessageBuilder` does not automatically resolve this mismatch.

## 6. Configuring the converter for `KafkaTemplate`

You can attach a `RecordMessageConverter` to the template when customization is needed. Example configuring `MessagingMessageConverter` and a header mapper:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.core.ProducerFactory;
import org.springframework.kafka.support.DefaultKafkaHeaderMapper;
import org.springframework.kafka.support.converter.MessagingMessageConverter;
import org.springframework.kafka.support.converter.RecordMessageConverter;

@Configuration
public class KafkaMessageConversionConfiguration {

    @Bean
    public RecordMessageConverter outboundRecordMessageConverter() {
        MessagingMessageConverter converter =
                new MessagingMessageConverter();
        converter.setHeaderMapper(new DefaultKafkaHeaderMapper());
        return converter;
    }

    @Bean
    public KafkaTemplate<String, OrderCreatedEvent> orderKafkaTemplate(
            ProducerFactory<String, OrderCreatedEvent> producerFactory,
            RecordMessageConverter outboundRecordMessageConverter) {

        KafkaTemplate<String, OrderCreatedEvent> template =
                new KafkaTemplate<>(producerFactory);
        template.setMessageConverter(outboundRecordMessageConverter);
        return template;
    }
}
```

The example above highlights the customization points: `MessagingMessageConverter` handles converting between Spring Message and Kafka record; `DefaultKafkaHeaderMapper` maps headers. The producer factory must still configure serializers compatible with `String` keys and `OrderCreatedEvent` values.

If Spring Boot already auto-configures a default `KafkaTemplate`, declare custom beans only when truly needed and check auto-configuration conditions to avoid injecting the wrong template. When multiple templates or converters exist, name beans clearly and use `@Qualifier`.

## 7. Mapping custom headers

Custom headers can carry correlation ID, trace context, or event type:

```java
Message<OrderCreatedEvent> message = MessageBuilder
        .withPayload(event)
        .setHeader(KafkaHeaders.TOPIC, "orders.created")
        .setHeader(KafkaHeaders.MESSAGE_KEY, event.orderId())
        .setHeader("correlation-id", "corr-9f81")
        .setHeader("event-type", "OrderCreated")
        .build();
```

`KafkaHeaderMapper` decides how custom headers are converted into Kafka headers. `DefaultKafkaHeaderMapper` supports mapping multiple header types and can include type metadata for non-byte-array values. `SimpleKafkaHeaderMapper` fits when the application prefers simpler byte/string conventions.

On the consumer side, custom headers are mapped back into Spring Message according to the mapper configuration. Producer and consumer must agree on header names, data types, and encoding. If a non-Spring Kafka consumer reads the record, headers are still byte arrays and that consumer must know how to decode them.

Do not place large payloads, secret tokens, or unnecessary sensitive data in headers. Headers are meant for small metadata; business content belongs in the payload protected by appropriate data policies.

## 8. Using a JSON message converter when the serializer is String

There are two common ways to send a POJO as JSON:

1. Use `MessagingMessageConverter` (or the default converter) to create `ProducerRecord<OrderCreatedEvent>`, then use `JsonSerializer` in the producer factory.
2. Use a JSON message converter to convert the payload into a JSON string, then use `StringSerializer`.

Example of the second approach:

```java
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.core.ProducerFactory;
import org.springframework.kafka.support.converter.RecordMessageConverter;
import org.springframework.kafka.support.converter.StringJsonMessageConverter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class StringJsonKafkaConfiguration {

    @Bean
    public RecordMessageConverter stringJsonMessageConverter() {
        return new StringJsonMessageConverter();
    }

    @Bean
    public KafkaTemplate<String, String> jsonTextKafkaTemplate(
            ProducerFactory<String, String> producerFactory,
            RecordMessageConverter stringJsonMessageConverter) {

        KafkaTemplate<String, String> template =
                new KafkaTemplate<>(producerFactory);
        template.setMessageConverter(stringJsonMessageConverter);
        return template;
    }
}
```

In this approach, `ProducerFactory<String, String>` must use `StringSerializer` for both key and value. The converter turns the POJO inside `Message<?>` into a JSON String before sending. Do not combine `StringJsonMessageConverter` with a factory that only has `JsonSerializer` without understanding the exact value type the converter produces.

Both strategies can produce JSON on the wire, but serializer and converter must form a compatible pair. Avoid configuring two components simultaneously to serialize the payload into two different formats.

## 9. Tracking send results and errors

Sending with `Message<?>` is still an asynchronous operation. Observe the future to know whether the record was successfully written by the broker:

```java
import java.util.concurrent.CompletableFuture;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Service;

@Service
public class AuditedMessagePublisher {

    private static final Logger log =
            LoggerFactory.getLogger(AuditedMessagePublisher.class);

    private final KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate;

    public AuditedMessagePublisher(
            KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderCreatedEvent>> send(
            Message<?> message) {

        return kafkaTemplate.send(message).whenComplete((result, exception) -> {
            if (exception != null) {
                log.error("Kafka message send failed", exception);
                return;
            }

            var metadata = result.getRecordMetadata();
            log.info(
                    "Sent topic={} partition={} offset={}",
                    metadata.topic(),
                    metadata.partition(),
                    metadata.offset()
            );
        });
    }
}
```

The example uses `Message<?>` in the method signature to accept a message built in an earlier step; in real systems, ensure the inner payload is `OrderCreatedEvent` and required headers are present. Otherwise, use `Message<OrderCreatedEvent>` to express the payload type more clearly.

Common errors include missing topic header, non-existent partition, incompatible key/value serializer, unmappable header, or broker/network rejection. Some errors happen when the converter builds `ProducerRecord`; serialization errors happen when the Kafka producer serializes key/value. Log sufficient topic, identifying key, exception, and metadata on successful send for investigation.

## 10. Common pitfalls

- **Missing `KafkaHeaders.TOPIC`:** if the template has no default topic, the converter cannot determine the target topic.
- **Using `MessageHeaders.TIMESTAMP` instead of Kafka timestamp:** use `KafkaHeaders.TIMESTAMP` when controlling the record timestamp.
- **Wrong key header:** `KafkaHeaders.MESSAGE_KEY` is the header for the Kafka record key; similarly named custom headers do not automatically become the key.
- **Confusing converter with serializer:** the converter builds `ProducerRecord`; the serializer turns key/value into bytes.
- **Generic type and serializer mismatch:** for example, template value is a POJO while the factory uses `StringSerializer`.
- **Specifying a non-existent partition:** the record cannot be written to that partition; verify topic metadata/provisioning.
- **Assuming every custom header is transferred verbatim:** the header mapper may convert types or filter headers per configuration.
- **Putting large data or secrets in headers:** increases overhead and risks exposing data via logs/monitoring.
- **Ignoring the future returned by `send(message)`:** the application fails to observe asynchronous send failures.
- **Creating a custom converter without attaching it to the template:** a bean existing in the context does not mean `KafkaTemplate` uses it automatically.

## 11. Testing sending `Message<?>`

Tests should verify both the message conversion step and the send result:

- **Message factory unit test:** create a message and verify payload, topic, key, partition, timestamp, and custom headers.
- **Converter test:** verify `RecordMessageConverter` creates `ProducerRecord` with the right topic/key/partition/timestamp.
- **Serializer test:** verify the producer factory serializes the payload in the expected wire format, such as JSON or String.
- **Integration test:** use Embedded Kafka or Testcontainers, send `Message<?>`, consume the record, and verify the actual payload and headers.
- **Failure test:** omit the topic header, specify an invalid partition, or misconfigure the serializer to verify errors are observed as expected.
- **Header mapping test:** verify custom headers are converted into Kafka headers and the consumer can read them back with the chosen mapper.

For integration tests, create topics with an explicit partition count and use a dedicated consumer group. When asserting outcomes, read `RecordMetadata` from the future or metadata on `ConsumerRecord`, rather than assuming the partition is always `0` if the producer did not specify one.

## 12. Checklist before sending `Message<?>`

- [ ] Payload type matches `KafkaTemplate<K, V>` and the producer serializer.
- [ ] `KafkaHeaders.TOPIC` is set or the template has a configured default topic.
- [ ] Key is set via `KafkaHeaders.MESSAGE_KEY` when key-based routing is needed.
- [ ] Partition is set only after verifying the partition exists.
- [ ] Kafka timestamp uses `KafkaHeaders.TIMESTAMP` in milliseconds.
- [ ] Custom headers have consistent names, types, and encoding.
- [ ] `RecordMessageConverter`/header mapper matches the sending approach.
- [ ] Message converter is clearly distinguished from key/value serializers.
- [ ] If using a JSON message converter, the serializer accepts the exact String/`byte[]` type the converter produces.
- [ ] Send futures are observed and errors are handled per policy.
- [ ] Integration tests verify actual records and headers on Kafka.

Sending `Message<?>` lets producers bundle payload and metadata into a Spring Message, while `RecordMessageConverter` converts it into a Kafka record before serializers produce bytes. When proper Kafka headers, header mappers, and compatible serializers are declared, `KafkaTemplate.send(message)` creates a readable, extensible, and clearly testable sending flow.
