# Framework Conversion and Native Pulsar Schema

Spring Cloud Stream can convert messages using Spring Messaging's conversion mechanism or delegate serialization and deserialization to Apache Pulsar via native schemas. Both approaches allow functions to accept Java types such as records or POJOs, but they create different data contracts on the topic.

In the default mode, Spring Cloud Stream uses the framework's message converter. If no content type is specified, the framework defaults to `application/json`; the payload is converted to `byte[]` before the Pulsar binder sends it using `Schema.BYTES`. When the consumer receives the data, the binder retrieves `byte[]` and Spring's `MessageConverter` converts it into the target type. The Pulsar broker does not receive a corresponding JSON Schema or Avro Schema merely because the application set the content type to `application/json`.

With native encoding/decoding, the application enables `use-native-encoding` on the producer and `use-native-decoding` on the consumer. The Pulsar binder uses Pulsar Schema to serialize/deserialize data and exchange `SchemaInfo` with the broker. The application must declare `schema-type` and `message-type` for the binding, or provide appropriate custom schema mappings.

This lesson explains the differences between the two mechanisms, how to configure native JSON/Avro, how to manage schemas per topic, how to control schema evolution and header conversion, and how to test contracts across services.

## Learning Objectives

After completing this lesson, you will be able to:

- Distinguish Spring's `MessageConverter` from native Pulsar Schema.
- Explain why `contentType` `application/json` does not automatically register a JSON Schema in Pulsar.
- Configure `use-native-encoding` and `use-native-decoding` per binding.
- Declare `schema-type` and `message-type` for producers and consumers.
- Use `message-key-type` and `message-value-type` when payloads have separate key and value types.
- Understand `SchemaInfo`, schema versions, and the built-in schema registry in the Pulsar broker.
- Choose `BACKWARD`, `FORWARD`, `FULL`, and their `TRANSITIVE` variants.
- Configure `PulsarHeaderMapper` to convert headers safely.
- Select the appropriate binder, binding, or Spring Boot configuration level.
- Test serialization, schema compatibility, and multi-version producer/consumer deployments.

## 1. Two Data Conversion Layers

When a Spring Cloud Stream function emits or receives a message, there are two layers to distinguish:

1. **Framework message conversion:** converts a Java payload into a representation passed through Spring Messaging/binder.
2. **Native Pulsar schema:** uses Pulsar's Schema API to serialize/deserialize payloads and exchange schema metadata with the broker.

The two layers may produce similar JSON when inspecting the raw bytes, but the contract and metadata on the broker differ.

| Aspect | Framework message conversion | Native Pulsar Schema |
|---|---|---|
| Conversion component | Spring `MessageConverter` | Pulsar Schema |
| Primary configuration | `contentType` and message converter | `schema-type`, `message-type` |
| Producer | Framework converts payload to `byte[]`; binder sends `Schema.BYTES` | Pulsar serializer produces bytes per the selected schema |
| Consumer | Receives `byte[]` and framework converts to target type | Pulsar deserializer constructs Java type per schema |
| Schema metadata at broker | Does not auto-register JSON/Avro schema solely from `contentType` | Pulsar manages `SchemaInfo` and schema versions per topic |
| Schema compatibility check | Depends on converter/application | Pulsar broker schema compatibility check |
| Best suited for | Flexible, middleware-neutral integration | Data contracts governed in Pulsar |

~~~mermaid
flowchart TD
    A["Java object in function"] --> B{"Choose conversion mechanism"}
    B -->|Framework| C["Spring MessageConverter"]
    C --> D["byte[]"]
    D --> E["Pulsar Schema.BYTES"]
    B -->|Native| F["Pulsar Schema serializer"]
    F --> G["SchemaInfo + payload bytes"]
    E --> H["Pulsar topic"]
    G --> H
    H --> I{"Consumer binding"}
    I -->|Framework| J["byte[] then MessageConverter"]
    I -->|Native| K["Pulsar Schema deserializer"]
    J --> L["Java object"]
    K --> L
~~~

Do not choose a mode solely based on whether the final payload is JSON. Decide where schemas are governed, how consumers decode data, and how compatibility is verified when producers and consumers are deployed independently.

## 2. Default Mechanism: Spring MessageConverter

In binder-based applications, Spring Cloud Stream defaults to Spring Framework message conversion. If no content type is declared, the default content type is `application/json` for both inbound and outbound bindings.

