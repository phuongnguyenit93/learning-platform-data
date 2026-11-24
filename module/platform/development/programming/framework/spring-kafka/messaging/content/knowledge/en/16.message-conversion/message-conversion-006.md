# MessageConverter for JSON

## 1. What problem does MessageConverter solve?

Kafka only stores keys and values as bytes. On the application side, data is usually Java objects such as `OrderCreatedEvent`. To exchange data, the producer must convert objects into a transmittable format and the consumer must convert received data into the type used by the listener.

In Spring Kafka, `MessageConverter` connects Spring Messaging's `Message<?>` model with Kafka records. A converter can convert an object payload into JSON as a `String` or `byte[]` when sending, and then convert received JSON into a Java object when the listener processes it.

For example, the application wants to send an object:

~~~java
import java.time.Instant;

OrderCreatedEvent event = new OrderCreatedEvent(
    "evt-1001",
    "ORD-1001",
    "CUS-42",
    Instant.parse("2025-01-01T10:00:00Z")
);
~~~

The listener wants to receive the object directly:

~~~java
@KafkaListener(topics = "orders")
public void handle(OrderCreatedEvent event) {
    orderService.apply(event);
}
~~~

`MessageConverter` handles the conversion step at the Spring Messaging/Kafka boundary so business code does not have to invoke Jackson manually in every listener or publisher.

Overview flow:

~~~mermaid
flowchart LR
    A["Java object"] --> B["Spring Message<?>"]
    B --> C["RecordMessageConverter"]
    C --> D["Kafka ProducerRecord"]
    D --> E["Kafka serializer"]
    E --> F["Kafka topic: bytes"]
    F --> G["Kafka deserializer"]
    G --> H["ConsumerRecord"]
    H --> I["RecordMessageConverter"]
    I --> J["Spring Message / listener payload"]
    J --> K["Java object"]
~~~

The converter does not completely replace Kafka serializers/deserializers. The two mechanisms work together and must be configured compatibly.

## 2. Distinguishing Serializer/Deserializer and MessageConverter

This is the most important point when choosing how to convert JSON.

| Component | Where it operates | Responsibility |
|---|---|---|
| `Serializer<K/V>` | Kafka producer client | Converts key/value to bytes before writing |
| `Deserializer<K/V>` | Kafka consumer client | Converts bytes into the key/value type received by the consumer |
| `RecordMessageConverter` | Spring Kafka | Converts between Spring `Message<?>` and Kafka `ProducerRecord`/`ConsumerRecord` |
| `BatchMessageConverter` | Spring Kafka batch listener | Converts data for a listener receiving a batch |

There are two common ways to get JSON into and out of Kafka.

**Approach A — Using JsonSerializer/JsonDeserializer**

- The producer passes Java objects directly into `KafkaTemplate`.
- `JsonSerializer` converts the object into JSON bytes.
- The consumer uses `JsonDeserializer` to create the Java object before the listener receives the record.
- No JSON `MessageConverter` is needed if the listener only receives the deserialized object.

**Approach B — Using StringJsonMessageConverter**

- `KafkaTemplate.send(Message<?>)` receives a Spring Message whose payload is an object.
- `StringJsonMessageConverter` converts the object into a JSON `String`.
- `StringSerializer` converts the JSON string into bytes.
- The consumer uses `StringDeserializer` to get back the JSON `String`.
- `StringJsonMessageConverter` converts the JSON into the object type requested by the listener.

Comparison table:

| Criterion | JsonSerializer/JsonDeserializer | StringJsonMessageConverter |
|---|---|---|
| Layer converting object to JSON | Kafka serializer | Spring Kafka message converter |
| Value type between converter and Kafka client | JSON bytes | JSON `String` |
| Serializer/deserializer | `JsonSerializer` / `JsonDeserializer` | `StringSerializer` / `StringDeserializer` |
| Sending with `KafkaTemplate` | Can use `send(topic, key, object)` | Use `send(Message<?>)` so the converter participates |
| Listener receiving object | Deserializer creates object before listener | Converter creates object from JSON string |
| Suitable for | Direct Java-typed Kafka flows | Spring Messaging and header integration |

