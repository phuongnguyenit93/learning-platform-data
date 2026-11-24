# Type Headers When Evolving Classes

Spring Kafka can attach **type headers** to Kafka records when using `JsonSerializer`. These headers tell the consumer which Java type a JSON payload should be deserialized into. This approach is convenient when a single topic carries multiple event types, but it can create coupling between producer and consumer if headers contain the fully qualified class name (FQCN) of a Java class.

When a class is renamed, moved to another package, or extracted into a separate contract module, old consumers may fail to find the class recorded in the header. One way to reduce coupling is **type mapping**: the producer emits a stable token such as `order-created`, while each consumer maps that token to the corresponding DTO in its own codebase. Type headers only select the target type for deserialization; they do not replace schemas, versioning, or payload compatibility rules.

This lesson belongs to the **Schema and Data Evolution** chapter of the **SPRING_KAFKA_MESSAGING** module, focusing on how type headers work in Spring Kafka, how to evolve classes safely between producers and consumers, and how to test compatibility across multi-version deployments.

## Learning Outcomes

After this lesson, you will be able to:

- Explain the role of JSON type headers in Spring Kafka.
- Identify headers such as `__TypeId__`, `__ContentTypeId__`, and `__KeyTypeId__`.
- Understand the risks when type headers contain a producer's FQCN or package name.
- Configure `spring.json.type.mapping` on both producer and consumer.
- Use stable tokens to decouple event contracts from internal class names.
- Choose between type headers and a default target type.
- Handle topics with a single event type or multiple event types.
- Distinguish type headers from event versions and Schema Registry.
- Manage trusted packages and risks from untrusted type headers.
- Test class renames, package moves, and rolling deployments across versions.

## 1. What problem do type headers solve?

A Kafka record has a key, value, and headers. When the value is JSON, the raw bytes do not tell Jackson which Java class they should become. Spring Kafka can attach type metadata to the record so the consumer can select the deserialization target type.

Example producer sending an object:

~~~java
public record OrderCreated(
        String eventId,
        String orderId,
        Instant occurredAt
) {}
~~~

With `JsonSerializer`, Spring Kafka can write a type header alongside the JSON payload:

~~~text
Kafka record
├── key: order-1001
├── value: {"eventId":"evt-1","orderId":"order-1001",...}
└── headers
    └── __TypeId__: com.acme.orders.events.OrderCreated
~~~

A consumer using `JsonDeserializer` can read the type header to determine the target class. This is useful when a single topic carries multiple event classes, though the class name becomes part of the metadata exchanged between the two applications.

If the producer moves the package from `com.acme.orders.events.OrderCreated` to `com.acme.contract.OrderCreated`, consumers still relying on the old FQCN may fail to deserialize new records.

## 2. Common type headers

The Spring Kafka JSON serializer can write the following type headers:

| Header | Role |
|---|---|
| `__TypeId__` | Type ID of the primary payload. |
| `__ContentTypeId__` | Type ID of content elements, such as the element type inside a collection. |
| `__KeyTypeId__` | Type ID of the key when the key is also serialized with JSON type metadata. |

For a simple object payload, `__TypeId__` is usually the most important header. When the payload is a collection, map, or generic structure, content/key type metadata can be used to resolve element types.

Header values are stored as `byte[]` in Kafka. With `ConsumerRecord`, the application can inspect raw headers. With `JsonDeserializer`, the framework can consume type metadata during deserialization.

Header names and usage belong to the Spring Kafka JSON serializer/deserializer. Do not assume every JSON serializer writes the same set of headers.

## 3. Risks when type headers contain FQCNs

Without type mapping configured, the JSON serializer can typically write the Java class name as the type ID. The consumer must then locate that class on its classpath and allow deserialization of that class.

Example of producer and consumer coupled to the same FQCN:

~~~text
Producer:
com.acme.orders.events.OrderCreated

Kafka header:
__TypeId__ = com.acme.orders.events.OrderCreated

Consumer:
expects com.acme.orders.events.OrderCreated
~~~

Changes that can break compatibility:

- Renaming the class.
- Moving the class to a different package.
- Moving the DTO into a new contract module.
- Producer and consumer using out-of-sync library versions.
- Consumer lacking the dependency that contains the producer's class.
- Different classes sharing the same name with different structures or business meanings.

A consumer should not have to import a producer's entire internal module just to deserialize an event. The event contract should remain independent of any single service's package structure.

## 4. Type mapping: stable tokens instead of class names

Spring Kafka supports the `spring.json.type.mapping` property to map a token to a local Java class.

