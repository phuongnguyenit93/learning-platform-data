# Testing Serializer Compatibility in Spring Kafka

A newly deployed producer can successfully publish messages to Kafka, yet an older consumer immediately throws deserialization errors and stops processing its partition. The problem rarely lies in the broker: **Kafka stores and transports bytes**, while interpreting those bytes depends on the application's serializer, deserializer, schema, headers, and data contract. During rolling upgrades, producers and consumers are not necessarily upgraded at the same time; a seemingly minor change such as renaming a field, changing a numeric type, altering a Java class in a type header, or changing the serialization format can break the ability to read old or new data.

This lesson belongs to **Spring Kafka Reliability Operations → Upgrades and Compatibility**, guiding you through **serializer/deserializer compatibility testing** before release: identifying writer/reader versions; distinguishing backward, forward, full, and transitive compatibility; implementing JSON tests with Spring Kafka; understanding schema checks for Avro, Protobuf, and JSON Schema; running integration tests with Embedded Kafka; and designing rolling deployments, rollbacks, replays, and handling of undecodable records. Examples use **Java 17, Spring Boot 3.x, Spring Kafka 3.x, JUnit 5**. Policy decisions must align with your actual serializer/schema registry ecosystem and business requirements.

## 1. What Is Serializer Compatibility?

Producers turn objects into bytes to write to a topic:

```text
Producer v1                               Kafka topic
  OrderCreatedV1                             orders.events.v1
      |                                           |
      v                                           |
  Serializer v1 -> bytes + optional headers ----->|
                                                  |
                                           Consumer v1
                                                  |
                                           Deserializer v1
                                                  |
                                             Domain object

Upgrade phase:
  Producer v2 -> bytes v2 ------> Consumer v1 (not yet upgraded)
  Producer v1 -> bytes v1 ------> Consumer v2 (already upgraded)
```

**Wire compatibility** means writer and reader versions expected to run concurrently can exchange data without failing or misinterpreting semantics. It spans multiple layers:

1. **Encoding format:** JSON, Avro, Protobuf, String, or a custom binary format.
2. **Schema:** field names, types, nullability, defaults, field numbers, enums, and evolution rules.
3. **Envelope/headers:** schema ID, event type, version, Spring JSON type headers.
4. **Deserializer configuration:** target class, trusted packages, strictness, converters, reader schema.
5. **Business meaning:** currency units, timezones, new enums, optional fields, and how consumers handle unknown values.

For instance, a schema still parses cleanly yet the `amount` field changes from **dollars/VND** to **cents** without renaming or adding a unit: the result is **semantically incompatible**, even though the deserializer throws no exception. Tests therefore need both **schema-level** and **behavior-level** checks.

### 1.1. A Producer Succeeding Does Not Mean Consumers Can Read It

The Kafka broker does not inherently know what Java record `OrderCreatedV2` is. A producer can write valid new JSON while an old consumer uses `JsonDeserializer<OrderCreatedV1>`:

```json
{
  "eventId": "evt-100",
  "orderId": "order-501",
  "amount": 120.50,
  "note": "priority delivery"
}
```

If the old consumer ignores the unknown `note` field, it may keep working. If the old consumer enables strict validation with `additionalProperties: false`, or Java code rejects unknown properties, reading fails. **Do not conclude compatibility merely because JSON is syntactically valid.**

## 2. Backward, Forward, Full, and Transitive

Before changing serializers/schemas, identify precisely **who reads data written by whom**.

| Mode | Writer → Reader Pairs Supported | Deployment Scenario |
| --- | --- | --- |
| **BACKWARD** | Old writer → new reader | Upgrade consumers first, producers second |
| **FORWARD** | New writer → old reader | Upgrade producers first, consumers second |
| **FULL** | Both directions | Old and new producer/consumer versions coexist |
| **BACKWARD_TRANSITIVE** | New reader reads **all** prior writer versions in the check history | Replaying multi-version historical data |
| **FORWARD_TRANSITIVE** | All old readers read the new writer within policy scope | Old consumers remain live for a long time |
| **FULL_TRANSITIVE** | Both directions across all relevant versions | Long-lived mixed versions and deep history |

These names commonly appear in **Schema Registry**. With a registry configured for non-transitive `BACKWARD`, checks may compare only against the **most recent prior schema version**, not necessarily every version ever registered. Details depend on the registry and configured policy.

### 2.1. Example with Three Versions

```text
Version 1: OrderCreated { orderId, amount }
Version 2: OrderCreated { orderId, amount, note? }
Version 3: OrderCreated { orderId, amount, note?, source? }
```

If a v3 consumer must replay v1 records still sitting in Kafka, **v3 must read v1**, not just v2. With non-transitive checks comparing only v3 against v2, a multi-step migration path can hide incompatibility with v1. Retention, replay windows, and how long old consumers stay alive directly drive the choice of compatibility mode.

### 2.2. Compatibility Is Not Strictly Symmetric

A new **optional/default** field is usually easy for new readers to handle when reading old data. Yet old readers may reject the new field if they require a fixed property set. Conversely, removing a field required by old readers breaks **forward compatibility**.

Do not infer from the name `BACKWARD` that it means "old consumer reads new producer": it specifically means **new reader reads old writer's data**.

## 3. Defining a Message Contract Before Testing

A minimal contract should record:

```yaml
topic: orders.events.v1
eventType: OrderCreated
key:
  format: UTF-8 String
  meaning: orderId
value:
  format: JSON
  schemaVersion: 2
  requiredFields:
    - eventId
    - orderId
    - amount
  optionalFields:
    - note
orderingScope: one orderId
supportedReaders:
  - consumer-v1
  - consumer-v2
retention: 7 days
```

