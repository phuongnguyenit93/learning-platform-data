# JsonSerializer and JsonDeserializer

Kafka stores records as byte arrays. Producers must convert keys and values from Java types into bytes before sending; consumers must convert received bytes back into data types the application can use. This process is called serialization and deserialization.

In Spring Kafka, `JsonSerializer` and `JsonDeserializer` allow services to exchange events in JSON without calling `ObjectMapper` manually in every service. A producer can send a Java DTO, and the consumer receives the corresponding DTO. For both sides to understand the same data contract, you need consistent serializer/deserializer configuration, intentional management of type headers, and control over trusted packages allowed for deserialization.

## 1. Serialization and Deserialization in Kafka

Kafka brokers do not understand Java objects. Brokers receive keys and values as bytes and store them in partition logs. Conversion takes place on the producer and consumer sides:

```text
Producer application
  OrderCreatedEvent (Java object)
           |
           v
     JsonSerializer
           |
           v
      JSON bytes
           |
           v
       Kafka broker
           |
           v
      JSON bytes
           |
           v
    JsonDeserializer
           |
           v
  OrderCreatedEvent (Java object)
           |
           v
     Consumer listener
```

`JsonSerializer` uses Jackson to convert an object into JSON. `JsonDeserializer` uses Jackson to read JSON and instantiate a Java object. Kafka merely transports bytes; the broker neither converts JSON into DTOs nor validates JSON structure against application Java classes.

Example event:

```java
package com.example.messaging.event;

import java.math.BigDecimal;
import java.time.Instant;

public record OrderCreatedEvent(
        String eventId,
        String orderId,
        BigDecimal total,
        Instant occurredAt) {
}
```

This record represents the payload contract between producer and consumer. Both services must agree on field names, data types, semantics, and schema evolution rules.

## 2. Configuring JsonSerializer and JsonDeserializer with Spring Boot

With Spring Boot, configure serializers and deserializers in `application.yml`:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
    consumer:
      group-id: order-projection
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        "[spring.json.trusted.packages]": com.example.messaging.event
```

The producer uses `StringSerializer` for the key and `JsonSerializer` for the value. The consumer uses `StringDeserializer` for the key and `JsonDeserializer` for the value. `trusted.packages` restricts the packages that the deserializer is permitted to instantiate via type headers.

After configuring, you can inject a template with matching generic types:

```java
import com.example.messaging.event.OrderCreatedEvent;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(OrderCreatedEvent event) {
        kafkaTemplate.send("orders.created", event.orderId(), event);
    }
}
```

The listener receives the deserialized DTO:

```java
import com.example.messaging.event.OrderCreatedEvent;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderProjectionListener {

    @KafkaListener(topics = "orders.created", groupId = "order-projection")
    public void onMessage(OrderCreatedEvent event) {
        // Update read model from event.
    }
}
```

`KafkaTemplate<String, OrderCreatedEvent>` and DTO-typed listeners let business code work directly with objects. Generic types do not configure serializers automatically; the key/value types in code must match the serializers/deserializers configured on the producer and consumer factories.

## 3. Type Headers in JSON Messages

By default, Spring Kafka's `JsonSerializer` adds type information to Kafka headers. This header indicates which Java class the producer serialized, such as `com.example.messaging.event.OrderCreatedEvent`. `JsonDeserializer` can read the type header to determine which class to instantiate.

Default flow:

```text
Producer
  Java DTO
     |
     v
  JsonSerializer
     |------------------------------|
     v                              v
  JSON value                 Type information header
     |                              |
     +---------------+--------------+
                     v
                  Kafka
                     |
                     v
              JsonDeserializer
                     |
          reads type header to select class
                     |
                     v
                 Java DTO
```

Type headers are convenient when multiple event types share a topic or when the consumer needs to distinguish payload types. However, the default header can contain the producer's package and class name. This creates coupling between services: if the producer renames its package or class, the consumer may no longer be able to resolve that type.

For independent services, do not treat internal Java class names as a stable integration contract by default. You can use type mappings to map short tokens to local classes, or disable type headers and declare a fixed target type on the consumer.

## 4. Disabling Type Headers and Declaring a Default Type

If a topic carries only a single event type, the consumer can use a default type instead of relying on class names sent by the producer in headers.

```yaml
spring:
  kafka:
    producer:
      properties:
        "[spring.json.add.type.headers]": false
    consumer:
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        "[spring.json.use.type.headers]": false
        "[spring.json.value.default.type]": com.example.messaging.event.OrderCreatedEvent
        "[spring.json.trusted.packages]": com.example.messaging.event