Example producer mapping its class to the `order-created` token:

~~~yaml
spring:
  kafka:
    producer:
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      properties:
        spring.json.type.mapping: order-created:com.acme.orders.events.OrderCreated
~~~

Consumer mapping the same token to its own DTO:

~~~yaml
spring:
  kafka:
    consumer:
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.trusted.packages: com.acme.fulfillment.contract
        spring.json.type.mapping: order-created:com.acme.fulfillment.contract.OrderCreated
~~~

Producer and consumer can use classes in different packages while the wire token on Kafka stays `order-created`.

~~~text
Producer class
com.acme.orders.events.OrderCreated
          |
          | producer type mapping
          v
Kafka __TypeId__ = order-created
          |
          | consumer type mapping
          v
Consumer class
com.acme.fulfillment.contract.OrderCreated
~~~

Type mapping eliminates dependence on the producer's FQCN. However, both classes must still remain compatible in JSON structure and field semantics. A stable token does not automatically transform schemas or repair incompatible data.

## 5. Complete configuration for producer and consumer

Spring Boot example for two independent applications:

**Producer application**

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      properties:
        spring.json.type.mapping: order-created:com.acme.orders.events.OrderCreated
~~~

**Consumer application**

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: orders-fulfillment
      enable-auto-commit: false
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.trusted.packages: com.acme.fulfillment.contract
        spring.json.type.mapping: order-created:com.acme.fulfillment.contract.OrderCreated
        spring.json.use.type.headers: true
~~~

Ensure producer and consumer agree on the exact token. The class name after the colon is local to each application and does not need to match.

In projects with multiple `ProducerFactory` or `ConsumerFactory` beans, verify that properties are applied to the right factory. Configuration under `spring.kafka.producer.properties` does not automatically apply to a manually constructed `ProducerFactory` that bypasses Boot properties.

## 6. Using type mapping for multiple event types

Type mapping is especially useful when one topic carries multiple event types.

Example producer:

~~~yaml
spring:
  kafka:
    producer:
      properties:
        spring.json.type.mapping: >-
          order-created:com.acme.orders.OrderCreated,
          order-cancelled:com.acme.orders.OrderCancelled
~~~

The consumer can map those tokens to its own contracts:

~~~yaml
spring:
  kafka:
    consumer:
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.trusted.packages: com.acme.fulfillment.contract
        spring.json.type.mapping: >-
          order-created:com.acme.fulfillment.contract.OrderCreated,
          order-cancelled:com.acme.fulfillment.contract.OrderCancelled
~~~

When receiving token `order-created`, the deserializer selects DTO OrderCreated. For `order-cancelled`, it selects OrderCancelled.

Tokens must be unique within an application's mapping and managed as part of the event contract. Do not change a token simply because a Java class is renamed or a package is refactored.

If a consumer does not need to support a given event type, consider splitting topics or explicit routing rather than creating an overly broad mapping for every class.

## 7. Type headers vs. default target type

Not every application needs type headers. If a topic carries only one fixed payload type, the consumer can configure a default target type.

~~~yaml
spring:
  kafka:
    consumer:
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.use.type.headers: false
        spring.json.value.default.type: com.acme.fulfillment.contract.OrderCreated
        spring.json.trusted.packages: com.acme.fulfillment.contract
~~~

When `spring.json.use.type.headers=false`, the consumer ignores type headers for determining the target type and uses the configured default value type.

This fits when a topic has a single fixed event contract. If a topic holds multiple event types, a single default type cannot select the right DTO; use type mapping/type headers or an envelope with an explicit discriminator and matching deserializer.

Do not disable type headers on the consumer while expecting it to distinguish multiple classes via mapping. Mapping requires an incoming type ID to select the class.

## 8. When should writing type headers be disabled?

A producer can omit type metadata if consumers already know the target type and the topic contract has only one payload kind.

Example:

~~~yaml
spring:
  kafka:
    producer:
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      properties:
        spring.json.add.type.headers: false
~~~

The corresponding consumer uses a default type:

~~~yaml
spring:
  kafka:
    consumer:
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.use.type.headers: false
        spring.json.value.default.type: com.acme.contract.OrderCreated
        spring.json.trusted.packages: com.acme.contract
~~~

Disabling type headers reduces record dependence on class metadata, but producers and consumers must agree that the topic carries only one payload type or use another type-discrimination mechanism.

If a topic carries multiple event classes, do not disable type headers before an alternative discriminator/deserializer solution is in place.

## 9. Header removal after deserialization

