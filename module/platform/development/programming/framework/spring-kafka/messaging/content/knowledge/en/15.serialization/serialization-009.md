# Configuring Default Types

## 1. What Problem Does a Default Type Solve?

Kafka stores keys and values as bytes. When a consumer reads a record, the deserializer must know the target data type to turn those bytes into an object. For JSON, Spring Kafka provides `JsonSerializer` and `JsonDeserializer` to perform this conversion.

`JsonDeserializer` can obtain type information from type headers written by Spring Kafka's JSON serializer. However, not every producer creates those headers. A producer written in another language, a producer using a standard JSON serializer, or a system with type headers disabled may emit plain JSON only.

When the consumer already knows the expected payload type, you can configure a **default type** so `JsonDeserializer` falls back to a default class when no suitable type header exists. For example, if the `orders` topic only carries `OrderCreated` events, the consumer can default to deserializing values into `OrderCreated`.

Default types are especially useful when:

- The consumer receives JSON from a non-Spring Kafka producer.
- The producer does not emit type headers.
- The topic contract defines a specific payload type.
- The consumer wants to ignore type headers and always deserialize into a chosen DTO.

A default type is a consumer-side configuration. It does not alter the JSON sent by the producer and does not add metadata to records.

## 2. How Type Headers and Default Types Work Together

By default, Spring Kafka's `JsonSerializer` can add type information to Kafka record headers. `JsonDeserializer` uses type headers by default if present and enabled. The default type acts as a fallback when no type information is available to determine the target class.

Common type headers include:

| Header | Purpose |
|---|---|
| `__TypeId__` | Primary type of the payload/value |
| `__KeyTypeId__` | Type of the key when the key is also serialized as JSON |
| `__ContentTypeId__` | Element type inside a nested-content structure in supported cases |

Two common configuration approaches exist:

1. **Prefer type headers, use default type as fallback:** keep `spring.json.use.type.headers=true` (default). If a valid header exists, the deserializer uses the type from the header; if absent, it uses the default type.
2. **Ignore type headers, always use default type:** set `spring.json.use.type.headers=false`. This fits when a topic has a fixed payload type or the producer sends plain JSON and the consumer wants to control the target type.

If type headers are enabled and a header points to a nonexistent or untrusted class, the deserializer may fail. Do not treat a default type as an automatic fix for broken type headers. When you want to lock down the target type, explicitly disable type header usage.

## 3. Configuring a Default Value Type with Spring Boot

Suppose the `orders` topic contains JSON solely for this class:

```java
package com.example.messaging.events;

public record OrderCreated(
        String eventId,
        String orderId,
        BigDecimal total) {}
```

The consumer can configure `spring.json.value.default.type` in `application.yml`:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: order-service
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.value.default.type: com.example.messaging.events.OrderCreated
        spring.json.use.type.headers: false
        spring.json.trusted.packages: com.example.messaging.events
```

Meaning:

- `value-deserializer` selects `JsonDeserializer` for values.
- `spring.json.value.default.type` specifies the Java class used to deserialize values.
- `spring.json.use.type.headers: false` instructs the deserializer to ignore type headers and use the default type.
- `spring.json.trusted.packages` restricts the packages permitted when resolving type information.

In this example, the key is a string, so `StringDeserializer` is used; no default type is needed for the key. If the key is also a JSON object, configure the matching key serializer/deserializer and consider `spring.json.key.default.type`.

### Producer Sending JSON

The producer can use `JsonSerializer`:

```yaml
spring:
  kafka:
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
```

Service emitting the event:

```java
@Service
public class OrderEventPublisher {
    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderCreated>> publish(
            OrderCreated event) {
        return kafkaTemplate.send("orders", event.orderId(), event);
    }
}
```

A consumer using the default type can receive the payload directly:

```java
@Component
public class OrderCreatedListener {

    @KafkaListener(topics = "orders", groupId = "order-service")
    public void onOrderCreated(OrderCreated event) {
        // Process the event deserialized as OrderCreated.
    }
}
```

The generic type `KafkaTemplate<String, OrderCreated>` makes Spring wiring and producer code type-clear. Generic Java types are not sent across Kafka as part of the payload; consumer-side deserialization still depends on bytes, serializers, type headers, and default types.

## 4. Configuring Default Types in Java

If constructing a `ConsumerFactory` manually, you can configure `JsonDeserializer` properties in a map:

```java
@Configuration
public class KafkaConsumerConfiguration {

