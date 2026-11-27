# Adding Fields, Renaming Fields, and Handling Default Values

Event messages often outlive a single application version. A producer may have emitted millions of events under an old structure while a new consumer is rolling out. Other consumers may still run an older version, or a replay job may re-read data stored months earlier. Therefore, schema changes must account for both newly produced data and previously emitted data.

In Spring Cloud Stream, functions typically receive payloads converted into a DTO, `String`, or `byte[]`. Binders transport messages over Kafka, RabbitMQ, or Pulsar; binders do not automatically make every schema change compatible. Producers and consumers need a shared contract covering field names, data types, semantics, default values, and schema versions.

This lesson focuses on three common changes: adding fields, renaming fields, and handling missing or defaulted fields. The core principle is evolving contracts incrementally, preserving readability of old data during the transition window, and testing with payloads from multiple versions.

## 1. Event Contracts and Compatibility

A schema describes data structure: field names, types, required fields, optional fields, enums, nested structures, and sometimes default rules. An event contract goes further than a schema. It must describe business meaning, units of measurement, time zones, null rules, field ownership, and consumer behavior when encountering unknown values.

Example order-created event:

~~~json
{
  "eventId": "evt-1001",
  "eventType": "OrderCreated",
  "schemaVersion": 1,
  "orderId": "ORD-1001",
  "customerId": "CUS-42",
  "total": 125000,
  "currency": "VND"
}
~~~

A later version might add a **channel** field indicating whether the order came from web, mobile app, or physical store:

~~~json
{
  "eventId": "evt-1002",
  "eventType": "OrderCreated",
  "schemaVersion": 2,
  "orderId": "ORD-1002",
  "customerId": "CUS-42",
  "total": 125000,
  "currency": "VND",
  "channel": "MOBILE"
}
~~~

Old consumers may not know about the **channel** field. New consumers must handle version 1 events lacking this field. Both directions must be evaluated.

Two commonly used compatibility concepts:

| Capability | Meaning | Question When Changing |
|---|---|---|
| Backward compatibility | Consumers using the new schema can read data written with the old schema. | Can new consumers read events that lack the new field? |
| Forward compatibility | Consumers using the old schema can read data written with the new schema. | Can old consumers tolerate new fields or new values? |
| Full compatibility | Satisfies both directions. | Can producers and consumers be deployed in either order and still read data? |

Exact mode names and check scopes vary by schema registry. A registry may check compatibility against only the immediately preceding version or against the entire schema history. Confirm which mode is active rather than relying solely on the mode name.

## 2. Adding a New Field Compatibly

Adding an optional field is usually lower risk than removing fields or changing data types. Nevertheless, a new field can still break old consumers if parsers are configured to reject unknown properties. Conversely, new consumers can fail when reading old events if the new field is treated as required with no handling for its absence.

Before adding a field, decide:

1. Is the field required on every new event?
2. How will old data lacking this field be interpreted?
3. Do `null`, empty string, `0`, and omitted field carry different meanings?
4. Do old consumers ignore unknown fields, or must they be upgraded first?
5. Is backfilling stored data or replaying old events necessary?

### Adding an Optional Field in JSON

Suppose the new DTO adds **channel**:

~~~java
public record OrderCreated(
        String orderId,
        String customerId,
        BigDecimal total,
        String currency,
        String channel) {
}
~~~

An old event without the **channel** property may be mapped to `null`, depending on the constructor, Jackson configuration, and converter in use. The consumer should handle that case explicitly:

~~~java
@Bean
public Consumer<OrderCreated> orderConsumer(OrderService service) {
    return event -> {
        String channel = event.channel() == null || event.channel().isBlank()
                ? "UNKNOWN"
                : event.channel();

        service.process(event, channel);
    };
}
~~~

In this example, **UNKNOWN** is an application-layer fallback value. It lets the new consumer keep reading old events without pretending to know the exact order channel. If business rules stipulate all historical orders count as **WEB**, use that value and document it explicitly as a historical data conversion rule.

Avoid using primitive types for fields that may be absent if you need to distinguish an unsent value from zero. For instance, `int quantity` can receive `0` when the property is missing in certain conversion paths. Using `Integer` or an appropriate nullable type lets you distinguish `null` from `0` and validate according to business rules.

### JSON Schema Rules

In JSON Schema, properties not listed in the `required` array are optional. An optional property may be absent; that differs from a property that is present with a `null` value. If `null` must be allowed, the schema must declare a type or union containing `null` per the JSON Schema version in use.

