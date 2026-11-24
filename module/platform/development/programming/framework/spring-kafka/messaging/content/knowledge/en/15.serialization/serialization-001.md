# What Are Serializers and Deserializers?

Kafka transmits and stores records as bytes. A producer may work with Java objects, strings, or application data types; a consumer also wants to receive data in a meaningful type. Serializers and deserializers handle those two conversion directions:

- **Serializer** converts a key or value from an application data type into a byte array before the producer sends a record.
- **Deserializer** converts the byte array read by the consumer back into an application data type.

In Spring Kafka, a serializer is configured for the producer and a deserializer is configured for the consumer. Both sides must agree on the byte format, schema, and how the data is interpreted. If a producer sends JSON while a consumer decodes it as Avro, the broker may still store the record successfully, but the consumer will fail when reading or converting the payload.

Serialization is therefore part of the communication contract between services. A sound design considers the data format, compatibility when schemas evolve, handling of malformed data, and how errors are observed in operations.

This lesson belongs to the **Serialization** chapter of the **SPRING_KAFKA_MESSAGING** module. The module focuses on building applications that send and receive events using Spring Kafka, `KafkaTemplate`, and `@KafkaListener`, understanding topics, partitions, offsets, and consumer groups, while also learning serialization, retries, dead-letter handling, transactions, exactly-once semantics, concurrency, and testing to operate reliable messaging flows.

## 1. Where Does Serialization Fit in the Kafka Flow?

A Kafka record has a key, a value, and metadata such as timestamp and headers. The broker does not need to know what type a Java object has; it receives and stores the key/value bytes along with the record metadata.

~~~mermaid
flowchart LR
    A[Application object] --> B[Serializer]
    B --> C[Key bytes and value bytes]
    C --> D[Kafka Producer]
    D --> E[Kafka Broker and partition]
    E --> F[Kafka Consumer]
    F --> G[Key bytes and value bytes]
    G --> H[Deserializer]
    H --> I[Application object]
~~~

On the producer side:

1. The service creates an event, for example `OrderCreated`.
2. `KafkaTemplate` builds a record with a topic, key, value, and headers.
3. The producer invokes the serializer for the key and value.
4. The Kafka client sends the bytes to the broker.

On the consumer side:

1. The Kafka consumer fetches records as bytes.
2. The consumer invokes the deserializer for the key and value.
3. Spring Kafka receives the decoded object and passes it to the listener.
4. The listener processes the business data.

Serializers/deserializers do not determine the topic, partition, offset, or consumer group. They only convert the data representation at the boundary between the application and the Kafka client.

## 2. How Do Serializers and Deserializers Work?

### 2.1. Serializer

A serializer takes a Java value and converts it into bytes. In the Kafka client, the core interface is `org.apache.kafka.common.serialization.Serializer<T>`.

For example, `StringSerializer` converts a string into bytes according to the charset used by the implementation. Spring Kafka's `JsonSerializer` converts an object into JSON bytes.

Given an event:

~~~java
public record OrderCreated(
    String eventId,
    String orderId,
    BigDecimal total,
    Instant occurredAt
) {}
~~~

The producer can pass this object to `KafkaTemplate`:

~~~java
kafkaTemplate.send("order-events", event.orderId(), event);
~~~

If the value serializer is `JsonSerializer`, the `OrderCreated` object is converted into JSON bytes before being sent. If the key serializer is `StringSerializer`, `orderId` is converted into separate bytes for the key.

### 2.2. Deserializer

A deserializer takes bytes and converts them into an application type. The Kafka client defines `org.apache.kafka.common.serialization.Deserializer<T>`.

For example:

- `StringDeserializer` converts bytes into a `String`.
- `ByteArrayDeserializer` keeps the payload as `byte[]`.
- Spring Kafka's `JsonDeserializer` converts JSON bytes into a Java object based on the configured type/default type or type header.
- Avro/Protobuf deserializers decode according to their corresponding schema and mechanism.

The consumer can receive the event in a listener:

~~~java
@KafkaListener(
    topics = "order-events",
    groupId = "billing-service"
)
public void onOrderCreated(OrderCreated event) {
    billingService.startBilling(event);
}
~~~

The listener receives `OrderCreated` only when the consumer has decoded it successfully and Spring Kafka can pass the payload to the parameter type. If the deserializer fails, the listener method may never be invoked; the failure occurs during the poll/deserialization phase and must be handled by the container's error handling.