Do not configure both layers to convert the same JSON payload in incompatible ways. For example, if the converter already produces a JSON String, the producer value serializer must be `StringSerializer`, not `JsonSerializer` expecting a business object.

## 3. Common JSON MessageConverters

Spring Kafka provides Jackson-based converters to work with different payload types:

| Converter | Intermediate payload type | Matching serializer/deserializer |
|---|---|---|
| `StringJsonMessageConverter` | `String` containing JSON | `StringSerializer` / `StringDeserializer` |
| `ByteArrayJsonMessageConverter` | `byte[]` containing JSON | `ByteArraySerializer` / `ByteArrayDeserializer` |
| `BytesJsonMessageConverter` | Kafka `Bytes` containing JSON | `BytesSerializer` / `BytesDeserializer` |

These converters are commonly constructed with Jackson's `ObjectMapper`. Use the String converter when readable text JSON is desired; use byte array when the transport contract requires byte values; use `Bytes` when the application works with Kafka's `Bytes` type.

The examples below use `StringJsonMessageConverter`, `StringSerializer`, and `StringDeserializer`. This is an easy-to-read configuration when learning JSON conversion via Spring Messaging.

Class names and constructors may vary across Spring Kafka major versions. Use the API matching your project's dependency version; the configuration examples in this lesson illustrate common Spring Kafka 3.x APIs.

## 4. Configuring StringJsonMessageConverter in Spring Boot

When using the String converter, both producer and consumer work with JSON as `String` at the Kafka client layer:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092

    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
      acks: all

    consumer:
      group-id: order-projection
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      enable-auto-commit: false
      auto-offset-reset: earliest

    listener:
      type: single
      ack-mode: record
~~~

The serializer/deserializer properties are `StringSerializer` and `StringDeserializer` because the converter will turn the object payload into a JSON String before sending and turn the JSON String into an object when the listener receives it.

Declare the converter sharing the Spring Boot-managed `ObjectMapper`:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.support.converter.RecordMessageConverter;
import org.springframework.kafka.support.converter.StringJsonMessageConverter;

@Configuration
public class KafkaMessageConversionConfiguration {

    @Bean
    RecordMessageConverter jsonRecordMessageConverter(
            ObjectMapper objectMapper) {
        return new StringJsonMessageConverter(objectMapper);
    }
}
~~~

Using the injected `ObjectMapper` lets the converter share the application's Jackson configuration, such as the Java Time module, naming strategy, or custom serializers/deserializers. If creating a completely separate `ObjectMapper`, make sure its settings are compatible with the data exchanged by other producers and consumers.

## 5. Attaching the converter to KafkaTemplate to send JSON

`KafkaTemplate` supports sending Spring `Message<?>`. When calling the `send(Message<?>)` overload, the template uses `RecordMessageConverter` to convert the Spring Message into a Kafka `ProducerRecord`.

You can declare a dedicated template:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.core.ProducerFactory;
import org.springframework.kafka.support.converter.RecordMessageConverter;

@Configuration
public class KafkaTemplateConfiguration {

    @Bean
    KafkaTemplate<String, String> jsonKafkaTemplate(
            ProducerFactory<String, String> producerFactory,
            RecordMessageConverter jsonRecordMessageConverter) {

        var template = new KafkaTemplate<>(producerFactory);
        template.setMessageConverter(jsonRecordMessageConverter);
        return template;
    }
}
~~~

The template's generic type is `KafkaTemplate<String, String>` because after conversion, the value sent to the Kafka client is a JSON String. The producer factory must use `StringSerializer` for value.

Building a Spring Message from an object:

~~~java
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public void publish(OrderCreatedEvent event, String correlationId) {
    Message<OrderCreatedEvent> message = MessageBuilder
        .withPayload(event)
        .setHeader(KafkaHeaders.TOPIC, "orders")
        .setHeader(KafkaHeaders.KEY, event.orderId())
        .setHeader("correlation-id", correlationId)
        .build();

    jsonKafkaTemplate.send(message);
}
~~~

Here:

- Payload is `OrderCreatedEvent`.
- `KafkaHeaders.TOPIC` specifies the target topic.
- `KafkaHeaders.KEY` sets the Kafka record key.
- `correlation-id` is a custom header to correlate logs across services.
- The converter serializes the payload object into a JSON String before the template sends the record.

If you need to inspect the send result, you can observe the returned `CompletableFuture`:

~~~java
jsonKafkaTemplate.send(message)
    .whenComplete((result, error) -> {
        if (error != null) {
            log.error("Failed to send OrderCreated", error);
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
~~~

A completed future indicates the producer received acknowledgment according to the `acks` setting. It does not prove that a consumer has finished processing the event.

**Note:** the `send(topic, key, value)` overload is not the Spring `Message<?>` send path, so it does not automatically invoke the converter configured for `send(Message<?>)`. If calling that overload with `KafkaTemplate<String, String>`, `value` must be a JSON String. If you want to pass an object directly with the topic/key/value overload, use `JsonSerializer` or convert the object to JSON beforehand.

## 6. Attaching the converter to the listener container to receive JSON

On the consumer side, the deserializer retrieves a JSON String from Kafka. The listener container uses `RecordMessageConverter` to convert JSON into the object type declared by the listener method.

Declaring the listener container factory:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.support.converter.RecordMessageConverter;

@Configuration
public class KafkaListenerConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, String>
            kafkaListenerContainerFactory(
                    ConsumerFactory<String, String> consumerFactory,
                    RecordMessageConverter jsonRecordMessageConverter) {

        var factory =
            new ConcurrentKafkaListenerContainerFactory<String, String>();

        factory.setConsumerFactory(consumerFactory);
        factory.setRecordMessageConverter(jsonRecordMessageConverter);
        return factory;
    }
}
~~~

The listener can receive the object directly:

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderCreatedListener {

    private final OrderProjectionService orderProjectionService;

    public OrderCreatedListener(
            OrderProjectionService orderProjectionService) {
        this.orderProjectionService = orderProjectionService;
    }

    @KafkaListener(
        topics = "orders",
        groupId = "order-projection",
        containerFactory = "kafkaListenerContainerFactory"
    )
    public void handle(OrderCreatedEvent event) {
        orderProjectionService.apply(event);
    }
}
~~~

The container factory must use `ConsumerFactory<String, String>` because the consumer deserializer returns a JSON String. The converter then constructs `OrderCreatedEvent` for the listener to receive.

You can also receive additional metadata via annotations:

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.annotation.Payload;
import org.springframework.kafka.annotation.Header;
import org.springframework.kafka.support.KafkaHeaders;

@KafkaListener(
    topics = "orders",
    groupId = "order-projection",
    containerFactory = "kafkaListenerContainerFactory"
)
public void handle(
        @Payload OrderCreatedEvent event,
        @Header(KafkaHeaders.RECEIVED_KEY) String key,
        @Header(KafkaHeaders.RECEIVED_TOPIC) String topic,
        @Header(name = "correlation-id", required = false) String correlationId) {

    orderProjectionService.apply(event, key, topic, correlationId);
}
~~~

Inbound headers can include key, topic, partition, offset, and custom metadata. Using `@Payload` for business data and `@Header` for metadata makes the listener signature clearly express each parameter's responsibility.

## 7. ObjectMapper and JSON formatting

`StringJsonMessageConverter` relies on Jackson to convert objects to JSON and back. Therefore, `ObjectMapper` must understand the object structures of producer and consumer.

Example event:

~~~java
import java.time.Instant;

public record OrderCreatedEvent(
    String eventId,
    String orderId,
    String customerId,
    Instant createdAt
) {}
~~~

If the payload contains `Instant`, `LocalDate`, `LocalDateTime`, or other Java date/time types, `ObjectMapper` needs the appropriate Java Time module. Spring Boot usually auto-configures the mapper with modules on the classpath. If creating a mapper manually, you can register `JavaTimeModule`:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

ObjectMapper objectMapper = new ObjectMapper()
    .registerModule(new JavaTimeModule());
~~~

Do not instantiate a separate `new ObjectMapper()` inside each publisher or listener. That easily creates discrepancies in date formats, naming strategies, null handling, and custom serializers across components.

The JSON contract should clearly define:

- Field names and data types.
- Date/time format, timezone, and precision.
- Required fields, optional fields, and default values.
- Compatibility rules when adding or changing fields.
- Event versions and how consumers handle versions they do not yet support.

JSON is a text format, but it does not solve schema evolution on its own. If the system needs strict schema control or cross-language compatibility, consider JSON Schema, Avro, or Protobuf along with a schema management process.

## 8. Type headers and selecting the target type

JSON only carries data; it does not inherently carry Java types. When converting JSON into an object, the converter must know the target type. Spring Kafka can infer the type from the listener parameter and can use type metadata in Kafka headers depending on the type mapper configuration.

Example listener explicitly declaring the type:

~~~java
@KafkaListener(topics = "orders", groupId = "order-projection")
public void handle(OrderCreatedEvent event) {
    orderProjectionService.apply(event);
}
~~~

The `OrderCreatedEvent` type provides clear target information for the converter to build the object. For listeners accepting an interface, abstract class, or `Object`, the converter may need type metadata or additional type mapping configuration.

Some principles:

- Prefer concrete parameter types when a listener handles only one event type.
- If using type headers, align how the producer emits and the consumer reads those headers.
- With multiple languages, avoid relying on Java class names as a public contract.
- Only trust allowed packages/types if deserialization configuration uses trusted packages.
- Do not enable wildcard trusted packages for data from untrusted sources without a security review.

Type headers help choose the target type, but they do not replace event versioning. A Java class changing its package or name can prevent older consumers from reading type metadata if the system depends directly on class names.

## 9. Header mapping and Spring Message metadata

A Spring Message has payload and headers. `RecordMessageConverter` maps appropriate headers to Kafka record headers when sending and converts received headers into a Spring Message on the listener side.

Commonly used headers:

| Header | Direction | Meaning |
|---|---|---|
| `KafkaHeaders.TOPIC` | Outbound | Target topic |
| `KafkaHeaders.KEY` | Outbound | Kafka record key |
| `KafkaHeaders.PARTITION` | Outbound | Target partition if explicitly specified |
| `KafkaHeaders.RECEIVED_TOPIC` | Inbound | Topic containing the record |
| `KafkaHeaders.RECEIVED_KEY` | Inbound | Key of the record |
| `KafkaHeaders.RECEIVED_PARTITION` | Inbound | Partition received |
| `KafkaHeaders.OFFSET` | Inbound | Offset of the record |
| `correlation-id` | Outbound/inbound | Custom application metadata |

Do not put critical business data only in headers if consumers need it for processing when the payload is stored or forwarded independently. Such data should belong in the payload or in a well-documented event contract.

Kafka headers are byte arrays at the broker level. The converter can map certain Spring header types to appropriate values, but custom headers should use simple and consistent types, such as Strings, byte arrays, or numbers with clear conversion rules.

## 10. Handling JSON conversion errors

Conversion errors can occur at two different stages:

| Stage | Example | How observed |
|---|---|---|
| Kafka deserialization | Invalid bytes or unreadable by deserializer | Occurs during consumer poll; typically needs `ErrorHandlingDeserializer` to feed errors into Spring Kafka's error handling |
| Message conversion | Invalid JSON String or cannot map to listener type | Occurs in listener adapter/converter; container's error handler can handle it |
| Business validation | Valid JSON but missing required data per business rules | Handled via validation or business exceptions in listener/service |

If using `StringDeserializer`, the Kafka client only converts bytes into a String. JSON parsing happens in `StringJsonMessageConverter`; such errors occur on the listener processing path and can be handled by the configured error handler.

If using `JsonDeserializer` instead of `StringJsonMessageConverter`, JSON parsing happens in the Kafka deserializer before the listener receives the record. In that case, consider `ErrorHandlingDeserializer` so Spring Kafka can forward deserialization errors to the error handler and apply appropriate retry/recovery.

Example consumer configuration wrapping `JsonDeserializer` with `ErrorHandlingDeserializer` (this is an alternative strategy, not something to add on top of the String converter configuration above):

~~~yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.value.default.type: com.example.events.OrderCreatedEvent
        spring.json.trusted.packages: com.example.events
~~~

In this configuration, `ErrorHandlingDeserializer` wraps `JsonDeserializer` so errors converting JSON into objects can be routed to Spring Kafka's error handling mechanism. If using `StringJsonMessageConverter`, JSON parsing still occurs in the listener adapter/converter and there is no need to configure `JsonDeserializer` for the same value.

Distinguish JSON syntax errors, type mapping errors, and business validation errors. Do not retry a malformed payload infinitely because the exact same record will keep failing. You can use `DefaultErrorHandler`, bounded backoff, and dead-letter publishing for records that cannot be processed per consumer policy.

## 11. Batch listeners and MessageConverter

If a listener receives multiple records in one invocation, configure batch mode and an appropriate batch message converter. `RecordMessageConverter` serves single-record conversion; batch listeners use `BatchMessageConverter` to convert a list of records into the shape accepted by the listener method.

Example creating a batch converter from a record converter:

~~~java
import org.springframework.kafka.support.converter.BatchMessagingMessageConverter;
import org.springframework.kafka.support.converter.RecordMessageConverter;

@Bean
BatchMessagingMessageConverter batchMessageConverter(
        RecordMessageConverter jsonRecordMessageConverter) {
    return new BatchMessagingMessageConverter(
        jsonRecordMessageConverter
    );
}
~~~

Attach the converter to the batch container factory according to the API of your Spring Kafka version, and enable batch listener mode. The listener can receive `List<OrderCreatedEvent>` or a list of `Message<?>` depending on converter configuration and method signature.

Batch factory example:

~~~java
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.support.converter.BatchMessageConverter;

@Bean
ConcurrentKafkaListenerContainerFactory<String, String>
        batchKafkaListenerContainerFactory(
                ConsumerFactory<String, String> consumerFactory,
                BatchMessageConverter batchMessageConverter) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, String>();
    factory.setConsumerFactory(consumerFactory);
    factory.setBatchListener(true);
    factory.setBatchMessageConverter(batchMessageConverter);
    return factory;
}
~~~

A listener using this factory can receive the converted payload list:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "order-batch-projection",
    containerFactory = "batchKafkaListenerContainerFactory"
)
public void handleBatch(List<OrderCreatedEvent> events) {
    orderProjectionService.applyBatch(events);
}
~~~