Illustrative example:

~~~json
{
  "type": "object",
  "properties": {
    "orderId": { "type": "string" },
    "customerId": { "type": "string" },
    "channel": {
      "type": ["string", "null"],
      "default": "UNKNOWN"
    }
  },
  "required": ["orderId", "customerId"]
}
~~~

In JSON Schema, the `default` keyword is primarily metadata/an annotation describing a default value. Validators themselves are not required to insert that value into JSON when a field is missing. To apply a default, consumers must implement it in code or use tooling that supports default materialization and verify that tool's exact behavior.

This distinction matters when a team assumes merely adding `default` to a schema means every consumer will automatically receive the value. The schema may validate while payloads still omit the field.

## 3. Placing Default Values at the Right Layer

Default values can live in the schema, DTO, mapper, or business logic. These locations do not carry identical semantics.

| Location | Effect | Watch Out For |
|---|---|---|
| Schema | Describes default value or format-specific read rules. | Enforcement depends on format and library. |
| DTO/constructor | Initializes fields when object is instantiated. | Constructors or deserializers may overwrite initial values. |
| Mapper | Transforms old-version data into the current internal model. | Good place to centralize conversion rules. |
| Domain service | Applies business rules when data is missing. | Must distinguish missing data from invalid data. |

Do not assign arbitrary defaults in the producer just so the new schema always looks populated. If the producer does not know the real value, sending **UNKNOWN** may be more accurate than sending **WEB** or **0**. Default values must reflect business meaning, not merely make deserialization succeed.

### Distinguishing Absent, Null, Empty, and Zero

In JSON, the following states can carry different meanings:

~~~json
{}
~~~

~~~json
{"channel": null}
~~~

~~~json
{"channel": ""}
~~~

~~~json
{"channel": "WEB"}
~~~

The first case is an absent property. The second is a property present with a `null` value. The third is an empty string. The last has a concrete value. If business logic needs to distinguish these cases, do not collapse them into a single fallback branch.

A mapper example can express the rules explicitly:

~~~java
static String resolveChannel(OrderCreated event) {
    if (event.channel() == null) {
        return "UNKNOWN";
    }
    if (event.channel().isBlank()) {
        throw new IllegalArgumentException("channel must not be blank");
    }
    return event.channel();
}
~~~

In this example, a missing field is accepted and mapped to **UNKNOWN**, whereas an empty string is treated as invalid data. Choose this pattern only if it matches the agreed business contract.

## 4. Adding Fields with Avro

Avro supports schema resolution between writer schema and reader schema. When a consumer reads a record written with an old schema using a new reader schema, the reader schema can supply a default value for a new field absent from the writer schema.

Example version 1 writer schema:

~~~json
{
  "type": "record",
  "name": "OrderCreated",
  "fields": [
    { "name": "orderId", "type": "string" },
    { "name": "customerId", "type": "string" },
    { "name": "total", "type": "double" }
  ]
}
~~~

Version 2 reader schema adding **channel** with a default:

~~~json
{
  "type": "record",
  "name": "OrderCreated",
  "fields": [
    { "name": "orderId", "type": "string" },
    { "name": "customerId", "type": "string" },
    { "name": "total", "type": "double" },
    {
      "name": "channel",
      "type": ["null", "string"],
      "default": null
    }
  ]
}
~~~

When the v2 reader schema reads a record written with the v1 writer schema, Avro can supply **null** for **channel** per the declared default. If the new field lacks an appropriate default, schema resolution can fail when reading old data.

Note: with Avro unions, the default value must match the first branch of the union per Avro rules. That is why the example places **null** first in the union with `default: null`. Do not apply Avro's default rules to JSON Schema or Protobuf because each format has its own semantics.

Spring Cloud Stream can integrate with a schema registry and Avro depending on the version, dependencies, and application configuration. If using a registry, verify that the writer schema is registered, how the producer sends the schema ID, and how the consumer fetches schemas on read. Binders transport payloads; the schema registry and Avro serializer/deserializer are responsible for schema resolution.

## 5. Renaming a Field Is a Contract Change

Renaming a field may look like a cosmetic code change, but for emitted data it is a structural change. A new producer may emit **buyerId** while an old consumer still looks for **customerId**. If the old field disappears immediately, old consumers may receive `null`, default values, or parse errors.