    @Bean
    ConsumerFactory<String, OrderCreated> orderConsumerFactory() {
        Map<String, Object> props = new HashMap<>();
        props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
        props.put(ConsumerConfig.GROUP_ID_CONFIG, "order-service");
        props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
                StringDeserializer.class);
        props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
                JsonDeserializer.class);
        props.put(JsonDeserializer.VALUE_DEFAULT_TYPE,
                OrderCreated.class.getName());
        props.put(JsonDeserializer.USE_TYPE_INFO_HEADERS, false);
        props.put(JsonDeserializer.TRUSTED_PACKAGES,
                "com.example.messaging.events");

        return new DefaultKafkaConsumerFactory<>(props);
    }
}
```

The constants `JsonDeserializer.VALUE_DEFAULT_TYPE`, `USE_TYPE_INFO_HEADERS`, and `TRUSTED_PACKAGES` correspond to `spring.json.value.default.type`, `spring.json.use.type.headers`, and `spring.json.trusted.packages`.

When declaring a custom `ConsumerFactory`, ensure the listener container factory uses this bean. If Spring Boot already auto-configures another `ConsumerFactory`, use explicit bean names and wiring so listeners do not accidentally use the default configuration.

You can configure the deserializer directly via constructor or fluent API instead of a property map. Once `JsonDeserializer` is configured via setters or fluent API, avoid mixing property-map configuration for the same deserializer; choose one consistent approach and verify the behavior on your Spring Kafka version.

## 5. Default Types for Both Key and Value

A Kafka record has two distinct data parts: key and value. If both are serialized as JSON, default types can be configured independently:

```yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.key.default.type: com.example.messaging.OrderKey
        spring.json.value.default.type: com.example.messaging.events.OrderCreated
        spring.json.use.type.headers: false
        spring.json.trusted.packages: com.example.messaging
```

`spring.json.key.default.type` specifies the type for the key; `spring.json.value.default.type` specifies the type for the value. Do not set a single shared default type expecting the deserializer to infer two different types automatically.

In many systems, keys remain strings such as `orderId`, while values are JSON DTOs. In that case, use `StringDeserializer` for keys and `JsonDeserializer` for values. This is simpler, easier to observe, and avoids unnecessary complexity on the key.

## 6. Default Types Without Disabling Type Headers

Setting `spring.json.use.type.headers=false` is not always necessary. If a Spring Kafka producer sends valid type headers, the consumer can use headers to identify the class. The default type is used only when required type information is absent.

Example:

```yaml
spring:
  kafka:
    consumer:
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.value.default.type: com.example.messaging.events.OrderCreated
        spring.json.use.type.headers: true
        spring.json.trusted.packages: com.example.messaging.events
```

With this configuration:

- Records with valid type headers: the deserializer uses the type specified by the header.
- Records without type headers: the deserializer uses `OrderCreated` as the default type.
- Records with type headers pointing to an unloadable or untrusted class: deserialization may fail; the default type does not automatically override a bad header class.

Choose `true` when a topic can hold multiple payload types and producers send reliable type information. Choose `false` when a topic has a single fixed contract and the consumer wants to coerce every record into a specific DTO.

## 7. Distinguishing Default Type and Type Mapping

Default types and type mappings both relate to resolving Java types from JSON, but they solve different needs.

| Mechanism | Purpose | When to use |
|---|---|---|
| Default type | Specifies a fallback or fixed type for key/value | Topic has one payload type, or producer sends no type headers |
| Type mapping | Maps short tokens in type headers to Java classes | Topic carries multiple event types and you want to avoid sending full class names |
| Default type headers | Lets the serializer write type metadata so the deserializer infers the type | Producer and consumer share type contracts or compatible mappings |

For example, the `domain-events` topic carries two event types: `OrderCreated` and `PaymentReceived`. A single default type cannot represent both if the consumer needs to distinguish them. Type mapping can be used instead:

```yaml
spring:
  kafka:
    producer:
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      properties:
        spring.json.type.mapping: orderCreated:com.example.orders.OrderCreated,paymentReceived:com.example.payments.PaymentReceived
    consumer:
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.type.mapping: orderCreated:com.example.consumer.OrderCreated,paymentReceived:com.example.consumer.PaymentReceived
        spring.json.use.type.headers: true
        spring.json.trusted.packages: com.example.consumer
```

The producer writes the token `orderCreated` or `paymentReceived` into the type header instead of the full class name. The consumer maps that token to its corresponding DTO. Both sides can use different packages/class names as long as they agree on the tokens.

Do not set `spring.json.use.type.headers=false` in the type mapping example above, because the deserializer needs to read the type header to determine which type a record belongs to. If type headers are disabled, mappings are no longer used to resolve types by token.

## 8. Non-Spring Kafka Producers

A major advantage of default types is supporting producers outside the Spring ecosystem. For example, a Python application sending plain JSON to the `orders` topic:

```python
import json

payload = {
    "eventId": "evt-1001",
    "orderId": "ORD-1001",
    "total": 125.50
}

producer.send(
    "orders",
    key=b"ORD-1001",
    value=json.dumps(payload).encode("utf-8")
)
```

This producer does not add Spring Kafka-specific type headers. The Java consumer can use `JsonDeserializer` with `spring.json.value.default.type` to convert the JSON into `OrderCreated`, provided field names, data types, and schemas are compatible.

A default type only handles selecting the Java class. It does not translate differing schemas, rename fields, normalize date/time formats, or manage event versions. For polyglot systems, define a neutral schema and explicit compatibility rules; consider JSON Schema, Avro, or Protobuf with a schema registry if requirements demand it.

## 9. Security When Using Type Information

Type headers can carry class names or mapping tokens. When the deserializer uses this information to load classes, trusted packages must be restricted. `spring.json.trusted.packages` specifies the packages the deserializer is allowed to resolve.

Example:

```yaml
spring:
  kafka:
    consumer:
      properties:
        spring.json.trusted.packages: com.example.messaging.events,com.example.shared.events
