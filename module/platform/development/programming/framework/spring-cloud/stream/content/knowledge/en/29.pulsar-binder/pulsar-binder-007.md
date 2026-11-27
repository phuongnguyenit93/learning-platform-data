# Configuring `schema-type`, `message-type`, and Key/Value Types

When Spring Cloud Stream sends or receives messages over Pulsar, the application must agree on how data is converted between Java objects and bytes on the topic. Pulsar supports named and versioned schemas such as JSON, Avro, Protobuf, primitive, and KeyValue. The Spring Cloud Stream Pulsar binder provides extended properties to declare schemas per binding: `schema-type`, `message-type`, `message-key-type`, and `message-value-type`.

These properties are especially important when native encoding/decoding is enabled. In the default mode, Spring Cloud Stream typically converts objects to JSON bytes via its message converter and the binder sends those bytes using `Schema.BYTES`; in that mode, Pulsar does not manage a JSON schema for the object. If you want the broker and clients to use Pulsar Schema Registry, the producer must use native encoding and the consumer must use native decoding, and both sides must agree on the schema type and data types.

## 1. Three Layers to Distinguish

Before configuring, distinguish three concepts:

| Concept | Question answered | Example |
|---|---|---|
| Spring Cloud Stream `content-type` | How does the framework message converter interpret the payload? | `application/json` |
| Pulsar `schema-type` | Which schema does the Pulsar client use to encode/decode the payload? | `JSON`, `AVRO`, `PROTOBUF`, `KEY_VALUE` |
| `message-type` | Which Java class represents the value processed by producer/consumer? | `com.acme.OrderCreated` |

For `KeyValue` messages, you must also specify the Java types for the key and value via `message-key-type` and `message-value-type`. This is data type information for the `KeyValue` schema; do not confuse it with the Pulsar message key used for routing or ordering.

A valid schema must simultaneously match the actual payload, the Java type accepted/returned by the function, and the schema registered on the topic. Merely declaring `content-type: application/json` does not mean the topic uses a Pulsar JSON schema.

## 2. Two Data Conversion Paths

The Spring Cloud Stream Pulsar binder supports two primary conversion approaches.

### 2.1. Default Framework Message Conversion

Without native encoding/decoding enabled, Spring Cloud Stream uses Spring Messaging's message conversion. By default, `content-type` is `application/json`:

- Producer: Java object is serialized to `byte[]` by the message converter.
- Binder: sends the byte array to Pulsar using `Schema.BYTES`.
- Consumer: receives `byte[]` from Pulsar.
- Framework: uses the message converter to turn bytes into the target Java type.

~~~mermaid
flowchart LR
    A[Java object] --> B[Spring MessageConverter]
    B --> C[JSON bytes]
    C --> D[Pulsar binder]
    D --> E[Schema.BYTES]
    E --> F[(Pulsar topic)]
    F --> G[byte array]
    G --> H[Spring MessageConverter]
    H --> I[Java object]
~~~

This path is convenient when the application relies on Spring's message model and uses `content-type` to select converters. However, Pulsar sees the payload as raw bytes; the object's JSON schema is not registered as a Pulsar schema solely through `content-type`.

### 2.2. Native Encoding/Decoding via Pulsar Schema

Native encoding instructs the Pulsar client to serialize objects using a Pulsar schema. Native decoding instructs the Pulsar client to deserialize payloads into the declared data type:

- Producer binding sets `use-native-encoding: true`.
- Consumer binding sets `use-native-decoding: true`.
- Pulsar extended binding declares `schema-type` and the corresponding Java type information.

~~~mermaid
flowchart LR
    A[Java object] --> B[Pulsar Schema encoder]
    B --> C[Schema-aware payload]
    C --> D[(Pulsar topic + schema version)]
    D --> E[Pulsar Schema decoder]
    E --> F[Java object]
~~~

When using native mode, framework message conversion driven by `content-type` is no longer responsible for encoding/decoding the payload. Schema and data types must be configured accordingly on the Pulsar binding.

