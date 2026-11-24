# Data Contract Between Producer and Consumer

In Kafka, producers and consumers are typically deployed, scaled, and released independently. Both sides still need to understand the same event structure to exchange data safely. A **data contract** defines which fields a payload contains, their data types, which fields are required, the business semantics of each field, and how that structure can change over time.

A contract is not just a Java DTO. The real contract is the serialized data format written to Kafka, together with the compatibility rules that producer/consumer versions must follow. If a producer renames a field, changes a type, or alters the meaning of data before the consumer understands it, the application may fail to deserialize or process business logic incorrectly even though Kafka still accepts the record normally.

## 1. Why do producers and consumers need a shared contract?

Kafka stores keys and values as bytes. The producer decides how to convert an object into bytes; the consumer decides how to read bytes back into an object. The Kafka broker does not understand the meaning of the fields inside the payload.

```text
Producer service                         Consumer service
      |                                         |
      v                                         v
OrderCreatedEvent                         OrderCreatedEvent
      |                                         ^
      v                                         |
Serializer ---- bytes ----> Kafka ---- bytes ---- Deserializer
                 topic: orders.created
```

For example, the producer sends an event:

```json
{
  "eventId": "evt-1001",
  "orderId": "ord-42",
  "total": 125000,
  "currency": "VND"
}
```

The consumer may need `eventId` to deduplicate, `orderId` to update a projection, and `total` to calculate revenue. If the producer changes `total` from an integer to a string without an agreement, the consumer may fail while parsing or accidentally misinterpret the value.

A data contract helps teams agree in advance on:

- Field names, data types, units of measurement, and business semantics.
- Required fields, optional fields, and default values.
- Rules for enums, timestamps, currency, identifiers, and null.
- How to add, remove, or modify fields.
- Schema versions and compatibility policies.
- How to handle old records when replaying from Kafka.

## 2. Distinguishing schema, event, and Java DTO

Three related but non-identical concepts:

| Concept | Meaning | Example |
| --- | --- | --- |
| Event | A business event that has occurred | `OrderCreated` |
| Schema | Definition of the structure and data types of an event | Avro, Protobuf, JSON Schema |
| Java DTO | Java type used inside an application to represent the event | `OrderCreatedEvent` |

An event can be represented by a Java record in the producer and a different class in the consumer. The two classes do not need to be identical as long as both adhere to the same wire contract.

You should not treat the Java class name or Java package as a shared contract across services. Serializing the class name into a Kafka header can be convenient for Spring applications in the same ecosystem, but it creates coupling when consumers use other languages or packages are renamed. Distinguish framework type metadata from a stable business schema.

## 3. Designing an event contract

A good event should describe an event that occurred, not merely mirror the current database structure. For example:

```json
{
  "eventId": "evt-1001",
  "eventType": "OrderCreated",
  "eventVersion": 1,
  "occurredAt": "2026-11-17T09:30:00Z",
  "producer": "order-service",
  "data": {
    "orderId": "ord-42",
    "customerId": "cus-18",
    "totalMinor": 12500000,
    "currency": "VND"
  }
}
```

The illustrative envelope separates common metadata from business data:

| Field | Purpose |
| --- | --- |
| `eventId` | Unique identifier for tracing and deduplication |
| `eventType` | Name of the event type |
| `eventVersion` | Contract version if the system uses versioning in the payload |
| `occurredAt` | Business occurrence timestamp, should use UTC and a consistent format |
| `producer` | Service that emitted the event |
| `data` | Business payload of the event |

`totalMinor` illustrates storing money in the smallest unit to avoid floating-point precision errors; the unit must be clearly defined per currency. For VND, you can define the unit as dong and choose a clearer field name such as `totalAmount`. The important thing is that the contract states the unit, scale, and value range clearly.

Not every event needs a custom envelope. Kafka headers can be used for correlation ID, trace context, or transport metadata. Choose a consistent convention and avoid duplicating metadata in both the payload and headers without reason.

## 4. Rules for designing data fields

When defining a schema, specify each attribute clearly:

| Attribute | Question to answer |
| --- | --- |
| Name | Is the field name stable and meaningful? |
| Type | String, integer, decimal, boolean, timestamp, object, or array? |
| Required | Can the consumer handle the field being absent? |
| Nullable | Can the field be present with a `null` value? |
| Default | When an old record lacks the field, what is the fallback value? |
| Semantics | What does the value represent, in what unit, and in what timezone? |
| Constraints | Are there length limits, value ranges, or format rules? |