This is an **illustrative contract**, not a Kafka-enforced config. Also document event IDs/idempotency, versioning, encoding, timezones, units, enum values, length bounds, nullability, and error rules. In polyglot systems, a Java class name **should not be the sole long-term wire identifier** for an event.

In particular, distinguish:

- **Kafka key serializer:** determines key bytes, which can affect partitioning and ordering.
- **Kafka value serializer:** determines payload bytes, schema, and how events are read.
- **Header serializer/converter:** determines metadata attached to the message.
- **Schema Registry serializer:** typically prepends a schema ID or dedicated binary envelope; not identical to sending plain JSON.

An upgrade that changes the key's `StringSerializer` to another encoding can route the same `orderId` to a **different partition**, even when the value JSON still parses fine. **Key** compatibility must therefore also be tested when ordering or deduplication depends on keys.

## 4. JSON Practice: Adding an Optional Field While Old Consumers Keep Reading

Consider two versions of the `OrderCreated` event. Suppose the system treats `note` as supplementary data; consumer v1 does not use it.

**`OrderCreatedV1.java`:**

```java
package com.example.kafka.events;

import java.math.BigDecimal;
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public record OrderCreatedV1(
        String eventId,
        String orderId,
        BigDecimal amount) {}
```

**`OrderCreatedV2.java`:**

```java
package com.example.kafka.events;

import java.math.BigDecimal;
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public record OrderCreatedV2(
        String eventId,
        String orderId,
        BigDecimal amount,
        String note) {}
```

The only change is adding a nullable `note`. With standard Jackson record binding, if v1 JSON omits `note`, the `note` component in V2 receives `null`. Ensure services handle `null` safely and **do not assume `note` is present in every historical record**.

### 4.1. Old and New Payloads

JSON v1:

```json
{
  "eventId": "evt-101",
  "orderId": "order-501",
  "amount": 120.50
}
```

JSON v2:

```json
{
  "eventId": "evt-101",
  "orderId": "order-501",
  "amount": 120.50,
  "note": "priority delivery"
}
```

Two checks are required:

1. **Backward:** reader `OrderCreatedV2` reads JSON v1; `note == null` and old fields remain intact.
2. **Forward:** reader `OrderCreatedV1` reads JSON v2; ignores `note` without corrupting `eventId`, `orderId`, or `amount`.

`@JsonIgnoreProperties(ignoreUnknown = true)` lets V1 itself ignore new properties. However, **merely adding the annotation in today's V1 code does not prove the V1 binary already running in production has that behavior**. When testing rolling compatibility, test against the **actual released reader implementation/binary**, not a V1 copy quietly patched to make tests pass.

### 4.2. Risky Changes Even in JSON

| Change | Risk | How to Evaluate |
| --- | --- | --- |
| Add optional field `note` | Old reader may reject unknown fields | Test v1 reading v2 |
| Add required field without default | New reader cannot read old records | Test v2 reading v1, check constraints |
| Change `amount` number to `"120.50"` string | Strict parser or schema validation fails | Test both directions; avoid relying on implicit coercion |
| Change `amount` from VND to cents | Parses cleanly yet yields wrong business value | Assert semantic transformations and units |
| Rename `orderId` to `id` | Old reader may receive `null` | Requires alias/migration/new version |
| Add enum value `REFUNDED` | Old consumer may lack a branch for it | Test unknown enum handling |
| Remove `eventId` field | Breaks dedup/audit key | Block immediately in contract tests |
| Change `null` to missing or vice versa | Can alter "unchanged"/"clear" meaning | Verify null semantics |
| Switch JSON to Avro on the same topic | Old deserializer cannot parse new bytes at all | New topic version/migration or format-distinguishing envelope |

Do not assume default `ObjectMapper` settings are identical across all services. Flags such as `FAIL_ON_UNKNOWN_PROPERTIES`, `FAIL_ON_MISSING_CREATOR_PROPERTIES`, date modules, and custom deserializers can produce different outcomes.

## 5. Unit Testing JSON Compatibility at the Byte Level

The first test layer needs no Kafka broker: serialize data with the **actual writer** and deserialize with the **target reader**. Byte-level comparison catches cases where JSON code uses unexpected annotations, changed timestamp formats, or serializer wrappers.

### 5.1. Using `ObjectMapper` as a JSON Baseline

`OrderJsonCompatibilityTest.java`:

```java
package com.example.kafka.events;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;

import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

class OrderJsonCompatibilityTest {

    private final ObjectMapper mapper =
            new ObjectMapper().findAndRegisterModules();

    @Test
    void newReaderCanReadOldPayload() throws Exception {
        byte[] v1Payload = """
                {"eventId":"evt-101","orderId":"order-501",
                 "amount":120.50}
                """.getBytes(StandardCharsets.UTF_8);

        OrderCreatedV2 result =
                mapper.readValue(v1Payload, OrderCreatedV2.class);

        assertThat(result.eventId()).isEqualTo("evt-101");
        assertThat(result.orderId()).isEqualTo("order-501");
        assertThat(result.amount())
                .isEqualByComparingTo("120.50");
        assertThat(result.note()).isNull();
    }

    @Test
    void oldReaderCanReadNewPayload() throws Exception {
        OrderCreatedV2 writerObject = new OrderCreatedV2(
                "evt-102",
                "order-502",
                new BigDecimal("57.25"),
                "priority delivery");

        byte[] v2Payload = mapper.writeValueAsBytes(writerObject);

        OrderCreatedV1 oldReaderResult =
                mapper.readValue(v2Payload, OrderCreatedV1.class);

        assertThat(oldReaderResult.eventId()).isEqualTo("evt-102");
        assertThat(oldReaderResult.orderId()).isEqualTo("order-502");
        assertThat(oldReaderResult.amount())
                .isEqualByComparingTo("57.25");
    }

    @Test
    void strictOldReaderMayRejectNewField() throws Exception {
        // Use a strict DTO without @JsonIgnoreProperties in a dedicated test.
        record StrictV1(
                String eventId, String orderId, BigDecimal amount) {}

        ObjectMapper strictMapper = new ObjectMapper()
                .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);

        byte[] v2Payload = """
                {"eventId":"evt-103","orderId":"order-503",
                 "amount":12.00,"note":"new"}
                """.getBytes(StandardCharsets.UTF_8);

        org.assertj.core.api.Assertions.assertThatThrownBy(
                () -> strictMapper.readValue(
                        v2Payload, StrictV1.class))
                .isInstanceOf(
                        com.fasterxml.jackson.databind.exc
                                .UnrecognizedPropertyException.class);
    }
}
```