## 3. Where Properties Live per Binding

`use-native-encoding` and `use-native-decoding` are standard Spring Cloud Stream properties:

~~~text
spring.cloud.stream.bindings.<binding-name>.producer.use-native-encoding
spring.cloud.stream.bindings.<binding-name>.consumer.use-native-decoding
~~~

Pulsar binder schema properties live under extended binding properties:

~~~text
spring.cloud.stream.pulsar.bindings.<binding-name>.producer.schema-type
spring.cloud.stream.pulsar.bindings.<binding-name>.producer.message-type
spring.cloud.stream.pulsar.bindings.<binding-name>.producer.message-key-type
spring.cloud.stream.pulsar.bindings.<binding-name>.producer.message-value-type

spring.cloud.stream.pulsar.bindings.<binding-name>.consumer.schema-type
spring.cloud.stream.pulsar.bindings.<binding-name>.consumer.message-type
spring.cloud.stream.pulsar.bindings.<binding-name>.consumer.message-key-type
spring.cloud.stream.pulsar.bindings.<binding-name>.consumer.message-value-type
~~~

In YAML, Java camelCase property names are written in kebab-case, such as `schema-type`, `message-type`, `message-key-type`, and `message-value-type`.

Producer and consumer may use different schemas if a function transforms data types between input and output. However, each binding must match the schema of the topic it reads from or writes to.

## 4. End-to-End Example with JSON Schema

Suppose an application receives `OrderCreated`, validates the data, and emits `OrderValidated`. Both the input topic and output topic use JSON schema.

Java models and function:

In a real project, place each `public record` in its own matching file; the snippet below shows both models side by side for readability.

~~~java
package com.acme.orders;

public record OrderCreated(
    String eventId,
    String orderId,
    long amount
) {}

public record OrderValidated(
    String eventId,
    String orderId,
    long amount,
    String status
) {}
~~~

~~~java
package com.acme.orders;

import java.util.function.Function;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderFunctions {

    @Bean
    Function<OrderCreated, OrderValidated> validateOrder() {
        return order -> {
            if (order.amount() <= 0) {
                throw new IllegalArgumentException("amount must be positive");
            }
            return new OrderValidated(
                order.eventId(),
                order.orderId(),
                order.amount(),
                "VALIDATED"
            );
        };
    }
}
~~~

Binding configuration:

~~~yaml
spring:
  cloud:
    function:
      definition: validateOrder
    stream:
      bindings:
        validateOrder-in-0:
          destination: orders.created
          consumer:
            use-native-decoding: true
        validateOrder-out-0:
          destination: orders.validated
          producer:
            use-native-encoding: true
      pulsar:
        bindings:
          validateOrder-in-0:
            consumer:
              schema-type: JSON
              message-type: com.acme.orders.OrderCreated
          validateOrder-out-0:
            producer:
              schema-type: JSON
              message-type: com.acme.orders.OrderValidated
~~~

Execution flow:

1. The Pulsar consumer reads a record from `orders.created`.
2. The native decoder uses the JSON schema to construct `OrderCreated`.
3. Function `validateOrder` receives the object and returns `OrderValidated`.
4. The native encoder uses the output binding's JSON schema to serialize the object.
5. The Pulsar producer writes the record to `orders.validated`.

Class names in `message-type` must be fully qualified class names and must be present on the classpath. If you rename a package or class, update the configuration and assess schema compatibility; do not rename a class merely to match a topic without checking existing data.

## 5. What Is `schema-type`?

`schema-type` selects the Pulsar schema type used for the payload. Common types include:

| Schema type | Suitable data | Notes |
|---|---|---|
| `STRING` | UTF-8 strings. | Used for simple text messages. |
| `BOOLEAN`, `INT8`, `INT16`, `INT32`, `INT64`, `FLOAT`, `DOUBLE` | Corresponding primitive values. | Spring for Apache Pulsar can infer schemas for supported Java primitive types. |
| `BYTES` | `byte[]` or self-managed binary payloads. | Does not provide field structure for schema registry validation like JSON/Avro. |
| `JSON` | Structured JSON objects. | Human-readable and suited for cross-language exchange. |
| `AVRO` | Records with an Avro schema. | Suited for structured data and schema evolution. |
| `PROTOBUF` | Messages using Protocol Buffers. | Suited for `.proto` contracts and schema-generated code. |
| `KEY_VALUE` | A message containing a key schema and value schema. | Requires declaring corresponding key/value types. |
| `AUTO_CONSUME` | Consumer reads unknown schemas as generic records. | Intended for multi-schema streams or inspection tools. |

The exact list and level of schema support depend on the Pulsar client and Spring for Apache Pulsar versions. Not every Pulsar schema type behaves identically on both producer and consumer. `AUTO_CONSUME` is a schema mode for reading generic records. `AUTO_PRODUCE_BYTES` is a producer-side schema strategy provided by Spring for Apache Pulsar, not a general-purpose `SchemaType` value meant to replace JSON or Avro in every binder configuration.

For Java primitives, Spring for Apache Pulsar can usually infer the appropriate schema automatically. For complex types, the default schema is typically JSON if no other configuration or mapping is present. In production systems, declare critical schemas explicitly rather than relying on default inference.

## 6. `message-type` Specifies the Java Type, Not the Schema Type

`message-type` is the fully qualified name of the Java class the binder should convert. Example:

~~~yaml
spring:
  cloud:
    stream:
      pulsar:
        bindings:
          customerEvents-in-0:
            consumer:
              schema-type: AVRO
              message-type: com.acme.customer.CustomerChanged
~~~

Here:

- `AVRO` tells Pulsar to use the Avro schema format.
- `com.acme.customer.CustomerChanged` tells the application which Java type to receive data as.

The two values must align. If you declare `schema-type: AVRO` but the class has a structure the Avro serializer/resolver cannot handle, the producer may fail during schema creation or serialization.

Do not put `application/json` into `message-type`; content type and Java type are separate concepts. Likewise, do not put a topic name into `message-type`; topics are declared via `destination` on the binding.

## 7. Primitive Types vs. Complex Types

Spring for Apache Pulsar can automatically infer schemas for several Java primitive/wrapper types such as `String`, `Integer`, `Long`, `Boolean`, `Float`, `Double`, and byte arrays. For complex objects, the framework typically defaults to JSON if no schema is specified.

Example producer sending strings:

~~~java
@Bean
Supplier<String> statusSupplier() {
    return () -> "READY";
}
~~~

~~~yaml
spring:
  cloud:
    function:
      definition: statusSupplier
    stream:
      bindings:
        statusSupplier-out-0:
          destination: system.status
          producer:
            use-native-encoding: true
~~~

For supported primitive types, the schema can be inferred from the `Supplier`'s generic type. If you prefer explicit configuration or need interoperability with other clients, you can set `schema-type: STRING` on the corresponding producer and consumer.

Example complex type:

~~~java
package com.acme;

record CustomerChanged(String customerId, String email) {}
~~~

~~~yaml
spring:
  cloud:
    function:
      definition: customerChanged
    stream:
      bindings:
        customerChanged-out-0:
          destination: customer.events
          producer:
            use-native-encoding: true
      pulsar:
        bindings:
          customerChanged-out-0:
            producer:
              schema-type: JSON
              message-type: com.acme.CustomerChanged
~~~

If `schema-type` is omitted for a complex type, Spring for Apache Pulsar may default to JSON. However, when a topic already has a different schema, the producer must use a schema compatible with the topic rather than relying on defaults.

## 8. When Messages Have Both Key and Value

Pulsar supports the `KEY_VALUE` schema to describe a typed key/value pair. In the Spring Cloud Stream Pulsar binder, you can specify:

- `schema-type: KEY_VALUE` to choose the overall schema.
- `message-key-type` to specify the Java type of the key.
- `message-value-type` to specify the Java type of the value.

