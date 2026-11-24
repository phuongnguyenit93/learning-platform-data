# Backward Compatibility When Adding, Removing, or Changing Field Types

## Objectives

After this lesson, you will be able to evaluate whether a change in a message contract breaks existing producers or consumers; distinguish backward, forward, and full compatibility; apply appropriate rules for JSON/Jackson in Spring; and roll out changes in phases so multiple application versions can coexist during upgrades.

## 1. What Is a Message Contract?

A message contract is an agreement on the structure and meaning of a message between the sender (producer) and the receiver (consumer). A contract typically describes:

- Event name or message type.
- Fields, data types, meaning, and units of each field.
- Required/optional fields, default values, and nullability rules.
- Encoding rules, such as JSON, Protocol Buffers, or Avro.
- Schema version and how data produced by older versions should be handled.

In Spring Messaging, applications work with `Message<?>`, which consists of a payload and headers. A `MessageConverter` converts payloads between serialized form and Java types; the `MessageHeaders.CONTENT_TYPE` header can tell the converter the content format. For example, the same JSON payload can be converted into a Java DTO via a Jackson converter. See [Spring MessageConverter Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0-M6/javadoc-api/org/springframework/messaging/converter/MessageConverter.html).

Do not equate a message contract with a Java class. Producers and consumers may be implemented in different languages, frameworks, and versions. A Java class is only one side's representation of the contract. When a class changes, what needs to be evaluated is the payload on the wire and how every consumer interprets that payload.

A change can be syntactically compatible yet still break business logic. For example, changing `amount` from major currency units to minor units while keeping the `long` type may deserialize successfully, yet older consumers will compute incorrect values. Therefore, you must verify both deserialization compatibility and data semantics.

## 2. Three Directions of Compatibility

Suppose the old contract version is V1 and the new version is V2.

| Compatibility Type | Question to Answer | Check Direction |
|---|---|---|
| Backward compatibility | Can new consumers read messages produced by old producers? | V2 reader reads V1 data |
| Forward compatibility | Can old consumers read messages produced by new producers? | V1 reader reads V2 data |
| Full compatibility | Can both old and new consumers read data from both old and new producers? | Check both directions |

Some schema registries also offer a **transitive** mode. Instead of comparing the new schema only against the immediately preceding version, the registry checks it against all prior versions. This matters when old messages remain stored in queues, topics, data lakes, or event stores and may be replayed across multiple upgrades.

There is no universal "adding a field is always safe" rule across all serializers. The outcome depends on the data format, schema, converter, consumer configuration, and the deployment order of producers and consumers.

## 3. Adding a New Field

Adding a field is usually the easiest change to manage, but both sides must be examined.

Suppose V1 sends:

~~~json
{
  "paymentId": "pay-1042",
  "amount": 125000
}
~~~

V2 adds a `currency` field:

~~~json
{
  "paymentId": "pay-1042",
  "amount": 125000,
  "currency": "VND"
}
~~~

### New Consumer Reading Old Messages

A V2 consumer receiving a V1 payload will not find `currency`. If the new field is optional, the consumer can apply a business-defined default value.

Java 17 DTO example:

~~~java
import java.math.BigDecimal;

public record PaymentAuthorized(
    String paymentId,
    BigDecimal amount,
    String currency
) {
    public String effectiveCurrency() {
        // Only valid if the legacy contract guarantees every amount is in VND.
        return currency == null ? "VND" : currency;
    }
}
~~~

Here, `currency` is a reference type so it can receive `null` when an older payload omits the property. The default value must come from a confirmed business rule. If older messages could contain multiple currencies, do not arbitrarily assign VND; preserve the missing-data state, look up the appropriate source, or reject the message according to a clear policy.

If the new field is truly required, do not add it as a mandatory requirement immediately. Roll it out in phases: deploy consumers capable of handling both old and new messages first, then have producers send the new field, and tighten validation only after all producers have been upgraded.

### Old Consumer Reading New Messages

A V1 consumer does not know about `currency`. With JSON, readability depends on how unknown properties are handled.