The final test shows how **two consumers with different Jackson policies** can yield different outcomes. When using Java records, Jackson requires a version supporting records and compatible configuration; Spring Boot 3.x provides modern Jackson via dependency management.

### 5.2. Testing Spring Kafka Serializers Directly

If the app uses `org.springframework.kafka.support.serializer.JsonSerializer` and `JsonDeserializer`, test **those exact classes** rather than stopping at `ObjectMapper`.

```java
import java.math.BigDecimal;
import org.springframework.kafka.support.serializer.JsonSerializer;
import org.springframework.kafka.support.serializer.JsonDeserializer;

JsonSerializer<OrderCreatedV2> writer = new JsonSerializer<>();
writer.setAddTypeInfo(false);

JsonDeserializer<OrderCreatedV1> oldReader =
        new JsonDeserializer<>(OrderCreatedV1.class, false);

byte[] payload = writer.serialize(
        "orders.events.v1",
        new OrderCreatedV2(
                "evt-200", "order-700",
                new BigDecimal("19.90"), "memo"));

OrderCreatedV1 result =
        oldReader.deserialize("orders.events.v1", payload);

assertThat(result.orderId()).isEqualTo("order-700");
```

This is a **fragment** to place inside a test method with AssertJ imported. `JsonSerializer.serialize(topic, value)` returns payload bytes, yet does not by itself verify the **Kafka headers** `KafkaTemplate` can attach to a `ProducerRecord`. If type headers are part of the wire contract, also test messages with real headers in integration tests.

**Golden fixtures:** store real payloads produced by releases V1 and V2 as version-controlled byte/JSON test files. Run a **writer-version × reader-version** test matrix against these fixtures before deploying. Never generate both sides from new classes in a single test run, as that can miss breaking changes against old binaries.

## 6. Spring Kafka JSON Type Headers: Pitfalls When Refactoring Java Classes

Spring Kafka's `JsonSerializer` can write type metadata into Kafka headers—for example, a header naming the serialized Java class. `JsonDeserializer` can read those headers to decide which object class to instantiate.

```text
Kafka record
   key: "order-501"
   value bytes: {"eventId":"...","orderId":"...","amount":120.50}
   headers:
       __TypeId__: com.oldcompany.events.OrderCreated
```

When refactoring packages:

```text
com.oldcompany.events.OrderCreated
    ->
com.example.kafka.events.OrderCreatedV2
```

The JSON payload may remain compatible, yet a deserializer relying on the old `__TypeId__` cannot find the class or rejects a package outside trusted packages. The failure is in **wire headers and runtime configuration**, not necessarily the JSON schema.

### 6.1. If a Topic Carries Only One Event Type

You can specify an explicit target type without relying on Java FQCN headers:

```yaml
spring:
  kafka:
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      properties:
        spring.json.add.type.headers: false

    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.use.type.headers: false
        spring.json.value.default.type: com.example.kafka.events.OrderCreatedV2
        spring.json.trusted.packages: com.example.kafka.events
```

In this example, each consumer knows which event type it reads. Apply the same configuration in both runtime and tests; disabling type headers is **suitable only when the consumer has another reliable way to determine the type**.

### 6.2. If a Topic Carries Multiple Event Types

Do not disable headers and force every message into `OrderCreatedV2`. Choose instead:

- A stable envelope: `eventType`, `eventVersion`, `payload` with safe mapping.
- Spring Kafka type mappings via agreed **logical type IDs**, rather than exposing Java class names as an external contract.
- Schema Registry with an appropriate subject strategy to identify each record's schema ID.
- Separate topics per event type if architecture and operations permit.

When using `spring.json.trusted.packages`, allowlist only permitted packages. Setting `"*"` for all packages weakens safety guardrails; never use it as the default fix for `ClassNotFoundException` or package errors after an upgrade.

**Real compatibility tests must check both value bytes and headers:** produce a record with the V1 serializer and consume it with the V2 deserializer; test the reverse direction as required by your rolling release strategy.

## 7. Using Avro, Protobuf, or JSON Schema with Schema Registry

Schema Registry manages schema versions and automatically rejects certain incompatible changes before a new schema is published. However, **schema compatibility checks do not replace runtime tests**: a serializer may use the wrong subject, wrong schema ID/wire envelope, or consumer logic may reject new values.

### 7.1. Illustrative Avro Evolution

Schema V1:

```json
{
  "type": "record",
  "name": "OrderCreated",
  "namespace": "com.example.events",
  "fields": [
    {"name": "eventId", "type": "string"},
    {"name": "orderId", "type": "string"},
    {"name": "amountCents", "type": "long"}
  ]
}
```