Example:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orderState-out-0:
          destination: orders.state
          producer:
            use-native-encoding: true
      pulsar:
        bindings:
          orderState-out-0:
            producer:
              schema-type: KEY_VALUE
              message-key-type: java.lang.String
              message-value-type: com.acme.orders.OrderState
~~~

In this example, the key is `String` and the value is `OrderState`. The value type must have an appropriate schema mapping, such as JSON or Avro depending on configuration and the Spring Pulsar version in use. If specific schemas are needed for each part of the `KeyValue` pair, configure an appropriate schema resolver/type mapping or customizer instead of assuming a single `message-type` property suffices for both.

### 8.1. Distinguishing `KeyValue` Schema from Pulsar Message Key

Two easily confused concepts:

| Concept | Meaning |
|---|---|
| Pulsar message key | Key metadata attached to a message, used for routing, ordering, or compaction depending on topic/subscription config. |
| `Schema.KEY_VALUE` | Payload structure having separate schemas for key and value. |
| `message-key-type` | Java type for the key component when `schema-type` is `KEY_VALUE`. |
| `message-value-type` | Java type for the value component when `schema-type` is `KEY_VALUE`. |

If you only need a Pulsar message key for routing while the payload remains a single regular object, you do not necessarily need `Schema.KEY_VALUE`. Conversely, if the payload itself is a schema-governed key/value pair, you must configure the `KeyValue` schema and each component's type properly.

### 8.2. `KeyValue` Encoding

Pulsar defines two common encodings for `KeyValue`:

- `INLINE`: key and value are encoded together inside the payload according to the `KeyValue` schema.
- `SEPARATED`: key is stored in message key metadata, while value is stored in the payload.

Current Spring for Apache Pulsar documentation describes complex `KEY_VALUE` support with `INLINE` encoding. If your system requires `SEPARATED` encoding, verify support in your exact binder/client version or use the appropriate Pulsar client API; do not assume binder configuration supports every `KeyValue` variant by default.

## 9. Consumer Configuration Must Match Producer

Producer and consumer must agree on `schema-type` and `message-type`. Example producer writing JSON:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orderEvents-out-0:
          destination: orders.events
          producer:
            use-native-encoding: true
      pulsar:
        bindings:
          orderEvents-out-0:
            producer:
              schema-type: JSON
              message-type: com.acme.orders.OrderCreated
~~~

Corresponding consumer:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orderProjection-in-0:
          destination: orders.events
          consumer:
            use-native-decoding: true
      pulsar:
        bindings:
          orderProjection-in-0:
            consumer:
              schema-type: JSON
              message-type: com.acme.orders.OrderCreated
~~~

If the producer uses Avro while the consumer declares JSON, the client may fail to decode the payload or the schema registry may reject the subscription. Sharing the same Java class name is also insufficient if the actual schema changed incompatibly.

When multiple consumers use different programming languages, they do not all need the same Java class; what matters is that each consumer's schema can read the message versions produced under the topic's compatibility strategy.

## 10. Native Encoding/Decoding and `content-type`

When native encoding/decoding is enabled, do not use `content-type` as the mechanism to choose the payload serializer. The Pulsar schema is selected via `schema-type` and the binding's type information.

| Setting | Producer | Consumer |
|---|---|---|
| Default framework conversion | Spring converter produces bytes; binder uses `Schema.BYTES`. | Binder receives bytes; Spring converter builds Java object. |
| Native mode | Pulsar Schema serializes Java object. | Pulsar Schema deserializes into Java object. |
| `content-type` | Affects framework message converter when converter is used. | Affects framework message converter when converter is used. |
| `schema-type` | Chooses Pulsar schema for writing. | Chooses Pulsar schema for reading. |
| `message-type` | Java object type to serialize. | Java object type to deserialize. |

Both sides can select native mode independently per binding, provided the payload remains compatible with how the other side reads it. In a schema-aware Pulsar pipeline, native encoding is typically enabled on outbound bindings and native decoding on the corresponding inbound bindings.