After `JsonDeserializer` uses type headers to instantiate the object, Spring Kafka may strip type headers from the record according to the version's default setting. This prevents internal deserialization metadata from appearing as application headers in the listener.

You can configure retaining type headers if the application needs to inspect metadata after deserialization:

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        spring.json.remove.type.headers: false
~~~

If exact raw headers must be audited, test the behavior against your actual Spring Kafka version. When the deserializer removes headers, the listener may no longer see them in `ConsumerRecord` headers.

Do not rely on post-deserialization type headers to authenticate the sender. Headers are merely metadata provided by the producer, not a digital signature or proof of identity.

## 10. Type headers are not event versions

Type ID and event version answer two different questions:

- Type ID: which event type/class does the payload belong to?
- Event version: which contract version is that event type using?

Example:

~~~text
__TypeId__ = order-created
event_version = 2
~~~

Type mapping can keep the `order-created` token unchanged while the schema expands compatibly. For incompatible changes, you can use a versioned token such as `order-created-v2` or keep the event-type token and version separate per contract convention.

Do not use class names like `OrderCreatedV2` as the sole versioning mechanism. Class names are implementation details; event versions need clear semantics for all producers and consumers.

## 11. Type mapping does not guarantee schema compatibility

Suppose the consumer maps token `order-created` to this class:

~~~java
public record OrderCreated(
        String eventId,
        String orderId,
        String currency
) {}
~~~

The producer may add a new field:

~~~java
public record OrderCreated(
        String eventId,
        String orderId,
        String currency,
        String salesChannel
) {}
~~~

Whether the consumer can deserialize still depends on Jackson configuration, field types, constructors, nullability, and unknown-property handling rules. Type mapping only selects the target class.

When evolving a schema, evaluate:

- Adding optional fields with defaults or explicit null handling.
- Whether removing a field still breaks old consumers.
- Whether changing data types prevents JSON deserialization.
- Whether changing enums causes old consumers to reject new values.
- Changing timestamp, decimal, or identifier formats.
- Whether new producers can run alongside old consumers during rolling deployments.
- Whether new consumers can read old records still within retention.

Type headers and schema compatibility are two separate layers that must be managed independently.

## 12. Safe package moves and class renames

Suppose the producer changes its package:

~~~text
Before:
com.acme.orders.events.OrderCreated

After:
com.acme.contracts.orders.OrderCreated
~~~

If the Kafka header carries an FQCN, consumers tied to the old name can fail. With type mapping, the producer simply keeps the token stable:

~~~yaml
spring:
  kafka:
    producer:
      properties:
        spring.json.type.mapping: order-created:com.acme.contracts.orders.OrderCreated
~~~

The consumer keeps its mapping:

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        spring.json.type.mapping: order-created:com.acme.fulfillment.contract.OrderCreated
~~~

Refactoring classes on the producer side does not alter the wire token. Deploy payload-compatible consumers first or concurrently per your rollout strategy before emitting payloads with schema changes.

Do not change the token during the same refactor without a migration plan for every consumer reading the topic.

## 13. Rolling deployments between producer and consumer

During rolling deployments, multiple versions of producers and consumers can run concurrently. Type headers must be designed so versions can communicate throughout the overlap window.

A safe sequence:

1. Identify the current type token and JSON contract being emitted.
2. Deploy new consumers with mappings for the current token and support for the new payload if needed.
3. Verify new consumers can read old records still in the topic.
4. Deploy new producers while continuing to emit the stable token.
5. If the schema changed, emit new fields/values only after compatible consumers are ready.
6. Monitor deserialization errors and DLT throughout the rollout.
7. Retire support for the old contract only after the retention window expires and no old consumers remain.

If a new token is needed, consumers must be deployed with support for that token before producers emit records using it. If producers emit it first, old consumers may not recognize the token and fail deserialization.

## 14. Trusted packages and untrusted type headers

`JsonDeserializer` provides a trusted packages mechanism to restrict which class packages may be deserialized when type headers contain class names.

Example:

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        spring.json.trusted.packages: com.acme.fulfillment.contract,com.acme.shared.events
~~~

Do not set `*` in production without a compelling reason and security review. Trust only the packages required by your contract.

Trusted packages act as an allowlist for type resolution, not an authentication mechanism. Producers can still send forged payloads or headers; consumers must validate data, enforce topic access controls, and never use type headers as authorization evidence.

Mapping tokens to local classes reduces reliance on loading classes by external FQCN, though mappings and inputs still require validation. Do not map unbounded tokens to arbitrary classes derived from payloads.