Schema V2 adds an optional `note` with a default:

```json
{
  "type": "record",
  "name": "OrderCreated",
  "namespace": "com.example.events",
  "fields": [
    {"name": "eventId", "type": "string"},
    {"name": "orderId", "type": "string"},
    {"name": "amountCents", "type": "long"},
    {
      "name": "note",
      "type": ["null", "string"],
      "default": null
    }
  ]
}
```

Avro resolves schemas using **writer schema and reader schema**. When a V2 reader reads a V1 record lacking `note`, Avro can supply the default `null`. When a V1 reader reads a V2 record, the reader normally skips the new `note` field. This is an example that can be bidirectionally compatible, yet must be tested against your exact registry compatibility policy and library.

**Crucially:** renaming `amountCents` to `amount` is not merely changing a display name. Old consumers may miss the required field. Renames may require aliases and a staged rollout plan; changing types, logical types, or currency units can create incompatibility or semantic bugs.

### 7.2. Protobuf Evolution

Protobuf relies heavily on **field numbers**:

```proto
syntax = "proto3";

package orders;

message OrderCreated {
  string event_id = 1;
  string order_id = 2;
  int64 amount_cents = 3;
  optional string note = 4;
}
```

Usually a new field number can be added and old readers skip it. **Never reuse an old field number for a new meaning:** a historical consumer could decode new bytes into the wrong field. When removing fields, mark both the field number and name `reserved` in future schemas.

Type changes, enums, `oneof`, and proto2/proto3 presence semantics follow their own rules. Do not blindly apply "adding an optional field is safe" from JSON or Avro to every Protobuf schema.

### 7.3. JSON Schema Evolution

JSON Schema controls required/optional fields, types, enums, and policies for undeclared properties. For example, a schema with:

```json
{
  "type": "object",
  "properties": {
    "orderId": {"type": "string"},
    "amount": {"type": "number"}
  },
  "required": ["orderId", "amount"],
  "additionalProperties": false
}
```

Readers or validators using this schema may reject a new `note` field when `additionalProperties` is disallowed. Thus **free-form JSON payloads** and **strict JSON Schema** do not share the same compatibility semantics. Test against the actual registry and validator implementation rather than relying on the rule of thumb "JSON always ignores unknown fields."

### 7.4. Schema ID and Wire Envelope

In some ecosystems—such as Confluent Schema Registry's wire format—the payload prepends a **marker and schema ID** before the Avro/Protobuf/JSON Schema data:

```text
Kafka value bytes
  |
  +-- wire-format marker / schema ID
  +-- serialized record bytes
```

A consumer using only `StringDeserializer` or `JsonDeserializer` to read all bytes will not understand this framing. You must use the **deserializer matching the registry ecosystem's serializer**. Do not assume every schema registry uses the same wire format or authentication protocol.

## 8. Configuring Schema Registry and Checking Compatibility Policies

Spring Boot example using **Confluent's serializers** (requires compatible dependencies/repositories; **not included by `spring-kafka` alone**):

```yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS}

    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: io.confluent.kafka.serializers.KafkaAvroSerializer
      properties:
        schema.registry.url: ${SCHEMA_REGISTRY_URL}
        auto.register.schemas: false
        # Subject/schema must be provisioned and verified beforehand.

    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: io.confluent.kafka.serializers.KafkaAvroDeserializer
      properties:
        schema.registry.url: ${SCHEMA_REGISTRY_URL}
        specific.avro.reader: true
```

`auto.register.schemas=false` prevents runtime producers from registering new schemas ad hoc when policy requires a separate pipeline to update the registry. If the schema does not yet exist under the right subject, **producers can fail serialization**; deployments need proper sequencing and preflight checks.

`specific.avro.reader=true` fits applications using generated Avro classes. If using `GenericRecord`, configuration and type handling differ. Registry URLs, credentials, and tokens must be protected via secret management; never commit secrets in source, logs, or test artifacts.

### 8.1. Subject Naming Strategy Is Part of the Contract

Common subject strategies in the Confluent ecosystem:

| Strategy | Idea | Consequence |
| --- | --- | --- |
| `TopicNameStrategy` | Subject tied to topic + key/value | One compatibility policy per topic's key/value type |
| `RecordNameStrategy` | Subject named by record/schema | Multiple topics can share one record contract |
| `TopicRecordNameStrategy` | Subject tied to topic and record name | Manages multiple record types inside one topic |

The chosen strategy must match whether a topic holds one or many event types, independent evolution rights per schema, and multi-topic reuse policies. **Changing subject naming strategy between producer/consumer or across environments** can cause unexpected schema ID/subject registrations and cause CI to validate against the wrong subject.

### 8.2. Registry Compatibility Tests in CI

With a registry supporting a Confluent-style compatibility API, the workflow can be:

```text
1. Fetch the subject already used in production.
2. Fetch the active compatibility policy.
3. Prepare the candidate schema from the new commit.
4. Invoke the compatibility check against the target subject/version.
5. Fail CI if incompatible.
6. If passed, run deserialization/semantic tests with real writer/reader.
7. Only then allow registration + rollout.
```

Example API call with a request file containing the **candidate schema escaped as required by the registry**:

```bash
curl --fail-with-body \
  -X POST \
  -H 'Content-Type: application/vnd.schemaregistry.v1+json' \
  --data @candidate-schema-request.json \
  "${SCHEMA_REGISTRY_URL}/compatibility/subjects/orders.events.v1-value/versions/latest"
```