Native mode also affects header propagation. Do not expect embedded Spring headers to be packed into the payload in the same way once the framework converter no longer serializes a message envelope. Pulsar has its own message properties/metadata and the binder provides a header mapper.

## 11. Headers Are Not the Payload Schema

Pulsar messages have metadata and user properties for carrying data such as correlation ID, event source, or tenant. The binder translates headers between Pulsar messages and Spring `Message` via `PulsarHeaderMapper`.

The default header mapper can be replaced with a custom `PulsarHeaderMapper` bean if special filtering or conversion is needed. Example:

~~~java
@Bean
PulsarHeaderMapper customPulsarHeaderMapper() {
    return JsonPulsarHeaderMapper.builder()
        .inboundPatterns("!secret", "*")
        .outboundPatterns("!password", "!token", "*")
        .trustedPackages("com.acme")
        .build();
}
~~~

`schema-type` describes payload structure; the header mapper describes metadata translation. Do not push all business fields into headers just to avoid schemas. Fields that require compatibility checking and consumer processing belong in the payload schema.

## 12. Custom Schema Mapping to Avoid Repeating `schema-type`

Spring for Apache Pulsar allows mapping Java types to Pulsar schemas. When a mapping exists, the framework can resolve the schema from the message type; the binder docs also note that custom schema mappings are consulted when `schema-type` is omitted.

Example mapping configuration:

~~~yaml
spring:
  pulsar:
    defaults:
      type-mappings:
        - message-type: com.acme.orders.OrderCreated
          schema-info:
            schema-type: JSON
        - message-type: com.acme.orders.OrderValidated
          schema-info:
            schema-type: AVRO
~~~

You can declare mappings using `SchemaResolverCustomizer` when more complex logic is required:

~~~java
@Bean
SchemaResolverCustomizer<DefaultSchemaResolver> orderSchemaMappings() {
    return resolver -> {
        resolver.addCustomSchemaMapping(
            OrderCreated.class,
            Schema.JSON(OrderCreated.class)
        );
        resolver.addCustomSchemaMapping(
            OrderValidated.class,
            Schema.AVRO(OrderValidated.class)
        );
    };
}
~~~

Another option is annotating a class with `@PulsarMessage(schemaType = SchemaType.JSON)` to set the default schema for that message type. This works well when the class belongs to your application and always shares the same default schema across bindings.

Custom mappings prevent repetitive configuration, but avoid mapping one class to different schemas depending on the topic without clear rules. If two bindings use different schemas for the same Java type, explicit per-binding configuration is usually easier to govern.

## 13. Pulsar Configuration Scope and Precedence

The Pulsar binder inherits Spring Boot auto-configuration from Spring for Apache Pulsar. There are three configuration levels:

1. Spring Boot properties, such as `spring.pulsar.producer.*` and `spring.pulsar.consumer.*`.
2. Binder-level properties, such as `spring.cloud.stream.pulsar.binder.producer.*` and `spring.cloud.stream.pulsar.binder.consumer.*`.
3. Extended binding properties, such as `spring.cloud.stream.pulsar.bindings.<binding-name>.producer.*` and `.consumer.*`.

Precedence from highest to lowest:

| Level | Scope |
|---|---|
| Extended binding properties | Only the specified binding. |
| Binder properties | Bindings belonging to the binder in the application. |
| Spring Boot properties | Baseline application configuration. |

Example where two output bindings need different schemas:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        customerJson-out-0:
          destination: customer.events.json
          producer:
            use-native-encoding: true
        customerAvro-out-0:
          destination: customer.events.avro
          producer:
            use-native-encoding: true
      pulsar:
        bindings:
          customerJson-out-0:
            producer:
              schema-type: JSON
              message-type: com.acme.CustomerChanged
          customerAvro-out-0:
            producer:
              schema-type: AVRO
              message-type: com.acme.CustomerChanged
~~~

Here the same Java type is emitted with two different schemas on two different topics. Do this only when both contracts are governed explicitly; do not send two different schemas to the same topic without a matching compatibility strategy and consumer support.