`optional` and `nullable` are not always the same. A field may be absent from the payload, or present with a `null` value; schema formats may handle these two cases differently. Document the expected behavior explicitly.

For example, a `discount` field:

- Missing `discount`: an older producer did not provide discount information.
- `discount: null`: the producer explicitly indicates unknown or not applicable, depending on the contract.
- `discount: 0`: discount information is present and its value is 0.

Do not assume these three states are equivalent.

## 5. What is schema compatibility?

Schema compatibility describes whether a new schema version can read or be read by data produced with another version. Compatibility must be considered in both directions because producers and consumers can be deployed at different times.

Three common directions:

| Mode | Question | Deployment implication |
| --- | --- | --- |
| Backward compatibility | Can the new consumer/schema read data written by the old schema? | Consumers can be upgraded first, then producers |
| Forward compatibility | Can the old consumer/schema read data written by the new schema? | Producers can be upgraded first within compatible changes |
| Full compatibility | Can both versions read each other's data in both directions? | Supports more flexible staggered version rollouts |

These terms are commonly used in Schema Registry. Specific validation rules depend on the schema format and registry configuration; do not assume every change is safe solely from the mode name.

### Compatibility and transitive compatibility

Standard compatibility may only check the new schema against the most recent version. Transitive compatibility checks against multiple or all previous versions according to the registry policy.

This matters when Kafka retains data for a long time and consumers may replay old records. A new schema that is compatible with the immediately preceding version is not guaranteed to read data from years earlier if previous changes were not checked transitively.

## 6. Commonly safe and unsafe changes

Compatibility depends on the schema format, defaults, nullability, and how the consumer is implemented. The table below is a general design guide, not a replacement for the compatibility checker of the format in use.

| Change | Risk | Recommended approach |
| --- | --- | --- |
| Add an optional field with an appropriate default | Usually easier to keep compatible | Define the default and meaning when old records lack the field |
| Add a required field without a default | New consumers may fail to read old records | Avoid; roll out in multiple steps or provide a default |
| Remove a field still used by consumers | Old consumers may fail when the field disappears | Stop using it first, then remove it in a later version |
| Rename a field | Consumers expecting the old name cannot find the field | Add the new field, migrate consumers, then remove the old field |
| Change data type | May fail to deserialize or alter semantics | Use a new field and perform a controlled transition |
| Add an enum symbol | Old consumers may encounter an unknown value | Design an `UNKNOWN`/fallback branch or control rollout order |
| Change field unit or meaning while keeping name/type | Deserialization succeeds but business logic is wrong | Treat as a breaking contract change; use a new field/version |
| Change nested object structure | May break old readers | Verify schema resolution and run contract tests |

A change can be syntactically compatible yet break semantics. For example, `amount` was previously in VND, and later the producer sends the amount in cents while still using an integer. The consumer deserializes successfully but calculates incorrectly. A contract must govern semantics, not just data types.

## 7. Example of JSON contract evolution

Suppose version 1 is:

```json
{
  "eventId": "evt-1001",
  "orderId": "ord-42",
  "total": 125000
}
```

Version 2 wants to add `currency`. A safer rollout is to treat the new field as optional or give it a clear default in the schema/consumer:

```json
{
  "eventId": "evt-1001",
  "orderId": "ord-42",
  "total": 125000,
  "currency": "VND"
}
```

New consumers must handle old records that lack `currency`. If new producers send this field, old consumers must also ignore unknown fields or schema validation must allow additional properties. With JSON Schema, keywords such as `required`, `properties`, and `additionalProperties` directly affect compatibility; do not assume every JSON consumer ignores unknown fields.

When changing `total` to a decimal type or changing its unit, do not silently change the type or semantics on the same field. You can add `totalAmount` along with `currency`, deploy consumers that read both forms, switch producers to the new field, and retire the old field once the support and replay window has passed.

## 8. Avro and schema evolution

Avro stores and resolves schemas using the writer schema and reader schema mechanism. When reading, Avro performs schema resolution between the schema used at write time and the schema expected by the consumer.

Example of a new Avro record version adding a `currency` field with a default:

```json
{
  "type": "record",
  "name": "OrderCreated",
  "namespace": "com.example.events",
  "fields": [
    { "name": "eventId", "type": "string" },
    { "name": "orderId", "type": "string" },
    { "name": "total", "type": "long" },
    { "name": "currency", "type": "string", "default": "VND" }
  ]
}
```