Responses typically include `{"is_compatible": true}` or `false` in this API. That is a **schema-level check**, not a guarantee that business logic or Spring deserializers will all work.

**Practical warning:** subject `orders.events.v1-value` illustrates `TopicNameStrategy`. Do not copy it verbatim if production uses another strategy. If policy requires transitive history, run the right mode and version scope; a single check against `latest` under default policy does not automatically prove consumers can read every historical writer.

## 9. Designing a Version Test Matrix

When upgrading from V1 to V2, include at a minimum:

| Writer | Reader | What to Verify |
| --- | --- | --- |
| V1 | V1 | Previously running baseline |
| V1 | V2 | **Backward**: new consumer reads old records |
| V2 | V1 | **Forward**: new producer does not break old consumers |
| V2 | V2 | New processing path |
| Historical V0 | V2 | Replay if V0 data remains retained |
| V2 key serializer | V1 consumer/key routing | Ordering, partitioning, deduplication |

Each test pair should verify:

1. Bytes produced by the **actual writer version's serializer**, not hand-written JSON that might differ from runtime.
2. Headers/schema IDs/event types sent by the real producer.
3. Deserializer and configuration of the **actual reader version**.
4. Parsed values: required fields, enums, nulls/defaults, timezones, and business semantics.
5. Handling of unknown fields and corrupted data: never silently map to an incomplete object missing keys.
6. When Kafka transactions are used, verify isolation semantics and offset/recovery behavior.

### 9.1. Golden Payloads and Old-Version Artifacts

A project can store:

```text
src/test/resources/compat/
  ├── order-created-v1.json
  ├── order-created-v2.json
  ├── avro-order-created-v1.bin
  ├── avro-order-created-v2.bin
  └── compatibility-cases.yml
```

Golden files must be generated by the **real writer version**, carry clear source/version/checksum metadata, and contain zero personal data. When using registry wire formats, store the **complete raw bytes**, including required headers/envelopes, alongside matching schema registry fixtures. Never edit old fixtures just to make tests pass; fixtures document released contracts.

When upgrading Java dependencies, re-test golden fixtures with the **new reader**. When upgrading producers, run the **actual binary or container image of the old consumer** to verify forward compatibility if old consumers will remain active.

## 10. Integration Testing with Embedded Kafka

Jackson unit tests bypass the Kafka producer, headers, topics, and consumer configuration. Integration tests with Embedded Kafka verify that a **real Kafka record carrying a V2 payload** can be decoded properly by a simulated V1 consumer in an isolated environment.

### 10.1. Dependencies

Example Gradle dependencies snippet:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.kafka:spring-kafka'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Example assumes Spring Boot 3.x managing compatible versions via BOM. Do not mix incompatible Spring Kafka/Spring Framework versions or assume an embedded broker reproduces every trait of a production cluster.

### 10.2. Practical Test: Raw V2 JSON to V1 Deserializer

`SerializerCompatibilityIT.java`:

```java
package com.example.kafka.events;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.Producer;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.serialization.ByteArraySerializer;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.apache.kafka.common.serialization.StringSerializer;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;
import org.springframework.kafka.support.serializer.JsonDeserializer;
import org.springframework.kafka.test.EmbeddedKafkaBroker;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.kafka.test.utils.KafkaTestUtils;

@SpringBootTest(
        classes = SerializerCompatibilityIT.TestApp.class)
@EmbeddedKafka(
        topics = "compat.orders.v1",
        partitions = 1,
        bootstrapServersProperty = "spring.kafka.bootstrap-servers")
class SerializerCompatibilityIT {

    private static final String TOPIC = "compat.orders.v1";
    private final ObjectMapper mapper = new ObjectMapper();

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestApp {}

    @Autowired
    EmbeddedKafkaBroker broker;

    @Test
    void oldReaderConsumesNewProducerJson() throws Exception {
        OrderCreatedV2 v2 = new OrderCreatedV2(
                "evt-200",
                "order-700",
                new BigDecimal("19.90"),
                "priority delivery");

        byte[] wireValue = mapper.writeValueAsBytes(v2);

        Map<String, Object> producerProps =
                KafkaTestUtils.producerProps(broker);
        producerProps.put(
                ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
                StringSerializer.class);
        producerProps.put(
                ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
                ByteArraySerializer.class);

        try (Producer<String, byte[]> producer =
                     new KafkaProducer<>(producerProps)) {
            producer.send(new ProducerRecord<>(
                    TOPIC, "order-700", wireValue))
                    .get(10, TimeUnit.SECONDS);
        }

        Map<String, Object> consumerProps =
                KafkaTestUtils.consumerProps(
                        "legacy-reader-" + UUID.randomUUID(),
                        "false", broker);
        consumerProps.put(
                ConsumerConfig.AUTO_OFFSET_RESET_CONFIG,
                "earliest");

        var consumerFactory =
                new DefaultKafkaConsumerFactory<String, OrderCreatedV1>(
                        consumerProps,
                        new StringDeserializer(),
                        new JsonDeserializer<>(
                                OrderCreatedV1.class, false));

        try (Consumer<String, OrderCreatedV1> consumer =
                     consumerFactory.createConsumer()) {
            broker.consumeFromAnEmbeddedTopic(consumer, TOPIC);

            ConsumerRecord<String, OrderCreatedV1> record =
                    KafkaTestUtils.getSingleRecord(
                            consumer, TOPIC, Duration.ofSeconds(15));

            assertThat(record.key()).isEqualTo("order-700");
            assertThat(record.value().eventId()).isEqualTo("evt-200");
            assertThat(record.value().orderId()).isEqualTo("order-700");
            assertThat(record.value().amount())
                    .isEqualByComparingTo("19.90");
        }
    }
}
```