On the outbound path:
1. The function returns a Java object.
2. Spring Cloud Stream uses `MessageConverter` to convert the object into `byte[]`.
3. The Pulsar binder sends `byte[]` to the topic using `Schema.BYTES`.

On the inbound path:
1. The Pulsar binder consumes the message as `byte[]`.
2. Spring Cloud Stream uses the content type and `MessageConverter` to convert `byte[]` into the function's parameter type.
3. The function receives the converted Java object.

Function example:

~~~java
import java.math.BigDecimal;
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderFunctions {

    @Bean
    Function<OrderCreated, OrderAccepted> acceptOrder() {
        return event -> new OrderAccepted(
            event.orderId(),
            "ACCEPTED",
            event.total()
        );
    }

    record OrderCreated(String orderId, BigDecimal total) {}
    record OrderAccepted(String orderId, String status, BigDecimal total) {}
}
~~~

Framework conversion configuration:

~~~yaml
spring:
  cloud:
    function:
      definition: acceptOrder
    stream:
      bindings:
        acceptOrder-in-0:
          destination: orders
          content-type: application/json
        acceptOrder-out-0:
          destination: accepted-orders
          content-type: application/json
~~~

This configuration instructs the framework to convert JSON payloads. It does not automatically register a Pulsar JSON Schema for the `orders` or `accepted-orders` topics. On the default path, the binder uses `Schema.BYTES` when sending payloads already serialized by the framework.

### When Is Framework Conversion Appropriate?

Use framework conversion when:
- The application needs to maintain a shared message converter model across multiple binders.
- The topic only needs to transport bytes and contracts are managed at the application or separate API layer.
- Services have agreed on a payload format without needing the Pulsar broker to enforce schemas.
- Custom conversion via Spring `MessageConverter` is required.

On the flip side, the broker lacks sufficient schema metadata to validate JSON/Avro compatibility solely from the content type. A producer can send bytes violating the contract without the broker catching it at the Pulsar Schema layer.

## 3. Native Encoding and Native Decoding

Native mode requires producer and consumer bindings to enable separate flags:

- Producer: `spring.cloud.stream.bindings.<binding-name>.producer.use-native-encoding=true`
- Consumer: `spring.cloud.stream.bindings.<binding-name>.consumer.use-native-decoding=true`

When native encoding/decoding is enabled, Spring Cloud Stream skips Spring `MessageConverter` for that binding's payload. The Pulsar binder uses the configured schema to encode or decode the payload.

Native mode does not infer business schemas from `contentType`. For Pulsar, declare extended binding properties:
- `spring.cloud.stream.pulsar.bindings.<binding-name>.producer.schema-type`
- `spring.cloud.stream.pulsar.bindings.<binding-name>.producer.message-type`
- `spring.cloud.stream.pulsar.bindings.<binding-name>.consumer.schema-type`
- `spring.cloud.stream.pulsar.bindings.<binding-name>.consumer.message-type`

Example function receiving `OrderCreated` and emitting `OrderAccepted`:

~~~yaml
spring:
  cloud:
    function:
      definition: acceptOrder
    stream:
      bindings:
        acceptOrder-in-0:
          destination: orders
          consumer:
            use-native-decoding: true
        acceptOrder-out-0:
          destination: accepted-orders
          producer:
            use-native-encoding: true
      pulsar:
        bindings:
          acceptOrder-in-0:
            consumer:
              schema-type: JSON
              message-type: com.acme.orders.OrderCreated
          acceptOrder-out-0:
            producer:
              schema-type: JSON
              message-type: com.acme.orders.OrderAccepted
~~~

Class names in `message-type` must be real types loadable by the application. Producer and consumer must use schemas compatible with the topic. If package or class names change, update configuration and test deployments together.

### Producer and Consumer Can Choose Independently

The `use-native-encoding` and `use-native-decoding` flags are configured per binding. A producer can be configured with native mode and a consumer with framework conversion (or vice versa), provided both ends agree on the actual representation stored on the topic.

For example, if a producer sends JSON bytes via `Schema.BYTES` through framework conversion, a framework-conversion consumer can read the bytes and parse JSON into an object. If a producer sends native Avro, the consumer must use native decoding with a compatible schema; simply setting `contentType` to `application/json` will not read Avro.