### 2.3. Both Directions Must Be Compatible

The serializer and deserializer do not necessarily have to be the exact same class. What matters is that the bytes produced by the producer match the format understood by the consumer.

| Producer serializer | Consumer deserializer | Result |
| --- | --- | --- |
| StringSerializer | StringDeserializer | Compatible for strings using the same encoding. |
| JsonSerializer | JsonDeserializer | Can be compatible if payload, type metadata, and type configuration match. |
| ByteArraySerializer | ByteArrayDeserializer | Preserves raw bytes; the application interprets the payload itself. |
| Avro serializer | Corresponding Avro deserializer | Requires consistent schema and schema identifier/registry. |
| JsonSerializer | Avro deserializer | Incompatible without a dedicated conversion layer. |

A producer sending valid JSON does not mean every consumer understands that schema. A contract needs to define fields, data types, null rules, versioning, and compatibility.

## 3. Key Serializer and Value Serializer

Each Kafka record can have a key and a value. The Kafka client invokes a separate serializer for each part:

- `key.serializer` converts the key into bytes.
- `value.serializer` converts the payload into bytes.

Spring Boot example:

~~~yaml
spring:
  kafka:
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
~~~

With this configuration, the key is a `String` and the value is an object serialized to JSON.

The key plays an important role in partitioning. The partitioner typically uses the key's bytes to select a partition. Therefore, the key serializer must be consistent across producers sending the same kind of key. If two services serialize the same business value into different bytes, partition mapping may differ and per-key ordering can be affected.

The value serializer formats the payload that consumers will read. It does not automatically turn a field inside the value into the Kafka key. If routing by `orderId` is needed, the producer must pass `orderId` explicitly as the key.

The consumer must configure the corresponding deserializers:

~~~yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
~~~

The key/value generic types on `KafkaTemplate` or `ConsumerFactory` provide compile-time type checking in Java code, but they do not replace serializer/deserializer configuration. Generic types do not automatically change the bytes on the wire.

## 4. Built-in Kafka Serializers and Deserializers

Kafka provides several common implementations in the `org.apache.kafka.common.serialization` package:

| Serializer | Deserializer | Data type |
| --- | --- | --- |
| StringSerializer | StringDeserializer | `String` |
| IntegerSerializer | IntegerDeserializer | `Integer` |
| LongSerializer | LongDeserializer | `Long` |
| ShortSerializer | ShortDeserializer | `Short` |
| FloatSerializer | FloatDeserializer | `Float` |
| DoubleSerializer | DoubleDeserializer | `Double` |
| ByteArraySerializer | ByteArrayDeserializer | `byte[]` |
| ByteBufferSerializer | ByteBufferDeserializer | `ByteBuffer` |
| UUIDSerializer | UUIDDeserializer | `UUID` |

Choose a serializer based on the data type and wire format required by the system. For simple strings or `byte[]`, the built-in serializers are usually sufficient. For business objects, you can choose JSON, Avro, Protobuf, or another schema-based format.

Do not casually use Java native serialization for cross-service events. Java serialization tightly couples the payload to Java class structure and runtime internals, making cross-language and cross-version compatibility difficult and introducing security risks when decoding untrusted data. Choose a format with a clear, controllable contract.

## 5. Configuring Spring Kafka JSON Serializer and Deserializer

Spring Kafka provides `JsonSerializer` and `JsonDeserializer` for working with JSON. This is a convenient option when Spring applications exchange structured events.

### 5.1. Producer Configuration with JsonSerializer

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
~~~

When calling:

~~~java
kafkaTemplate.send(
    "order-events",
    event.orderId(),
    new OrderCreated(
        "evt-100",
        "order-100",
        new BigDecimal("125.50"),
        Instant.now()
    )
);
~~~

`JsonSerializer` converts the object into JSON bytes. An example payload representation might look like:

~~~json
{
  "eventId": "evt-100",
  "orderId": "order-100",
  "total": 125.50,
  "occurredAt": "2026-11-17T03:00:00Z"
}
~~~

This is a JSON illustration; the actual representation of timestamps and decimal numbers depends on the Jackson configuration and the serializer in use.

### 5.2. Consumer Configuration with JsonDeserializer

