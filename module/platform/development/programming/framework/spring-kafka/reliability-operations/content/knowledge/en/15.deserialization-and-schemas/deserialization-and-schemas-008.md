# Schema Evolution

In a Kafka system, the same topic can exist for a very long time while producers and consumers are continuously upgraded. A new producer may begin emitting additional data fields before all consumers are updated; conversely, a new consumer must still read older records already sitting in the topic. **Schema evolution** is the process of changing message structures across multiple versions while maintaining safe reading, processing, and operations.

This is not merely about adding or removing fields in a Java DTO. Every change affects **serialization**, **deserialization**, **cross-version compatibility**, **deployment ordering**, **data replay**, and how the system recovers failed records. In Spring Kafka, schema evolution must be treated as part of the reliability strategy for both producers and listeners.

## 1. The problem when producers and consumers do not upgrade at the same time

Suppose the system has a topic `orders.created`. The first version of the event contains only the order ID and amount:

```json
{
  "orderId": "O-1001",
  "totalAmount": 125000
}
```

In the new version, the producer needs to add currency:

```json
{
  "orderId": "O-1001",
  "totalAmount": 125000,
  "currency": "VND"
}
```

During rollout, multiple versions can coexist simultaneously:

```text
Producer v1 ----------> Kafka topic <---------- Producer v2
                         |
                         +---- Consumer v1
                         +---- Consumer v2
                         +---- Consumer v3 (replaying old data)
```

Kafka stores records as bytes and does not inherently understand Java classes or payload business schemas. Successful reading depends on serializers/deserializers, schemas or metadata for identifying schemas, and business processing logic.

A consumer using the new DTO may fail to read old records if `currency` is required without a default. An old consumer may fail upon seeing the new field if its deserializer is configured to reject unknown fields. Even when a payload deserializes cleanly, business logic can still misprocess it if field semantics changed.

**Safe schema evolution** must answer two questions: which versions can read data from which versions, and what deployment order avoids downtime gaps?

## 2. Schema compatibility: backward, forward, and full

