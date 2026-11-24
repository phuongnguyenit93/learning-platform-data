# Avro, Protobuf, and JSON Schema

## Lesson Objectives

In the **Schema and Data Evolution** chapter, this lesson compares three common schema formats used when exchanging events over Kafka: Avro, Protocol Buffers (Protobuf), and JSON Schema. The focus is on describing data structures, serialization/deserialization, managing schema versions, and keeping producers and consumers compatible during staggered deployments.

**SPRING_KAFKA_MESSAGING** focuses on building Kafka event producers and consumers with Spring Kafka, KafkaTemplate, and @KafkaListener, while helping learners understand topics, partitions, offsets, consumer groups, serialization, retries, dead-letter handling, transactions, exactly-once semantics, concurrency, and testing. Schemas serve as the data contract between producers and consumers; controlled schema evolution lets messaging components evolve independently without disrupting live event streams.

After this lesson, you will be able to:

- Distinguish serialization formats, schemas, and Schema Registry.
- Understand the roles of Avro, Protobuf, and JSON Schema.
- Select a format based on performance, readability, ecosystem, and contract governance needs.
- Design evolvable schemas.
- Understand backward, forward, and full compatibility.
- Configure serializers/deserializers in Spring Kafka.
- Integrate Schema Registry to store and look up schema versions.
- Roll out schema changes in a safe sequence.
- Test compatibility across old and new data.
- Handle schema incompatibility in production environments.

## 1. Why does Kafka need schemas?

Kafka stores keys and values as byte arrays. Producers are responsible for converting objects into bytes; consumers are responsible for converting bytes back into objects. The broker does not inherently know whether a payload is `OrderCreated`, `PaymentCaptured`, or `CustomerUpdated`.

If producers and consumers agree on structures informally without a contract, changes can cause failures:

- Producer adds a field, but old consumers reject the payload.
- Producer changes a data type, causing consumer deserialization to fail.
- Two services interpret the same field with two different meanings.
- New consumers fail to read old records still retained in the topic.
- A schema changes while retry topics or DLTs still hold records under the old schema.

A schema describes the structure and data types of a message. It tells producers what to write and consumers how to read.

~~~mermaid
flowchart LR
    A["Producer object"] --> B["Serializer + schema"]
    B --> C["Kafka record bytes"]
    C --> D["Kafka topic"]
    D --> E["Consumer bytes"]
    E --> F["Deserializer + schema"]
    F --> G["Consumer object"]
    H["Schema Registry"] -. "stores schema versions" .-> B
    H -. "provides schemas" .-> F
~~~

A schema alone does not guarantee business correctness. It can confirm a field is a string, but it cannot verify whether `orderId` exists in the system or whether an order status transition is valid. Combine schema validation with business validation.

## 2. Distinguishing serialization formats, schemas, and Schema Registry

These three concepts are related but distinct.

| Concept | Role | Example |
|---|---|---|
| Serialization format | Rules for representing objects as bytes | Avro binary, Protobuf wire format, JSON text |
| Schema | Describes data structure and type rules | Avro record, `.proto` file, JSON Schema |
| Schema Registry | Stores schemas, versions, and checks compatibility | Confluent Schema Registry, Apicurio Registry |

A serializer can work without Schema Registry. For instance, Spring Kafka includes `JsonSerializer` and `JsonDeserializer` for JSON objects. However, serializing to JSON does not automatically create a versioned contract or verify compatibility between producers and consumers.

Schema Registry typically provides:

- Registering new schemas.
- Storing schema versions under subjects.
- Checking compatibility before accepting a new version.
- Looking up schemas by the ID written into messages by the serializer.
- Managing subject naming strategies.
- Enforcing compatibility policies.

The Registry is not in the path of every record in the sense of transmitting the entire schema inside every message. Serializers typically register or look up the schema and write a schema identifier into the payload framing. Consumers use that identifier to fetch the matching schema and deserialize.

## 3. Three formats from an application perspective