Do not use a batch converter configuration for a record listener if the factory and listener signature are incompatible. Test batches with one record, batches with multiple records, and a conversion error on a single element.

## 12. Testing MessageConverter

Test three areas separately: JSON mapping, the outbound path, and the inbound path.

**Converter unit tests:** verify objects convert to valid JSON and JSON converts back to the right object type. Check date/time fields, nulls, enums, nested objects, and incompatible fields.

**Publisher tests:** send `Message<?>` via `KafkaTemplate`, verifying topic, key, headers, and JSON value. If mocking the template, verify the converter is configured or test conversion output separately.

**Integration tests:** use Embedded Kafka or Testcontainers, send a Spring Message with an object payload, and verify the listener receives the expected object and metadata. Use bounded timeouts rather than fixed `Thread.sleep()`.

Scenarios to test:

- Valid JSON mapping to the right listener type.
- Malformed JSON.
- Missing required fields or incompatible field types.
- Missing or unsupported type/version headers.
- Correlation ID header preserved intact.
- Mismatched producer/consumer serializer configuration.
- Multiple event versions handled by the consumer per contract.

Example testing JSON mapping with the converter:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.junit.jupiter.api.Test;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.kafka.support.converter.StringJsonMessageConverter;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class JsonMessageConverterTest {

    private final StringJsonMessageConverter converter =
        new StringJsonMessageConverter();

    record TestEvent(String eventId, String orderId) {}

    @Test
    void convertsSpringMessageToKafkaRecordAndBack() {
        var event = new TestEvent("evt-1", "ORD-1");
        Message<TestEvent> outbound = MessageBuilder
            .withPayload(event)
            .setHeader(KafkaHeaders.TOPIC, "orders")
            .setHeader(KafkaHeaders.KEY, "ORD-1")
            .build();

        ProducerRecord<?, ?> kafkaRecord = converter.fromMessage(outbound, null);

        assertThat(kafkaRecord.topic()).isEqualTo("orders");
        assertThat(kafkaRecord.key()).isEqualTo("ORD-1");
        assertThat(kafkaRecord.value()).isInstanceOf(String.class);

        String json = (String) kafkaRecord.value();
        ConsumerRecord<String, String> inbound =
            new ConsumerRecord<>("orders", 0, 0L, "ORD-1", json);

        Message<?> converted = converter.toMessage(
            inbound, null, null, TestEvent.class
        );

        assertThat(converted.getPayload()).isEqualTo(event);
    }
}
~~~