In Spring Framework 6.2, `MappingJackson2MessageConverter` uses Jackson 2 and disables `DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES` by default. Thus, this converter can ignore new JSON fields not declared by the older DTO. If an application replaces the converter or supplies a custom-configured `ObjectMapper`, verify the actual behavior rather than relying on defaults. See [MappingJackson2MessageConverter Javadoc](https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/messaging/converter/MappingJackson2MessageConverter.html).

Explicit configuration example with Spring Messaging 6.2 and Jackson 2:

~~~java
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.messaging.converter.MappingJackson2MessageConverter;

ObjectMapper objectMapper = new ObjectMapper()
    .disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);

MappingJackson2MessageConverter converter =
    new MappingJackson2MessageConverter(objectMapper);
~~~

This is a converter configuration snippet, not a standalone application. In a real system, use the converter registered with your messaging endpoint or broker adapter. Spring Framework 7 introduces converter APIs based on Jackson 3; class names and packages may differ. Check the Javadoc for the exact version your project uses.

**Takeaway when adding fields:** a new field should be treated as optional by new consumers during the transition window; old consumers must ignore unknown properties if forward compatibility is required. If an old consumer has custom validation or uses a closed schema, adding a field can still cause the message to be rejected.

## 4. Distinguishing Missing Fields, Null, and Default Values

The following three states are not the same:

~~~json
{}
~~~

~~~json
{ "discount": null }
~~~

~~~json
{ "discount": 0 }
~~~

- **Missing property:** the producer did not send the field.
- **Null:** the producer sent the field explicitly stating there is currently no value.
- **Default value:** the producer sent a concrete value, such as `0`, `false`, or an empty string.

With Java primitive types such as `int` or `boolean`, deserialization may turn a missing or null state into `0` or `false`, depending on Jackson configuration. This loses the ability to distinguish "not sent" from "sent value 0". Use reference types such as `Integer`, `Boolean`, or `BigDecimal` when you need to detect an absent value.

If business logic needs to distinguish between missing and explicit null, a regular DTO with nullable properties may not suffice because both states collapse into `null`. In that case, use a JSON tree/presence wrapper, a custom deserializer, or a schema format with explicit presence tracking.

Do not use default values merely to avoid deserialization errors. Defaults must carry stable business semantics. For example, `quantity = 0` may be valid and different from "unknown quantity"; `isActive = false` differs from "legacy producer did not send `isActive`".

## 5. Removing an Existing Field

Removing a field can break consumers that still depend on it.

Suppose V1 has `legacyCode` and V2 removes that field. Two scenarios must be checked:

- **New consumer reading old messages:** old messages still contain `legacyCode`. The new consumer must ignore this field or continue supporting the legacy alias/field during the transition period.
- **Old consumer reading new messages:** new messages no longer contain `legacyCode`. The old consumer may deserialize successfully, yet business logic can still fail if that field is required.

A safe rollout path:

1. Mark the old field as deprecated in contract documentation and code.
2. Migrate consumers away from depending on the old field; keep accepting messages with or without it.
3. If a replacement is needed, add the new field with a clear name and meaning.
4. Stop producers from sending the old field once all consumers are ready.
5. Wait out the retention/replay window for old messages, or ensure consumers can still read the old schema.
6. Only then remove the old field from the schema and DTOs.

For event sourcing or brokers with long retention, step 5 is critical. A message created months ago may still be replayed into a new consumer. Just because current producers no longer send the old field does not mean historical data has disappeared.

## 6. Renaming a Field

Renaming looks minor in code, but on the wire format it is usually removing one key and adding another.

For example, renaming `customer_name` to `displayName`. During the transition period, a Jackson DTO can accept both old and new names using `@JsonAlias`:

~~~java
import com.fasterxml.jackson.annotation.JsonAlias;
import com.fasterxml.jackson.annotation.JsonProperty;

public record CustomerSnapshot(
    @JsonProperty("displayName")
    @JsonAlias({"customer_name", "name"})
    String displayName
) {}
~~~

`@JsonAlias` allows the deserializer to accept the old names. When serializing, the primary property is still written as `displayName`. Thus, aliases help new consumers read old messages; they do not make old consumers automatically understand the new name.