**Avro** is a schema-based data format that typically uses binary encoding for compact transmission. Schemas are commonly written in JSON. Avro supports schema resolution between writer and reader schemas, making it well-suited for events with many historical versions to re-read.

**Protobuf** uses `.proto` files to define messages, field numbers, and types. Data is encoded in a binary wire format. Field numbers are part of the contract and must remain stable across versions.

**JSON Schema** describes JSON structures using keywords such as `type`, `properties`, `required`, and `additionalProperties`. Payloads remain JSON, making them easier to inspect and debug, though typically larger than equivalent binary formats.

| Criterion | Avro | Protobuf | JSON Schema |
|---|---|---|---|
| Schema definition | JSON schema document | `.proto` file | JSON schema document |
| Typical payload | Binary | Binary | JSON text |
| Human readability | Requires schema/tooling | Requires schema/tooling | Easy to read |
| Code generation | `SpecificRecord` depending on toolchain | Generated message classes | Can use POJOs/JSON trees |
| Evolution | Reader/writer schema resolution | Field numbers and wire compatibility | JSON Schema rules and registry compatibility |
| Size | Usually compact | Usually compact | Usually larger |
| Best suited for | Event data, data pipelines | Efficient API/service contracts | Contracts needing JSON and observability |

There is no universally best format for all systems. Choose based on client languages, available tooling, schema governance needs, payload size, performance, and operability.

## 4. What is compatibility?

Compatibility describes whether old and new schema versions can operate together without breaking existing producers or consumers.

Three primary directions:

- **Backward compatibility:** consumers using the new schema can read data written under the old schema.
- **Forward compatibility:** consumers using the old schema can read data written under the new schema.
- **Full compatibility:** satisfies both backward and forward compatibility.

Example:

~~~text
Version 1:
OrderCreated {
  orderId: string
}

Version 2:
OrderCreated {
  orderId: string
  source: string
}
~~~

If the `source` field is added with a format-appropriate default value, new consumers can read old records. This is the backward direction.

If old consumers must also read new records, the format and schema policy must allow old consumers to ignore or handle the extra field. This is the forward direction.

Full compatibility satisfies both directions. However, structural compatibility does not prove semantic compatibility. If `amount` remains a decimal yet switches units from VND to USD, the schema may stay compatible while business logic fails severely.

### 4.1. Compatibility across one version or all versions

Schema Registry typically supports these modes:

| Policy | High-level meaning |
|---|---|
| BACKWARD | Compares new schema against the latest prior version (backward) |
| BACKWARD_TRANSITIVE | Compares new schema against all prior versions (backward) |
| FORWARD | Compares new schema against the latest prior version (forward) |
| FORWARD_TRANSITIVE | Compares against all prior versions (forward) |
| FULL | Backward and forward against the latest prior version |
| FULL_TRANSITIVE | Backward and forward against all prior versions |
| NONE | Disables automatic compatibility checks |

The default policy and enforcement depend on the Registry. For topics retaining data long-term, transitive compatibility is worth considering because new consumers may have to read records from many older versions, not just the most recent one.

## 5. Avro: schemas and schema resolution

Avro schemas are usually written in JSON. A record schema has a name, namespace, and list of fields.

Example initial schema version:

~~~json
{
  "type": "record",
  "name": "OrderCreated",
  "namespace": "com.example.events",
  "fields": [
    {
      "name": "orderId",
      "type": "string"
    },
    {
      "name": "customerId",
      "type": "string"
    },
    {
      "name": "total",
      "type": "double"
    }
  ]
}
~~~

The schema describes field names and types. The Avro serializer uses the schema to encode data; the deserializer uses both writer schema and reader schema to decode according to resolution rules.

### 5.1. Adding fields in Avro

When adding a field, declare a default if new readers must read records written under the old schema.

New version:

