# Type Headers and Java Type Information

When sending Java objects over Kafka as JSON, the producer converts objects into bytes to write into records. The consumer receives those bytes and needs to know which Java class to deserialize into. Looking at the JSON alone is often insufficient to distinguish object types with similar structures, especially when a single topic carries multiple event types.

Spring Kafka solves this using **type headers**: `JsonSerializer` can attach Java type metadata to Kafka headers, while `JsonDeserializer` reads that metadata to choose the target type. This mechanism is useful when a topic carries multiple event types or payloads with distinct concrete types. However, Java class names should not become a tightly coupled contract between services; type mapping, trusted packages, and default types help control type exchange safely.

## 1. Why Is Java Type Information Needed?

Suppose the `orders.events` topic receives two event types declared in separate Java files:

```java
// OrderCreated.java
package com.example.events;

import java.time.Instant;

public record OrderCreated(String orderId, Instant createdAt) {}
```

```java
// OrderPaid.java
package com.example.events;

import java.math.BigDecimal;
import java.time.Instant;

public record OrderPaid(String orderId, BigDecimal amount, Instant paidAt) {}
```

The JSON for both event types may share several fields, yet the consumer needs to instantiate the right object to run business logic. If everything is deserialized into a `Map` or a generic DTO, the application has to inspect fields and convert manually.

Spring Kafka's JSON serializer can write type metadata into record headers:

```text
Kafka record
  key: order-1001
  value: {"orderId":"order-1001","createdAt":"..."}
  headers:
    __TypeId__: com.example.events.OrderCreated
```

The consumer uses `__TypeId__` to identify the Java class to instantiate. In the example above, `JsonDeserializer` can deserialize the value into `OrderCreated` rather than a generic type.

Type headers are metadata on the Kafka record, not fields added to the JSON payload. Producers can keep clean JSON in the value while passing type information in headers.

## 2. Spring Kafka Type Headers

Spring Kafka's JSON type mapper uses several conventional header names:

| Header | Meaning |
|---|---|
| `__TypeId__` | Primary type of the serialized object, usually a class name or mapping token |
| `__ContentTypeId__` | Element type inside a container such as a collection or array |
| `__KeyTypeId__` | Key type of a map-like structure |

For a simple object, `__TypeId__` is typically the most important header. For complex types such as `List<OrderLine>` or `Map<String, OrderLine>`, content/key type metadata provides the generic type details that Java type erasure cannot recover from the container class name alone.

The default header value can be a fully qualified class name, such as `com.example.events.OrderCreated`. If producer and consumer use different packages or are implemented in different languages, relying on fully qualified class names makes the messaging contract fragile during refactoring. Spring Kafka supports type mapping to replace class names with stable tokens.

## 3. How Do JsonSerializer and JsonDeserializer Work Together?

In a standard JSON setup, `JsonSerializer` adds type headers and `JsonDeserializer` uses those headers to select the target Java type. Both components can be configured via Spring Boot.

Processing flow:

```text
Producer
  OrderCreated object
       |
       v
  JsonSerializer
       |
       +---- JSON bytes (record value)
       +---- __TypeId__ (record header)
       |
       v
  Kafka topic
       |
       v
  JsonDeserializer
       |
       +---- read __TypeId__ or default type
       +---- check trusted packages
       +---- instantiate matching Java object
       |
       v
  @KafkaListener
```

Defaults and exact API details may vary across Spring Kafka versions. In common versions, adding type headers on the JSON serializer and using type headers on the JSON deserializer are enabled by default. When changing configuration, verify against the exact library version your application uses.

### Configuring a Producer to Send JSON

Spring Boot example using `String` for keys and JSON for values:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
```

The producer sends objects through `KafkaTemplate`:

```java
import java.time.Instant;
import com.example.events.OrderCreated;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

@Service
class OrderEventPublisher {

    private final KafkaTemplate<String, Object> kafkaTemplate;

    OrderEventPublisher(KafkaTemplate<String, Object> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(String orderId) {
        var event = new OrderCreated(orderId, Instant.now());
        kafkaTemplate.send("orders.events", orderId, event);
    }
}
```

`JsonSerializer` serializes the object into JSON bytes and, by default, attaches the runtime type's metadata to headers. The key still uses `StringSerializer`, so the key needs no JSON type header.

### Configuring a Consumer to Read JSON via Type Headers

```yaml
spring:
  kafka:
    consumer:
      group-id: order-projection
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.trusted.packages: com.example.events
```

When the consumer receives a record whose `__TypeId__` points to `com.example.events.OrderCreated`, `JsonDeserializer` can instantiate `OrderCreated` if the class exists and its package is trusted.

The listener can declare the concrete type:

```java
import java.time.Instant;
import com.example.events.OrderCreated;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
class OrderCreatedListener {

    @KafkaListener(topics = "orders.events", groupId = "order-created-projection")
    public void consume(OrderCreated event) {
        updateOrderProjection(event.orderId(), event.createdAt());
    }