**Intentional limitation of this test:** the producer emits JSON bytes using `ObjectMapper` and `ByteArraySerializer`, not a `KafkaTemplate` configured with `JsonSerializer` and type headers. It verifies **JSON payload and V1 `JsonDeserializer`** inside Kafka; it **does not test actual type headers**. If the real application uses Spring Kafka type headers or Avro wire formats, add tests using the **exact production producer factory/serializer config**.

Each test must isolate its topic or consumer group to avoid reading leftover records from other tests. In suites sharing topics across test cases, use `@DirtiesContext`, distinct topics, or separate broker/context fixtures. Never raise timeouts just to hide interference from shared data.

### 10.3. Testing Schema Headers and Versioned Events

When messages carry `eventType`, `schemaVersion`, or `__TypeId__` headers, construct `ProducerRecord`s using the runtime serializer/config and inspect the **entire record**:

```java
for (var header : record.headers()) {
    String name = header.key();
    // Assert only headers belonging to the wire contract.
    // Do not print all header values if credentials/PII may exist.
}
```

This is a **fragment** for testing message metadata. When using Spring `JsonSerializer`, `serialize(topic, headers, value)` may write type headers per configuration; assert the **exact version/logical ID** rather than merely asserting a Java FQCN that happens to exist on the current classpath.

## 11. When Deserialization Fails Before the Listener Is Invoked

A critical failure mode during rolling deployments:

```text
Producer v2 sends incompatible value bytes
    |
    v
KafkaConsumer.poll()
    |
    v
Deserializer throws exception
    |
    X  @KafkaListener NEVER receives an object
```

Because the error happens before the listener method is invoked, **`try/catch` inside `@KafkaListener` cannot catch it directly**. Without a strategy, the consumer can keep retrying the failing offset and stall the partition.

### 11.1. Spring Kafka's `ErrorHandlingDeserializer`

A JSON reader configuration can use the wrapper:

```yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      enable-auto-commit: false
      properties:
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.value.default.type: com.example.kafka.events.OrderCreatedV2
        spring.json.use.type.headers: false
        spring.json.trusted.packages: com.example.kafka.events
```

`ErrorHandlingDeserializer` captures deserialization failures via Spring Kafka's mechanism and lets the container/error handler handle the record instead of throwing an unhandled exception in `poll()`. **It does not fix payloads or automatically send to a DLT.** You must configure the error handler, recoverer, commit/seek policy, and DLT per your Spring Kafka version and operational contract.

For instance, with a **non-transactional** record listener, `DefaultErrorHandler` paired with `DeadLetterPublishingRecoverer` can be an option. With transactional listeners, after-rollback recovery and offset commits behave differently; do not copy the same error handler without checking transaction semantics.

### 11.2. Never Lose Records Simply by Skipping Deserialization Errors

When failures occur:

1. Record **topic, partition, offset, error code, and schema ID** as approved.
2. Determine whether the error stems from schema/serializer mismatch, corrupted payload, or missing dependency/config.
3. If recovery/DLT is permitted, store raw bytes in an access-controlled location with replay metadata; never dump raw payloads to logs.
4. Confirm DLT publishing succeeds and offsets advance per policy.
5. Once the consumer is fixed, provide an idempotent replay/reprocessing path for failed records.

If the failure came from an entire new deployment writing a broken format, dumping millions of records into a DLT may not be best: **halt the rollout/roll back the producer**, restore compatibility, and then replay according to plan.

### 11.3. Tombstones and `null` Values

On compacted topics, a Kafka tombstone is a record with a key and a **`null` value**. Never assume `null` always means an invalid payload; listeners may need `@Payload(required = false)` or raw `ConsumerRecord` handling per contract.

```text
key=order-501
value=null
meaning=delete state for order-501
```

If a serializer change turns `null` into the string `"null"` or an object `{"value":null}`, consumers can misinterpret it. Verify **actual tombstone bytes** for both v1 and v2 producers before changing serialization formats on compacted topics.

## 12. Rolling Deployment and Safe Upgrade Sequencing

Serializer changes typically roll out across multiple pods/services, creating a **mixed-version** phase:

```text
T0: Producer V1  -> Consumer V1

T1: Producer V1  -> Consumer V1 + Consumer V2
                   (requires BACKWARD compatibility)

T2: Producer V1 + Producer V2
                  -> Consumer V2
                   (mixed-version writers)

T3: Producer V2  -> Consumer V2

During rollback:
Producer V2 -> Consumer V1 may reappear!
```

Rules:

- **Consumer-first:** if the V2 reader can read V1 bytes, upgrading consumers before producers is usually smooth.
- **Producer-first:** safe only if the V1 reader can read V2 bytes.
- **Rolling or bidirectional rollback:** usually requires FULL compatibility across versions that can meet.
- **Historical replay:** new consumers must read old versions remaining in retention or archives; requires transitive behavior or suitable migration readers.

### 12.1. Recommended Process

1. **Inventory:** list all producers and consumers per topic/group; find batch jobs, connectors, replay tools, and rarely run old-version services.
2. **Contract diff:** compare schemas, JSON headers, serializer classes, key encoders, defaults/nulls/enums, and business semantics.
3. **Registry check:** if using a registry, test the candidate schema against the target subject and expected mode.
4. **Golden tests:** run V1/V2 writers against V1/V2 readers, including real payloads/headers.
5. **Deploy compatible readers first:** when following a backward path.
6. **Canary producer:** emit a small fraction of V2 and monitor deserialization errors, lag, DLT, and business output.
7. **Gradual rollout:** keep feature flags/versioned serializers if rollback may be needed.
8. **Monitor:** confirm zero abnormal lag growth, zero parse errors, and healthy DLQ and business metrics.
9. **Cleanup:** retire old readers/schemas only after retention, replay, and rollback windows close or explicit migration completes.