The consumer needs to know the target type to convert JSON bytes into an object. You can configure a default type:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: billing-service
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.value.default.type: com.example.orders.events.OrderCreated
        spring.json.trusted.packages: com.example.orders.events
~~~

In this example:

- `spring.json.value.default.type` specifies the default Java type for the value.
- `spring.json.trusted.packages` restricts the packages that `JsonDeserializer` is allowed to instantiate when using type information.
- The package must match the actual location of the class in the consumer application.

Do not set trusted packages to `*` just to make deserialization errors disappear. Restrict trusted packages to only the event types you need to receive. Type headers from producers should also be controlled because they can contain class names; do not treat type metadata as a stable contract across services if internal packages may change.

### 5.3. Type Headers and Default Type

Spring Kafka's `JsonSerializer` can write Java type information into Kafka headers. `JsonDeserializer` can use the type header to decide which class to instantiate. This is convenient when a topic carries multiple event types, but it can couple the consumer to the producer's package/class names.

Several options are available:

- Use type headers generated by Spring Kafka and configure explicit type mappings.
- Disable type headers if the consumer already knows the target type via a default type.
- Use type mappings to map short, stable tokens to local classes.
- Use a shared envelope with `eventType`/`version` fields instead of relying on Java class names.

Example of disabling type headers on the producer:

~~~yaml
spring:
  kafka:
    producer:
      properties:
        spring.json.add.type.headers: false
~~~

When type headers are disabled, the consumer needs to know the target type via a default type or another mechanism. Do not disable headers and forget to configure the deserializer, otherwise the consumer may fail to determine which class to instantiate.

Specific property names and exact behavior should be verified against the Spring Kafka version in use. Spring Kafka can configure `JsonSerializer`/`JsonDeserializer` via properties or constructors/setters depending on the version's API.

## 6. Schemas and Compatibility When Data Evolves

Events often outlive a single application version. A producer may be deployed before or after a consumer; an older consumer may read records produced by a newer producer. Therefore, schema changes require compatibility rules.

Example initial schema:

~~~json
{
  "eventId": "evt-100",
  "orderId": "order-100",
  "total": 125.50
}
~~~

A later version adds a field:

~~~json
{
  "eventId": "evt-100",
  "orderId": "order-100",
  "total": 125.50,
  "currency": "VND"
}
~~~

If older consumers ignore unknown fields, adding a field can be compatible. However, compatibility also depends on the serializer/deserializer, Jackson configuration, data types, constructors, and application validation.

Commonly used principles:

- Add new fields with sensible defaults or allow missing fields when backward compatibility is needed.
- Avoid changing the type of an existing field if older consumers still read the data.
- Avoid renaming or removing fields that older consumers still depend on.
- Use a version/schema identifier when making incompatible changes.
- Test newer producers against older consumers and vice versa according to the deployment strategy.
- Do not reuse the same event type for payloads with different meanings.

### 6.1. Backward, Forward, and Full Compatibility

Compatibility terms commonly used in schema registries:

| Type | General meaning |
| --- | --- |
| Backward | A new consumer/schema can read data produced under an older schema. |
| Forward | An older consumer/schema can read data produced under a newer schema. |
| Full | Satisfies both backward and forward compatibility according to registry rules. |

The exact policy depends on the schema format and registry configuration. Plain JSON does not automatically provide a compatibility guarantee just because a field is added. With Avro/Protobuf and a schema registry, compatibility can be checked against the system's schema evolution rules.

### 6.2. Event Contracts Independent of Java Classes

Do not treat Java package and class names as the public contract of an event. If a producer moves a class from package `com.example.orders` to `com.example.ordering`, a consumer relying on type headers may fail to decode even though the JSON fields did not change.

A stable contract should describe:

- Event name and version.
- Required/optional fields.
- Field types and formats.
- Business meaning.
- Null/default rules.
- Compatibility rules for adding/modifying/removing fields.
- How event identity and correlation are represented.

You can use a schema registry or a shared contract repository to manage schemas. With plain JSON, a review process and compatibility tests are necessary because the broker does not automatically validate payload schemas.

## 7. Avro, Protobuf, and Schema-Based Formats

JSON is human-readable and widespread, but for systems with many services or strict schema requirements, Avro or Protobuf can be considered.