This is a direct unit test of both conversion directions of `RecordMessageConverter`: Spring Message to Kafka ProducerRecord and ConsumerRecord to Spring Message with the target payload type. Integration tests through `KafkaTemplate.send(Message<?>)` and `@KafkaListener` are still necessary to verify serializer, deserializer, container factory, and broker all work together properly.

## 13. Common pitfalls and fixes

| Symptom | Cause | Fix |
|---|---|---|
| Producer throws data type error | Converter produces String while producer uses serializer for another object | Use `StringSerializer` with `StringJsonMessageConverter` |
| Listener receives String instead of object | Listener factory has no converter attached or uses incompatible deserializer/type | Attach `RecordMessageConverter` to the right container factory |
| JSON parsing fails | Malformed payload or contract mismatch | Check JSON, version, and Jackson configuration |
| Target type not found | Listener accepts `Object` or interface and lacks type mapping | Use a concrete parameter type or configure type mapper |
| Header is missing | Header was not added to Spring Message or not mapped | Check header name, data type, and converter |
| `send(topic, key, object)` does not invoke converter | This overload sends value directly via serializer | Use `send(Message<?>)` or JsonSerializer |
| Some listeners convert, others do not | Listeners use different container factories | Attach converter to the exact factory referenced in `@KafkaListener` |

