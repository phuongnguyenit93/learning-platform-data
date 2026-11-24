# Schema Registry and Corresponding Serializers

Kafka stores records as keys, values, and headers. The broker itself does not understand the business structure of JSON, Avro, or Protobuf payloads. If producers and consumers change data structures independently over time, the two sides can fall out of sync: a producer might add a field that old consumers cannot process, or a new consumer might require a field that old records do not contain.

**Schema Registry** manages schemas centrally. Producers and consumers use corresponding serializers/deserializers to register and look up schemas and encode/decode payloads. With Spring Kafka, you can configure Confluent serializers for Avro, Protobuf, or JSON Schema alongside `KafkaTemplate` and `@KafkaListener`.

## 1. What problem does Schema Registry solve?

A schema describes the structure and data types of an event. For example, an `OrderCreated` event might contain `orderId`, `customerId`, `totalAmount`, and `createdAt`. If services define schemas independently, adding fields or changing types easily causes producers and consumers to drift apart.

Schema Registry provides a central place to manage schemas by subject and version, while enforcing compatibility rules before a new schema is accepted.

```text
                  Schema Registry (HTTP)
                 +------------------------+
                 | Subject: orders-value  |
                 | Version 1, 2, 3 ...    |
                 | Schema ID              |
                 | Compatibility policy   |
                 +------------------------+
                       ^            ^
              register/lookup   lookup by ID
                       |            |
Producer               |            |                 Consumer
KafkaTemplate          |            |                 @KafkaListener
     |                 |            |                       ^
     v                 |            |                       |
Avro/Proto/JSON        |            |             Avro/Proto/JSON
Serializer ------------            -------------- Deserializer
     |                                                    ^
     v                                                    |
Kafka topic: serialized record ---------------------------+
```

Schema Registry is a separate service, typically accessed over HTTP. It is not the Kafka broker and does not store full event payloads. Kafka still stores records; the Registry stores schemas, subjects, versions, IDs, and related metadata.

## 2. Subject, version, and schema ID

Schema Registry organizes schemas by **subject**. Each subject can have multiple versions. A registered schema receives a schema ID that the serializer writes into the wire format; the consumer uses this ID to fetch the right schema when deserializing.

| Concept | Meaning |
|---|---|
| Subject | Group of schemas managed together, usually tied to a topic's key or value |
| Version | Schema version within a subject, typically incremented sequentially |
| Schema ID | Schema identifier embedded in serialized records |
| Compatibility | Rules determining whether a new schema is compatible with prior schemas |
| Reference | Schemas may reference other schemas, depending on format and Registry |

With `TopicNameStrategy`, the value schema of topic `orders.events` typically belongs to subject `orders.events-value`; the key schema belongs to subject `orders.events-key`.

A schema ID is not a version number. A schema can be reused and share the same ID across multiple subjects depending on Registry configuration; do not infer version numbers solely from the ID.

## 3. How does the serializer write the schema ID into a record?

In Confluent's wire format, a serialized payload begins with a prefix containing a magic byte and schema ID, followed by data encoded in the corresponding format. For Avro, the remainder is encoded as Avro binary; Protobuf and JSON Schema have their own format-specific payload sections.

```text
Serialized value
+----------------+-------------------+--------------------------+
| Magic byte     | Schema ID         | Encoded payload          |
| 1 byte         | 4 bytes           | Avro / Protobuf / JSON   |
+----------------+-------------------+--------------------------+
```

The serializer typically looks up the matching schema in the Registry or registers a new schema per configuration. It writes the schema ID into the payload so the deserializer knows which schema to fetch. The deserializer can cache schemas to avoid calling the Registry on every record.

Do not manually slice or prepend magic bytes or schema IDs in business code. Use matching serializers and deserializers of the same format and compatible versions. If a consumer uses `StringDeserializer` to read Avro or Protobuf payloads, the received bytes cannot be interpreted as plain JSON strings.

## 4. Choosing a format: Avro, Protobuf, or JSON Schema

Confluent provides serializers/deserializers for popular formats:

| Format | Serializer | Deserializer | Characteristics |
|---|---|---|---|
| Avro | KafkaAvroSerializer | KafkaAvroDeserializer | Compact schema, explicit types, typically uses generated SpecificRecord or GenericRecord |
| Protobuf | KafkaProtobufSerializer | KafkaProtobufDeserializer | Based on `.proto`, supports nested messages and field numbers |
| JSON Schema | KafkaJsonSchemaSerializer | KafkaJsonSchemaDeserializer | Human-readable JSON, schema describes structure and data constraints |

Choose a format based on your ecosystem and data requirements:

- Avro suits event data with explicit schemas and compact binary payloads.
- Protobuf suits organizations already using Protocol Buffers or sharing contracts across multiple languages.
- JSON Schema suits systems needing easily debuggable JSON payloads while still managing schemas/compatibility centrally.

Do not confuse Spring Kafka's `org.springframework.kafka.support.serializer.JsonSerializer` with Confluent's `KafkaJsonSchemaSerializer`. Spring's `JsonSerializer` converts objects to JSON and may use type headers; it does not automatically register or look up schemas in Schema Registry.

## 5. Adding serializer dependencies to a Spring Boot application

Spring Kafka does not bundle Confluent serializers. Add the dependency for your chosen format and manage compatible versions across the Confluent client, Kafka client, and Spring Kafka.

Maven example for Avro:

```xml
<repositories>
    <repository>
        <id>confluent</id>
        <url>https://packages.confluent.io/maven/</url>
    </repository>
</repositories>

<dependencies>
    <dependency>
        <groupId>io.confluent</groupId>
        <artifactId>kafka-avro-serializer</artifactId>
        <version>CONFLUENT_VERSION</version>
    </dependency>
</dependencies>
```

For Protobuf, the serializer dependency is `kafka-protobuf-serializer`; for JSON Schema, it is `kafka-json-schema-serializer`. An additional build step is needed to generate Java classes from `.proto`, `.avsc`, or corresponding schemas if the application uses generated types.

Do not arbitrarily match the Confluent version to the Spring Kafka version. These are two library suites with separate release lifecycles; manage versions explicitly and check dependency convergence in the project.

## 6. Configuring Avro serializer/deserializer in Spring Boot

Assuming Schema Registry runs at `http://localhost:8081`, the producer sends Avro, and the consumer expects a generated `SpecificRecord`:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    properties:
      "[schema.registry.url]": http://localhost:8081
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: io.confluent.kafka.serializers.KafkaAvroSerializer
    consumer:
      group-id: order-projection
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: io.confluent.kafka.serializers.KafkaAvroDeserializer
      properties:
        "[specific.avro.reader]": true
```

`schema.registry.url` is passed to the Confluent serializer/deserializer. `specific.avro.reader=true` instructs the Avro deserializer to instantiate generated classes implementing `SpecificRecord` when matching classes exist on the classpath. Without specific reader enabled, the deserializer typically returns `GenericRecord`.

Additional properties such as `auto.register.schemas`, subject naming strategy, and authentication can be placed under `spring.kafka.producer.properties` or `spring.kafka.properties` depending on desired scope. In Spring Boot, dotted keys inside maps should use bracket notation as shown so the binder preserves the exact property names.

## 7. Sending Avro events with KafkaTemplate

Assuming the build generated `OrderCreated` from an Avro schema, the producer can use that class as the value type:

```java
import com.example.avro.OrderCreated;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

@Service
class OrderEventPublisher {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    OrderEventPublisher(KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(String orderId, String customerId, double totalAmount) {
        OrderCreated event = OrderCreated.newBuilder()
                .setOrderId(orderId)
                .setCustomerId(customerId)
                .setTotalAmount(totalAmount)
                .build();

        kafkaTemplate.send("orders.events", orderId, event);
    }
}
```

`KafkaAvroSerializer` accepts the `SpecificRecord`, resolves its schema, and uses Schema Registry to look up or register the schema per configuration. `KafkaTemplate` still sends the record through the Kafka producer normally; Registry integration happens inside the serializer.

This example assumes the Avro schema defines `orderId`, `customerId`, `totalAmount` and the generated class provides the corresponding builder. `KafkaTemplate.send()` returns a future; in production applications, observe that future to handle serialization or publishing failures.

## 8. Receiving Avro events with @KafkaListener

When the consumer uses `KafkaAvroDeserializer` with `specific.avro.reader=true`, the listener can receive the generated Avro class:

```java
import com.example.avro.OrderCreated;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
class OrderEventListener {