| Format | Characteristics |
| --- | --- |
| JSON | Human-readable, easy to debug, widespread; payloads are usually larger and schema enforcement depends on applications/tooling. |
| Avro | Schema-based, supports rule-driven schema evolution; typically used with a schema registry. |
| Protobuf | Compact binary format with field numbers and compatibility rules; well suited for polyglot environments. |
| Thrift/other formats | Suitable when the system already has corresponding contracts and tooling. |

When using a schema registry, the serializer typically registers or looks up the schema and then writes a schema identifier alongside the payload according to the serializer's wire format. The consumer deserializer fetches the corresponding schema to decode.

You cannot use `JsonDeserializer` to directly read Avro or Protobuf payloads. Each format requires its own matching serializer/deserializer and appropriate schema/registry configuration.

Choosing a format should be based on compatibility requirements, performance, payload size, observability, and schema governance capabilities. A binary format does not make a system reliable on its own without a schema management process.

## 8. Custom Serializers and Deserializers

For specialized data formats, you can implement Kafka's `Serializer` and `Deserializer` interfaces.

Example custom serializer for a simple type:

~~~java
public class OrderIdSerializer implements Serializer<OrderId> {

    @Override
    public byte[] serialize(String topic, OrderId data) {
        if (data == null) {
            return null;
        }

        return data.value().getBytes(StandardCharsets.UTF_8);
    }
}
~~~

Corresponding deserializer:

~~~java
public class OrderIdDeserializer implements Deserializer<OrderId> {

    @Override
    public OrderId deserialize(String topic, byte[] data) {
        if (data == null) {
            return null;
        }

        return new OrderId(
            new String(data, StandardCharsets.UTF_8)
        );
    }
}
~~~

This example assumes `OrderId` is a value object with a matching constructor and accessor. The serializer and deserializer must agree on encoding, null semantics, and validation.

When writing custom implementations, pay attention to:

- Handling `null` explicitly.
- Using an explicit encoding instead of relying on the machine's default charset.
- Never swallowing exceptions and returning dummy payloads.
- Not logging sensitive payloads.
- Closing resources if the serializer/deserializer owns dedicated resources.
- Not holding shared mutable state across multiple clients if the implementation is not thread-safe.
- Testing round-trips and malformed data.

Kafka `Serializer`/`Deserializer` interfaces include lifecycle methods such as `configure`/`close`. Implement them according to the Kafka client version's contract and how factories instantiate instances. If complex dependency injection is needed, Spring Kafka configuration supporting suppliers or configured instances can be used.

## 9. Null, Empty Bytes, and Tombstones

Three cases must be distinguished:

| Case | Meaning |
| --- | --- |
| Serializer receives `null` and returns `null` | The Kafka record has a corresponding `null` key/value. |
| Serializer returns an empty byte array | A payload exists with a length of 0 bytes. |
| Serializer returns a non-empty byte array | The payload contains bytes to be deserialized. |

In a compacted topic, a record with a non-null key and a `null` value is used as a tombstone to mark that the key should be deleted from the compacted state after compaction runs. A record with a `null` key is not a tombstone for a specific entity.

A deserializer can receive `null` data and must handle it according to application semantics. Do not automatically treat `null`, empty string, empty `byte[]`, and the JSON literal `null` as the same value.

For example:

- Kafka `null` value: no payload bytes exist.
- Empty `byte[]`: payload of length 0 bytes.
- JSON `null`: four byte characters `null` in UTF-8 JSON.
- JSON `{}`: an empty JSON object, completely different from the cases above.

Distinguishing these cases accurately is critical when handling tombstones, compacted topics, and optional data.

## 10. Headers and Metadata Do Not Replace Payload Schemas

Kafka records have headers to carry metadata such as correlation ID, trace ID, content type, or schema version. Headers can help a consumer choose how to process a record, but they do not guarantee payload compatibility on their own.

Example of a producer adding a header:

~~~java
ProducerRecord<String, OrderCreated> record =
    new ProducerRecord<>(
        "order-events",
        event.orderId(),
        event
    );

record.headers().add(
    "event-version",
    "2".getBytes(StandardCharsets.UTF_8)
);

kafkaTemplate.send(record);
~~~

The consumer can read the header:

~~~java
@KafkaListener(topics = "order-events", groupId = "billing-service")
public void onOrderCreated(
        ConsumerRecord<String, OrderCreated> record) {

    Header versionHeader = record.headers().lastHeader("event-version");
    String version = versionHeader == null
        ? "1"
        : new String(versionHeader.value(), StandardCharsets.UTF_8);

    billingService.process(version, record.value());
}
~~~