## 15. Polymorphic payloads and class hierarchies

Some applications use an interface or abstract class as a shared supertype:

~~~java
public sealed interface OrderEvent
        permits OrderCreated, OrderCancelled {}

public record OrderCreated(String orderId) implements OrderEvent {}

public record OrderCancelled(String orderId, String reason)
        implements OrderEvent {}
~~~

The producer can serialize concrete implementations and write the corresponding type mapping. The consumer needs mappings for each permitted subtype.

If a consumer only accepts `OrderEvent` without mappings for its subtypes, deserialization can fail or fail to instantiate the expected type. Define the exact list of valid subtypes and test each one.

Do not widen trusted packages excessively just to support polymorphism. The list of subtypes should be a managed, reviewed, and versioned part of the contract.

## 16. Inspecting type headers for investigation

You can read headers directly from `ConsumerRecord`:

~~~java
Header typeHeader = record.headers().lastHeader("__TypeId__");

String typeId = typeHeader == null || typeHeader.value() == null
        ? null
        : new String(typeHeader.value(), StandardCharsets.UTF_8);
~~~

This code reads the raw header only if it still exists after deserialization. If `JsonDeserializer` stripped type headers per configuration, the value may no longer be present in the listener's record.

To inspect raw type metadata, use a test consumer with `ByteArrayDeserializer` or configure `spring.json.remove.type.headers=false`. Do not log full payloads or sensitive headers in production logs.

When a type ID is an FQCN, check whether that class exists on the consumer classpath and belongs to trusted packages. When it is a token, check the consumer's token mapping.

## 17. Common errors when evolving classes

| Symptom | Possible cause | Resolution |
|---|---|---|
| `ClassNotFoundException` | Header contains an FQCN that no longer exists on the consumer | Use stable type mapping or keep compatibility classes during migration. |
| Unmapped Type ID | New token is not yet configured in the consumer | Deploy consumer mapping before producers emit the new token. |
| Untrusted type | Package is not listed in trusted packages | Add the exact reviewed contract package; do not open wildcards casually. |
| JSON mapping error | Payload fields/types are incompatible with DTO | Check schema, fields, enums, and Jackson configuration. |
| Consumer selects wrong class | Misconfigured header/type mapping or duplicate token | Standardize tokens and test mapping on both sides. |
| Type header missing | Producer disabled adding type headers or uses another serializer | Verify active serializer and effective configuration. |
| Listener does not see type header | Deserializer removed type headers | Configure keeping headers if auditing is needed. |
| Multi-event topic with fixed default type | Consumer cannot select the right subtype | Use type mapping/type headers or a discriminator strategy. |

When deserialization fails, records may route to the error handler/DLT. Preserve raw bytes and headers for investigation, because failed deserialization means the listener never received an object.

## 18. Testing type headers and class evolution

An integration test suite should verify the metadata actually written to Kafka records and confirm the consumer maps to the right local class.

| Scenario | What to verify |
|---|---|
| Producer mapping | Header contains token `order-created`, not an internal FQCN. |
| Consumer mapping | Token deserializes into the DTO in the consumer's package. |
| Package move | Producer changes package while keeping token; consumer still reads it. |
| Class rename | Class refactoring does not alter the wire token. |
| Multiple event types | Each token selects the proper subtype. |
| Unknown token | Consumer fails cleanly and the record flows through the error path. |
| Default type | Single-payload-type topic deserializes cleanly without type headers. |
| Type headers disabled | Producer/consumer remain compatible per default type/discriminator configuration. |
| Trusted package | Untrusted classes are rejected. |
| Rolling compatibility | Old/new consumers read the supported payload set. |
| Header retention | Type header is preserved or stripped per configuration. |
| Raw DLT | Payload and type headers are preserved for deserialization failure investigation. |

Example verifying the type header via `ConsumerRecord`:

~~~java
Header header = received.headers().lastHeader("__TypeId__");

assertThat(header).isNotNull();
assertThat(new String(header.value(), StandardCharsets.UTF_8))
        .isEqualTo("order-created");
~~~

To verify the target class, send records with a real producer and receive them via a consumer configured with the application's `JsonDeserializer` and type mapping. Unit tests on map strings alone do not prove that serializers/deserializers are using the right properties.

Use EmbeddedKafka or Testcontainers and await records using Awaitility or a latch with a timeout. Avoid fixed `Thread.sleep` calls.

## 19. Conventions for managing type tokens

Type tokens are part of the protocol between producer and consumer. Establish clear conventions:

- Use stable, descriptive names without Java package names.
- Never reuse a token for a different event meaning.
- Keep the token unchanged during class or package refactors.
- Use versioned tokens when incompatible contracts must be separated.
- Publish token mappings in event contract documentation.
- Deploy consumers supporting a token before producers emit the new token.
- Maintain tests for every active token.
- Do not expose internal class names or module names as public contracts.
- Manage token deprecation alongside retention periods and rollout schedules.

Example tokens:

| Token | Meaning |
|---|---|
| `order-created` | Order creation event. |
| `order-cancelled` | Order cancellation event. |
| `order-created-v2` | Version 2 contract when an incompatible change requires separating tokens. |

Tokens do not need a version suffix for compatible contract changes. Versioning decisions should follow the system's schema policy rather than whether a Java class was renamed.

## 20. When to use Schema Registry?

Type mapping solves Java class selection at the consumer. It does not provide a schema repository, compatibility enforcement, schema IDs, or full cross-language support.

If your system spans multiple services, multiple languages, or requires strict schema evolution governance, consider Avro, Protobuf, or JSON Schema alongside a platform-appropriate Schema Registry.

| Requirement | Spring Kafka Type Mapping | Schema Registry |
|---|---|---|
| Select Java class from a type token | Yes | Not primary purpose |
| Decouple producer/consumer FQCNs | Yes | Can decouple via schema contract/serializer |
| Store and manage schema versions | No | Yes |
| Policy-based compatibility checks | Not built-in | Yes, depending on registry and config |
| Multi-language support | Limited if tied to Jackson/Java | Better suited with cross-language schema formats |
| Schema IDs and schema lookup | No | Yes |

Type mapping works well for simple JSON applications with manually managed contracts. As governance requirements grow, Schema Registry helps catch breaking changes before producers emit new data.

## 21. Capstone exercise: refactor OrderCreated without changing the wire contract

Assume two applications:

- Producer previously used `com.acme.orders.events.OrderCreated`.
- Consumer uses `com.acme.fulfillment.contract.OrderCreated`.

Requirements:

1. Configure the producer `JsonSerializer` with token `order-created`.
2. Configure the consumer `JsonDeserializer` mapping the token to the consumer's DTO.
3. Send a record and verify Kafka header `__TypeId__` holds the token rather than an FQCN.
4. Change the producer class's package while keeping the token unchanged.
5. Verify the consumer needs no package mapping changes.
6. Add event type `order-cancelled` and its corresponding subtype mapping.
7. Test a consumer missing the mapping for the new token and observe error handling/DLT.
8. Disable type headers for a single-event topic and configure a default target type.
9. Test an untrusted package rejection.
10. Verify header removal behavior after deserialization.
11. Add an optional field to the payload and verify old consumers handle it per contract.
12. Simulate a rolling deployment with two producer/consumer versions.
13. Write integration tests covering class rename, package move, and multiple event types.
14. Document type token conventions and the deprecation process for old tokens.

The exercise is complete when the producer can refactor internal classes without altering the wire type token, the consumer maps the token to its own DTO, and payloads remain schema-compatible.

## 22. Learning sequence and completion criteria

| Stage | Core focus | Self-check criteria |
|---|---|---|
| 1. Type metadata | `__TypeId__` and related headers | Able to read and explain type headers. |
| 2. FQCN coupling | Package/class renames | Able to explain why old consumers can fail. |
| 3. Type mapping | Token-to-class mapping | Producer/consumer use different packages with the same token. |
| 4. Multiple types | Polymorphic events | Correctly maps each event subtype. |
| 5. Default target | Single topic, single payload type | Deserializes cleanly without type headers. |
| 6. Header policy | Add/use/remove type headers | Controls metadata lifecycle. |
| 7. Schema evolution | Fields and event versions | Distinguishes type tokens from schema versions. |
| 8. Security | Trusted packages and untrusted headers | Safely restricts type resolution. |
| 9. Deployment | Rolling upgrades and backward compatibility | New consumers support old records and new producers. |
| 10. Testing | Round-trip and compatibility matrix | Verifies wire headers alongside target classes. |

This lesson is complete when you can explain the risks of FQCNs in type headers, configure bidirectional type mapping, choose a default target type for single-type topics, and test class/package evolution without unexpectedly changing the wire contract.

Type headers help Spring Kafka select Java classes during JSON deserialization, yet Java classes are implementation details that can change. Use stable tokens to reduce coupling, manage event versions and schema compatibility separately, restrict trusted packages, and test producers and consumers across rolling deployments.