For operational clarity, establish one consistent convention per topic and document it in the event contract: framework conversion or native schema, schema type, message type, and evolution policy.

## 4. `schema-type` and `message-type`

These two properties serve two distinct purposes:

- `schema-type` selects the Pulsar schema kind used for serialization/deserialization, such as `JSON` or `AVRO`.
- `message-type` specifies the Java type the binder needs when constructing the native schema or converting data back to the application.

Example:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        publishOrder-out-0:
          producer:
            use-native-encoding: true
      pulsar:
        bindings:
          publishOrder-out-0:
            producer:
              schema-type: AVRO
              message-type: com.acme.events.OrderCreated
~~~

When `schema-type` is omitted, the binder can look up configured custom schema mappings. If no matching mapping exists, producer/consumer creation may fail or behave unexpectedly. For systems requiring explicit contracts, declaring `schema-type` explicitly lets reviewers see the serialization choice directly in configuration.

### Common Schema Types

Pulsar supports primitive and structured schemas. Commonly used groups include:

| Group | Examples | Suitable data |
|---|---|---|
| Primitive | `STRING`, `BOOLEAN`, `INT32`, `INT64`, `BYTES` | Simple values or raw byte payloads |
| JSON | `JSON` | POJOs/records represented with JSON schema |
| AVRO | `AVRO` | Records with Avro schema |
| Protobuf | `PROTOBUF`, `PROTOBUF_NATIVE` | Messages defined with Protocol Buffers |
| KeyValue | `KEY_VALUE` | Messages with separate schemas for key and value |

The exact list and naming of `schema-type` depend on the Pulsar client and binder versions. Check the enum/schema mapping of your project's version before introducing a new schema type into configuration.

## 5. Native JSON Example with a Java Record

Define the event type:

~~~java
package com.acme.orders;

import java.math.BigDecimal;

public record OrderCreated(
    String eventId,
    String orderId,
    BigDecimal total
) {}
~~~

Producer function:

~~~java
import java.math.BigDecimal;
import java.util.UUID;
import java.util.function.Supplier;

@Bean
Supplier<OrderCreated> publishOrder() {
    return () -> new OrderCreated(
        UUID.randomUUID().toString(),
        "ORD-1001",
        new BigDecimal("125.50")
    );
}
~~~

Producer configuration:

~~~yaml
spring:
  cloud:
    function:
      definition: publishOrder
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders
          producer:
            use-native-encoding: true
      pulsar:
        bindings:
          publishOrder-out-0:
            producer:
              schema-type: JSON
              message-type: com.acme.orders.OrderCreated
~~~

The Pulsar binder uses a JSON Schema for `OrderCreated` instead of sending bytes with `Schema.BYTES` via framework conversion. When the producer connects to the topic, the broker can check `SchemaInfo` and compatibility according to the topic's configuration.

Note that Java records must be compatible with the chosen schema mechanism and library version. When using nested types, enums, collections, or nullable fields, inspect the generated schema rather than relying solely on the class name.

## 6. Native AVRO Example

With Avro, `message-type` can be a POJO/record suitable for Avro schema generation or a type supported by Spring for Apache Pulsar.

~~~yaml
spring:
  cloud:
    function:
      definition: publishOrder
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders-avro
          producer:
            use-native-encoding: true
      pulsar:
        bindings:
          publishOrder-out-0:
            producer:
              schema-type: AVRO
              message-type: com.acme.events.OrderCreated
~~~

Consumer:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders-avro
          group: order-processor
          consumer:
            use-native-decoding: true
      pulsar:
        bindings:
          processOrder-in-0:
            consumer:
              schema-type: AVRO
              message-type: com.acme.events.OrderCreated
~~~

Producer and consumer must agree on compatible schemas—not necessarily the exact same class version if schema evolution permits. For example, a newer consumer can read data written with an older schema when changes adhere to backward compatibility.

Do not switch `schema-type` from `AVRO` to `JSON` on the same topic without a migration plan. The schema type is part of the topic's contract; existing consumers may fail to decode the new data.

## 7. KeyValue Schema and Separate Key/Value Types

Some applications require distinct types for key and value. For example:
- Key: `orderId` for routing or partitioning.
- Value: `OrderCreated` containing the event payload.

Pulsar supports `KeyValue` schemas. The binder provides `message-key-type` and `message-value-type` to declare target types for the key and value when native conversion is used.