    private void updateOrderProjection(String orderId, Instant createdAt) {
        // Update the order read model.
    }
}
```

In this illustrative example, `Instant` imports and the DTOs must exist in the project. If a listener needs to handle multiple event types, pick a suitable common type or use `ConsumerRecord<String, Object>` and branch by runtime type.

## 4. Type Mapping: Using Tokens Instead of Full Class Names

Type mapping lets you associate a short token with a Java class. For example:

```text
orderCreated:com.example.events.OrderCreated
orderPaid:com.example.events.OrderPaid
```

When the producer serializes `OrderCreated`, the `__TypeId__` header can contain the token `orderCreated` instead of the fully qualified class name. A consumer with the corresponding mapping resolves that token to the Java class `OrderCreated`.

### Declaring Mappings on Producer and Consumer

Producer:

```yaml
spring:
  kafka:
    producer:
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      properties:
        spring.json.type.mapping: >-
          orderCreated:com.example.events.OrderCreated,
          orderPaid:com.example.events.OrderPaid
```

Consumer:

```yaml
spring:
  kafka:
    consumer:
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.trusted.packages: com.example.events
        spring.json.type.mapping: >-
          orderCreated:com.example.events.OrderCreated,
          orderPaid:com.example.events.OrderPaid
```

Both sides must agree on the token, but they do not have to use the same Java class or package. The producer uses the mapping to translate its local Java class into a token when writing headers; the consumer uses the mapping to translate that token into the consumer's DTO. If the consumer lacks a matching mapping, the deserializer may fail to resolve the target type.

For example, producer and consumer can use different mappings sharing the same token:

```yaml
# Producer
spring.kafka.producer.properties.spring.json.type.mapping: >-
  orderCreated:com.orders.internal.event.OrderCreated
```

```yaml
# Consumer
spring:
  kafka:
    consumer:
      properties:
        spring.json.type.mapping: >-
          orderCreated:com.reporting.contract.OrderCreatedMessage
        spring.json.trusted.packages: com.reporting.contract
```

This allows both services to share the `orderCreated` contract without depending on each other's internal packages.

Tokens should represent the contract's event type, such as `orderCreated`, rather than implementation names like `OrderCreatedV2Internal`. When packages change or Java classes are refactored, the token can stay stable while each service updates its own mapping.

## 5. One Topic Carrying Multiple Event Types

Type mapping is valuable when a single topic holds multiple event types with different structures. Each record carries its own type header, allowing the deserializer to construct the matching object type per record.

Example declaring two events:

```java
package com.example.events;

import java.time.Instant;

public record OrderCreated(String orderId, Instant createdAt) {}
```

```java
package com.example.events;

import java.math.BigDecimal;
import java.time.Instant;

public record OrderPaid(String orderId, BigDecimal amount, Instant paidAt) {}
```

The producer can send both object types to the same topic:

```java
import com.example.events.OrderCreated;
import com.example.events.OrderPaid;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

@Service
class MixedOrderEventPublisher {

    private final KafkaTemplate<String, Object> kafkaTemplate;

    MixedOrderEventPublisher(KafkaTemplate<String, Object> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(OrderCreated created, OrderPaid paid) {
        kafkaTemplate.send("orders.events", created.orderId(), created);
        kafkaTemplate.send("orders.events", paid.orderId(), paid);
    }
}
```

With the configured mapping, the corresponding headers might be:

```text
Record 1: __TypeId__ = orderCreated
Record 2: __TypeId__ = orderPaid
```

The listener accepts the general `Object` type and dispatches based on runtime type:

```java
import com.example.events.OrderCreated;
import com.example.events.OrderPaid;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
class OrderEventRouter {

    @KafkaListener(topics = "orders.events", groupId = "order-event-router")
    public void consume(Object event) {
        if (event instanceof OrderCreated created) {
            handleCreated(created);
        } else if (event instanceof OrderPaid paid) {
            handlePaid(paid);
        } else {
            throw new IllegalArgumentException(
                    "Unsupported event type: "
                            + (event == null ? "null" : event.getClass().getName())
            );
        }
    }

    private void handleCreated(OrderCreated event) {
        // Handle OrderCreated.
    }