Do not roll out a rename by changing the name in a single commit and deploying all producers and consumers simultaneously. Use a transition workflow:

1. Expand the schema to accept both the old name and the new name.
2. Deploy consumers capable of reading both names.
3. Deploy producers writing the new field; during the compatibility window, keep writing the old field as well.
4. Monitor the proportion of upgraded consumers and producers, along with older data remaining within retention.
5. Retire the old field only after all relevant consumers have upgraded and replayable data no longer depends on the old field.
6. Remove the old field in a subsequent schema change, if allowed by the registry and compatibility policy.

### Transition Example with JSON and Jackson

During the transition window, the DTO can accept both names:

~~~java
public class CustomerReference {

    private String buyerId;
    private String customerId;

    public void setBuyerId(String buyerId) {
        this.buyerId = buyerId;
    }

    public void setCustomerId(String customerId) {
        this.customerId = customerId;
    }

    public String effectiveBuyerId() {
        if (buyerId != null && !buyerId.isBlank()
                && customerId != null && !customerId.isBlank()
                && !buyerId.equals(customerId)) {
            throw new IllegalArgumentException(
                    "buyerId and customerId do not match");
        }
        if (buyerId != null && !buyerId.isBlank()) {
            return buyerId;
        }
        return customerId;
    }
}
~~~

In this example, two setters separate the old and new names so the consumer can detect when both appear with conflicting values. If the DTO only keeps the new property **buyerId**, you can use **@JsonAlias("customerId")** so Jackson accepts the old name when deserializing. An alias does not automatically make the serializer write both names. If the producer needs dual-writing, build a transition payload containing both **buyerId** and **customerId** explicitly, or use a DTO with both properties and a mapper controlling emission.

Example mapper creating a transition payload:

~~~java
Map<String, Object> toTransitionPayload(String buyerId) {
    return Map.of(
            "buyerId", buyerId,
            "customerId", buyerId
    );
}
~~~

Do not dual-write indefinitely. Two fields representing the same data can diverge if a producer updates one and forgets the other. Define which field is authoritative, precedence rules when both appear with differing values, and when the transition window ends.

## 6. Renaming Rules in Avro and Protobuf

Schema formats have their own mechanisms for renaming. JSON/Jackson techniques cannot be applied universally across all formats.

### Avro Aliases

Avro supports **aliases** so a reader schema can recognize old names in certain schema resolution scenarios. For example, a reader schema renames a record or field while declaring the corresponding alias:

~~~json
{
  "type": "record",
  "name": "OrderCreated",
  "fields": [
    { "name": "orderId", "type": "string" },
    {
      "name": "buyerId",
      "type": "string",
      "aliases": ["customerId"]
    }
  ]
}
~~~

An alias aids schema resolution; it does not mean a new producer will emit both fields simultaneously. Verify alias support in the serializer, deserializer, and schema registry in use. Test with the old writer schema and new reader schema before deployment.

### Protobuf Field Numbers

In Protocol Buffers, the field number is the identifier on the wire. When renaming a field in a `.proto` file, keeping the same field number usually preserves binary wire readability for that field, but names in generated code and JSON mappings can change. Systems relying on JSON names or reflection can still be affected.

Example:

~~~protobuf
message OrderCreated {
  string buyer_id = 2;
}
~~~

If the field was previously named **customer_id** with number 2, renaming it to **buyer_id** while keeping number 2 can remain binary-wire compatible. However, never reuse number 2 for a different field. When removing a field, mark the used number and names as `reserved`:

~~~protobuf
message OrderCreated {
  reserved 2;
  reserved "customer_id", "buyer_id";
  string order_id = 1;
}
~~~

The `reserved` snippet illustrates when field number 2 is deleted after a rename transition; both the old and new names are kept in the `reserved` list to prevent reuse. In a real schema, keep the remaining fields intact and never redeclare a reserved number or name. Never reuse a published field number, even if the old field no longer exists in code.

With Protobuf `proto3`, scalar fields can return default values such as `0`, `false`, or an empty string when absent. If you need to distinguish an absent field from an explicit default value, use an appropriate presence mechanism, such as `optional` or wrapper messages depending on version and language. Do not interpret `0` as a user-supplied value unless the schema guarantees presence.

## 7. Changing Data Types and Field Meanings

Name changes are not the only risk. Type changes can prevent consumers from deserializing or alter the meaning of values.