Example:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders-key-value
          producer:
            use-native-encoding: true
      pulsar:
        bindings:
          publishOrder-out-0:
            producer:
              schema-type: KEY_VALUE
              message-key-type: java.lang.String
              message-value-type: com.acme.orders.OrderCreated
~~~

When using native decoding on the consumer, configure the corresponding settings on the input binding:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders-key-value
          consumer:
            use-native-decoding: true
      pulsar:
        bindings:
          processOrder-in-0:
            consumer:
              schema-type: KEY_VALUE
              message-key-type: java.lang.String
              message-value-type: com.acme.orders.OrderCreated
~~~

Pulsar `KeyValue` schemas can encode key/value as `INLINE` (both inside the payload) or `SEPARATED` (key as message key, value as payload). The encoding choice must be agreed upon across producers, consumers, and any other systems reading the topic. Do not assume all clients interpret key/value identically without aligning schema and encoding.

## 8. `SchemaInfo` and Pulsar's Schema Registry

Pulsar manages schemas using `SchemaInfo` metadata. This information is stored per topic and includes:
- `name`: schema name.
- `type`: schema type.
- `schema`: schema definition in bytes.
- `properties`: custom key/value metadata.

When a producer connects with a schema:
1. The client builds a schema instance from the data type.
2. The producer sends `SchemaInfo` to the broker.
3. The broker looks up registered schemas for the topic.
4. If the schema does not exist yet, the broker evaluates auto-update and compatibility policies.
5. If valid, the broker registers the schema version and returns it to the producer.
6. Messages are written tagged with the schema version so consumers can select the corresponding schema during deserialization.

On the read path, a consumer connects with a compatible schema. The broker checks the consumer's schema against the topic schema according to the compatibility policy.

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant B as Pulsar broker
    participant R as Schema registry
    participant T as Topic
    participant C as Consumer
    P->>B: Connect with SchemaInfo
    B->>R: Lookup / register schema
    R-->>B: Schema version or incompatibility
    B-->>P: Accept or reject producer
    P->>T: Publish message with schema version
    C->>B: Subscribe with consumer SchemaInfo
    B->>R: Check consumer compatibility
    R-->>B: Compatible schema version
    B-->>C: Deliver message with schema version
    Note over C: Client deserializes using the schema version
~~~

Pulsar's schema registry is built into the Pulsar broker and storage. It differs from the Spring Cloud Stream Schema Registry server. Spring Schema Registry is a separate component in the Spring Cloud Stream ecosystem, whereas native Pulsar Schema uses `SchemaInfo` managed by Pulsar per topic.

One operational point to verify is schema validation enforcement for producers. Under the default Pulsar configuration described in the 5.0.x documentation, this enforcement is disabled for producers; a producer without a declared schema can still write raw bytes to a topic that already has a schema. If you need the broker to reject producers that do not conform to the topic schema, enable and test the schema validation enforcement policy on the cluster rather than relying solely on the topic having a registered `SchemaInfo`.

## 9. Schema Compatibility and Evolution

Schema evolution allows data structures to change over time without breaking all running producers and consumers. Pulsar checks compatibility based on the schema type and configured strategy.

Common strategies:

| Strategy | Meaning | Typically compatible changes |
|---|---|---|
| `BACKWARD` | Consumer using new schema can read data from the immediately preceding schema | Adding an optional field; deleting a field |
| `BACKWARD_TRANSITIVE` | New schema can read data from all older schemas | Applies backward check across entire history |
| `FORWARD` | Consumer using old schema can read data written with the new schema | Adding a field; deleting an optional field |
| `FORWARD_TRANSITIVE` | Old consumer can read data from all newer schemas in history | Applies forward check throughout |
| `FULL` | New schema and preceding schema can read each other's data | Changing optional fields per schema type rules |
| `FULL_TRANSITIVE` | Bidirectional compatibility across all previous versions | Full check across entire history |

Example:
- Producer v1 emits `OrderCreated(orderId, total)`.
- Producer v2 adds an optional `currency` field.
- Consumer v2 can read v1 messages if the schema allows a default/optional value.
- Whether Consumer v1 can read v2 messages depends on `FORWARD`/`FULL` compatibility and how the schema defines the new field.

"Optional" does not merely mean a nullable Java field. It must be represented properly in the schema—such as a nullable union or a default value per Avro/JSON Schema rules. A Java field may be nullable while the generated schema still marks it required if not configured properly.