If V1 and V2 cannot be made compatible due to breaking schema changes, consider a **new topic version** (`orders.events.v2`) with controlled dual-read/dual-write, key/idempotency rules, and clear cutover boundaries. Never silently alter the format of a topic still serving older consumers.

### 12.2. Rollback Is Not Merely Swapping an Image

Suppose producer V2 already published V2 data to the topic. If you roll the consumer back to V1 yet V1 cannot understand V2 records still in the log, **rolling back code will not save the partition**. A rollback plan must anticipate:

- Can V1 readers stay capable of reading V2 bytes?
- Can producers be paused to stop writing incompatible data?
- Is there a multi-version reader/router available?
- Will records need replaying to a new topic after fixing the format?
- Do V2 records already read/applied need deduplication during replay?

The goal of compatibility testing is catching this risk **before** incompatible data sits durably in Kafka.

## 13. Non-Schema Factors That Still Need Verification

### 13.1. Partition Keys, Ordering, and Idempotency

If previously the key was:

```text
StringSerializer("order-501") -> UTF-8 bytes
```

and after upgrading it becomes a quoted JSON string:

```text
JsonSerializer("order-501") -> bytes of "order-501"
```

the Kafka partitioner hashes different key bytes. Events for the same order can land in a different partition, breaking ordering during mixed phases. Inspect **serialized key bytes and partition assignments** whenever key serialization changes, not only the value schema.

Consumer idempotency should rely on a stable `eventId`/business key; if v2 changes event ID formatting or changes only the key, verify deduplication still works. When records are redelivered or replayed after rollback, never create duplicate side effects.

### 13.2. Timestamps and Numeric Precision

| Change | Risk |
| --- | --- |
| ISO timestamp to epoch number | Parser failure, milliseconds vs. seconds confusion |
| `LocalDateTime` to `Instant` without timezone contract | Shifted business timestamps |
| `double` to decimal/string | Rounding and precision differences |
| `amount` from cents to major currency unit | Wrong monetary amounts despite clean deserialization |
| Different enum string casing | Old consumers fail to map |

Compatibility tests must assert **decoded business values**, not just `notNull`. A payment event that parses cleanly while multiplying the amount by 100 is still a severe breaking change.

### 13.3. Schema Registry Availability and Authentication

Registry-backed serializers may need to look up schema IDs or register schemas. When upgrading:

- Verify the subject/schema exists and the app holds appropriate READ/WRITE permissions.
- Verify TLS certificates, auth tokens, endpoints, and timeouts.
- Have a strategy for transient registry outages; do not treat every registry error as an invalid payload.
- Never expose registry credentials in logs or HTTP exception messages.
- In tests, distinguish **incompatible schema** from **unavailable schema registry**.

Even when a schema is marked compatible, producers can still fail if registering under the wrong subject, using the wrong serializer version, or denied registry permissions.

## 14. Pre-Release Automated Test Matrix

A practical CI pipeline can be structured as:

```text
Pull request changing event model / serializer
       |
       v
Compile + unit serializer tests
       |
       +-- old bytes -> new reader
       +-- new bytes -> old reader
       +-- missing/null/unknown/enum
       |
       v
Schema Registry compatibility checks
       |
       +-- subject + version + policy
       +-- transitive history if needed
       |
       v
Embedded Kafka integration tests
       |
       +-- value bytes + headers + key
       +-- error handler/DLT
       |
       v
Contract tests with actual release binaries
       |
       +-- producer V2 / consumer V1
       +-- producer V1 / consumer V2
       |
       v
Staging rollout tests
       |
       +-- canary + lag/DLT/semantic output
```

### 14.1. Choosing Boundary Data

| Fixture | What It Checks |
| --- | --- |
| V1 payload missing new field | V2 reader default/null logic |
| V2 payload with new field | V1 reader unknown-field handling |
| `null` in optional field | Absent vs. null distinction and validation |
| Missing required field | Intentional failure, never instantiating invalid object |
| New enum value | Fallback or error per contract |
| Very large/small decimals, special precision | No rounding errors |
| Unicode / escaped characters | Encoding, parsers, and JSON escaping |
| Tombstone with null value | Proper compacted-topic consumer handling |
| Messages with V1 and V2 headers | No reliance on old Java FQCNs |
| Keys sharing business identity | Stable key bytes and partition routing |
| Schema Registry envelope | Reader resolves exact schema ID |
| Corrupted/short/truncated bytes | Deserialization recovery and DLT |
| Multi-version records on one topic | Accurate dispatch by event type/version |

Never use real personal data to build golden payloads. If verifying log redaction, use synthetic marker strings and assert those markers never appear in public logs or exception output.

### 14.2. Acceptance Test Criteria

For a change to be considered deployable, `schemaCompatible=true` alone is not enough; you also need:

```text
Schema compatibility: PASS
Wire payload compatibility: PASS
Headers / schema IDs: PASS
Old reader with new writer: PASS if rollout needs it
New reader with old writer: PASS if replay/rollout needs it
Key routing and ordering: PASS
Business semantics: PASS
Deserialization failure recovery: PASS
Canary lag / DLT / error budget: within policy
```

Not every system needs full bidirectional compatibility. Yet every compatibility direction that deployment, rollback, or replay **can trigger** must be explicitly defined and tested.