## 14. Schema Registry and Schema Versions

Pulsar stores `SchemaInfo` and schema versions per topic. When a producer registers a new schema, the broker checks compatibility according to the configured strategy. Messages are written tagged with version metadata so consumers can retrieve the corresponding schema during deserialization.

The schema registry helps:

- Identify the data structure registered for a topic.
- Track schema versions.
- Validate whether a new schema is compatible with the current schema.
- Allow consumers to read messages produced with compatible schema versions.

`schema-type` selects only the schema family such as JSON/Avro; it is not a version number. `message-type` selects only the Java class; it does not replace broker-side schema version management.

### 14.1. Compatibility Strategies

Pulsar supports several strategies, with common options being:

| Strategy | Meaning | Typical usage |
|---|---|---|
| `BACKWARD` | Consumer with new schema can read data written with the immediately preceding schema. | Typically adding optional fields or removing fields per schema rules. |
| `BACKWARD_TRANSITIVE` | New consumer can read data from all older schemas. | Used when compatibility with entire data history is required. |
| `FORWARD` | Old consumer can read data written by new producer. | Requires keeping old consumers compatible with new fields. |
| `FORWARD_TRANSITIVE` | Old consumer can read data from all newer schemas. | Used when multiple producer/consumer generations coexist. |
| `FULL` | Both backward and forward compatible with adjacent version. | Fits rolling upgrades when schema changes are bidirectionally compatible. |
| `FULL_TRANSITIVE` | Bidirectionally compatible across all prior versions. | Used when strict full-history compatibility is required. |
| `ALWAYS_COMPATIBLE` | Does not reject schema changes due to compatibility checks. | Use only when another contract governance mechanism exists. |
| `ALWAYS_INCOMPATIBLE` | Disallows schema evolution. | When locking down a contract or requiring separate topics/versions. |

Allowed changes depend on the schema type and compatibility checker. For JSON and Avro, default broker configuration typically uses `FULL`; other schema types may default to `ALWAYS_INCOMPATIBLE`. Inspect actual broker configuration rather than assuming a single cluster-wide default.

### 14.2. Example of Safe Schema Evolution

Schema V1:

~~~json
{
  "eventId": "evt-100",
  "orderId": "order-9001",
  "amount": 125000
}
~~~

Schema V2 adding an optional field:

~~~json
{
  "eventId": "evt-100",
  "orderId": "order-9001",
  "amount": 125000,
  "source": "MOBILE"
}
~~~

If the schema and compatibility strategy allow it, a V1 consumer can ignore the new field and a V2 consumer can handle older data using an appropriate default or null. Changing `amount`'s type from numeric to string or altering a field's meaning without renaming it may be rejected by the compatibility checker or cause old consumers to misinterpret data.

Do not remove required fields or change types simply because new Java code compiles. Verify schema compatibility, producer/consumer rollout order, and historical data.

## 15. `KeyValue` Schema and Independent Key/Value Evolution

With `KEY_VALUE`, the overall schema comprises both a key schema and a value schema. Changes to both parts must be managed:

- Keys are typically used for entity identification, routing, or compaction. Changing the key type can alter how consumers look up or group records.
- Values typically carry business content and can evolve fields under the compatibility strategy.
- The `KeyValue` schema version represents the pair structure; when modifying either key or value schema, check overall compatibility.

Example:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        accountState-out-0:
          destination: account.state
          producer:
            use-native-encoding: true
      pulsar:
        bindings:
          accountState-out-0:
            producer:
              schema-type: KEY_VALUE
              message-key-type: java.lang.String
              message-value-type: com.acme.AccountState
~~~

If the key is `accountId`, keeping it as a stable `String` across versions is usually much easier to keep compatible than changing to a complex class. The value can evolve under the chosen schema strategy.

## 16. `AUTO_CONSUME` and Generic Records