For a safe rollout, you can temporarily send both old and new keys, have new consumers prefer the new key with fallback to the old key, and wait until old consumers are upgraded before stopping the old key. If both keys appear together, explicitly define which key takes precedence and test conflicting values.

With Avro, field aliases support schema resolution when the reader schema renames a field. With Protocol Buffers binary wire format, the field name is not the wire identifier; the field number is. However, renaming still affects JSON/TextFormat mappings and generated code. Therefore, evaluate the binary format and JSON representation separately.

## 7. Changing a Field's Data Type

Changing a type in place on the same field name is the riskiest of the three change types.

Example:

~~~json
{ "customerId": "00042" }
~~~

changed to:

~~~json
{ "customerId": 42 }
~~~

Consumers may:
- Fail to deserialize due to a Java type mismatch.
- Lose leading zeros if an identifier is changed from string to number.
- Overflow when values exceed the new type's range.
- Change precision when switching among integer, floating-point, and decimal types.
- Run without error yet misinterpret units or meaning.

Identifiers should generally remain strings because they may contain leading zeros, letters, or formatting characters. Monetary values should use `BigDecimal` or integers in minor units with explicit scale rules; avoid changing money from decimal to `double` because floating point can introduce rounding errors.

### Strategy for Changing Types Using a New Field

Instead of changing the type in place, add a new field with a name that clearly indicates its type/meaning:

~~~json
{
  "customerId": "00042",
  "customerIdNumeric": 42
}
~~~

New consumers read `customerIdNumeric` when present, otherwise converting from `customerId` using tested rules. Producers can dual-write both fields during the transition period. Only after all consumers use the new field and old data is no longer needed should the old field be retired.

If the business meaning changes—not just the data type—consider creating a new event type or schema version. For example, if `amount` was previously pre-tax total and is now post-tax total, keeping the same `BigDecimal` type is still a semantic breaking change.

### Notes on Numeric Types

- `int32` to `int64` can preserve old values within the valid range, but Java consumers, database columns, JSON Schema, and serializers all need to be checked.
- `long` to `double` can lose precision for large integers.
- `BigDecimal` to `double` can alter monetary values.
- Timestamp string to epoch milliseconds is a change in both format and unit; timezone, precision, and conversion rules must be specified.
- Changing an enum to a string or vice versa affects both serialization and how unknown values are handled.

Do not conclude a type change is safe just because a small sample deserializes successfully. Test with boundary values, realistic data, and every deployed serializer and consumer.

## 8. Format-Specific Rules

### JSON and Jackson in Spring

JSON is often viewed as flexible because objects can carry new properties. However, that flexibility helps only when consumers are configured to handle them.

In Spring Messaging, `MessageConverter` converts serialized payloads into Java types. With a Jackson converter, verify:

- Which converter is used on each endpoint.
- Whether `Content-Type` is accurately set to `application/json`.
- Whether unknown properties are ignored or cause failures.
- Whether missing vs. null is distinguished.
- How unrecognized enum values are handled.
- Whether custom serializers/deserializers alter default behavior.

Spring Framework 6.2 `MappingJackson2MessageConverter` ignores unknown JSON properties by default. However, custom configurations, other converters, or consumers written in other languages may behave differently. Do not extrapolate the behavior of one Spring consumer to the entire system.

New enum values can also break old consumers. Unknown properties and unknown enum values are two different cases. You can design enums with a fallback value such as `UNKNOWN`, or use strings and map to domain enums with controlled logic. Do not rely on `FAIL_ON_UNKNOWN_PROPERTIES` to handle enums.

### Protocol Buffers

For Protobuf binary wire format:

- Each field has a unique field number; this number is the wire identifier and must never change once the message type is in use.
- Adding a new field is generally safe if you use a previously unused number and old consumers handle unknown fields properly in their runtime.
- When removing a field, you must reserve its field number; you should also reserve its field name to prevent accidental reuse and keep JSON/TextFormat safe.
- Never reuse a removed field number.
- Avoid changing a field's type in place. Some type pairs share conditionally compatible wire representations, yet can still cause data loss or break application code.
- Adding an enum value may be wire-compatible, yet still break consumer code that has exhaustive switches or lacks a fallback branch.