~~~json
{
  "type": "record",
  "name": "OrderCreated",
  "namespace": "com.example.events",
  "fields": [
    {
      "name": "orderId",
      "type": "string"
    },
    {
      "name": "customerId",
      "type": "string"
    },
    {
      "name": "total",
      "type": "double"
    },
    {
      "name": "source",
      "type": "string",
      "default": "unknown"
    }
  ]
}
~~~

When a reader using the new schema reads an old record without `source`, Avro supplies the default `unknown`.

If you add a field without a default, the new reader schema may fail to read old records because the writer schema provides no value for that required field.

### 5.2. Removing fields in Avro

When a new reader no longer declares a field present in the old writer schema, the reader can ignore the old field. This typically supports backward compatibility.

However, old consumers reading new records without the field may need a default in their old reader schema. Therefore, removing a field may not be forward-compatible if the old schema lacks a default for that field.

Do not remove a field merely because the current producer stopped writing it. The topic may still contain old records and old consumers may not have upgraded yet.

### 5.3. Renaming fields and aliases

Renaming fields requires caution. Avro supports `aliases` on the reader schema to map an old name to a new name.

Example new reader schema:

~~~json
{
  "name": "orderNumber",
  "type": "string",
  "aliases": ["orderId"]
}
~~~

When the reader uses the new schema, the alias lets it accept the `orderId` field from the old writer schema. However, old consumers may not recognize the new name from new producers. Hence, renaming does not automatically guarantee full compatibility.

A safer rollout typically keeps the old field during a transition period, adds the new field with a default, migrates consumers, and removes the old field only after confirming no consumers depend on it.

### 5.4. Changing types in Avro

Avro supports certain type promotions when the reader decodes writer data, such as `int` to `long`, `float`, or `double` per Avro's resolution rules.

Do not generalize that all type changes are safe. Changing `string` to `long`, `bytes` to `record`, or altering union structures can cause incompatibility. Always run compatibility checks against the real Registry and test with real data.

### 5.5. Unions and nullable fields

A field can allow null using a union:

~~~json
{
  "name": "note",
  "type": ["null", "string"],
  "default": null
}
~~~

A union's default must match its first branch per Avro rules. The example places `null` first with `default: null`.

Do not confuse nullable with optional in a business sense. `null` may mean unknown, not applicable, or omitted; define semantics explicitly in the event contract.

## 6. Protobuf: field numbers are a long-term contract

Protobuf defines messages in `.proto` files.

Example:

~~~protobuf
syntax = "proto3";

package com.example.events;

message OrderCreated {
  string order_id = 1;
  string customer_id = 2;
  double total = 3;
}
~~~

Each field has a name, type, and field number. The wire format uses field numbers to identify fields, making field numbers more critical than field names once data is encoded.

### 6.1. Adding fields in Protobuf

You can add a new field using a previously unused field number:

~~~protobuf
syntax = "proto3";

package com.example.events;

message OrderCreated {
  string order_id = 1;
  string customer_id = 2;
  double total = 3;
  string source = 4;
}
~~~

Old consumers typically skip unknown fields per Protobuf's mechanism. New consumers reading old records see the default value or absent state depending on field type and presence declaration.

In proto3, regular scalar fields have defaults such as `0`, `false`, or empty string. If you need to distinguish "not sent" from "sent with default value", use `optional` or an appropriate message wrapper/presence pattern.

### 6.2. Never reuse field numbers

When removing a field, reserve both its number and name to prevent future versions from reusing them accidentally:

~~~protobuf
message OrderCreated {
  reserved 3;
  reserved "total";

  string order_id = 1;
  string customer_id = 2;
  string source = 4;
}
~~~

Never reuse a released field number. An old consumer could interpret bytes of the new field as the old field and corrupt data silently without throwing an error.

Do not renumber fields simply to tidy up the file. Do not arbitrarily change types or wire semantics; some types share similar wire encodings while differing in meaning or value bounds.

### 6.3. Renaming fields