In this example, the `event-version` header is application-defined metadata. The consumer must handle missing or malformed headers. If a header dictates the schema, you must ensure producers always write it accurately and consumers have explicit mappings.

Do not use headers to carry arbitrarily large schema definitions or replace a schema registry. Headers are suited for small, stable, purpose-built metadata.

## 11. Complete Producer and Consumer Configuration in Spring Boot

Example basic JSON configuration:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      acks: all
      properties:
        spring.json.add.type.headers: false
    consumer:
      group-id: billing-service
      enable-auto-commit: false
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.value.default.type: com.example.orders.events.OrderCreated
        spring.json.trusted.packages: com.example.orders.events
~~~

Key points to note:

- The producer uses `StringSerializer` and `JsonSerializer`.
- The consumer uses `StringDeserializer` and `JsonDeserializer` accordingly.
- The producer disables type headers, so the consumer configures a default type.
- Trusted packages are restricted.
- Auto-commit is disabled so the listener container manages acknowledgements/commits as configured.

If a producer sends multiple event types to the same topic, a single default type may not suffice. In that case, you need type mappings, a shared envelope, a schema registry, or a deserializer that dispatches based on contract.

The class name in the default type must exist in the consumer application. If the producer and consumer have different packages, do not depend on type headers containing the producer's class name; use type mappings or a neutral contract.

## 12. Deserialization Errors and Error Handling

Serialization errors can occur on the producer before a record is sent. Deserialization errors occur on the consumer when bytes cannot be converted into the expected type.

Common causes:

- Invalid JSON or a truncated payload.
- Producer and consumer using different formats.
- Incorrect consumer default type.
- Type header pointing to a nonexistent or untrusted class.
- Missing schema identifier.
- Incompatible field types.
- A custom deserializer throwing an exception on malformed data.

With Spring Kafka, deserialization errors can occur before the listener method is invoked. To route these errors into the container's error handling, you can use a mechanism such as `ErrorHandlingDeserializer` wrapping the actual deserializer. It preserves error information in headers so the error handler can process failed records according to policy.

Example configuration:

~~~yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.key.delegate.class: org.apache.kafka.common.serialization.StringDeserializer
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.value.default.type: com.example.orders.events.OrderCreated
        spring.json.trusted.packages: com.example.orders.events
~~~

`ErrorHandlingDeserializer` wraps the delegate deserializer. When the delegate fails, Spring Kafka can attach exception information to headers so a container error handler or dead-letter recoverer can handle it. An appropriate error handler must be configured; adding the wrapper alone does not automatically guarantee failed records are routed to a DLT.

Do not infinitely retry a malformed payload. Schema/format errors typically do not resolve themselves unless the data changes. Distinguish non-deserializable data errors from transient errors such as an unreachable schema registry, then choose retry, DLT, or stopping processing appropriately.

## 13. Security and Untrusted Data

A deserializer converts bytes from the broker into objects inside the application. Because data may come from other producers or topics written to by multiple systems, you should not assume every payload is trustworthy.

Key principles:

- Allow only necessary packages/types when using `JsonDeserializer`.
- Avoid Java native deserialization for external data.
- Limit record sizes and payload nesting depth as needed.
- Validate business fields after deserialization.
- Avoid logging entire payloads if they contain sensitive information.
- Manage schemas and type mappings explicitly.
- Keep serializer/deserializer dependencies updated to receive security patches.

Trusted packages are only a type-control layer within `JsonDeserializer`; they do not replace validation, Kafka ACLs, or data access checks.

## 14. Testing Serializers and Deserializers

A good serializer/deserializer should be tested at multiple levels.

### 14.1. Round-Trip Test

With the same format, serializing and then deserializing must restore equivalent data according to the contract:

~~~java
@Test
void shouldRoundTripOrderCreated() {
    JsonSerializer<OrderCreated> serializer = new JsonSerializer<>();
    JsonDeserializer<OrderCreated> deserializer =
        new JsonDeserializer<>(OrderCreated.class);

    OrderCreated event = new OrderCreated(
        "evt-100",
        "order-100",
        new BigDecimal("125.50"),
        Instant.parse("2026-11-17T03:00:00Z")
    );

    byte[] bytes = serializer.serialize("order-events", event);
    OrderCreated restored =
        deserializer.deserialize("order-events", bytes);

    assertThat(restored).isEqualTo(event);
}
~~~