| Change | Risk | Mitigation |
|---|---|---|
| Add optional field | New consumers encounter old data lacking the field. | Provide explicit fallbacks and test against old schemas. |
| Add required field | Old data lacks the field. | Avoid if historical reads are needed; consider a new version or migration. |
| Change String to number | Old payloads may contain unparseable strings. | Add a new field, migrate in a controlled way, and keep the old field during transition. |
| Change unit from dong to thousands of dong | Same type but different meaning. | Create a new field or new event version; never change semantics silently. |
| Remove field | Old consumers and replays may still need the field. | Deprecate first, monitor, and remove only after the compatibility window. |
| Add enum value | Old consumers may reject unknown values. | Design consumers with an unknown/other branch and test new values. |
| Change null to empty string | Can lose information about unknown states. | Finalize semantics and convert data intentionally. |

If a field changes business meaning, treat it as a contract change even if its name and type stay the same. For example, **total** previously meant pre-tax total and later changes to post-tax total. Old consumers still parse it successfully yet compute wrong results. Create new fields such as **totalBeforeTax** and **totalAfterTax**, or emit a new event type/version if the change invalidates the old contract.

## 8. Rolling Out via Expand, Migrate, Contract

A safe workflow for schema changes typically has three phases:

### Expand

- Add the new field in an optional way or with a format-appropriate default.
- Upgrade consumers to read both old and new payloads.
- Test new producers with old consumers and new consumers with old payloads.

### Migrate

- Deploy producers starting to write the new field.
- If needed, dual-write old and new fields for a defined period.
- Backfill stored data or replay events if business requirements call for it.
- Monitor parse errors, fallback rates, and un-upgraded consumers.

### Contract

- Confirm all active consumers have switched to the new field.
- Confirm data in retention, DLQs, backups, and replay workflows no longer depends on the old field or has a compatible mapper.
- Stop emitting the old field, then remove it from the schema according to registry policy.

The Mermaid diagram below illustrates the rollout sequence:

~~~mermaid
flowchart LR
    A[Old schema] --> B[Expand: add optional field]
    B --> C[Consumers read old and new]
    C --> D[Producers write new field]
    D --> E[Migrate: backfill and monitor]
    E --> F[Stop using old field]
    F --> G[Contract: remove old field]
~~~

Not every change needs dual-write or backfill. If the new field only adds non-required metadata and history is not needed, consumers can apply a fallback for old events. Choose the workflow based on replay needs, retention duration, and actual consumer count.

## 9. Managing Schema Versions and Registries

A schema registry stores schemas by subject or equivalent identifier, manages versions, and checks compatibility rules before producers register new schemas. A registry lowers the risk of producers emitting a schema that breaks consumers, though it does not replace application testing.

When using a registry:

- Choose a subject naming strategy suited to whether multiple event types share a topic or each event type has its own subject.
- Enable the compatibility mode matching the deployment order of producers and consumers.
- Confirm whether the registry checks only the immediately preceding version or full history.
- Manage schema IDs and registry access permissions as part of deployment configuration.
- Do not delete old schemas while replayable data or old consumers remain active.
- Run schema compatibility checks in CI before release.

Spring Cloud Stream provides schema registry support in certain generations and configurations; Kafka, Pulsar, or external platforms can also provide their own registries. How subjects, serializers, schema IDs, and dependencies are configured varies by version. Pick one clear mechanism and verify producers and consumers follow the same schema rules, avoiding mixing incompatible serializers.

A **schemaVersion** field in the payload can help applications manage versions themselves, but it does not replace schema IDs or format-level schema resolution. When using a schema registry, clarify whether application version, event version, and schema version share the same number or are three independent concepts.

## 10. Testing Schema Changes in Spring Cloud Stream

Testing with only a new payload cannot catch compatibility bugs with historical data. Every change needs fixtures for both old and new versions, including missing fields, nulls, defaults, and unexpected values.

Example consumer handling an event with a new field:

~~~java
public record OrderCreated(
        String orderId,
        String customerId,
        BigDecimal total,
        String channel) {
}

@Bean
public Consumer<OrderCreated> orderConsumer(OrderService service) {
    return event -> {
        String channel = event.channel() == null
                ? "UNKNOWN"
                : event.channel();
        service.process(event.orderId(), event.customerId(),
                event.total(), channel);
    };
}
~~~

Test fixtures:

~~~json
{
  "orderId": "ORD-OLD",
  "customerId": "CUS-1",
  "total": 100000,
  "currency": "VND"
}
~~~

