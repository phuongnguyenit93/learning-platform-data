# Renaming or Removing Fields

The schema of a Kafka event is the data contract between producer and consumer. When renaming or removing a field, a new producer may write payloads that old consumers do not understand; conversely, a new consumer may fail to read records written under the old schema. The problem persists after deployment because Kafka keeps records according to retention and consumers may replay historical data.

Therefore, renaming or removing a field must be rolled out in multiple compatible steps. Before modifying a schema, determine the format in use (Avro, JSON Schema, or Protobuf), Schema Registry compatibility rules, and the active producer/consumer versions.

## 1. Kafka does not define payload schemas itself

Kafka stores keys, values, and headers as bytes. The Kafka broker does not know what field `customerName` represents and does not check whether a consumer understands a payload. Schema validation is typically performed at the producer and consumer via serializers, deserializers, and schema management systems such as Confluent Schema Registry.

A record may carry a schema ID or format metadata added by the serializer. The consumer uses a deserializer to retrieve the matching schema and convert bytes into an object. When a schema changes, readability depends on the format's resolution rules and the compatibility policy configured for the subject.

Questions to answer before making changes:

- Which producers are writing this event type? Are old producers still running during rollout?
- Which consumers are reading? Are there external consumers or scheduled replay jobs?
- How long do old records remain in Kafka, object storage, or a data lake?
- Can consumers read records written under multiple schema versions?
- Which compatibility mode does Schema Registry use, and does it check against the latest version or the full history?

Do not treat successful code compilation as proof that schemas are compatible. Producers and consumers can be deployed at different times, and old data continues to be read after rollout.

## 2. Understanding backward, forward, and full compatibility

Schema Registry commonly uses the following compatibility concepts. Typical interpretations are based on reader/writer direction:

| Mode | Meaning | Verification question |
| --- | --- | --- |
| Backward | The new schema can read data written with the old schema | Can the new consumer read old records? |
| Forward | Old consumers/schemas can read data written with the new schema | Can old consumers tolerate new records? |
| Full | Supports both backward and forward | Can producers and consumers be upgraded in either order? |
| Transitive | Checks compatibility against multiple historical versions rather than only the previous one | Can the new consumer read all data still eligible for replay? |

Exact mode names and checking algorithms depend on the format and Schema Registry version. For example, `BACKWARD_TRANSITIVE` checks the new schema against prior versions; `FULL_TRANSITIVE` requires both directions across schema history. Confirm the policy applied to the specific subject, because subject naming strategies can create separate subjects per topic, record name, or key/value.

A change can be compatible in one direction but incompatible in the other. In independent producer/consumer rollouts, full compatibility usually provides safer deployment headroom, though it does not replace checking the schema format, semantics, and actual consumers.

## 3. Renaming a field is actually removing an old field and adding a new one

Suppose an initial event has fields:

```json
{
  "customerId": "C-102",
  "customerName": "An"
}
```

Later, the business wants to rename `customerName` to `displayName`. At the data-contract level, this is two operations:

1. Add the `displayName` field.
2. Deprecate and eventually remove the `customerName` field.

If the new producer writes only `displayName`, old consumers still looking for `customerName` may receive a missing value or fail deserialization/validation. If the new consumer reads only `displayName`, old records containing only `customerName` will also lack the value the consumer expects.

During the transition period, new consumers should read both names and prefer the new one. New producers can write both fields with the same meaning for a period of time. Only remove the old name once old consumers and replay workflows have been addressed.

```java
String displayName = event.displayName() != null
        ? event.displayName()
        : event.customerName();
```

This snippet illustrates consumer-side fallback. In actual DTOs, allow both old and new fields to coexist during the transition window, and define clearly how to handle cases where both have values that differ.

Do not rename a field if its business meaning has also changed. For example, `amount` previously meant pre-tax amount and is later used for post-tax amount. That is a semantic change; create a new field or a new event version rather than reusing the same name for a different meaning.

## 4. Renaming a field in Avro

Avro resolution compares the writer schema (used when writing the record) with the reader schema (used by the consumer when reading). The reader schema can declare `aliases` to map an old name to a new name when reading data written with an old schema.

Example old schema:

```json
{
  "type": "record",
  "name": "CustomerUpdated",
  "fields": [
    { "name": "customerId", "type": "string" },
    { "name": "customerName", "type": "string" }
  ]
}
```

New schema using `displayName` and declaring an alias:

```json
{
  "type": "record",
  "name": "CustomerUpdated",
  "fields": [
    { "name": "customerId", "type": "string" },
    {
      "name": "displayName",
      "type": ["null", "string"],
      "default": null,
      "aliases": ["customerName"]
    }
  ]
}
```

When the reader uses the new schema, the alias `customerName` lets Avro match the field of that name in the old writer schema and populate `displayName`. `default: null` also enables the reader to read writer schemas lacking `displayName` when no matching field exists for resolution.