This is an illustrative example. With `JsonDeserializer`, configuration for type headers, trusted packages, and constructors may vary by version; actual tests should configure the serializer/deserializer identically to the application environment.

Round-trip tests do not prove independent producer and consumer compatibility. Additional tests using published payload fixtures or old/new schema versions are needed.

### 14.2. Compatibility Test

You can maintain JSON fixtures representing older event versions and verify that the current consumer can read them. When changing schemas, test:

- New consumer reading old payloads.
- Old consumer reading new payloads if required by the deployment strategy.
- Missing, null, or newly added fields handled properly.
- Invalid payloads classified into observable errors.
- Headers/types/schema versions mapped accurately.

### 14.3. Integration Test with Kafka

Use Embedded Kafka or Testcontainers to verify the complete path:

1. `KafkaTemplate` sends the object.
2. The producer serializer converts the object into bytes.
3. The broker stores the record.
4. The consumer deserializer restores the object.
5. `@KafkaListener` receives the expected payload.
6. Deserialization errors pass through `ErrorHandlingDeserializer` and the configured error handler.

Mock serializers/deserializers can be useful for unit tests, but they do not replace integration tests when verifying the actual wire format between producer and consumer.

## 15. Monitoring Serialization in Operations

When serialization/deserialization fails, sufficient information is needed to identify the topic, schema, and involved producer/consumer.

Recommended metrics and signals to monitor:

- Serializer error count per producer.
- Deserializer error count per topic and consumer group.
- Rate of invalid payloads.
- Event/schema versions.
- Record sizes.
- DLT rate caused by data errors.
- Schema registry call latency if used.
- Serialization/deserialization duration when payloads are large or throughput is high.

Logs should include topic, partition, offset, key/event ID if safe, exception type, and schema/version. Do not log full error payloads by default; payloads may contain sensitive data or be excessively large.

If errors appear only after deploying a new producer, compare the new version's schema/headers/serializer configuration with running consumers. If errors occur across multiple topics simultaneously, inspect shared dependencies such as the schema registry, shared serializers, or common configuration.

## 16. Common Misconceptions

| Misconception | Accurate understanding |
| --- | --- |
| The Kafka broker stores Java objects. | The broker stores key/value bytes along with record metadata. |
| Serializers apply only to values. | Keys and values have separate serializers. |
| Generic types on `KafkaTemplate` automatically choose the serializer. | Generics provide Java type safety; serializers must still be configured. |
| Valid JSON guarantees every consumer can read it. | Consumers also need compatible schemas, types, and configuration. |
| Type headers are a durable inter-service contract. | Headers may contain internal class names; prefer stable mappings or schema contracts. |
| Trusted packages replace validation. | They only control `JsonDeserializer` types, not business validation. |
| A `null` key is the same as an empty `byte[]`. | `null` and empty payloads have different semantics; tombstones require a non-null key and a `null` value. |
| Deserialization errors always reach the listener. | Errors can happen before the listener method; container error handling is required. |
| Retries always fix deserialization errors. | Schema-mismatched payloads usually do not self-heal; use a DLT or data remediation. |
| Round-trip tests alone prove compatibility. | Schema/version tests between independent producers and consumers are required. |

## 17. Serialization Design Checklist

Before releasing an event contract, verify:

1. Are the key and value formats clearly defined?
2. Are the producer serializer and consumer deserializer wire-format compatible?
3. Is the key serializer consistent across producers in the same domain?
4. Does the consumer have clear type/default type or schema mapping configuration?
5. Are type headers used intentionally without depending on internal packages?
6. Does the schema define backward/forward compatibility rules?
7. Are `null`, empty bytes, JSON `null`, and tombstones properly distinguished?
8. Do deserialization errors go through an error handler/DLT per policy?
9. Are trusted packages and validation appropriately constrained?
10. Are there round-trip, compatibility fixture, and Kafka integration tests?
11. Are metrics and logs sufficient to trace errors without exposing sensitive payloads?

Serializers and deserializers form the conversion boundary between application data types and Kafka's byte format. When both sides agree on wire format, schemas, and versioning, producers can emit events and consumers can decode them independently across deployments. When errors occur, distinguish conversion failures on the producer, decoding failures before the listener, and business validation errors after deserialization to apply the right handling strategy.