### Transitive vs. Non-Transitive

Non-transitive checks the new schema only against the latest version according to the strategy. Transitive checks against all prior versions. Example:
- V1 -> V2 -> V3.
- `BACKWARD` checks V3 against V2 only.
- `BACKWARD_TRANSITIVE` checks V3 against both V2 and V1.

Transitive strategies are useful when older consumers remain running or historical data is retained long-term. They also constrain changes more strictly since compatibility must hold across many versions.

### Default Compatibility Should Not Be Guessed

According to Pulsar 5.0.x documentation, the default for Avro and JSON is `FULL`; other schema types typically default to `ALWAYS_INCOMPATIBLE`. Actual values depend on broker version and configuration. Before deploying, inspect the strategy of the specific topic and schema type; do not rely on defaults remembered from another cluster.

Schema compatibility checks data structure only according to the strategy. It does not prove business meaning remained unchanged. For example, changing `total`'s currency unit from VND to USD while keeping a decimal type may be structurally compatible yet semantically broken. Version semantics or add an explicit currency field.

## 10. Safe Schema Changes

A schema evolution workflow should include these steps:

1. Identify which schema versions producers and consumers currently use.
2. Inspect the current schema on the topic and its compatibility strategy.
3. Create the new schema in a test environment.
4. Verify the new schema is compatible under the chosen strategy.
5. Deploy consumers capable of reading both old and new schemas.
6. Only then deploy producers emitting the new schema.
7. Monitor deserialization errors, schema rejections, and consumer lag.
8. Retire support for old schemas only after old data expires from retention or all consumers have upgraded.

This is typically a consumer-first rollout when backward compatibility is required: new consumers must be able to read old messages before producers begin emitting new messages.

Do not delete old schemas just to tidy up the registry. Historical messages may still require older schema versions for decoding. Keeping schema history is part of replay and audit capability.

## 11. Header Conversion Between Pulsar and Spring Message

Payload schemas and message headers are two separate parts. Native schemas determine how payloads are encoded/decoded; the Pulsar binder must also convert metadata/headers between Pulsar messages and Spring `Message` instances.

The Pulsar binder provides a default `PulsarHeaderMapper`. You can replace it with a custom `PulsarHeaderMapper` bean, such as `JsonPulsarHeaderMapper`, to control:
- `inboundPatterns`: which headers are copied from Pulsar into Spring `Message`.
- `outboundPatterns`: which headers are sent from Spring `Message` out to Pulsar.
- `trustedPackages`: which packages are allowed when deserializing object headers.
- `toStringClasses`: header types represented as strings.

Example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.pulsar.support.header.JsonPulsarHeaderMapper;
import org.springframework.pulsar.support.header.PulsarHeaderMapper;

@Configuration
class PulsarHeaderConfiguration {

    @Bean
    PulsarHeaderMapper pulsarHeaderMapper() {
        return JsonPulsarHeaderMapper.builder()
            .inboundPatterns("!secret", "*")
            .outboundPatterns("!password", "!accessToken", "*")
            .trustedPackages("com.acme.events")
            .build();
    }
}
~~~

Exact package names and APIs should be verified against the Spring for Apache Pulsar version in use. The example illustrates a header filtering policy: exclude `secret` from entering the application and prevent `password`/`accessToken` from being emitted to the broker.

Do not place the entire business payload inside headers. Headers belong to correlation IDs, trace IDs, tenants, event types, or routing metadata. Payload schemas should hold structured business data.

### Headers Do Not Replace Schemas

A `content-type` or `event-type` header does not register a Pulsar schema. When using native encoding, `schema-type` and `message-type` determine the serializer/deserializer. The header mapper controls only message metadata. Both configurations must be tested independently.

## 12. Configuration Levels and Precedence Order

The Pulsar binder uses Spring for Apache Pulsar to create producers and consumers. Thus, properties can be configured at multiple levels:

- Spring Boot properties: `spring.pulsar.producer...`, `spring.pulsar.consumer...`
- Binder-wide properties: `spring.cloud.stream.pulsar.binder.producer...`, `spring.cloud.stream.pulsar.binder.consumer...`
- Extended binding properties: `spring.cloud.stream.pulsar.bindings.<binding-name>.producer...` or `consumer...`

Precedence order from highest to lowest:

1. Extended binding properties.
2. Binder properties.
3. Spring Boot properties.

Example:

~~~yaml
spring:
  pulsar:
    client:
      service-url: pulsar://localhost:6650
  cloud:
    stream:
      pulsar:
        binder:
          producer:
            batching-enabled: true
        bindings:
          publishOrder-out-0:
            producer:
              schema-type: JSON
              message-type: com.acme.orders.OrderCreated
              batching-enabled: false
~~~

In this example, `batching-enabled` at the binding level overrides the binder-level setting for output binding `publishOrder-out-0`. The Spring Boot service URL applies to the application-wide Pulsar client.

Use the binder level for shared settings. Use extended bindings when two functions or two topics need different schemas, batching, or producer/consumer behavior. Avoid setting the same property at multiple levels without documenting the effective value; when debugging, inspect property sources and the specific binding.

## 13. Custom Schema Mapping

If an application has many data types or wants shared schema mappings, you can configure custom schema mappings in the Pulsar binder. When `schema-type` is omitted, the binder can consult these mappings to determine the appropriate schema.

Custom mappings help:
- Standardize schema types for shared classes.
- Avoid repeating `schema-type` and `message-type` across many bindings.
- Centralize mappings between Java types and Pulsar Schemas.

However, mappings do not replace broker-side schema compatibility. Mappings only help the binder choose a schema/data type; the Pulsar broker still manages `SchemaInfo` per topic and checks compatibility when producers/consumers connect.

When modifying a mapping, check every binding using that class. A new mapping could switch a producer from `Schema.BYTES` to a native schema or change the schema type, impacting running consumers.

## 14. Common Errors

| Symptom | Possible cause | Resolution |
|---|---|---|
| JSON payload works but topic has no JSON Schema | Using framework conversion and `Schema.BYTES` | Enable native encoding and declare `schema-type`/`message-type` |
| Native consumer fails to deserialize | Missing `use-native-decoding` or wrong `schema-type`/`message-type` | Check input binding configuration and class |
| Producer/consumer use incompatible schemas | Incompatible message type or schema version | Inspect `SchemaInfo` and compatibility strategy |
| Producer rejected by broker on creation | New schema is incompatible or auto-update is restricted | Check compatibility strategy and register schema |
| Native Avro read as JSON | Producer/consumer disagree on schema type | Align Avro contract and native decoding |
| `message-type` not found | Incorrect fully qualified class name or class missing from classpath | Check package, dependencies, and classloader |
| `KeyValue` deserializes incorrectly | Missing `message-key-type`/`message-value-type` or mismatched encoding | Declare both types and align `INLINE`/`SEPARATED` |
| `contentType` has no effect as expected | Binding has native encoding/decoding enabled | Configure Pulsar schema instead of relying on `MessageConverter` |
| Headers are lost | Header mapper does not match the corresponding pattern | Check inbound/outbound patterns |
| Sensitive headers leaked out | Mapper allows overly broad wildcard | Use explicit deny patterns and `trustedPackages` |
| New schema accepted but business logic fails | Structurally compatible but semantics changed | Version semantics and run contract tests |
| One function overrides another's settings | Using binder-wide property when binding needs specific settings | Move to extended binding properties |

## 15. Testing Framework Conversion and Native Schema

Test the two conversion paths separately. Do not use a single test to conclude both framework converters and Pulsar native schemas work properly.

### Testing Framework Conversion

1. Configure producer and consumer without enabling native encoding/decoding.
2. Send a Java record with `contentType` `application/json`.
3. Verify the payload travels through Pulsar as `Schema.BYTES`.
4. Verify the consumer receives bytes and Spring `MessageConverter` converts them to the expected Java type.
5. Check optional fields, decimals, timestamps, and nested objects.
6. Verify the broker is not assumed to be validating JSON schema.

### Testing Native JSON/Avro

1. Enable `use-native-encoding` on the producer.
2. Declare `schema-type` and `message-type`.
3. Enable `use-native-decoding` on the consumer.
4. Use the same or a compatible schema.
5. Send messages and verify the consumer receives the right object.
6. Inspect `SchemaInfo` and schema version on the topic.
7. Test a producer with an incompatible schema and verify the broker rejects it when compatibility enforcement is enabled.
8. Test old/new consumer schemas under `BACKWARD`/`FORWARD`/`FULL` strategies.