The new field's default allows the new reader schema to read old records that lack that field. Adding a new field without a default may prevent new readers from reading old records because there is no value to populate.

Some important Avro principles:

- New fields should have a default if old data needs to be read.
- Removing a field can be compatible when the new reader ignores the old writer's field.
- Renaming a field should consider `aliases` so schema resolution recognizes the old name.
- Type changes are safe only for type promotions supported by Avro.
- Adding an enum symbol may prevent old readers from handling the new symbol; consider enum defaults and compatibility mode.

Use an Avro schema compatibility checker to verify the actual policy rather than relying solely on a reference table.

## 9. Protobuf and field number rules

Protocol Buffers uses field numbers as identifiers on the wire format. Field names can change while preserving the wire representation as long as the field number and wire type remain unchanged, whereas changing or reusing a deleted field number can cause data to be misinterpreted.

Example:

```protobuf
syntax = "proto3";

message OrderCreated {
  string event_id = 1;
  string order_id = 2;
  int64 total = 3;
  string currency = 4;
}
```

If removing `total = 3`, reserve both the field number and the name as appropriate:

```protobuf
message OrderCreated {
  reserved 3;
  reserved "total";

  string event_id = 1;
  string order_id = 2;
  string currency = 4;
}
```

Never reuse a field number that has already been released. When changing a field's type, check Protobuf wire types and compatibility rules; two types sharing a wire representation do not necessarily share the same meaning or value range. Changes such as `string` to `bytes`, cardinality changes, or changing a scalar to a message require separate evaluation.

## 10. JSON, Avro, or Protobuf?

No single format fits every system:

| Criterion | JSON | Avro | Protobuf |
| --- | --- | --- | --- |
| Human readability | High | Lower when payload is binary | Lower when payload is binary |
| Explicit schema | JSON Schema must be managed separately | Explicit schema definition | Explicit `.proto` definition |
| Payload size | Usually larger than binary formats | Usually compact | Usually compact |
| Code generation | Can use DTO/validation libraries | Generated `SpecificRecord` classes | Generated message classes |
| Schema evolution | Depends on JSON Schema and policy | Writer/reader schema resolution | Based on field numbers and wire rules |
| Best suited for | Simple integration, easy debugging, web-heavy ecosystems | Event streaming and schema registry | APIs/events needing strong schemas across multiple languages |

The choice should be based on cross-service interoperability, schema governance requirements, performance, tooling, and team skills. A binary format does not automatically make a system compatible; schemas still require versioning and compatibility checks.

## 11. How does Schema Registry manage contracts?

Schema Registry stores schemas and schema versions under subjects, and checks compatibility when a new schema is registered. Registry-integrated serializers/deserializers can embed a schema ID into the payload format so consumers can look up the corresponding writer schema when reading.

With Confluent Schema Registry, default subjects are typically based on the topic and data kind, for example:

- `orders.created-value` for the value schema.
- `orders.created-key` for the key schema.

Subject naming strategies can change the scope of schema sharing, such as topic-based, record-based, or topic-record-based. Choose a strategy deliberately because it determines which schemas are checked for compatibility against each other.

Illustrative producer/consumer configuration with Avro:

```yaml
spring:
  kafka:
    properties:
      "[schema.registry.url]": ${SCHEMA_REGISTRY_URL}
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: io.confluent.kafka.serializers.KafkaAvroSerializer
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: io.confluent.kafka.serializers.KafkaAvroDeserializer
      properties:
        "[specific.avro.reader]": true
```

This example assumes the project already includes serializer/deserializer dependencies compatible with the Kafka client and Schema Registry versions in use. `specific.avro.reader=true` instructs the deserializer to instantiate generated `SpecificRecord` objects when the schema/class matches. If using `GenericRecord`, payload binding in the listener differs.

Schema Registry is not part of the core Kafka broker protocol; it is a separate service that serializers and deserializers must reach. Configure endpoint, TLS/SASL, authentication, timeouts, and availability for the Registry just like any critical runtime dependency.

## 12. Integrating Schema Registry with Spring Kafka

Spring Kafka exposes Kafka's `Serializer`/`Deserializer` abstractions through `ProducerFactory` and `ConsumerFactory`. Schema Registry serializers still operate at the Kafka client layer; there is no need for `RecordMessageConverter` to re-parse Avro/Protobuf payloads already converted into objects by the deserializer.