    private void handlePaid(OrderPaid event) {
        // Handle OrderPaid.
    }
}
```

This is routing by Java class after deserialization. In multi-service systems, you can also design an event interface or a business discriminator inside the payload. Avoid letting consumers depend on the producer's internal implementation names.

## 6. Default Type When Records Lack Type Headers

Not every producer sends Spring Kafka type headers. Records may originate from another producer, predate enabling type headers, or come from a producer that disabled header metadata.

If the consumer already knows the payload type, you can configure a default type:

```yaml
spring:
  kafka:
    consumer:
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.value.default.type: com.example.events.OrderCreated
        spring.json.trusted.packages: com.example.events
```

When a record has no type header and no other target type is determined, `JsonDeserializer` can use the configured default type to instantiate `OrderCreated`. Default types are especially useful when a topic contains a single payload type and the producer does not need to emit type metadata.

To always use the default type and ignore type headers, configure:

```yaml
spring:
  kafka:
    consumer:
      properties:
        spring.json.use.type.headers: false
        spring.json.value.default.type: com.example.events.OrderCreated
        spring.json.trusted.packages: com.example.events
```

When `spring.json.use.type.headers` is `false`, the deserializer does not use type headers to select the target type. Ensure every record read by this consumer can deserialize into the default type; this configuration is unsuitable if the topic carries multiple distinct event types.

You can configure a default type for keys via `spring.json.key.default.type` when keys are also deserialized as JSON. In many systems, keys are simple strings or numbers, making `StringDeserializer` or the corresponding primitive deserializer easier to manage.

## 7. Trusted Packages and Safe Deserialization

Type headers can contain class names or tokens sent by producers. Consumers should not blindly trust every class name coming from uncontrolled sources. Spring Kafka's JSON deserializer uses trusted packages to restrict which packages are allowed for object instantiation.

Example trusting only packages containing event contracts:

```yaml
spring:
  kafka:
    consumer:
      properties:
        spring.json.trusted.packages: com.example.events,com.example.shared.contract
```

Do not configure the `*` wildcard in production without clear justification and controls. Trusting all packages widens the range of classes the deserializer can instantiate. Allow only the packages containing required DTOs or event contracts.

Common errors:

- Header contains a class name not present on the consumer classpath.
- Token in `__TypeId__` has no matching mapping.
- Target class's package has not been added to trusted packages.
- Producer and consumer disagree on JSON structure or event version.
- Consumer forces every record into one default type while the topic holds multiple event types.

When encountering deserialization errors, check type headers, mappings, classpath, and trusted packages before broadening configuration.

## 8. Keeping or Removing Type Headers

Type headers are helpful metadata, though not every consumer needs them. Some systems want JSON payloads independent of Java classes, especially when consumers are written in Python, Go, or another platform.

The producer can disable adding type headers:

```yaml
spring:
  kafka:
    producer:
      properties:
        spring.json.add.type.headers: false
```

The consumer can ignore type headers and use a default type or an application-determined type:

```yaml
spring:
  kafka:
    consumer:
      properties:
        spring.json.use.type.headers: false
        spring.json.value.default.type: com.example.events.OrderCreated
        spring.json.trusted.packages: com.example.events
```

Additionally, `JsonDeserializer` by default removes type headers after using them to deserialize. If the application needs to read these headers inside the listener, configure:

```yaml
spring:
  kafka:
    consumer:
      properties:
        spring.json.remove.type.headers: false
```

When retained, the listener can access them via `ConsumerRecord.headers()`. If headers have been stripped by the deserializer, do not assume they remain present just because the producer sent them. Consider carefully before enabling header retention if downstream steps will inspect or forward this metadata.

## 9. Type Headers Do Not Replace Event Versioning

A type header specifies which Java class a record should deserialize into. It does not fully describe the schema version, field compatibility rules, or business meaning of the payload.

For example, `OrderCreated` may evolve over multiple versions:

```text
orderCreated
  version 1: orderId, createdAt
  version 2: orderId, createdAt, channel
```

Both can still share the type token `orderCreated`, but the consumer must know whether the new field is optional or required and how to handle older records. You can include `schemaVersion` in the payload or a separate header, maintain backward compatibility, and deploy producers and consumers in an appropriate sequence.

For systems using Avro, Protobuf, or JSON Schema with Schema Registry, the registry's schema IDs/versions and compatibility rules serve as the dedicated source of schema metadata. Spring Kafka type headers do not replace those mechanisms.

## 10. Common Misconceptions

1. **Assuming `__TypeId__` is a field inside the JSON.** It is a Kafka header, outside the record value.
2. **Assuming every producer sends type headers.** Non-Spring Kafka producers or producers with type headers disabled may omit them.
3. **Assuming type mapping only needs to be configured on the producer.** The consumer needs a corresponding mapping to translate tokens into Java classes.
4. **Using fully qualified class names as a long-term inter-service contract.** Package refactoring can break consumer deserialization; stable mapping tokens reduce coupling.
5. **Trusting all packages with a wildcard.** Restrict trusted packages to only the necessary DTO/event contracts.
6. **Assuming a default type handles polymorphic topics.** A single default type only works when payloads share one type or the consumer applies custom conversion logic.
7. **Assuming a type header equals a schema version.** Java types and contract versions are distinct concepts.
8. **Assuming headers are guaranteed to remain in the listener.** `JsonDeserializer` may remove type headers after use; set `spring.json.remove.type.headers` if retention is needed.

Type headers help Spring Kafka turn JSON bytes into the right Java types without embedding class names into the payload. Use type mapping to stabilize contracts between producers and consumers, configure trusted packages under the principle of least privilege, and pick a default type or disable type headers when a topic has a single fixed payload type. For topics carrying multiple event types, align mappings and versioning so services can deserialize data safely across deployments.