```

In this configuration:

- `spring.json.add.type.headers=false` instructs the serializer not to add type information headers.
- `spring.json.use.type.headers=false` instructs the deserializer not to use type headers when choosing a class.
- `spring.json.value.default.type` specifies the Java class used to deserialize the value.
- `spring.json.trusted.packages` specifies the allowed packages when the deserializer processes Java types.

This approach works well when a topic has a single well-defined schema/event type and the consumer knows the target DTO ahead of time. If a topic carries multiple event types, a single default type will not suffice; use type mappings, an envelope with an `eventType` field, or an appropriate topic/schema design.

## 5. Using Type Mapping to Reduce Class Name Coupling

Spring Kafka supports type mapping: the producer sends a token instead of a full class name, and the consumer maps that token to its own local class. This lets producer and consumer place their DTOs in different packages.

Producer example:

```yaml
spring:
  kafka:
    producer:
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      properties:
        "[spring.json.type.mapping]": orderCreated:com.example.producer.event.OrderCreatedEvent
```

Consumer:

```yaml
spring:
  kafka:
    consumer:
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        "[spring.json.type.mapping]": orderCreated:com.example.consumer.contract.OrderCreated
        "[spring.json.trusted.packages]": com.example.consumer.contract
```

The producer emits the token `orderCreated` in the type header. The consumer receives that token and maps it to `com.example.consumer.contract.OrderCreated`. The two classes do not need to share the same package or name, though the JSON structure and field semantics must still be compatible.

When there are multiple event types, you can declare multiple token/class pairs in `spring.json.type.mapping`, separated by commas. Each token should be stable, descriptive, and managed as part of the data contract.

Type mapping only solves mapping a type identifier to a class. It does not perform arbitrary schema transformations, rename fields, or guarantee compatibility between two differing JSON structures.

## 6. Trusted Packages and Safe Deserialization

When `JsonDeserializer` uses type headers to select a class, it must verify whether the package is trusted. Configuring `spring.json.trusted.packages` restricts the valid packages.

Example:

```yaml
spring:
  kafka:
    consumer:
      properties:
        "[spring.json.trusted.packages]": com.example.messaging.event,com.example.shared.contract
```

Add only packages containing DTOs that the application explicitly controls. Do not casually use the wildcard `*` just to silence trusted-package errors. For topics receiving data from external systems, exercise extra caution since both type metadata and payload originate from another source.

Trusted packages do not replace producer authentication, Kafka ACLs, or business data validation. After deserialization, the application still needs to validate required fields, size limits, value ranges, and authorization to perform operations.

## 7. Are Type Headers Kept or Removed After Deserialization?

Under Spring Kafka's default configuration, `JsonDeserializer` removes type information headers after deserializing. This prevents internal producer metadata from automatically propagating to subsequent publishes if an application consumes and re-emits records.

You can control this behavior via property:

```yaml
spring:
  kafka:
    consumer:
      properties:
        "[spring.json.remove.type.headers]": false
```

Keep type headers only if the application genuinely needs them for downstream steps. When republishing events, explicitly decide which type metadata belongs to the public contract; do not blindly forward internal headers or headers that may expose inappropriate details.

## 8. Configuring in Java Instead of application.yml

When you need custom-configured serializers/deserializers, you can declare them directly in Java:

```java
import java.util.HashMap;
import java.util.Map;

import com.example.messaging.event.OrderCreatedEvent;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.apache.kafka.common.serialization.StringSerializer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;
import org.springframework.kafka.core.ProducerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.support.serializer.JsonSerializer;
import org.springframework.kafka.support.serializer.JsonDeserializer;

@Configuration
public class JsonKafkaConfiguration {