~~~json
{
  "orderId": "ORD-NEW",
  "customerId": "CUS-1",
  "total": 100000,
  "currency": "VND",
  "channel": "MOBILE"
}
~~~

The consumer must handle both payloads. In this example, the **currency** field appears in the JSON but not in the illustrative record; in a real project, the DTO must declare that field if used, or the converter must be configured to handle unknown properties. This is why testing against actual DTOs and Jackson configurations matters instead of inspecting JSON by eye.

Recommended test matrix:

| Test Case | Input | Expected Outcome |
|---|---|---|
| Old payload | Lacks the new field. | New consumer applies contract fallback. |
| New payload | Has valid new field. | Consumer receives the exact sent value. |
| Null field | Field present as `null`. | Behavior matches documented null rules. |
| Empty field | Empty string or whitespace. | Accepted or rejected per business rules. |
| Wrong field type | String instead of number, or object instead of string. | Conversion error recorded and routed to retry/DLQ appropriately. |
| Unknown field | New producer adds another property. | Old consumer acts per parser unknown-field policy. |
| Field rename | Only old name, only new name, or both. | Mapper/alias picks right value; conflicts detected. |
| Replay | Old events replayed after consumer upgrade. | Business outcome remains accurate without duplicate side effects. |
| Schema registry | Register new schema. | Registry accepts or rejects accurately per compatibility mode. |

With Spring Cloud Stream's Test Binder, you can test functions and bindings in-process. With Avro, Protobuf, or JSON Schema, add tests with real serializers/deserializers and schema resolution. Integration tests with Kafka, RabbitMQ, or Pulsar verify payloads over the broker, though they do not replace CI schema compatibility checks.

## 11. Common Pitfalls

| Symptom | Possible Cause | Resolution |
|---|---|---|
| New consumer fails reading old events | New field is required or lacks a suitable default. | Make the field optional, add format-appropriate defaults, or add mapper fallback. |
| Old consumer fails when producer adds a field | Parser rejects unknown properties or schema registry blocks change. | Check unknown-field policy and compatibility mode; deploy compatible consumer first. |
| New field always arrives as `null` | Producer does not send it yet, name mismatch, or converter fails to map. | Inspect wire payload, DTO, and mapper. |
| Value `0` interpreted as explicitly provided data | Using primitives or a format without clear presence. | Use wrappers/optionals/presence mechanisms and define semantics. |
| Rename loses data | Renamed only in producer or consumer without a transition phase. | Use aliases or time-boxed dual-read/dual-write. |
| Old and new fields differ | Producer writes both with separate logic or lacks an authoritative field. | Pick an authoritative source, define precedence, and alert on conflicts. |
| Registry rejects new schema | Schema violates compatibility mode or historical comparison. | Inspect schema diff and adjust change process. |
| Replay fails after removing old field | Old data still sits in retention, backups, or DLQs. | Keep compatible mappers or wait until replay windows expire before contracting. |

When troubleshooting, capture an actual payload from the producer, identify its writer schema or version, and run the exact failing consumer version against it. Never look only at the new DTO and assume old payloads convert automatically.

## 12. Checklist Before Releasing a New Schema

- [ ] Documented fields added, renamed, removed, or type-changed along with business rationale.
- [ ] Defined what absent, `null`, empty, and zero mean.
- [ ] New fields have handling for old data.
- [ ] New consumers can read both old and new payloads.
- [ ] Old consumers tested against new payloads, if forward compatibility is required.
- [ ] Default rules match the JSON Schema, Avro, or Protobuf format in use.
- [ ] Field renames have an alias or dual-read/dual-write plan and a sunset date.
- [ ] Protobuf field numbers are never reused; removed fields are marked `reserved`.
- [ ] Schema registry verified compatibility across the right historical scope.
- [ ] Old/new fixtures, nulls, missing fields, wrong types, and replays tested.
- [ ] Data in retention, DLQs, and backups accounted for before removing old fields.
- [ ] Consumers emit metrics or logs for fallbacks, schema parse errors, and unsupported values.

Adding fields, renaming fields, and setting default values are all inter-service contract changes. Define field semantics before picking schema syntax, verify how your format handles missing data, and roll out in stages so producers and consumers can coexist during transitions. With Spring Cloud Stream, testing historical payloads through the exact deployed converters, serializers, and binders is essential for safe schema evolution.