When a consumer does not know the schema class ahead of time or a topic may contain multiple schema versions, Pulsar supports `AUTO_CONSUME`. The consumer receives a `GenericRecord` and reads fields according to the actual schema attached to each message.

Example consumer configuration:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        auditReader-in-0:
          destination: audit.events
          consumer:
            use-native-decoding: true
      pulsar:
        bindings:
          auditReader-in-0:
            consumer:
              schema-type: AUTO_CONSUME
~~~

Example function receiving a generic record:

~~~java
@Bean
Consumer<GenericRecord> auditReader() {
    return record -> record.getFields().forEach((field) ->
        log.info("{}={}", field.getName(), record.getField(field))
    );
}
~~~

`GenericRecord` is useful for schema inspection, data migration, or audit tooling. For business services, concrete Java types usually provide stronger compile-time checks. When using generic records, handle potentially missing fields, differing types across schema versions, and null values.

## 17. `AUTO_PRODUCE_BYTES` and Raw Payloads

If a producer already holds raw JSON/Avro bytes and does not want to deserialize them into Java objects before sending, Spring for Apache Pulsar supports `AUTO_PRODUCE_BYTES` in appropriate scenarios. The producer sends `byte[]`, and Pulsar validates the bytes against the topic's schema.

This is an advanced option, not a universal substitute for schemas across all payload types. According to Spring Pulsar docs, `AUTO_PRODUCE_BYTES` support focuses on JSON and Avro. Verify that your binder version exposes this schema type in the way your application needs.

Do not send arbitrary raw bytes into a schema-governed topic expecting the broker to infer the contents automatically. The producer must supply valid bytes matching the target schema; otherwise validation/serialization may fail or data may become unreadable.

## 18. Common Schema Configuration Errors

| Symptom | Possible cause | Resolution |
|---|---|---|
| Consumer receives `byte[]` instead of Java object. | Using framework conversion or native decoding is not enabled. | Check `use-native-decoding` and `schema-type`. |
| Producer sends successfully, but topic lacks expected JSON schema. | Framework converter produced JSON bytes, but binder used `Schema.BYTES`. | Enable `use-native-encoding` and configure Pulsar `schema-type: JSON`. |
| `SchemaSerializationException` or schema creation failure. | Wrong `message-type`, class unsupported by schema, or schema mismatch. | Check FQN, classpath, schema resolver, and model. |
| Consumer fails to deserialize message. | Producer/consumer use incompatible schema type or message type. | Compare topic schema, binding properties, and schema version. |
| Broker rejects new schema registration. | New schema is incompatible per strategy. | Check field/type changes and compatibility strategy. |
| `KeyValue` schema fails to initialize. | Missing `message-key-type` or value schema mapping. | Declare key/value types and corresponding schema resolver. |
| Producer and consumer handle keys differently. | Confusing Pulsar message key with `KeyValue` schema component. | Determine whether you need message metadata key or `Schema.KEY_VALUE`. |
| Package rename on Java class breaks consumer. | `message-type` still points to old class or schema mapping not updated. | Sync configuration and assess schema compatibility. |
| `AUTO_CONSUME` returns generic record but code casts improperly. | Consumer assumes a fixed schema. | Read fields and types dynamically from `GenericRecord` per actual schema. |
| Headers are lost or fail to map. | Confusing header mapper with payload schema or mapper filters out headers. | Inspect `PulsarHeaderMapper` and metadata properties. |

## 19. Testing Producer and Consumer Schemas

Test Binder can test function logic and Spring `Message` conversion, but it does not prove that the Pulsar Schema Registry registered the right schema or that the broker accepts schema evolution. Integration tests with a real/compatible Pulsar broker are required.

Recommended scenarios:

1. Native JSON producer sends a record; native JSON consumer receives the right object and fields.
2. Avro producer sends schema; Avro consumer decodes the matching version.
3. Consumer uses an incompatible schema type; verify a clear error surfaces on subscribe/deserialize.
4. Send a compatible V2 schema; verify V1/V2 consumers behave according to the chosen strategy.
5. Send an incompatible V2 schema; verify the broker rejects registration per policy.
6. Send `KeyValue` messages; verify key type, value type, and encoding.
7. Read a topic with `AUTO_CONSUME`; verify `GenericRecord` exposes the right fields and types.
8. Producer sends raw bytes with `AUTO_PRODUCE_BYTES`; verify bytes are validated against the topic schema.
9. Test default framework conversion to confirm payloads use `Schema.BYTES`.
10. Test headers through `PulsarHeaderMapper`, including filtered and sensitive headers.

When testing schema evolution, record the schema versions and compatibility strategy used so results are reproducible. Do not assert only the final Java object; verify the registered schema on the topic and confirm the consumer truly uses native decoding.

## 20. Workflow for Choosing `schema-type` and `message-type`

1. Determine whether the payload is primitive, structured object, raw bytes, or a key/value pair.
2. Decide between Spring framework conversion and Pulsar native schemas.
3. If using framework conversion, declare the appropriate `content-type` and note that the binder may default to `Schema.BYTES`.
4. If using native mode, enable `use-native-encoding` on the producer and `use-native-decoding` on the corresponding consumer.
5. Choose `schema-type` matching the contract: `JSON`, `AVRO`, `PROTOBUF`, primitive, or `KEY_VALUE`.
6. For complex types, declare `message-type` using the fully qualified class name.
7. For `KEY_VALUE`, declare `message-key-type` and `message-value-type`; verify `INLINE`/`SEPARATED` encoding support for your version.
8. Ensure the producer schema is compatible with the topic schema and consumers.
9. Choose a schema compatibility strategy and producer/consumer rollout sequence.
10. If multiple bindings use different schemas, set extended binding properties rather than application-wide defaults.
11. Use custom schema mappings to avoid repetitive configuration while keeping mappings consistent per Java type.
12. Integration test schema registration, serialization, deserialization, versioning, headers, and incompatibility failures.

## 21. Production Checklist

- [ ] Each binding has an explicit decision between framework conversion and native encoding/decoding.
- [ ] Corresponding producers and consumers use compatible encode/decode modes.
- [ ] `schema-type` matches the schema registered on the topic.
- [ ] `message-type` is the FQN of a Java type present on the classpath.
- [ ] For `KEY_VALUE`, both key type and value type are declared completely.
- [ ] Pulsar message key metadata is not confused with `KeyValue` payload schema.
- [ ] Schema compatibility strategy is chosen intentionally.
- [ ] Schema changes have been tested against historical data and older consumer versions.
- [ ] Custom type mappings do not conflict across bindings.
- [ ] Header mapper does not expose secrets or sensitive data into metadata.
- [ ] Integration tests run against a Pulsar broker, not only Test Binder.
- [ ] Monitoring/alerting covers schema registration failures and deserialization errors.

`schema-type` defines the data format Pulsar understands; `message-type` specifies the Java object the application processes; key/value types add structure for paired messages. When these three layers align with native encoding/decoding, topic schemas, and compatibility strategies, the Spring Cloud Stream Pulsar binder can exchange structured messages across multiple services while keeping contract evolution under control over time.

## References

- [Spring Cloud Stream 5.0 – Binder for Apache Pulsar](https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html)
- [Spring for Apache Pulsar – Message Production and Schema Information](https://docs.spring.io/spring-pulsar/reference/reference/pulsar/message-production.html)
- [Spring for Apache Pulsar – Message Consumption and Schema Information](https://docs.spring.io/spring-pulsar/reference/reference/pulsar/message-consumption.html)
- [Spring for Apache Pulsar – SchemaResolver API](https://docs.spring.io/spring-pulsar/docs/1.2.x/api/org/springframework/pulsar/core/SchemaResolver.html)
- [Apache Pulsar – Schema Evolution and Compatibility](https://pulsar.apache.org/docs/4.2.x/schema-evolution-compatibility/)
- [Apache Pulsar – KeyValue Schema](https://pulsar.apache.org/docs/4.2.x/schema-understand/)