    @KafkaListener(topics = "orders.events", groupId = "order-projection")
    public void consume(OrderCreated event) {
        orderProjection.apply(
                event.getOrderId().toString(),
                event.getCustomerId().toString(),
                event.getTotalAmount()
        );
    }
}
```

If the listener uses `GenericRecord`, fields can be read by name:

```java
import org.apache.avro.generic.GenericRecord;

@KafkaListener(topics = "orders.events", groupId = "order-audit")
public void consume(GenericRecord event) {
    String orderId = event.get("orderId").toString();
    log.info("Received orderId={}", orderId);
}
```

Generated `SpecificRecord` classes offer a strongly typed API and easier Java refactoring. `GenericRecord` is flexible when one consumer must handle multiple schemas or schemas determined at runtime, though field names and types must be checked carefully.

## 9. Configuring Protobuf serializer/deserializer

With Protobuf, schemas are defined in `.proto` files and Java classes are generated by the Protobuf compiler/plugin. Spring Boot configuration uses Confluent's classes:

```yaml
spring:
  kafka:
    properties:
      "[schema.registry.url]": http://localhost:8081
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: io.confluent.kafka.serializers.protobuf.KafkaProtobufSerializer
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: io.confluent.kafka.serializers.protobuf.KafkaProtobufDeserializer
```

Producer sending a generated Protobuf message:

```java
import com.example.events.OrderCreated;

OrderCreated event = OrderCreated.newBuilder()
        .setOrderId("order-1001")
        .setCustomerId("customer-42")
        .build();

kafkaTemplate.send("orders.events", "order-1001", event);
```

The consumer can receive the generated Protobuf class or a generic type depending on deserializer configuration and schema. With Protobuf, field numbers are part of the wire contract; never reuse deleted field numbers. Keep retired field numbers/names in `reserved` when modifying messages to prevent old payloads from being misinterpreted.

## 10. Configuring JSON Schema serializer/deserializer

To keep JSON payloads while managing contracts in Schema Registry, use `KafkaJsonSchemaSerializer` and `KafkaJsonSchemaDeserializer`:

```yaml
spring:
  kafka:
    properties:
      "[schema.registry.url]": http://localhost:8081
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: io.confluent.kafka.serializers.json.KafkaJsonSchemaSerializer
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: io.confluent.kafka.serializers.json.KafkaJsonSchemaDeserializer
```

The producer can send a POJO matching the agreed JSON schema:

```java
public record OrderCreated(String orderId, String customerId, double totalAmount) {
}

kafkaTemplate.send("orders.events", event.orderId(), event);
```

The JSON Schema serializer needs the corresponding schema and can register/look up schemas by subject. How schemas are inferred from POJOs and options like explicit vs. inferred schemas depend on Confluent serializer configuration. For critical contracts, manage schemas deliberately and test compatibility instead of relying purely on runtime inference.

## 11. Subject naming strategy

The subject naming strategy determines which subject name the serializer uses when registering or looking up schemas. This choice affects compatibility scope and how different record types share schemas.

| Strategy | Example subject for topic `orders.events` | Meaning |
|---|---|---|
| TopicNameStrategy | `orders.events-value` | Common default; one subject for the topic's value |
| RecordNameStrategy | `com.example.avro.OrderCreated` | Subject based on the fully qualified record/message name |
| TopicRecordNameStrategy | `orders.events-com.example.avro.OrderCreated` | Combines topic and record name |

You can configure the value strategy:

```yaml
spring:
  kafka:
    producer:
      properties:
        "[value.subject.name.strategy]": io.confluent.kafka.serializers.subject.TopicRecordNameStrategy
```

`TopicNameStrategy` fits when each topic has one primary key/value schema. `RecordNameStrategy` is useful when the same record type spans multiple topics and needs compatibility tracked by record name. `TopicRecordNameStrategy` separates schemas by both topic and record type.

Do not arbitrarily change the subject naming strategy once production data exists. A different strategy can cause the serializer to look up a new subject and register independent versions, bypassing the compatibility policy previously enforced.

## 12. Auto-registering schemas and managing schemas via CI/CD

Confluent serializers typically default to `auto.register.schemas=true`. When enabled, the serializer can automatically register a schema not yet present in the subject. This is convenient for local development, whereas production needs control over who can change contracts.

Example disabling auto registration:

```yaml
spring:
  kafka:
    producer:
      properties:
        "[auto.register.schemas]": false
```

When auto registration is disabled, schemas must be pre-registered in the Registry by a pipeline or governance tool. The serializer must find the matching schema in the subject under the chosen strategy; otherwise, serialization will fail.

A typical CI/CD workflow includes:

1. Developer updates the schema in source control.
2. Pipeline validates syntax and runs a compatibility check against the current subject.
3. If compatible, the pipeline registers the new schema or publishes schema artifacts per organizational workflow.
4. Deploy consumers capable of reading both new and old schemas.
5. Deploy producers to start emitting records under the new schema.
6. Monitor deserialization errors and roll back or forward-fix if needed.

Do not let individual pods register differing schemas during concurrent deployments. Centralized schema management ensures you know exactly which version was approved and who changed the contract.

## 13. Compatibility modes in Schema Registry

Compatibility determines in which direction a new schema can work with data written under an old schema. Common modes:

| Mode | High-level meaning |
|---|---|
| BACKWARD | Consumers using the new schema can read data written with the previous schema |
| FORWARD | Consumers using the old schema can read data written with the new schema |
| FULL | Satisfies both backward and forward compatibility |
| BACKWARD_TRANSITIVE | Backward compatibility against all previous versions |
| FORWARD_TRANSITIVE | Forward compatibility against all previous versions |
| FULL_TRANSITIVE | Full compatibility against all previous versions |
| NONE | Disables compatibility checking |

The Registry can set compatibility globally or override it per subject. Know which policy applies to each subject; do not assume every topic uses the same mode.

With Avro, adding a new field with a default usually lets new reader schemas read old records. Removing a field or changing a type can break compatibility depending on direction. With Protobuf, never reuse field numbers; use `reserved` for removed tags. With JSON Schema, changes to `required`, types, or constraints can break compatibility with old producers or consumers.

Compatibility checks do not replace integration tests. Schema Registry checks format rules, not full business semantics—for example, changing `amount` from VND to cents while keeping the type numeric.

## 14. Safe schema evolution

When changing an event, follow the expand-and-contract workflow:

1. Add the new field compatibly, such as an Avro field with a default or an optional JSON Schema property.
2. Deploy consumers able to read both old and new payloads.
3. Deploy producers to start emitting the new field.
4. Monitor the ratio of old/new records and confirm all consumers have upgraded.
5. Remove the old field only after no consumers depend on it and the compatibility policy permits.

Avro example adding a `channel` field with a default:

```json
{
  "type": "record",
  "name": "OrderCreated",
  "namespace": "com.example.avro",
  "fields": [
    {"name": "orderId", "type": "string"},
    {"name": "customerId", "type": "string"},
    {"name": "channel", "type": ["null", "string"], "default": null}
  ]
}
```

New consumers can read old records lacking `channel` via the default value. Old producers will not spontaneously send the new field, so consumers must accept both states during the transition.

Do not change a field's meaning while keeping the same name and type. For instance, keeping `totalAmount` as a `double` while switching from VND to USD is a semantic breaking change that Schema Registry cannot detect.

## 15. Schema Registry authentication and security

In production, Schema Registry may require Basic Auth, API key/secret, or TLS depending on the platform. Serializers and deserializers must be supplied with the proper URL and credentials.

Example Basic Auth configuration using Confluent client properties:

```yaml
spring:
  kafka:
    properties:
      "[schema.registry.url]": https://schema-registry.example.com
      "[basic.auth.credentials.source]": USER_INFO
      "[basic.auth.user.info]": SCHEMA_REGISTRY_API_KEY:SCHEMA_REGISTRY_API_SECRET
```

Property names and authentication mechanisms depend on the Registry distribution. For Confluent Cloud, use provisioned credentials and the corresponding TLS endpoint. Never commit API keys/secrets to source control; use a secret manager or protected environment variables.

Access permissions to the Registry should follow least privilege: producers may need schema registration rights in development, while production runtimes may only need read access if CI/CD is the sole authorized publisher.

## 16. Common errors

| Error | Causes to check |
|---|---|
| Cannot connect to Schema Registry | Wrong URL, DNS, TLS, network, or service unavailable |
| Unauthorized/Forbidden | Incorrect API key, credentials, or Registry ACLs |
| Schema not found | Schema ID does not exist in the Registry the consumer is querying |
| Incompatible schema | New schema violates the subject's compatibility policy |
| Unexpected subject | Producer and consumer use different subject naming strategies or changed strategy between deploys |
| ClassCastException/GenericRecord instead of SpecificRecord | `specific.avro.reader` not enabled or generated class missing from classpath |
| SerializationException | Serializer received mismatched object/schema or Registry could not register/look up schema |
| Consumer reads corrupted bytes/JSON | Producer and consumer serializers/deserializers use mismatched formats, or Spring `JsonSerializer` was confused with Confluent JSON Schema serializer |

When debugging, record the topic, key/value subject, schema ID, serializer class, and root exception. Avoid logging sensitive payloads. You can query the Schema Registry API or admin tools to inspect subject versions and compatibility policies.

## 17. Testing producers and consumers with Schema Registry

Unit tests can verify mapping and event construction, but integration tests must verify that serializers/deserializers actually interact with the Registry.

A test suite should cover:

1. Producer registers or looks up the schema under the expected subject.
2. Published records carry a valid schema ID in the wire format.
3. Consumer uses the proper deserializer and receives the expected generated or generic type.
4. New consumers read records written under old schemas according to the chosen compatibility mode.
5. Incompatible schemas are rejected before deploying a new producer.
6. `auto.register.schemas=false` succeeds when the schema is pre-registered and fails clearly when missing.
7. Authentication/TLS works with test environment credentials.
8. Subject naming strategy aligns between producer and schema registration pipeline.

Use Kafka and Schema Registry via Testcontainers or a dedicated integration environment. Mocking `KafkaTemplate` alone does not verify wire formats, schema IDs, or compatibility checks.

## 18. Common misconceptions

1. **Thinking Schema Registry stores event payloads.** The Registry manages schemas/subjects/versions; Kafka stores records.
2. **Thinking schema ID equals version.** ID and version are two separate concepts.
3. **Using Spring `JsonSerializer` and expecting schemas to be registered.** Use a Registry-integrated serializer like `KafkaJsonSchemaSerializer` if JSON Schema is desired.
4. **Using an Avro serializer while the consumer uses `StringDeserializer`.** Both sides must agree on the wire format and serializer/deserializer.
5. **Enabling auto registration in production without controls.** Schemas may be registered outside review and compatibility gates.
6. **Changing subject naming strategy between deployments.** This can create a new subject and bypass the compatibility history enforced on the old subject.
7. **Assuming `BACKWARD`/`FULL` guarantees business correctness.** The Registry checks structure and format rules, not units or domain rules.
8. **Deleting or reusing Protobuf field numbers.** Old data may be misinterpreted; reserve deleted tags.
9. **Assuming serializer and Spring Kafka versions must match numerically.** Manage compatibility across Confluent client, Kafka client, and Spring Kafka rather than forcing identical version numbers.

Schema Registry lets producers and consumers share a versioned data contract governed by compatibility policies. In Spring Kafka, choose matching serializers/deserializers for your format, configure Registry URLs and subject naming strategies consistently, manage schemas through CI/CD pipelines, and test both old and new records. That way, schema changes can roll out incrementally without breaking communication between running services.