Compatibility is usually described from the perspective of the **reader schema** (consumer's schema) and **writer schema** (schema used to write the data).

| Mode | Relationship guaranteed | Typical scenario |
|---|---|---|
| **Backward compatible** | New reader can read data written by old writer | New consumer needs to replay old events. |
| **Forward compatible** | Old reader can read data written by new writer | New producer is deployed before old consumers. |
| **Full compatible** | Both backward and forward | Multiple producer/consumer versions can run simultaneously. |
| **None** | No compatibility checks in the registry | Only use when an explicit migration plan and risk isolation exist. |

For example, version `v2` adds field `currency` with a default. In a format like Avro, reader `v2` can apply the default when reading `v1` records lacking that field; that is a form of backward compatibility. Reader `v1` can generally ignore the new field emitted by writer `v2`; that is forward compatibility in simple cases.

### 2.1. Transitive and non-transitive

Many Schema Registries support two check scopes:

- `BACKWARD`, `FORWARD`, `FULL`: usually compares the new schema against the immediately preceding version or applicable registry target.
- `BACKWARD_TRANSITIVE`, `FORWARD_TRANSITIVE`, `FULL_TRANSITIVE`: requires the new schema to be compatible with **all** previous versions under that subject.

For example, consider a chain `v1 -> v2 -> v3`. Plain `BACKWARD` is not enough to prove reader `v3` can read every record ever written under `v1`. When retention is long, log compaction is enabled, or multi-year data replay is needed, **transitive** checks are usually worth considering.

**Note:** compatibility does not guarantee preserving *business semantics*. A schema can pass field/type checks while consumers still misinterpret data if units, enum meanings, timestamps, or pricing calculations changed.

## 3. Schema evolution example with Avro

Avro is commonly paired with Schema Registry. An Avro record can be decoded using a writer schema and reader schema pair: the writer schema describes the data that was written; the reader schema describes what fields the current application wants to read.

Schema `v1`:

```json
{
  "type": "record",
  "name": "OrderCreated",
  "namespace": "com.example.events",
  "fields": [
    { "name": "orderId", "type": "string" },
    { "name": "totalAmount", "type": "long" }
  ]
}
```

Schema `v2` adds `currency` with a default:

```json
{
  "type": "record",
  "name": "OrderCreated",
  "namespace": "com.example.events",
  "fields": [
    { "name": "orderId", "type": "string" },
    { "name": "totalAmount", "type": "long" },
    { "name": "currency", "type": "string", "default": "VND" }
  ]
}
```

When reader `v2` encounters `v1` data, Avro can fill in `"VND"` for the absent field. When reader `v1` encounters `v2` data, it can ignore `currency`. This change is usually suitable for multi-version rollouts, provided the default currency assumption holds true for all historical records.

Defaults are a **business decision**, not just a trick to pass schema checks. If older orders included both USD and VND without recording currency, defaulting every old record to VND will corrupt data during replay.

### 3.1. Optional fields and defaults

In Avro, a field can allow null values via a union:

```json
{
  "name": "couponCode",
  "type": ["null", "string"],
  "default": null
}
```

This field may be absent in old records and the new reader will populate `null`. When the application handles `null`, define valid behavior: no discount, default discount, or reject the record. Schema compatibility does not define that business rule automatically.

### 3.2. Avro changes requiring caution

- **Adding a required field with no default:** new readers may fail to read old records.
- **Deleting a field:** old readers may still expect it; depending on defaults and schema resolution, forward compatibility can break.
- **Changing field type:** not all type changes are valid; some numeric promotions are supported by Avro yet carry business risk.
- **Renaming a field:** may require aliases alongside appropriate reader schemas; do not assume renames are compatible.
- **Changing namespace or record name:** affects record resolution and subject naming; evaluate separately.
- **Changing enums:** adding/removing symbols can affect old readers; verify compatibility and appropriate defaults/fallbacks.

Schema Registry accepting a change does not guarantee existing Java code is ready for every branch of the new event.

## 4. Protobuf and JSON Schema follow different rules

Compatibility must be evaluated by **schema format**, not solely by mode name. Avro, Protobuf, and JSON Schema interpret fields differently.

### 4.1. Protobuf: field numbers are critical identity

Protobuf example:

```proto
syntax = "proto3";

package com.example.events;

message OrderCreated {
  string order_id = 1;
  int64 total_amount = 2;
  string currency = 3;
}
```

Fields `1`, `2`, `3` are encoded by number. Renaming a field has less wire-format impact than changing a field number; however, renaming can still affect JSON mappings, generated code, or business APIs.

Core rules:

- Never arbitrarily **reuse a field number** previously assigned to another field.
- When deleting a field, consider declaring `reserved` for its old number and name.
- Never make wire-incompatible type changes or alter the meaning of an existing field.
- Understand field presence, default values, and enum semantics in your Protobuf version.

Example:

```proto
message OrderCreated {
  string order_id = 1;
  int64 total_amount = 2;

  reserved 3;
  reserved "legacy_currency";

  string currency_code = 4;
}
```

`reserved` prevents accidentally reassigning retired numbers or names. However, it does not migrate data from the old field to the new field; data migration and reading logic must still be designed.

### 4.2. JSON Schema: required, additionalProperties, and data types

In JSON Schema, keywords such as `required`, `type`, `enum`, and `additionalProperties` determine which data is accepted.

```json
{
  "type": "object",
  "properties": {
    "orderId": { "type": "string" },
    "totalAmount": { "type": "number" },
    "currency": { "type": "string", "default": "VND" }
  },
  "required": ["orderId", "totalAmount"],
  "additionalProperties": true
}
```

A schema allowing `additionalProperties` can accept new fields unknown to older readers, yet a Java app may still configure Jackson strictly and reject unknown properties. Conversely, passing a schema registry check does not mean consumers will automatically apply defaults in every deserializer.

**Important difference:** the `default` keyword in JSON Schema may only be an annotation; it does not force every JSON Schema validator or JSON deserializer to insert missing fields. Do not mechanically apply Avro default semantics to JSON Schema.

## 5. What does Schema Registry do and not do?

A Schema Registry stores schemas by **subject** and version, managing schema IDs and compatibility rules. In the common Confluent Schema Registry integration, the serializer embeds the schema ID into the wire format so the deserializer knows the record's writer schema.

```text
Producer
  | 1. Register or look up writer schema
  | 2. Serialize payload + schema identifier
  v
Kafka topic (opaque bytes)
  |
  | 3. Consumer fetches writer schema by ID
  | 4. Deserialize/resolve against reader model
  v
Spring Kafka listener
```

This illustrates a Registry-integrated serializer using the corresponding wire format. The Kafka broker **does not call the Registry itself to validate each record**; ecosystem serializers/deserializers and tooling handle that part.

The Registry helps:

- Store and look up schemas by subject/version/ID.
- Block registering schemas that violate the compatibility policy.
- Help consumers identify writer schemas in integrated formats.
- Support CI schema checks before deployment.

The Registry **does not** guarantee on its own:

- That historical data retains valid business meaning for new readers.
- That old consumers actually tolerate unknown fields or new enums.
- That database/API side effects roll back when deserialization fails.
- That failed records are retried, routed to DLT, or replayed properly.
- That all clients and serializers use the Registry properly.

## 6. Subject naming and compatibility scope

In the Schema Registry model, a **subject** is the scope for version and compatibility management. A subject does not necessarily correspond one-to-one with a physical topic.

Common subject naming strategies:

| Strategy | General meaning | When to use |
|---|---|---|
| Topic-based (e.g., `TopicNameStrategy`) | Subject scoped by topic and key/value, such as `orders.created-value` | One primary event type per topic. |
| Record-based (`RecordNameStrategy`) | Subject scoped by record/schema name | Sharing a record type across multiple topics. |
| Topic + record (`TopicRecordNameStrategy`) | Combines topic and record name | Multiple event types in one topic, governed per topic. |

Exact names and support depend on serializer/registry vendor. Apply consistently across producers, consumers, and CI pipelines.

If two different event types accidentally share a subject with an unsuitable compatibility policy, schema registration can be blocked or lead to confusing governance. If one type has multiple independent subjects, compatibility is checked against different version histories; this can reduce consistency unless governed.

Do not confuse **topic naming** with **subject naming**. Spring Kafka retry/DLT topics are Kafka topics; schema subjects depend on the serializer strategy. When records move to a DLT, clarify which schema the serializer uses and whether DLT subjects are organized as intended.

## 7. Configuring Spring Kafka with schema-aware serializers/deserializers

With Spring Boot and Confluent Avro SerDes, an illustrative configuration:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: io.confluent.kafka.serializers.KafkaAvroSerializer
      properties:
        schema.registry.url: http://localhost:8081
    consumer:
      group-id: order-service
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: io.confluent.kafka.serializers.KafkaAvroDeserializer
      properties:
        schema.registry.url: http://localhost:8081
        specific.avro.reader: true
```

The example requires the corresponding Avro SerDes libraries on the classpath and matching generated model classes. The URL is illustrative for local environments. In production, secure the Registry with TLS/authentication and configure serializers with required credentials.

With `specific.avro.reader: true`, the consumer uses specific Avro classes where applicable. If reading `GenericRecord` instead, the model strategy differs. Keep consistent serializer, subject, and schema evolution rules across participating services.

### 7.1. Integrating ErrorHandlingDeserializer

If the deserializer throws an exception before Spring Kafka invokes the listener, the business listener **never receives the payload** to handle the failure itself. Spring Kafka provides `ErrorHandlingDeserializer` to record deserialization errors so the error handler/recoverer can handle the record per policy.

Example:

```yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.value.delegate.class: io.confluent.kafka.serializers.KafkaAvroDeserializer
        schema.registry.url: http://localhost:8081
        specific.avro.reader: true
```

When the delegate deserializer fails due to an invalid schema, missing writer schema, unavailable Registry, or corrupted data, `ErrorHandlingDeserializer` enables the container to recognize the error so the error handler decides recovery.

Do not default to infinite retries for schema errors: a permanently malformed record will not fix itself on subsequent retries. Some transient Registry/network errors can recover, whereas incompatible payload/schema errors usually require quarantine and investigation.

### 7.2. Publishing failed records to a DLT

When a record fails deserialization, the recoverer may need to send **raw bytes** to the DLT instead of a regular Java object. Thus, the `KafkaTemplate` used for the DLT must have serializers compatible with all data types the recoverer can emit.

If only `KafkaAvroSerializer` is configured while the recoverer sends `byte[]` from a deserialization failure, DLT publishing can fail depending on configuration. You can use `DelegatingByTypeSerializer` or a separate `KafkaTemplate` with appropriate serializers to handle both regular objects and raw bytes. This design must be tested against the exact failure types production can hit.

The DLT should preserve keys, raw data or required payloads, original topic/partition/offset, and exception metadata. Limit logging full payloads if sensitive data is present. Separate permanent data errors from Registry connectivity errors to avoid misclassifying transient incidents as terminal business failures.

## 8. Safe rollout process for a schema change

A sound migration usually follows **expand -> migrate -> contract**: expand reading capability before producers emit the new format, and drop old support only once confirmed no longer needed.

For example, to add `currency`:

1. **Design compatible schema v2:** the new field has an appropriate default or optional semantics.
2. **Verify in CI:** validate schema compatibility with the Registry and test the application's reader.
3. **Deploy consumers accepting both v1 and v2:** listeners/DTOs do not assume only new data arrives.
4. **Deploy producers writing v2:** monitor serialization and deserialization errors across every service.
5. **Monitor the transition window:** are there still old consumers, old retry/DLT listeners, or old replay jobs?
6. **Contract only when ready:** removing old fields or tightening compatibility policies requires an explicit plan, especially if old data remains within retention.

Diagram:

```text
Phase A:   Producer v1 ---> topic ---> Consumer v1
Phase B:   Producer v1 ---> topic ---> Consumer v2 (reads v1 + v2)
Phase C:   Producer v2 ---> topic ---> Consumer v2
Phase D:   Consumer v2 still reads old records during replay
```

In systems with multiple consumer groups, do not upgrade only the primary consumer. Side services, analytics jobs, retry/DLT consumers, and replay tools are also readers of the topic; a rarely used consumer still running in production can become a failure point when producers switch formats.

If there is no compatible way to evolve the schema, consider a **new event type or new topic**, dual-writing during transition, and a transparent cutover/rollback strategy. Never force incompatible data onto the same stream hoping every consumer copes on its own.

## 9. Replay, retention, and log compaction

Kafka retains data via time/size retention or log compaction; older records can be re-read when:

- A consumer group resets offsets.
- A new consumer group is created for analytics or migration.
- A DLT root cause is fixed and records are replayed back to the business topic.
- A stateful consumer restores state.
- History is reprocessed after discovering a calculation bug.

Therefore, compatibility does not only matter during rolling deployments. **New readers must have a strategy for reading old records that still exist**, especially with `BACKWARD_TRANSITIVE` when topics retain multiple schema versions long-term.

Tombstones in compacted topics normally have null values. Design listeners and serializers to handle tombstones explicitly; never interpret null values as schema-corrupted records in every case.

If an old schema is deleted from the Registry while Kafka still retains records referencing that schema ID, deserializers can fail to resolve historical data. Manage the lifecycle of schema IDs, subjects, and registry retention carefully; avoid deleting schemas while replay or DLT recovery is still needed.

## 10. Schema compatibility differs from semantic compatibility

Some structurally valid changes still break business logic:

| Change | Can schema accept it? | Business risk |
|---|---|---|
| Add `currency` field with default | Possibly | Default is wrong for historical data. |
| Keep `long` type yet switch currency units from whole units to cents | Possibly | Consumers miscalculate amounts. |
| Add new enum value | Depends on format/policy | Old readers lack handling for the new enum branch. |
| Change `orderId` to a different ID meaning while still a string | Possibly | Deduplication, partitioning, and joins break. |
| Change meaning of timestamp while still using `long` | Possibly | Timezone, event-time, or retention logic skews. |
| Drop an old rarely used field | Depends on policy | Batch jobs or DLT replay still depend on that field. |

Therefore, event contracts should also document **units, requiredness, null meanings, enum semantics, data provenance, and business invariants**. Never treat "the Registry returned compatible" as sufficient to deploy.

For changes with fundamentally different business semantics, creating a new event type (`OrderCreatedV2`) or a new topic can be safer than keeping the same name while changing semantics.

## 11. Schema IDs, caching, and Registry availability

Schema Registry-integrated SerDes usually cache schema metadata in the client to avoid calling the Registry on every record. This improves performance yet has consequences:

- A producer may keep sending data using cached schema IDs while the Registry is temporarily interrupted.
- A consumer seeing a never-before-seen schema ID may need to query the Registry; network failures cause temporary deserialization failures.
- A schema ID or subject missing in the target environment causes errors that simple retries cannot fix.
- Rollouts introducing new schemas must ensure the Registry and access permissions are ready in the target environment.

Do not treat every Schema Registry-related exception as a permanent payload error by default. Classify them: timeout/authentication/connection, missing subject/version, incompatible schema, invalid wire format, and application bugs.

Monitor both Kafka consumer lag and Registry health. If the Registry suffers an outage, multiple consumers may hit deserialization errors simultaneously upon seeing new schema IDs, triggering retry storms or DLT spikes.

## 12. CI/CD and contract testing

To prevent schema errors from reaching production, test **before deployment**:

1. Validate Avro/Protobuf/JSON Schema syntax.
2. Check compatibility against the target environment's subject and policy.
3. Instantiate the application's real serializers/deserializers to test reading/writing.
4. Use **golden messages** from older schema versions; confirm new code reads and handles them properly.
5. Test old code reading new data if the rollout requires forward compatibility.
6. Test null values, missing fields, unknown enums, and malformed records.
7. Verify deserialization failures route into recovery/DLT properly without losing raw data.
8. Test replaying old records and DLT records using the new consumer version.

Example test matrix:

| Writer schema | Reader code | Expectation |
|---|---|---|
| v1 | consumer v1 | Reads as currently expected. |
| v1 | consumer v2 | Reads cleanly and applies valid defaults. |
| v2 | consumer v1 | Does not fail if forward compatibility is required. |
| v2 | consumer v2 | Reads all new fields completely. |
| Unknown schema ID | consumer v2 | Catches deserialization error, triggers recovery/alert. |
| Malformed payload | consumer v2 | Does not crash container infinitely; routes to DLT appropriately. |

Do not mock only Java DTOs. Test **actually serialized bytes** because wire-format, schema ID, enum, and type-resolution bugs may never surface in unit tests invoking listener methods directly.

## 13. Observing schema evolution in operations

When deploying a new schema version, monitor:

- Record counts by schema ID/version on producers and consumers where tooling allows.
- Serialization/deserialization error rates, especially post-rollout.
- Schema Registry errors (timeouts, authorization, subject not found).
- Consumer lag by topic/partition and application version.
- Counts of records entering retry/DLT and accompanying exception types.
- Rate of events falling back to old-schema defaults.
- Rollout completion time across all dependent consumer groups.

Logs should link `topic`, `partition`, `offset`, `eventId`, consumer version, and necessary schema metadata. Avoid logging payloads or raw bytes if they contain sensitive data.

A spike in `SerializationException`, `RecordDeserializationException`, or delegate deserializer exceptions after a new producer deployment is a signal to inspect schemas/wire formats immediately. Exact exceptions depend on libraries and `ErrorHandlingDeserializer` usage.

When a rollback is needed, distinguish rolling back **producer code** from rolling back **schemas in the Registry**. Records already written with the new schema remain in Kafka; reverting producer code does not erase them. Registry subjects/versions must not be deleted recklessly because consumers may need both old and new schema IDs to decode existing records.

## 14. Common mistakes when changing schemas

- **Adding a required field without a default:** new consumers fail to read older records.
- **Changing semantics while keeping the same type:** schema checks pass, yet business logic breaks.
- **Checking only the immediately prior version:** replaying very old records can still fail without transitive guarantees.
- **Upgrading producers before readers are ready:** old consumers may fail to read new data.
- **Expanding enums without fallbacks:** old consumers encounter unknown values.
- **Changing Protobuf field numbers or reusing old numbers:** risk of silent misdecoding and broken compatibility.
- **Assuming JSON Schema defaults auto-insert fields:** behavior depends on validators and deserializers.
- **Not testing DLT/retry:** schema-failed records may fail to publish because the DLT serializer does not support raw bytes.
- **Deleting schemas from the Registry while old data remains:** loses ability to resolve schema IDs during replay.
- **Testing only happy-path DTOs:** misses wire-format, schema ID, and real compatibility failures.
- **Confusing topics with subjects:** applies policies to the wrong scope or fails to govern the same record type across topics.
- **Rolling back code and assuming everything reverted to v1:** already-written v2 records remain and will be re-read.

## 15. Guide to choosing a production strategy

| Context | Strategy to consider |
|---|---|
| Consumers must replay full history | Backward transitive, golden message tests across versions. |
| Producers deploy before consumers | Require forward compatibility or roll out readers first. |
| Multiple producers and consumers coexist | Full/full transitive if format and business contract allow. |
| Adding a new field | Valid optional/default, deploy tolerant readers first. |
| Major change to meaning or data type | New event type/topic and controlled migration. |
| Corrupted schema data or unknown ID | `ErrorHandlingDeserializer`, error classification, and proper DLT. |
| DLT/replay contains multi-version data | Preserve schema ID/wire bytes, use type-appropriate serializers/recoverers. |
| Schema Registry is a critical dependency | Monitor availability, authentication, caching, and registry governance. |

Successful **schema evolution** is not just registering a new schema. It is the ability for old and new writers, old and new readers, DLT/retry consumers, and replay tools to handle data predictably together. Combining compatibility policies, expand-contract rollouts, serialized-byte testing, and intentional recovery lets Spring Kafka evolve event contracts while maintaining reliability across the entire data lifecycle.