    @Bean
    public ProducerFactory<String, OrderCreatedEvent> orderProducerFactory() {
        Map<String, Object> properties = new HashMap<>();
        properties.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
                "localhost:9092");
        return new DefaultKafkaProducerFactory<>(
                properties,
                new StringSerializer(),
                new JsonSerializer<>());
    }

    @Bean
    public ConsumerFactory<String, OrderCreatedEvent> orderConsumerFactory() {
        Map<String, Object> properties = new HashMap<>();
        properties.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
                "localhost:9092");
        properties.put(ConsumerConfig.GROUP_ID_CONFIG,
                "order-projection");

        JsonDeserializer<OrderCreatedEvent> valueDeserializer =
                new JsonDeserializer<>(OrderCreatedEvent.class);
        valueDeserializer.addTrustedPackages(
                "com.example.messaging.event");

        return new DefaultKafkaConsumerFactory<>(
                properties,
                new StringDeserializer(),
                valueDeserializer);
    }
}
```

This snippet illustrates explicit serializer/deserializer instantiation, not a complete production configuration. In real applications, add security properties, client IDs, template/listener factory beans, and environment-specific settings.

When configuring serializers/deserializers via constructors or setters, avoid simultaneously reconfiguring the same instance via a property map if the Spring Kafka version's API disallows mixing both styles. Pick one consistent configuration style to prevent overridden values or initialization errors.

## 9. Common Errors During Serialization and Deserialization

| Error | Common cause | Resolution |
| --- | --- | --- |
| `SerializationException` on send | Value cannot be serialized or type mismatch | Inspect DTO, Jackson modules, and configured serializer |
| `DeserializationException` on receive | Malformed JSON, incompatible field, or unresolvable class | Check payload, type header, default type, and DTO |
| `ClassNotFoundException` | Type header contains a class name missing on the consumer | Use type mapping or a default type |
| Trusted package error | Package in type header is not permitted | Add only trusted DTO packages to the allowlist |
| Producer sends fine but consumer cannot read DTO | Mismatched serializer/deserializer or differing type mapping tokens | Align configuration and JSON contract |
| New field breaks old consumers | Incompatible schema change | Use optional/default fields, versioning, and compatibility tests |
| Consumer receives `null` | Record has a `null` value, common with tombstones in compacted topics | Handle `null` explicitly and distinguish tombstones from JSON payloads |

## 10. Handling Deserialization Errors Before the Listener Is Invoked

Deserialization occurs before the `@KafkaListener` method receives an object. If the JSON is invalid or the type is rejected, the listener may not be called; the exception arises in the consumer poll/adapter before entering business code.

Spring Kafka provides `ErrorHandlingDeserializer` to wrap the actual deserializer and convert deserialization failures into error information that the container/error handler can process. Example:

```yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        "[spring.deserializer.key.delegate.class]": org.apache.kafka.common.serialization.StringDeserializer
        "[spring.deserializer.value.delegate.class]": org.springframework.kafka.support.serializer.JsonDeserializer
        "[spring.json.value.default.type]": com.example.messaging.event.OrderCreatedEvent
        "[spring.json.trusted.packages]": com.example.messaging.event