Renaming a field while preserving its field number typically leaves the wire format unchanged, yet it can affect generated APIs, JSON mappings, and consumer code. If using Protobuf JSON mapping, field names appear in the JSON representation and require separate evaluation.

Keep field numbers stable and roll out code updates in proper order. For removed fields, use `reserved` to protect the contract.

### 6.4. Enums in Protobuf

Enums must preserve stable numeric values. The first value should usually be `UNSPECIFIED = 0` to provide an explicit default:

~~~protobuf
enum OrderStatus {
  ORDER_STATUS_UNSPECIFIED = 0;
  ORDER_STATUS_PENDING = 1;
  ORDER_STATUS_CONFIRMED = 2;
  ORDER_STATUS_CANCELLED = 3;
}
~~~

When adding an enum value, old consumers may encounter a numeric value their code does not yet recognize. Define how unknown values are handled and never reuse numeric values of deleted enums. You can reserve removed names and numbers.

## 7. JSON Schema: JSON structure and validation rules

JSON Schema describes a JSON document using keywords. Example:

~~~json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "title": "OrderCreated",
  "properties": {
    "orderId": {
      "type": "string"
    },
    "customerId": {
      "type": "string"
    },
    "total": {
      "type": "number"
    }
  },
  "required": [
    "orderId",
    "customerId",
    "total"
  ],
  "additionalProperties": true
}
~~~

`properties` defines fields and types. `required` lists mandatory fields. `additionalProperties` determines whether undeclared fields are allowed.

### 7.1. Adding properties

You can add a property omitted from `required` so old payloads remain valid under the new schema:

~~~json
{
  "type": "object",
  "properties": {
    "orderId": {
      "type": "string"
    },
    "customerId": {
      "type": "string"
    },
    "total": {
      "type": "number"
    },
    "source": {
      "type": "string"
    }
  },
  "required": [
    "orderId",
    "customerId",
    "total"
  ],
  "additionalProperties": true
}
~~~

If `source` is added to `required`, old records missing that field become invalid under the new schema. This is why new fields should usually stay optional during evolution.

### 7.2. `additionalProperties` affects compatibility

If the old schema sets `additionalProperties` to `false`, consumers validating JSON against the old schema may reject new payloads carrying extra fields. That turns a minor producer addition into a breaking change for old consumers.

If additional properties are permitted, consumers can accept new fields they do not yet know. In exchange, the schema is no longer strict about undeclared fields.

The choice depends on governance:

- Strict contract: forbids undeclared fields, requiring planned consumer/producer rollouts.
- Extensible contract: permits additional fields, requiring consumers to ignore unknown fields.
- Distinct policies can be applied per subject or event type.

### 7.3. `default` in JSON Schema does not auto-populate data

JSON Schema's `default` keyword is primarily an annotation describing a suggested value. Standard JSON Schema validators do not mutate payloads to inject missing fields merely because a schema declares `default`.

This differs from Avro's default resolution. If consumers need default values, the application must apply them in code or use a library with explicitly defined default-injection behavior.

### 7.4. Changing types and `required`

Changing a field from `string` to `number` can invalidate old payloads. Narrowing an `enum` or adding constraints such as `minimum`, `pattern`, or `maxLength` can also cause previously valid data to be rejected.

When evolving a schema, check more than names and types. Evaluate:

- `required`.
- `additionalProperties`.
- `enum`.
- `oneOf`, `anyOf`, `allOf`.
- `minimum`, `maximum`.
- `pattern`, `minLength`, `maxLength`.
- `format` and custom validations.
- Schema references.

## 8. Comparing evolution across the three formats