Example listener using a generated Avro class:

```java
@KafkaListener(topics = "orders.created", groupId = "order-projection")
public void onMessage(OrderCreated event) {
    orderService.process(
            event.getEventId().toString(),
            event.getOrderId().toString(),
            event.getTotal());
}
```

Producer sending a generated object:

```java
kafkaTemplate.send("orders.created", event.getOrderId().toString(), event);
```

`KafkaAvroSerializer` serializes the object according to the registered schema or configured registration policy. The consumer uses the writer schema ID in the payload to fetch the required schema and deserialize. Services need to share the schema contract via the Registry or an artifact/schema repository; they do not necessarily need to share the exact same Java class.

If `auto.register.schemas=false` is enabled, schemas must be pre-registered through CI/CD or a governance process. This is a common choice to prevent runtime producers from registering schemas outside the review process.

## 13. Versioning: schema version or event version?

Schema Registry can manage multiple schema versions under the same subject. This does not necessarily require renaming Kafka topics or adding a `version` field to every event.

Distinguish between:

- **Schema version:** the version of the serialized structure managed by the Registry.
- **Event type/version:** the semantic version of the event by domain convention, if the application needs it.
- **Topic version:** changing the topic name, such as `orders.created.v2`, typically used for incompatible changes or major migrations.

Do not bump `eventVersion` just because an optional field was added if the schema compatibility policy handles the change and semantics remain unchanged. Conversely, if the meaning of the event changes significantly, a new event type/version may be needed even if the field structure stays the same.

Create a new topic only with clear justification: a breaking contract change, changes to partitioning/retention/security boundaries, or a need to run two streams in parallel during migration. Creating a new topic version for every small change increases operational and consumer-coordination overhead.

## 14. Safe contract rollout workflow

For additive, compatible changes, use the **expand -> migrate -> contract** strategy:

1. **Expand schema:** add the new field as optional/with a default, keeping the old field.
2. **Upgrade consumers:** new consumers can read both old and new records; deploy and monitor.
3. **Upgrade producers:** producers begin emitting the new field once consumers are ready.
4. **Migrate usage:** consumers switch to using the new field; verify data and metrics.
5. **Contract:** remove the old field only after no old producers/consumers remain and the required replay window has elapsed.

Example of renaming `customerName` to `displayName`:

```text
Phase 1: Producer sends customerName
         Consumer reads customerName

Phase 2: Schema adds displayName (optional)
         Consumer reads displayName if present, falls back to customerName

Phase 3: Producer sends both fields
         Consumer switches to displayName

Phase 4: Confirm all consumers have migrated
         Producer stops sending customerName

Phase 5: Schema removes customerName after compatibility/replay window
```

Do not remove the old field in the same release when producers and consumers are deployed independently. During rolling deployments, old and new versions can run concurrently.

## 15. Contracts must remain compatible with historical data

Kafka retains records according to the topic's retention settings. New consumers may re-read old data when resetting offsets, rebuilding projections, or recovering from incidents. Therefore, a new schema must be evaluated against the historical data consumers can actually encounter, not just payloads producers emit today.

Identify:

- Topic retention and the maximum replay horizon.
- Whether consumers can start from `earliest` or only read new records.
- Whether archives/backups exist outside Kafka.
- Whether data produced by multiple producer versions coexists.
- Whether Registry compatibility is latest or transitive.
- Whether consumers have fallbacks for unknown new fields or enum values.

If a new schema is compatible only with the immediately preceding version and cannot read older records, full-topic replay can fail. Use transitive compatibility when data must be readable across multiple schema generations, or build a dedicated migration/reprocessing plan.

## 16. Schema evolution and partition keys

The Kafka key typically determines the partition and therefore affects ordering. The key is also part of the data contract, even though Schema Registry may manage keys and values under separate subjects.

Changing the key can:

- Route the same aggregate to a different partition.
- Alter relative ordering between events.
- Impact compaction if the topic uses `cleanup.policy=compact`.
- Prevent consumers from looking up data under the old key.

Do not silently change the key or partitioning algorithm during a schema migration. If the key must change, evaluate re-keying/migration, partition assignment, and how consumers rebuild state.

## 17. Contract testing in CI/CD

Do not wait until deployment to discover that producers and consumers are incompatible. Contracts can be verified at multiple layers:

| Test type | Scope |
| --- | --- |
| Schema validation | Payload matches schema, types, required/default rules, and constraints |
| Compatibility check | New schema satisfies policy against prior versions |
| Producer contract test | Producer serializes events with the correct wire format and semantics |
| Consumer contract test | Consumer can read fixtures of supported versions |
| Cross-language test | Producers/consumers in different languages interpret the same payload identically |
| Replay test | New consumer handles representative historical data |
| Integration test | Serializer, Registry, Kafka broker, and listener work together |

Example CI workflow:

```text
Pull request modifies schema
        |
        v
Lint / validate schema
        |
        v
Compatibility check against Registry policy
        |
        v
Generate classes + compile
        |
        v
Producer/consumer contract tests
        |
        v
Replay fixtures from old schemas
        |
        v
Allow merge and release
```

With Schema Registry, you can invoke the compatibility check API in CI or use platform plugins/tooling to block breaking schemas before deployment. Verify that you check against the exact subject naming strategy and compatibility mode used in production.

## 18. Common pitfalls

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| New consumer cannot read old records | New schema lacks defaults for new fields or reader cannot resolve writer schema | Verify backward compatibility and historical fixtures |
| Old consumer fails when producer adds a field | JSON parser/validator rejects unknown fields or schema is forward-incompatible | Allow new fields, upgrade consumers first, or use version migration |
| Deserialization fails even with matching field names | Data type, nullability, or format mismatch | Inspect the wire schema, not just Java DTOs |
| Consumer parses successfully but computes wrong values | Field unit or meaning changed | Treat semantics as part of the contract; introduce a new field/version |
| New enum value breaks old consumer | Consumer does not handle unknown symbols | Provide fallback/UNKNOWN handling or roll out consumers first |
| Avro fails reading old data after adding a field | New field has no default | Add a valid default or use a different migration path |
| Protobuf payload is misinterpreted | Reused field number or incompatible wire type change | Reserve deleted tags; never reuse field numbers |
| Registry rejects new schema | Compatibility mode disallows the change | Inspect compatibility report, adjust schema or migration plan |
| Producer registers schemas unexpectedly | `auto.register.schemas=true` at runtime | Disable auto registration and register via CI/CD for governance |
| Full topic replay fails | Schema is only compatible with the previous version | Use transitive checks or test across the entire supported history |

## 19. Contract design and release checklist

- [ ] The event has a stable name and business meaning.
- [ ] Every field has clear type, required/optional status, nullability, and semantics.
- [ ] Timestamps, currency, units, and timezones are standardized.
- [ ] Key contract and partitioning are reviewed alongside the value schema.
- [ ] JSON, Avro, or Protobuf is chosen according to integration needs.
- [ ] Schema Registry subject naming and compatibility mode are defined.
- [ ] Backward/forward/full and transitive compatibility are checked based on replay needs.
- [ ] New consumers can handle historical records within the support window.
- [ ] Breaking changes have a separate migration or topic/event version.
- [ ] Rollout follows expand -> migrate -> contract.
- [ ] CI runs schema compatibility and contract tests.
- [ ] A plan exists for replay, rollback, and DLT handling on contract errors.

## 20. Conclusion

The data contract between producer and consumer is an agreement on the structure, types, semantics, and evolution rules of events written to Kafka. Manage the wire schema rather than relying on services sharing the same Java DTO. Design fields explicitly, distinguish optional/null/default, keep semantics stable, and treat keys and partitioning as part of the contract.

For multi-service or polyglot systems, Avro, Protobuf, or JSON Schema combined with Schema Registry help manage versions and enforce compatibility. Choose backward/forward/full and transitive compatibility according to rollout and replay requirements. Roll out changes with expand -> migrate -> contract, test new schemas against historical data, and block breaking changes in CI/CD. A well-defined contract lets producers and consumers release independently while exchanging events reliably.

## References

- [Apache Kafka — Message Serialization](https://kafka.apache.org/documentation/#producerconfigs_key.serializer)
- [Confluent Schema Registry — Schema Evolution and Compatibility](https://docs.confluent.io/platform/current/schema-registry/fundamentals/schema-evolution.html)
- [Apache Avro — Schema Resolution](https://avro.apache.org/docs/current/specification/)
- [Protocol Buffers — Updating a Message Type](https://protobuf.dev/programming-guides/proto3/#updating)
- [Spring for Apache Kafka — Serialization, Deserialization and Message Conversion](https://docs.spring.io/spring-kafka/reference/kafka/serdes.html)