Example:

~~~protobuf
syntax = "proto3";

message PaymentAuthorized {
  string payment_id = 1;
  int64 amount_minor_units = 2;
  string currency = 3;

  // Removed legacy field; do not reuse field number 4 or this name.
  reserved 4;
  reserved "legacy_amount";
}
~~~

These rules apply to the binary wire format. ProtoJSON and TextFormat have their own compatibility rules; field names and enum names are represented in JSON, so renaming can still have an impact even when binary field numbers stay unchanged.

Refer to [Protocol Buffers: Updating A Message Type](https://protobuf.dev/programming-guides/proto3/#updating) and [Proto Best Practices](https://protobuf.dev/programming-guides/dos-donts/).

### Apache Avro

Avro supports schema resolution between the writer schema and the reader schema. When a consumer reads a record written with an older schema, the new reader schema can add a field if that field has a default. The default value is used when the writer schema lacks the corresponding field.

Example adding the `currency` field:

~~~json
{
  "type": "record",
  "name": "PaymentAuthorized",
  "fields": [
    { "name": "paymentId", "type": "string" },
    { "name": "amountMinorUnits", "type": "long" },
    {
      "name": "currency",
      "type": ["null", "string"],
      "default": null
    }
  ]
}
~~~

With nullable unions, place the `null` branch first if the default is `null`. A default in Avro is a read-time rule when the reader has a field absent from the writer schema; it does not mean a producer is allowed to omit the field when writing if the writer schema requires it.

When removing a field, the new reader schema can simply omit a field present in the old writer schema. When renaming, aliases map old names to new names. Avro also allows specific type promotions such as `int` to `long`, `float`, or `double`, and `float` to `double`; not all type changes are valid.

Refer to [Apache Avro Specification](https://avro.apache.org/docs/current/specification/), especially the sections on schema resolution, field defaults, aliases, and type promotion.

## 9. Schema Registry and Compatibility Checks

If your system uses a schema registry, choose a compatibility mode matching how producers and consumers are deployed:

- **BACKWARD:** consumers using the new schema can read data from the immediately preceding schema.
- **BACKWARD_TRANSITIVE:** new consumers can read data from all previously registered schemas.
- **FORWARD:** old consumers can read data produced with the new schema.
- **FORWARD_TRANSITIVE:** all old consumer schemas are checked against the new schema.
- **FULL:** backward and forward compatible with the immediately preceding version.
- **FULL_TRANSITIVE:** backward and forward compatible with all prior versions.
- **NONE:** no compatibility checks performed.

For example, Confluent Schema Registry defaults to `BACKWARD` rather than `BACKWARD_TRANSITIVE`. Rules differ across Avro, Protobuf, and JSON Schema. For JSON Schema in particular, behavior also depends on open/closed content models and compatibility policies. See [Confluent Schema Evolution and Compatibility](https://docs.confluent.io/platform/current/schema-registry/fundamentals/schema-evolution.html).

A registry checks only the schema rules it understands. It does not know every consumer's business logic, cannot guarantee units of measurement did not change, and does not replace contract tests. Combine registry checks with real producer/consumer testing.

## 10. Rolling Out via the Expand-Contract Pattern

For systems with multiple instances or independent deployments, evolve contracts in multiple steps.

### When Adding a Field

1. Design the new field as optional during the transition period; clearly define the default or missing-value handling.
2. Deploy new consumers first so they can read both old and new messages.
3. Confirm whether old consumers ignore the new field. If old consumers are strict, upgrade them before producers start sending the new field.
4. Begin having producers populate the new field.
5. Monitor the rate of messages containing the new field and deserialization errors.
6. Only after all producers/consumers have migrated should you consider tightening validation.

### When Removing a Field

1. Stop using the old field in consumer logic.
2. Deploy consumers that can handle messages with or without the field.
3. Stop emitting the old field from producers.
4. Wait out the retention and replay window of old messages, or ensure old schemas remain supported.
5. Remove the field from schemas/DTOs once no consumers or historical data dependencies remain.

### When Changing Type or Meaning

1. Keep the old field intact.
2. Add a new field with a different name and the new type/meaning.
3. Upgrade consumers to read the new field, falling back to the old field.
4. Upgrade producers to dual-write or migrate in cohorts.
5. Reconcile data between both fields and resolve discrepancies.
6. Retire the old field after all consumers and replay pipelines have migrated.

This pattern is commonly called expand-contract: expand the contract so both versions coexist, gradually migrate producers and consumers, and only then contract and clean up the old field.

## 11. Compatibility Testing

Every contract change should have a test matrix. Do not test only the new DTO against the new payload.

| Producer | Consumer | Scenario to Verify |
|---|---|---|
| V1 | V1 | Existing behavior remains unchanged |
| V1 | V2 | New consumer can read old messages |
| V2 | V1 | Old consumer can handle new messages if forward compatibility is required |
| V2 | V2 | New behavior matches the contract |

The test suite should include:

- Payloads missing the new field.
- Payloads containing the new field with a valid value.
- Payloads with the new field set to `null`.
- Payloads with unknown fields not declared by the consumer.
- New enum values.
- Minimum/maximum numeric values, overflow, and precision.
- Field renames with both old and new names present.
- Stored messages from older schemas being replayed.
- Invalid types or malformed formats rejected in a controlled manner.
- The application's actual custom `ObjectMapper` or converter.

Save representative payloads from previous versions as test fixtures. Whenever DTOs or schemas change, rerun all those fixtures against the new consumer. If using a schema registry, include compatibility checks in CI before registering a new schema.

## 12. Common Mistakes

- **Adding a required field immediately:** new consumers cannot read messages produced by old producers.
- **Assuming every consumer ignores unknown fields:** Jackson, Protobuf, JSON Schema, and hand-rolled consumers follow different rules.
- **Confusing missing with null or zero:** default values can corrupt business logic.
- **Removing a field before upgrading consumers:** old consumers may still require that field.
- **Changing a type in place:** producers and consumers running different versions will interpret the same key as different types.
- **Renaming without alias/dual-write support:** old consumers fail to recognize the new name.
- **Testing only the new schema:** misses historical messages or older producers.
- **Believing a schema registry guarantees everything:** a registry does not verify business semantics or all runtime behaviors.
- **Deleting a field and reusing its identifier:** in Protobuf, reusing a field number can cause data to be decoded incorrectly.

## 13. Pre-Release Checklist

- [ ] Identified which consumers read the message and which producers write it.
- [ ] Determined whether backward, forward, or full compatibility is required.
- [ ] Verified serialization format and converter version.
- [ ] New fields have clear missing/null/default rules.
- [ ] Tested whether old consumers can handle new fields.
- [ ] Removed fields have zero remaining users and a plan for historical messages.
- [ ] Type or semantic changes use a new field or a new event version as needed.
- [ ] Removed Protobuf field numbers are reserved.
- [ ] Avro defaults/aliases align with the reader schema.
- [ ] Schema Registry compatibility checks and contract tests have passed.
- [ ] Dual-read/dual-write plan and timeline for removing the old field are defined.
- [ ] Metrics/logs monitor deserialization errors and message rates by schema version.

## References

- [Spring Framework — MessageConverter API](https://docs.spring.io/spring-framework/docs/6.2.0-M6/javadoc-api/org/springframework/messaging/converter/MessageConverter.html): payload conversion and the role of content type.
- [Spring Framework — MappingJackson2MessageConverter](https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/messaging/converter/MappingJackson2MessageConverter.html): Jackson 2 configuration and handling unknown properties.
- [Protocol Buffers — Proto3 Language Guide](https://protobuf.dev/programming-guides/proto3/): field numbers, unknown fields, adding/removing fields, and wire compatibility.
- [Protocol Buffers — Best Practices](https://protobuf.dev/programming-guides/dos-donts/): avoiding field type changes and rules for deletion.
- [Apache Avro — Specification](https://avro.apache.org/docs/current/specification/): schema resolution, defaults, aliases, and type promotion.
- [Confluent — Schema Evolution and Compatibility](https://docs.confluent.io/platform/current/schema-registry/fundamentals/schema-evolution.html): backward, forward, full, and transitive compatibility.