Key point: aliases work in the direction of the reader schema resolving names from the writer schema. Old consumers still using the old reader schema do not automatically know that the new writer schema renamed the field to `displayName`. Thus, aliases help new consumers read old data; they do not automatically guarantee that a new producer writing only the new name will be compatible with old consumers.

In a rollout where producers and consumers run concurrently, keep the old field or dual-write during the transition window. Remove the old field only when old consumers no longer need to read new records and the compatibility policy permits it.

## 5. Removing a field in Avro

When removing a field from a new writer schema, new consumers can typically read old records with the extra field because the reader can ignore unused fields. The reverse direction requires care: old consumers whose reader schema expects a field removed by the new writer schema may fail resolution unless the reader schema declares a default.

For example, the old schema had a required `legacyCode`:

```json
{
  "name": "legacyCode",
  "type": "string"
}
```

Before stopping writes to this field, deploy consumers whose reader schema tolerates the absence of `legacyCode`, such as via an appropriate default or a new schema that has removed the field. Only then deploy producers that stop writing the field, and finally remove the field from the schema per compatibility policy.

An Avro default is the value the reader uses when the writer schema does not supply the corresponding field. It does not modify data already stored in Kafka and does not alter the original payload. Choose defaults that make business sense; do not mechanically use an empty string or 0 if those values could be mistaken for real data.

## 6. Renaming or removing a property in JSON Schema

With JSON Schema, fields are typically properties inside an object. A new schema can declare the new property while keeping the old property during the transition window:

```json
{
  "type": "object",
  "properties": {
    "customerId": { "type": "string" },
    "customerName": {
      "type": "string",
      "deprecated": true
    },
    "displayName": { "type": "string" }
  },
  "required": ["customerId"]
}
```

Here `deprecated: true` is an annotation informing tooling and humans that the old property should no longer be used. It does not remove the property, force producers to stop writing it, or copy `customerName` into `displayName`.

During the transition window, new consumers should read `displayName` first and fall back to `customerName`. Producers can write both. Add `displayName` to `required` only after ensuring every producer supplies this property and old data is handled under the compatibility policy.

JSON Schema can use `additionalProperties: false` to reject undeclared properties. Old consumers with that setting may reject new payloads containing `displayName`, even if they do not need that property. Therefore, adding a new property is safe only if consumer schemas/validators permit it or consumers are upgraded first.

The `default` attribute in JSON Schema is only an annotation under the JSON Schema specification; standard validators do not automatically inject default values into payloads. If consumers need a fallback, implement it in code or use an explicit data-normalization step.

## 7. Renaming or removing a field in Protobuf

Protobuf encodes fields by field number (tag number), not by field name on the wire. Therefore, renaming a field while keeping the same field number and wire type is typically compatible at the binary wire format level:

```protobuf
message CustomerUpdated {
  string display_name = 2; // Previously customer_name = 2
  string customer_id = 1;
}
```

Old Protobuf consumers still read field 2 under the old schema; new consumers read the same field 2 under the new name. However, field names are used in generated code, descriptors, and JSON mapping. If the system exchanges Protobuf JSON, renaming can alter JSON property names (e.g., `customerName` to `displayName`) and break JSON APIs even though the binary wire format stays compatible.

When removing a field, you must mark both the field number and the name as `reserved` to avoid accidentally reusing them:

```protobuf
message CustomerUpdated {
  string customer_id = 1;

  reserved 2;
  reserved "customer_name";
}
```

Never reassign a used tag number to a different meaning. If reused, old consumers may misinterpret new data as the old field and introduce subtle bugs. For enums, also reserve removed numeric values and enum names when you want to prevent reuse.

Schema Registry for Protobuf also enforces compatibility rules on descriptors and format settings. Thus, wire compatibility does not mean every tool, JSON representation, and compatibility mode will accept a rename. Verify with the exact registry and client versions deployed.

## 8. Safe rollout workflow for renaming a field

For renaming `customerName` to `displayName`, the rollout can be divided into phases:

```text
Phase 1: EXPAND
  Schema accepts both customerName and displayName
                 |
                 v
Phase 2: CONSUMER
  New consumer reads displayName, falls back to customerName
                 |
                 v
Phase 3: DUAL WRITE
  Producer writes both fields with the same meaning
                 |
                 v
Phase 4: MIGRATE
  Confirm no consumers remain dependent on customerName
                 |
                 v
Phase 5: CONTRACT
  Producer stops writing customerName, schema removes the old field
```

Practical steps:

1. Inventory producers, consumers, connectors, replay jobs, and external systems using the old field.
2. Register the expanded schema so existing consumers can still read new payloads under the chosen policy.
3. Deploy consumers that can read both the new and old names. With Avro, use aliases in the reader schema where appropriate; with JSON Schema/Protobuf, implement corresponding fallbacks or mappings.
4. Deploy producers dual-writing both fields. If both contain values, define clearly which value is authoritative and how discrepancies are detected.
5. Monitor metrics/logs to confirm consumers have switched to the new field and no longer depend on the old field.
6. Retire old producers, then stop writing the old field in new producers.
7. Remove the old field from the schema only when old consumers are gone and replay/retention policies no longer require it.

If dual-write is not feasible due to payload size or semantics, use a new event version or a dedicated topic/version contract. Do not force a new field to carry an old meaning merely to preserve nominal compatibility.

## 9. Safe rollout workflow for removing a field

Removing a field can generally follow the *deprecate -> stop use -> stop write -> remove* model:

1. Mark the field as deprecated in documentation/schemas if the format supports it.
2. Deploy consumers that stop depending on that field; audit code, dashboards, connectors, and reports.
3. Deploy producers that stop writing the field. Do not perform this step if old consumers still require the field.
4. Wait out the rollout, retry, retention, and committed replay windows. Also check data in storage outside Kafka.
5. Remove the field from the schema and verify compatibility against historical versions.
6. Retain necessary metadata to interpret old schemas and support historical data investigations.

Do not delete a field simply because it has not appeared in traffic for a few minutes. A weekly consumer, month-end batch job, or replay tool may still depend on the field. Wait durations must reflect the actual lifecycle of all consumers and data.

## 10. Compatibility policies do not replace application testing

Schema Registry can verify that a change is format-compatible, yet it does not fully understand business logic. For example, `customerName` and `displayName` are both strings so a schema checker may permit a change, yet consumers might interpret the two fields with different semantics.

Verify at least these producer/consumer pairs:

| Producer writes | Consumer reads | What to verify |
| --- | --- | --- |
| Old schema | New consumer | New consumer reads historical records and falls back properly |
| New schema | Old consumer | Old consumer does not error or has been retired before new producer runs |
| Dual-write producer | New consumer | Consumer prioritizes new field and detects conflicting values |
| Dual-write producer | Old consumer | Old consumer still reads the old field during transition |
| New schema after contract | Replay job | Historical data still within retention deserializes and processes cleanly |

Maintain payload fixtures written under each schema version, run integration tests with Schema Registry or an appropriate mock registry, and verify real deserialization. Also test null fields, absent fields, defaulted fields, and payloads where both names appear simultaneously.

## 11. Common pitfalls

| Mistake | Consequence | Prevention |
| --- | --- | --- |
| Renaming directly and deploying only new producers | Old consumers cannot find the old field | Roll out compatible consumers first and dual-write during transition |
| Assuming Avro aliases make old and new producers/consumers mutually understand each other | Aliases primarily help new reader schemas map old writer schemas | Check both reader/writer directions; keep old field when forward compatibility is needed |
| Removing a field still required by old consumers | Deserialization or validation fails | Consumers must drop dependency before producers stop writing and schema is contracted |
| Assuming JSON Schema `default` auto-injects values | Consumers still receive absent properties | Implement fallback/normalization explicitly in the application |
| Removing a Protobuf field and reusing its tag number | Wire data is misinterpreted | Reserve removed tag numbers and names |
| Checking only against the immediately preceding schema version | Replay jobs may encounter older schemas | Consider transitive compatibility matching the replay window |
| Removing a field when only online consumers have upgraded | Batch jobs or external systems still fail | Inventory all readers and data retention horizons |
| Renaming while also changing business meaning | Old consumers read the field but misinterpret the data | Create a new field/event version for semantic changes |

## 12. Checklist before renaming or removing a field

- [ ] Identified the schema format and serializer/deserializer versions.
- [ ] Identified the Schema Registry subject and compatibility mode (including transitive).
- [ ] Inventoried all producers, consumers, connectors, batch jobs, and replay processes.
- [ ] Distinguished pure renaming from semantic changes.
- [ ] When renaming, new consumers can read both old and new data.
- [ ] Producers dual-write or use a separate event versioning strategy during transition.
- [ ] Avro alias/default, JSON Schema optional/deprecated, or Protobuf tag/reserved are used accurately.
- [ ] Not relying on JSON Schema `default` as an automatic data-injection mechanism.
- [ ] Removed Protobuf field numbers or enum values are not reused.
- [ ] Tested old producer/new consumer, new producer/old consumer, and historical data replay.
- [ ] Contract the old field only after no readers/writers depend on it and retention/replay windows are accounted for.
- [ ] Metrics or logs exist to track usage of the old field during migration.

Renaming or removing a field is a data-contract transition, not merely editing a property name in a DTO. Expand the schema first, deploy consumers capable of reading both forms, transition producers step-by-step, and contract the old field only when all readers and historical data are ready. This keeps Kafka streams healthy throughout independent producer and consumer upgrades.