## 15. Observing Compatibility Failures in Production

After deployment, watch for:

| Signal | Possible Cause | Remediation Step |
| --- | --- | --- |
| `SerializationException` on producer | Wrong registered schema, serializer config, unsupported payload | Check writer schema/subject and exception classification |
| `RecordDeserializationException` on consumer | Invalid byte format or incompatible deserializer | Pause rollout, capture topic-partition-offset and wire format |
| Spring `MessageConversionException` | Envelope/header/type mapping failed | Check type IDs and converter policy |
| `ClassNotFoundException` reading type header | Producer wrote a Java class FQCN no longer present | Use logical type mapping/target type, check versions |
| `IllegalArgumentException` from trusted packages | Class in header not allowlisted | Review header and allowlist; avoid reckless wildcards |
| Consumer lag stuck at a single offset | Poison record after deployment | Inspect error handler, offset, and DLT; never blind-skip commits |
| DLT spikes under new version | Some consumer group does not understand V2 payloads | Check rollout order and reader compatibility |
| Decodes cleanly yet produces wrong output | Semantic incompatibility | Verify business invariants and audits |
| Producer timeouts after enabling registry | Registry/auth/network unavailable | Check dependencies and retry budget |
| Messages with same key distribute differently | Key serialization/partitioner changed | Compare serialized key bytes, ordering, and migration |

Diagnostic logs should capture approved `topic`, `partition`, `offset`, `producer_version`, `schema_id`, `event_type`, `error_code`, and correlation ID. Never log full message values, registry credentials, or exceptions containing raw payloads without a secure handling channel.

Aggregate metrics by topic, consumer group, and schema version/error code with controlled cardinality. Avoid using `eventId`, order ID, or offset as metric labels.

### 15.1. When a Compatibility Incident Occurs

1. **Identify the version pair** of producer/consumer that began failing after release.
2. **Preserve evidence safely:** store topic-partition-offset metadata, schema ID, and serialized key/value in an authorized store; do not print payloads in public logs.
3. **Stop the blast radius** if a producer continues emitting payloads consumers cannot understand.
4. **Inspect schema/headers/bytes** against golden fixtures and old binaries.
5. **Decide recovery:** deploy a reader supporting both versions, roll back the producer, replay/DLT, or route to a new topic version.
6. **Maintain clear offsets/idempotency:** never advance offsets just to "clear errors" without an approved decision to discard data.
7. **Verify resolution:** lag drops, DLT items are accounted for, and inbound/outbound event counts and business aggregates reconcile.
8. **Add regression tests** for the failing writer/reader pair and fixture.

Once incompatible records exist in Kafka, **never delete topics or reset group offsets recklessly**. Those actions can destroy data or cause consumers to reprocess events that already caused side effects.

## 16. Hands-On Exercise

Build a producer and consumer for `orders.events.v1`, then simulate an upgrade from V1 to V2.

1. **Define contract:** choose `orderId` as key, JSON value format with `eventId`, `orderId`, `amount`, and new optional `note`; document retention/replay and deployment order.
2. **Backward unit test:** produce a payload from writer V1; reader V2 must parse it with `note=null` without losing old fields.
3. **Forward unit test:** produce a payload from writer V2; run reader V1 **exactly as released**, without modifying the DTO just to pass tests.
4. **Strict-reader test:** enable `FAIL_ON_UNKNOWN_PROPERTIES` on the old reader and observe the exact condition where adding a new field becomes a breaking change.
5. **Spring serializer test:** test `JsonSerializer`/`JsonDeserializer` with type headers on and off; try refactoring a Java package.
6. **Embedded Kafka:** send a V2 record to the test broker and receive it with the V1 deserializer; assert value, key, topic, and partition.
7. **Golden fixtures:** save V1 and V2 JSON/raw bytes from actual runtimes; run the V1→V2 and V2→V1 matrix in CI.
8. **Schema Registry:** define Avro V1/V2, run compatibility checks against the active subject; compare `BACKWARD` vs. `FULL_TRANSITIVE`.
9. **Protobuf:** add a new field number, then create an intentional example reusing an old field number to see why it is a breaking change.
10. **Key compatibility:** switch the key serializer from String to JSON string and observe serialized key bytes/partition mapping; write a proposal to preserve ordering during migration.
11. **Deserialization failure:** send corrupted bytes using `ErrorHandlingDeserializer` and a configured error handler/DLT; confirm records are not silently lost.
12. **Rolling release:** simulate consumer-first then producer rollout; finally simulate consumer rollback and explain when `FULL` compatibility is required.
13. **Semantic test:** change currency units from VND to cents while keeping the `amount` field; verify business tests catch the bug even though JSON parses cleanly.
14. **Release checklist:** write a release sign-off stating supported version pairs, canary steps, monitoring metrics, and rollback/replay paths.

## 17. Summary

Testing serializer compatibility in Spring Kafka goes far beyond checking whether JSON still parses or Schema Registry returns `is_compatible=true`. You must verify **writer bytes, reader behavior, headers/schema IDs, key serialization, historical data, and business semantics** across all version combinations that can meet during rollouts and rollbacks.

**Backward** lets new consumers read old data; **forward** lets old consumers read new data; **full/transitive** serves mixed-version phases and historical replays within scope. Golden fixtures, direct serializer tests, Embedded Kafka, registry checks, and contract tests against real release artifacts reinforce one another as verification layers. When a breaking change is unavoidable, use a versioned topic/migration and reconciliation workflow rather than silently altering the format of an active topic. **The ultimate goal is ensuring serializer upgrades never cause data loss, stalled partitions, or corrupted business processing.**