When troubleshooting, check in order: the payload type before sending, which `KafkaTemplate` overload is called, the converter attached to the template/container factory, the actual serializer/deserializer, and the listener parameter type.

## 14. When should you use MessageConverter for JSON?

Use `MessageConverter` when the application works heavily with Spring `Message<?>`, needs payload and header mapping, or wants listeners to receive objects directly from JSON Strings/byte arrays without invoking Jackson manually.

Use `JsonSerializer`/`JsonDeserializer` when you want the Kafka client responsible for converting objects to JSON bytes and the application sends directly with standard `KafkaTemplate` overloads.

Whichever approach you choose, producer and consumer must agree on the JSON contract, data types, headers, versioning, and error handling policy. Do not let both the serializer and the converter transform the same payload under two different contracts.

Implementation checklist:

- [ ] Decided whether to use `JsonSerializer`/`JsonDeserializer` or `MessageConverter`.
- [ ] If using `StringJsonMessageConverter`, configured `StringSerializer` and `StringDeserializer`.
- [ ] Attached the converter to `KafkaTemplate` for the `send(Message<?>)` path.
- [ ] Attached the converter to the right listener container factory.
- [ ] Used concrete listener parameter types where possible.
- [ ] Aligned `ObjectMapper`, date/time formats, and JSON contracts.
- [ ] Managed type headers and trusted packages intentionally.
- [ ] Distinguished Kafka deserialization, message conversion, and validation errors.
- [ ] Tested valid JSON, malformed JSON, headers, and event versions.
- [ ] Did not confuse `send(topic, key, value)` with `send(Message<?>)`.

`MessageConverter` helps Spring Kafka bridge Spring's message model with Kafka records and convert JSON into objects that listeners can process. Configuring the right converter alongside compatible serializers/deserializers keeps application code clean, leverages headers effectively, and reduces manual data conversion inside each publisher or listener.