### Testing KeyValue and Headers

- Send key/value with two distinct types.
- Verify key/value types and `INLINE`/`SEPARATED` encoding.
- Verify correlation ID and event type are mapped via `PulsarHeaderMapper`.
- Verify `secret`/`password`/`accessToken` do not pass through the header mapper.
- Test an object header from an untrusted package and check deserialization behavior.

### Testing Migration

- Run producer v1 and consumer v1.
- Deploy consumer v2 capable of reading v1.
- Register schema v2.
- Switch producer to v2.
- Verify consumer v1/v2 behavior per compatibility strategy.
- Monitor schema rejections and deserialization errors.

Use a dedicated Pulsar broker or Testcontainers in integration tests. Unit testing `MessageConverter` does not replace testing the schema registry and compatibility at the broker.

## 16. Hands-On Exercise: Migrating the `orders` Topic to Native JSON Schema

Assume a system has a producer emitting `OrderCreated` and a consumer processing orders.

1. Create Java record `OrderCreated` with `eventId`, `orderId`, `total`.
2. Write a `Supplier` or `StreamBridge` producer emitting events.
3. Start with framework conversion and `contentType` `application/json`.
4. Verify messages travel through Pulsar using `Schema.BYTES`.
5. Enable `use-native-encoding` for the output binding.
6. Set `schema-type` `JSON` and `message-type` to the `OrderCreated` class.
7. Enable `use-native-decoding` for the input binding.
8. Set the corresponding `schema-type` and `message-type` on the consumer.
9. Send messages and verify the consumer receives the expected object.
10. Inspect `SchemaInfo` and the schema version on the `orders` topic.
11. Add an optional `currency` field to `OrderCreated` v2.
12. Check schema compatibility before deploying the new producer.
13. Test the old consumer against v2 messages and record the outcome.
14. Try a custom `PulsarHeaderMapper` to preserve `correlationId` while stripping sensitive headers.
15. Run integration tests against a broker and document the topic contract.

Acceptance checklist:

| Item | Verification criteria |
|---|---|
| Conversion mode | Framework vs. native explicitly chosen per binding |
| Producer | `use-native-encoding` configured properly when using Pulsar Schema |
| Consumer | `use-native-decoding` configured properly when using Pulsar Schema |
| Schema type | `JSON`/`AVRO`/`KeyValue` matches contract |
| Message type | Fully qualified class name is accurate |
| SchemaInfo | Schema and version exist on topic when native schema is used |
| Compatibility | Schema changes accepted or rejected by broker per policy |
| Headers | `PulsarHeaderMapper` maps properly and strips secrets |
| Key/value | Key/value types and encoding aligned |
| Configuration precedence | Binding overrides binder and Boot in proper order |
| Integration test | Real producer and consumer read and write data end-to-end |

## Conclusion

Spring Cloud Stream framework conversion and native Pulsar Schema are two distinct mechanisms. Framework conversion defaults to `application/json`, converts payloads to `byte[]`, and the Pulsar binder sends them using `Schema.BYTES`. This is convenient for middleware-neutral applications, but does not automatically register JSON/Avro schemas with the Pulsar broker.

Native encoding/decoding delegates serialization responsibility to Pulsar Schema. Producers and consumers enable `use-native-encoding`/`use-native-decoding` per binding and declare `schema-type` and `message-type`; for `KeyValue`, `message-key-type` and `message-value-type` can be specified. Pulsar manages `SchemaInfo`, schema versions, and compatibility per topic.

Choose one clear representation per topic, validate schema evolution before deploying new producers, configure header mappers to govern metadata, and test against a real broker. Content type, native schema, and headers are three separate concerns; configure and verify each one properly so services can exchange events reliably.

## References

- [Spring Cloud Stream 5.0.4 – Binder for Apache Pulsar](https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html)
- [Spring for Apache Pulsar – Message Conversion and Pulsar Schema](https://docs.spring.io/spring-pulsar/reference/)
- [Apache Pulsar 5.0 – Schema Overview](https://pulsar.apache.org/docs/5.0.x/schema-overview/)
- [Apache Pulsar 5.0 – Understand Schema and Compatibility](https://pulsar.apache.org/docs/5.0.x/schema-understand/)
- [Apache Pulsar – Manage Schemas](https://pulsar.apache.org/docs/5.0.x/admin-api-schemas/)