| Change | Avro | Protobuf | JSON Schema |
|---|---|---|---|
| Add optional field | Usually add a default so new readers read old records | Add a new field number | New property omitted from `required` |
| Remove field | New reader can ignore; old reader may need a default | Remove and reserve number/name | Remove property; assess strict/`required` consumers |
| Rename | Use `aliases` on reader schema; rollout still needed | Keep field number, but impacts generated code/JSON mapping | May require dual fields or migration |
| Change type | Only specific promotions supported | Must preserve wire compatibility and semantics | Must keep payload valid against consumer schema |
| Add enum value | Check enum resolution | Keep numeric values, consumer handles unknown | Check enum constraints and consumers |
| Nullable/optional | Union with `null` and matching default | Presence/`optional` or message wrapper | Omit from `required` and allow `null` if permitted |

Do not apply a single blanket rule across all three formats. For example, "adding a field is always safe" holds only when done in accordance with the format's semantics and compatibility policy.

## 9. Schema Registry and subjects

Schema Registry stores schemas by subject. The subject naming strategy dictates which schemas are managed together.

Common strategies:

- `TopicNameStrategy`: subject based on topic name and key/value, e.g., `orders-value`.
- `RecordNameStrategy`: subject based on fully qualified record/message name.
- `TopicRecordNameStrategy`: combines topic and record name.

The strategy defines the compatibility boundary. With `TopicNameStrategy`, value records on the same topic evolve under one subject. With `RecordNameStrategy`, different record types can be managed independently even within the same topic.

Choose a strategy matching topic design:

- Topic carries a single event type: `TopicNameStrategy` is usually straightforward.
- Topic carries multiple event types: consider `RecordNameStrategy` or `TopicRecordNameStrategy`.
- Separating compatibility by domain event: select the appropriate subject boundary.

Do not arbitrarily switch naming strategies between versions. Producers may register schemas under a different subject and inadvertently bypass the compatibility history of the previous subject.

## 10. Schema IDs in Kafka records

With Registry-integrated serializers, payloads typically carry framing containing a magic byte and schema ID; some formats such as Protobuf also include message index metadata. The exact layout depends on the serializer and registry implementation.

Consumers use the schema ID to retrieve the matching schema from the registry or local cache. Therefore:

- Schema Registry must be reachable whenever serializers/deserializers need uncached schemas.
- Consumers must have access to the registry and the corresponding schema ID.
- Never delete schema versions still referenced by records retained in Kafka.
- Retain registry data and backups in line with retention policies.
- When replaying old records, old schema IDs must remain resolvable.

Never manually parse or alter framing bytes without understanding the serializer contract. Use the official serializers/deserializers for your registry.

## 11. Integrating Avro with Spring Kafka

With Confluent Schema Registry, producers typically use `KafkaAvroSerializer` and consumers use `KafkaAvroDeserializer`.

Spring Boot configuration example:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    properties:
      schema.registry.url: http://localhost:8081
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: io.confluent.kafka.serializers.KafkaAvroSerializer
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: io.confluent.kafka.serializers.KafkaAvroDeserializer
      properties:
        specific.avro.reader: true
~~~

`specific.avro.reader` instructs the deserializer to return generated `SpecificRecord` classes when the schema and class match. If using `GenericRecord`, do not enable specific reader this way.

Example producer using a class generated from an Avro schema:

~~~java
@Service
public class OrderEventProducer {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public OrderEventProducer(
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderCreated>> publish(
            OrderCreated event) {
        return kafkaTemplate.send(
            "commerce.order.created",
            event.getOrderId().toString(),
            event
        );
    }
}
~~~

`OrderCreated` in this example is generated from an Avro schema and implements `SpecificRecord`. Accessor calls depend on code generation and the Avro plugin version.
This example uses the Spring Kafka 3.x API, where `KafkaTemplate.send` returns a `CompletableFuture`. In Spring Kafka 2.x, the equivalent API typically returns `ListenableFuture`; adjust return types and callbacks to match your project version.

Consumer:

~~~java
@KafkaListener(
    topics = "commerce.order.created",
    groupId = "billing-service"
)
public void listen(OrderCreated event) {
    billingService.process(event);
}
~~~

With generated classes, producers and consumers must use compatible schemas/classes. Avoid manually copying generated classes across services when the schema is the primary contract source.

## 12. Integrating Protobuf with Spring Kafka

With Confluent Schema Registry, the corresponding serializer/deserializer are `KafkaProtobufSerializer` and `KafkaProtobufDeserializer`.

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    properties:
      schema.registry.url: http://localhost:8081
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: io.confluent.kafka.serializers.protobuf.KafkaProtobufSerializer
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: io.confluent.kafka.serializers.protobuf.KafkaProtobufDeserializer
      properties:
        specific.protobuf.value.type: com.example.events.OrderCreated
~~~

`OrderCreated` is a generated Protobuf message class. Configuring the specific type instructs the deserializer to return the concrete class rather than a dynamic message representation.

Producer:

~~~java
@Service
public class ProtobufOrderProducer {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public ProtobufOrderProducer(
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderCreated>> publish(
            OrderCreated event) {
        return kafkaTemplate.send(
            "commerce.order.created",
            event.getOrderId(),
            event
        );
    }
}
~~~

Depending on the generated API, field accessors vary across scalar, message, and repeated fields. Keep `.proto` files as the contract source and generate code using the exact compiler/plugin in the build.

## 13. Integrating JSON Schema with Spring Kafka

Confluent's JSON Schema serializer/deserializer can manage JSON payloads alongside schemas in the registry.

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    properties:
      schema.registry.url: http://localhost:8081
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: io.confluent.kafka.serializers.json.KafkaJsonSchemaSerializer
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: io.confluent.kafka.serializers.json.KafkaJsonSchemaDeserializer
      properties:
        json.value.type: com.example.events.OrderCreated
~~~

`json.value.type` specifies the target Java type for the deserializer per the corresponding Confluent settings. Verify package names and serializer versions in your application.

The producer can still use `KafkaTemplate<String, OrderCreated>`:

~~~java
@Service
public class JsonSchemaOrderProducer {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public JsonSchemaOrderProducer(
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderCreated>> publish(
            OrderCreated event) {
        return kafkaTemplate.send(
            "commerce.order.created",
            event.orderId(),
            event
        );
    }
}
~~~

JSON Schema serialization can use POJOs, JSON trees, or structures compatible with the serializer. Do not confuse Spring Kafka's regular JSON serializer with the Schema Registry JSON Schema serializer: one merely serializes JSON objects, while the other also manages schema contracts and framing.

## 14. Schema Registry configuration and dependencies

Confluent serializers are distributed in their respective artifacts, for example:

| Format | Serializer/deserializer artifact |
|---|---|
| Avro | `kafka-avro-serializer` |
| Protobuf | `kafka-protobuf-serializer` |
| JSON Schema | `kafka-json-schema-serializer` |

Artifact versions must be compatible with the Kafka client, Spring Kafka, and Schema Registry deployed. Manage versions through your project's platform BOM/dependency management rather than pulling the latest version for each artifact independently.

Common properties to configure:

- `schema.registry.url`.
- Serializer/deserializer classes.
- `auto.register.schemas`.
- Subject naming strategy.
- Compatibility policy managed on the registry side.
- Specific reader/type for generated classes if used.
- Authentication/TLS if the registry is secured.

In production, many organizations disable runtime auto-registration and register schemas through CI/CD to enforce compatibility before deployment. Producers then use only pre-approved schemas. This prevents a new instance from registering schemas outside the governance workflow.

Example disabling auto-registration on the producer:

~~~yaml
spring:
  kafka:
    producer:
      properties:
        auto.register.schemas: false
~~~

With this configuration, the pipeline must register the right schema under the right subject before the producer sends records. If the schema does not exist yet or the subject mismatches the naming strategy, producer serialization can fail.

The YAML blocks in the Avro, Protobuf, and JSON Schema sections are mutually exclusive alternatives for each value format choice. Do not configure all three serializers simultaneously for the same producer value.

## 15. Safe schema rollout between producer and consumer

Producers and consumers are typically deployed independently. A new schema may appear while old consumers are still running.

For backward-compatible changes such as adding an optional/defaulted field:

1. Register the new schema and run compatibility checks.
2. Deploy new consumers capable of reading both old and new data.
3. Confirm new consumers run stably.
4. Deploy new producers to begin writing the new field.
5. Monitor deserialization, validation, and business logic errors.
6. Remove old compatibility logic only after an appropriate transition window.

For forward-compatible changes, new producers can emit data that old consumers can still read. However, verify actual semantics and rollout ordering for each client.

~~~mermaid
flowchart TD
    A["Design schema v2"] --> B["Compatibility check"]
    B --> C{"Pass?"}
    C -->|No| D["Adjust schema"]
    D --> B
    C -->|Yes| E["Register schema v2"]
    E --> F["Deploy consumer supporting v1 and v2"]
    F --> G["Deploy producer writing v2"]
    G --> H["Monitor errors and metrics"]
    H --> I["Remove old support after migration"]
~~~

Do not deploy new producers before consumers if old consumers cannot read the new payload. A passing Registry compatibility check is a good signal, but integration tests with real application versions are still necessary.

## 16. Schema compatibility does not replace event versioning

Schema versions describe payload structure. Event versions or event type versions can describe contract changes at the business level.

Examples:

- `OrderCreated` adds a `source` field: likely just schema evolution.
- `OrderCreated` changes semantics from "order created" to "order paid": this is a major business change; consider a new event type.
- `amount` changes units or rounding rules: requires explicit versioning/field semantics even if the type stays unchanged.

Do not use a version field to replace Schema Registry entirely. Conversely, do not use schema IDs as business event versions.

A solid event contract should specify:

- Event name and domain.
- Meaning of every field.
- Measurement units and timezones.
- Null/absent/default semantics.
- Enum and unknown-value rules.
- Producer ownership.
- Consumer expectations.
- Deprecation and removal policies.

## 17. Old data, replay, and retention

Kafka topics can retain records longer than the lifecycle of an application version. New consumers may re-read records written months earlier.

Consider:

- Can new consumers resolve old schema IDs?
- Does the Registry still retain old schema versions?
- Are old generated classes or schema files still maintained?
- Do retry topics and DLTs contain records from previous schema versions?
- Does replay pass through the current serializer/deserializer?
- Are migrations or adapters needed for legacy payloads?

Do not delete old schema versions simply because current producers stopped using them. Old records may still reference those schema IDs.

If an incompatible contract change is necessary, consider a new topic, a new event type, or a version-translation adapter. Running old and new consumers concurrently during migration helps reduce risk.

## 18. Testing schema evolution

A test pipeline should include these layers:

### 18.1. Schema validation

- Parse schemas.
- Validate schemas against format rules.
- Verify generated code compiles.
- Verify subjects and naming strategies.
- Trial-register schemas against the compatibility policy.

### 18.2. Compatibility tests

Test the new schema against old versions under the active policy:

- New Avro reader schema reads old Avro data.
- Old Protobuf consumer reads messages with new fields.
- Old JSON Schema validator accepts or rejects new payloads as expected.
- Test against all prior versions if using transitive compatibility.

### 18.3. Serialization round-trip

For each format:

1. Instantiate the object.
2. Serialize to bytes.
3. Deserialize back to an object.
4. Compare fields and semantics.
5. Verify schema ID/version in framing if using a registry.

### 18.4. Integration tests with Kafka

Use EmbeddedKafka or Testcontainers with the corresponding registry to verify:

- Producer sends records under the new schema.
- New consumer reads new records.
- New consumer reads old records.
- Old consumer handles new records per compatibility expectations.
- Schema-invalid records route through error handlers/DLT.
- Replaying old records still resolves schemas.

Do not only mock serializers. Compatibility is an interaction among schema, serializer, registry, payload, and consumer version.

## 19. Handling schema incompatibility in production

When producers or consumers report schema errors, isolate the root cause:

| Symptom | Possible cause | Resolution |
|---|---|---|
| Schema registration rejected | Violates subject compatibility policy | Review diff and adjust schema |
| Consumer cannot find schema ID | Registry lacks version or is unreachable | Check registry, cache, and backups |
| Deserialization error | Payload/schema mismatch or corrupted bytes | Quarantine record, check serializer and schema ID |
| Unknown field/type | Outdated consumer code/generated class | Upgrade consumer or add adapter |
| JSON validation fails | Mismatched `required`, types, or `additionalProperties` | Adjust contract or rollout |
| Protobuf field misread | Field number reused or altered | Restore numbering contract and publish proper schema |
| Avro missing field | Reader schema lacks default for old records | Add proper default or use migration |
| Old consumer fails after producer rollout | Effectively incompatible change | Roll back producer or deploy compatible adapter/consumer |

Do not resolve incompatibility by hastily turning off compatibility checks. If `NONE` policy must be used for a migration, maintain a plan to isolate the subject/topic, test exact versions, and provide a clear rollback path.

## 20. Common design mistakes

| Mistake | Consequence | Prevention |
|---|---|---|
| Adding required field without default in Avro | New consumer fails to read old records | Add fields with defaults |
| Reusing Protobuf field numbers | Old consumer misinterprets data | Reserve deleted numbers and names |
| Changing Protobuf enum numbers | Alters wire semantics | Keep numeric values stable |
| Adding JSON property when old schema forbids additional properties | Old consumer rejects payload | Use controlled rollout or allow extensions |
| Assuming JSON Schema `default` auto-populates values | Application receives missing field | Apply defaults explicitly in code |
| Using plain JSON serializer while assuming Registry governance | No schema IDs or compatibility checks | Choose the right Schema Registry serializer |
| Disabling auto-register without pre-registering schemas | Producer fails to send records | Register schemas in CI/CD |
| Deleting old schemas from Registry | Historical records become unreadable | Retain schema versions per retention/replay needs |
| Arbitrarily changing subject naming strategy | Bypasses compatibility history | Keep strategy fixed and plan migrations |
| Testing new schema only with new producer | Misses old record incompatibility | Test old/new producer/consumer matrix |

## 21. Checklist before releasing a new schema

- [ ] Chosen Avro, Protobuf, or JSON Schema based on requirements?
- [ ] Does the schema clearly define fields, nullability, defaults, and semantics?
- [ ] Is the subject naming strategy defined?
- [ ] Does the compatibility policy fit retention and replay needs?
- [ ] Has the new schema been checked against prior versions?
- [ ] Do new Avro fields have proper defaults?
- [ ] Have Protobuf field numbers never been reused?
- [ ] Are JSON Schema `required` and `additionalProperties` evaluated?
- [ ] Do producer and consumer serializers/deserializers use matching formats?
- [ ] Is generated code in sync with source schemas?
- [ ] Are old Registry versions retained?
- [ ] Tested old record/new consumer and new record/old consumer?
- [ ] Does rollout order align with compatibility direction?
- [ ] Is there a rollback or adapter plan if deployment fails?
- [ ] Can retry topics, DLT, and replays still read old schema versions?

## Conclusion

Avro, Protobuf, and JSON Schema all define data contracts, yet each follows distinct evolution rules. Avro relies on writer/reader schema resolution and defaults; Protobuf relies heavily on field numbers and wire compatibility; JSON Schema relies on validation rules such as `required`, `properties`, and `additionalProperties`. Schema Registry manages versions and checks compatibility, while Registry-integrated serializers/deserializers let producers and consumers exchange payloads tagged with schema IDs.

In Spring Kafka, choose serializers/deserializers matching your format, retain old schema versions for historical replay, and verify compatibility before deployment. Deploy consumers capable of reading old data before producers emit new structures when changes require backward compatibility. Combining schema tests, round-trip tests, integration tests, and controlled rollouts lets event contracts evolve without interrupting messaging flows.