```

Include only the DTO packages actually needed. Avoid configuring wildcard `*` in production without a clear reason and security review. Never treat type headers from external producers as trustworthy merely because they arrive inside a Kafka record.

If a topic has a single fixed payload type, setting a default type and disabling type headers can reduce reliance on producer-supplied class names. Even so, you must still validate payloads, bound record sizes, and handle malformed JSON.

## 10. Common Errors When Configuring Default Types

| Symptom | Possible cause | Check / Resolution |
|---|---|---|
| `No type information in headers and no default type provided` | Record lacks type headers and consumer has no default/target type configured | Set `spring.json.value.default.type` or configure target type via constructor |
| Class from type header not found | Producer sent a class name missing on the consumer or in a different package | Use shared-token type mapping, or disable type headers and set a default type for single-type topics |
| `not in the trusted packages` | Package in type header is missing from trusted list | Add the exact required DTO package to `spring.json.trusted.packages`; avoid opening wildcards casually |
| JSON parse/deserialization failure | Payload does not match DTO, incompatible field or data type | Inspect JSON bytes, schema, naming, and field types |
| Consumer always receives the wrong DTO | Type header takes precedence over default type | If locking down the DTO, set `spring.json.use.type.headers=false` |
| Multiple event types fail to deserialize | Only one default type configured for a topic carrying multiple payload types | Use type mapping/type headers or split topics by event type |
| YAML configuration has no effect | Wrong prefix, wrong indentation, or custom `ConsumerFactory` ignores Boot settings | Verify `spring.kafka.consumer.properties` and the actual bean used by the listener |

When investigating errors, check in order: active deserializer, actual JSON payload, type headers, default type, trusted packages, and DTO schema. Never fix errors by adding a wildcard package or forcing all payloads into one class without verifying the topic contract.

## 11. Testing Default Types

Tests should cover missing headers, present headers, and invalid headers:

1. **No type header:** send plain JSON to the topic and verify the consumer constructs `OrderCreated` from the default type.
2. **With type header and `use.type.headers=true`:** verify valid headers determine the payload type.
3. **With type header and `use.type.headers=false`:** verify the consumer ignores the header and deserializes using the default type.
4. **Header pointing to invalid class:** verify the error is logged and handled by the error handler; do not expect the default type to silently repair bad headers when type headers are enabled.
5. **Trusted packages:** verify classes outside allowed packages are rejected while allowed packages deserialize.
6. **Distinct key and value types:** test `key.default.type` and `value.default.type` independently when both use JSON.
7. **Multiple event types:** test type mapping so each type's token resolves to the right DTO.
8. **Polyglot compatibility:** send JSON from a non-Spring producer and verify the Java consumer deserializes it per the schema contract.

You can use `spring-kafka-test` or the Kafka test starter matching your Spring Boot version. Include at least one test with records lacking type headers, as that directly exercises default type behavior.

## 12. Configuration Selection Workflow

Before setting a default type, examine the topic structure:

1. If the topic carries only one value type, set `spring.json.value.default.type` to that topic's DTO.
2. If the producer emits no type headers, the default type acts as fallback; set `use.type.headers=false` to enforce a fixed type.
3. If the topic carries multiple event types and producers can emit type headers, use type mapping to govern type names and package compatibility.
4. If the key is also a JSON object, configure the key deserializer and `spring.json.key.default.type` separately.
5. Restrict trusted packages to only the DTO packages actually used.
6. Test headerless records, headered records, and schema-invalid records before deployment.

Do not use a single default type for a topic carrying multiple distinct event types if the consumer must tell them apart. Choose type headers/type mapping or split topics by business contract.

## 13. Summary

- A default type is the fallback or fixed Java type `JsonDeserializer` uses when no appropriate type information is present.
- `spring.json.value.default.type` sets the default value type; `spring.json.key.default.type` sets the default key type separately.
- `spring.json.use.type.headers=true` lets type headers determine the type when present, with the default type acting as fallback when headers are missing.
- `spring.json.use.type.headers=false` ignores type headers and uses the configured default/target type.
- Type mapping fits topics carrying multiple event types; a single default type fits topics carrying one payload type.
- `spring.json.trusted.packages` restricts packages allowed when resolving type information.
- Default types do not replace schema compatibility, validation, or versioning for polyglot systems.

When configured properly, default types enable Spring Kafka consumers to read JSON from both Spring and external producers without mandatory reliance on Spring type headers. Payload contracts, data types, mappings, and trust policies must still be aligned across sending and receiving systems.