```

With this configuration, `ErrorHandlingDeserializer` delegates keys to `StringDeserializer` and values to `JsonDeserializer`. When deserialization fails, the application must configure an appropriate error handler/recoverer, such as routing failed records to a DLT. Test both key errors and value errors because they may be handled differently.

Do not catch deserialization errors and replace corrupted payloads with empty objects without recording the cause. Doing so can turn corrupted data into seemingly valid events and corrupt business state.

## 11. Designing JSON Events for Cross-Service Compatibility

JSON keeps services independent of Java-specific byte formats, but it does not automatically guarantee schema compatibility. Design events as public contracts:

- Use stable, domain-meaningful field names.
- Prefer adding new fields in ways older consumers can ignore or fill with defaults.
- Avoid changing data types or repurposing fields currently in use.
- Include `eventId`, `eventType`, `occurredAt`, and aggregate ID when traceability is needed.
- Never serialize JPA entities directly or internal objects with lazy/circular relationships.
- Manage event versions when introducing breaking structural changes.

Example envelope:

```json
{
  "eventId": "evt-8f4c2a",
  "eventType": "OrderCreated",
  "schemaVersion": 1,
  "occurredAt": "2026-11-17T03:00:00Z",
  "aggregateId": "ORD-1042",
  "data": {
    "total": 125000.00,
    "currency": "VND"
  }
}
```

An envelope clarifies metadata and business payload. For systems with multiple programming languages or strict schema governance requirements, consider Avro/Protobuf with a schema registry instead of relying solely on Java classes and Jackson type headers.

## 12. Testing JsonSerializer and JsonDeserializer

Tests should verify both the JSON structure and the deserialized object. Example unit test using both components directly:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import java.time.Instant;

import com.example.messaging.event.OrderCreatedEvent;
import org.apache.kafka.common.header.internals.RecordHeaders;
import org.junit.jupiter.api.Test;
import org.springframework.kafka.support.serializer.JsonSerializer;
import org.springframework.kafka.support.serializer.JsonDeserializer;

class OrderJsonSerializationTest {

    @Test
    void serializesAndDeserializesOrderEvent() {
        OrderCreatedEvent original = new OrderCreatedEvent(
                "evt-1",
                "ORD-42",
                new BigDecimal("125000.00"),
                Instant.parse("2026-11-17T03:00:00Z"));

        JsonSerializer<OrderCreatedEvent> serializer =
                new JsonSerializer<>();
        byte[] bytes = serializer.serialize("orders.created", original);

        JsonDeserializer<OrderCreatedEvent> deserializer =
                new JsonDeserializer<>(OrderCreatedEvent.class);
        deserializer.addTrustedPackages("com.example.messaging.event");
        OrderCreatedEvent restored = deserializer.deserialize(
                "orders.created", new RecordHeaders(), bytes);

        assertThat(restored).isEqualTo(original);
    }
}
```

Because this example calls the `serialize` overload without headers, the deserializer uses `OrderCreatedEvent.class` as its fixed target type. When testing flows with type headers, pass the same headers produced by the producer to verify type mapping as well. In integration tests, use a test broker and verify records flow through the application's actual producer/consumer factories.

Cases to test:

1. Valid DTOs serialize to JSON and deserialize to exact values.
2. Producer and consumer use compatible type mapping tokens.
3. Consumer works when type headers are disabled and a default type is configured.
4. Malformed JSON passes through `ErrorHandlingDeserializer` and the error handler.
5. Payloads with new fields or missing optional fields are handled per schema policy.
6. Tombstones/`null` values are handled explicitly.

## 13. When to Use JSON vs. Other Formats

| Format | Strengths | Considerations |
| --- | --- | --- |
| JSON with `JsonSerializer`/`JsonDeserializer` | Human-readable, easy to debug, integrates with Jackson and Java DTOs | Payloads can be larger than binary; requires managing schemas and type metadata |
| String/byte array | Simple, full format control | Application parses and validates manually |
| Avro | Explicit schema, supports evolution and compact binary representation | Usually requires a schema registry and schema management process |
| Protobuf | Clear message contract, efficient, and polyglot | Requires managing `.proto` files, generated code, and compatibility |

JSON fits many Spring systems that need a quick start and prioritize readability. As the number of services, languages, or schema governance demands grows, schema-backed formats like Avro or Protobuf may be a better fit.

## 14. Conclusion

`JsonSerializer` converts Java objects into JSON bytes when a producer sends records; `JsonDeserializer` converts JSON bytes into DTOs when a consumer receives records. Spring Kafka can pass type information via Kafka headers, use a default type for single-payload topics, or use type mapping to avoid class-name coupling across services.

Configure key/value serializers with the right types, restrict trusted packages, align type mappings, and design JSON events as contracts independent of internal classes. For malformed payloads, use `ErrorHandlingDeserializer` paired with an error handler/DLT for clear management. Correct serialization is only the first step; schema compatibility, validation, idempotency, and integration testing are what keep messaging pipelines reliable.

## References

- [Spring for Apache Kafka — Serialization, Deserialization, and Message Conversion](https://docs.spring.io/spring-kafka/reference/kafka/serdes.html)
- [Spring for Apache Kafka — Serialization/Deserialization Properties](https://docs.spring.io/spring-kafka/reference/kafka/serdes.html#serdes-json-config)
- [Spring for Apache Kafka — ErrorHandlingDeserializer](https://docs.spring.io/spring-kafka/reference/kafka/serdes.html#error-handling-deserializer)
- [Jackson — Annotations and Databinding](https://github.com/FasterXML/jackson-databind)
