# Changing Field Types Can Break Compatibility

## 1. Why Is Changing a Field Type Risky?

In **SPRING_GRPC**, a Protobuf schema is the binary contract between clients, servers, and intermediary components. A released field may be used simultaneously by multiple application versions; old payloads may also sit in databases, event logs, queues, or backups.

Changing a field's type can cause the parser to misread bytes, skip the field, throw a parse error, or produce a value that is valid in Java yet wrong in business meaning. In particular, **two types sharing the same wire type are still not guaranteed to be compatible**: the wire type only describes how the parser locates and frames the data bytes, without guaranteeing identical encoding or value ranges.

This lesson focuses on wire types, type pairs sharing a wire type with different semantics, cardinality/presence changes, migrating via new field numbers, and testing between old and new schemas.

## 2. Wire Types Tell the Parser How to Read Data

Binary Protobuf does not write Java type names or field names into tags. Every field begins with a tag:

```text
tag = (field_number << 3) | wire_type
```

`field_number` identifies the field; `wire_type` tells how to read the value portion. Common wire types:

| Wire type | Value structure | Commonly used types |
| --- | --- | --- |
| 0 — Varint | Variable-length integer | `int32`, `int64`, `uint32`, `uint64`, `sint32`, `sint64`, `bool`, enum |
| 1 — 64-bit | Fixed 8 bytes | `fixed64`, `sfixed64`, `double` |
| 2 — Length-delimited | Length followed by a byte sequence | `string`, `bytes`, embedded message, packed repeated scalar |
| 5 — 32-bit | Fixed 4 bytes | `fixed32`, `sfixed32`, `float` |

Wire types 3 and 4 were used for groups in legacy Protobuf; do not choose groups for new schemas.

Types in the same row only share how data is framed on the wire. The parser knows how long the value region is, but how those bytes are interpreted into a value is still governed by the field type.

For instance, `float` and `fixed32` both use wire type 5. Both occupy 4 bytes, yet `float` interprets them according to IEEE 754, whereas `fixed32` interprets them as an unsigned 32-bit integer. Same byte length does not mean same value.

## 3. Same Wire Type Does Not Mean Same Semantics

Several pairs of types share a wire type yet cannot be swapped arbitrarily:

| Old type | New type | Same wire type? | Main risk |
| --- | --- | --- | --- |
| `int32` | `sint32` | Yes, varint | `sint32` uses ZigZag encoding; negative values are encoded differently |
| `int32` | `uint32` | Yes, varint | Signed/unsigned ranges differ; negative and large values can be misinterpreted |
| `int32` | `bool` | Yes, varint | Integer interpreted as false/true; any non-zero value becomes true |
| `int32` | enum | Yes, varint | Numeric value may not belong to enum; generated API and semantics differ |
| `float` | `fixed32` | Yes, 32-bit | IEEE 754 bit pattern is read as an integer |
| `double` | `fixed64` | Yes, 64-bit | IEEE 754 bit pattern is read as an integer |
| `string` | `bytes` | Yes, length-delimited | UTF-8 strings and arbitrary byte sequences follow different rules |
| `string` | embedded message | Yes, length-delimited | Text bytes are parsed as message tags/fields |
| `bytes` | embedded message | Yes, length-delimited | Byte payload may not be a valid message or may carry another schema |

For changes such as `int32` to `int64`, the wire type remains varint and some values can still be read. However, the value range changes; data exceeding the old type's range cannot be fully represented by old clients. Negative values, numeric bounds, and behavior across all consumer versions must be evaluated.

**Never use "same wire type" as the sole criterion for approving a type change.** Specific encoding, value range, presence, cardinality, and business meaning must all be considered.

## 4. Example: Changing int32 to sint32 Corrupts Negative Numbers

Schema v1:

```proto
syntax = "proto3";

package telemetry.v1;

message Reading {
  int32 offset = 1;
}
```

Schema v2 if changed in place:

```proto
syntax = "proto3";

package telemetry.v1;

message Reading {
  sint32 offset = 1;
}
```

Both fields use wire type 0, but their encodings differ:

- `int32` uses varint with standard Protobuf integer representation; negative numbers typically require long encodings.
- `sint32` uses ZigZag to map negative and positive numbers to smaller non-negative integers before varint encoding.
- When one version parses bytes produced by the other, the parser applies decoding rules for the type it knows.

Therefore, identical field number and wire type do not guarantee negative numbers keep their values. If data can be negative, silent corruption can occur even though the message parses successfully.

Similarly, changing `float` to `fixed32` can turn a value like 1.5 into a huge integer when interpreted as a raw bit pattern. Changing `string` to `bytes` can alter UTF-8 validation and generated APIs. These changes must be treated as breaking changes in a released contract.

## 5. Different Wire Types Usually Prevent Fields from Being Read as Expected

If the new type has a different wire type, the parser does not automatically convert values to the new type.

For example, the old schema has:

```proto
message Product {
  int32 quantity = 1;
}
```

If the new schema changes `quantity` to `string` while keeping number 1, the wire type changes from varint to length-delimited. Old and new clients have no automatic rule converting an integer into a string. Depending on the payload and parser, the field may be treated as unknown or parsing may fail due to structural mismatch.

Do not rely on unknown-field handling as a migration mechanism. Just because a parser skips a field does not mean the consumer preserves business behavior; critical values can silently vanish from the application API.

If a type change is intentional, add a new field with a new number and keep the old field during a transition period. Do not change the type of a field actively used by clients, servers, or stored data.

## 6. Cardinality and Packed Encoding Are Also Part of the Contract

Changing from a singular scalar to `repeated`, or vice versa, is not merely a Java type change.

Example:

```proto
// Old schema
message Score {
  int32 value = 1;
}
```

```proto
// New schema
message Score {
  repeated int32 value = 1;
}
```

For repeated numeric fields, Protobuf can use packed encoding: multiple values placed inside a single length-delimited payload. Protobuf parsers support packed/unpacked for packable repeated scalar types according to standard rules, but that does not make cardinality changes fully compatible.

Risks:

- New clients read old scalar payloads as a single-element list, while new logic may expect multiple values.
- Old clients reading multiple unpacked occurrences of a scalar field may retain only the last value.
- Old clients cannot interpret a packed list as an ordinary scalar merely by sharing the same field number.
- The generated Java API changes from a scalar getter to a list getter; source code must change.

`map<K,V>` is likewise encoded as repeated entry messages. Changing between maps, repeated messages, and scalars may retain some length-delimited framing while changing semantics and APIs. Treat cardinality/map changes as contract changes requiring separate migration.

## 7. Presence, Enum, and Oneof

### Presence

Switching between implicit-presence scalars and explicit-presence scalars may not change the wire tag, yet it changes how the application distinguishes an omitted field from a field carrying the default value. For example, `optional int32 count` exposes presence APIs such as `hasCount()`, whereas a non-optional proto3 scalar typically only returns 0 from its getter when unset.

If business logic relies on `hasX()`, changing presence can alter behavior even though the payload still parses.

### Enum

Enums use varint. Changing an enum field to `int32` or vice versa may keep the wire type while altering the generated API and handling of unknown numeric values. In Java Protobuf, enums can have the `UNRECOGNIZED` sentinel; code must handle that branch rather than assuming every number maps to a known enum constant.

Do not turn an enum into a numeric type just to make it "easier to extend." If new values are needed, consider adding new enum values with unused numbers and checking old client logic.

### Oneof

Moving a field into or out of a `oneof` changes semantics regarding whether fields can coexist. Binary payloads may still parse, but generated APIs and active-selection state change. Never alter `oneof` membership without checking existing data where multiple fields appear together and how different versions process them.

## 8. Generated Java API and Domain Semantics

Even when binary payloads parse, changing types can still break source compatibility:

- Getters/setters change return or parameter types.
- `string`/`bytes` expose different Java APIs (`String` vs. `ByteString`).
- Converting a scalar to a list changes getter structure.
- Converting an enum to an integer loses enum-specific APIs.
- Optional/presence introduces or alters presence-checking methods.

Beyond generated APIs, a new type can alter business meaning. For example, changing `quantity` from `int32` to `string` to accept values like `"unknown"` mixes numeric data with textual status. A domain model may need to represent known and unknown quantities explicitly via a message/`oneof` or separate status field rather than resorting to strings for convenience.

At the Spring service boundary, gateways/endpoints should map Protobuf DTOs to domain models. That helps applications enforce validation and fallbacks, though an adapter cannot fix a wire contract whose meaning was corrupted if old data was already misparsed.

## 9. How to Change Types Safely Using a New Field Number

Suppose an old field is `int32 quantity = 4`, and the new version needs to support larger values. Do not change number 4 directly to `int64` if the contract has been released and all consumers must be protected.

You can add a new field:

```proto
message InventoryItem {
  string sku = 1;

  int32 quantity = 4 [deprecated = true];
  int64 quantity_v2 = 7;
}
```

A migration path:

1. **Extend the schema:** add the new field with a never-used number; retain the old field.
2. **Upgrade servers:** read old and new fields using clear precedence rules; during transition, optionally write both when values fit within the old field's range.
3. **Upgrade clients:** read the new field first; fall back to the old field when old servers do not yet provide the new field.
4. **Verify data:** determine whether old values fit within the new domain and convert losslessly.
5. **Migrate consumers:** update all clients, batch jobs, event consumers, and persistence adapters.
6. **Stop writing the old field:** only after confirming no consumer still depends on it.
7. **Remove the old field and reserve its number/name:** do so in a separate schema change after the transition period.

If both fields appear in a request, define clear precedence or reject conflicting values. Do not let individual server replicas apply different rules. For responses, dual-write both fields only when they express the exact same meaning and conversion is lossless.

If new data cannot be represented in the old field, do not force new values into the old field via truncation, saturation, or fake strings. Keep both fields side by side until all consumers have migrated.

## 10. Testing Compatibility Between Old and New Schemas

Maintain generated sources or contract artifacts from schema v1 as fixtures. Do not simply compile schema v2 and test client v2 against server v2; that fails to test versions currently live in production.

A test suite should cover:

| Test | What to verify |
| --- | --- |
| v1 serialize → v2 parse | New server/client reads old payloads using the designed fallback |
| v2 serialize → v1 parse | Old consumer does not fail unexpectedly; new field follows compatibility policy |
| Old client → new server | Existing RPCs and request/response semantics remain intact |
| New client → old server | New client handles absent/default fields and older capabilities |
| Boundary values | 0, negative numbers, min/max, values exceeding old bounds, empty string/bytes |
| Repeated/oneof/presence | No dropped elements or unintended selection changes |
| Stored payload fixtures | Persisted data remains readable or migrates cleanly |

Example message-level test when transitioning from schema v1 to v2 with a new field:

```java
// Generated types v1 and v2 are placed in separate fixtures/modules.
InventoryItemV1 oldItem = InventoryItemV1.newBuilder()
    .setSku("SKU-100")
    .setQuantity(120)
    .build();

byte[] payload = oldItem.toByteArray();

InventoryItemV2 newItem = InventoryItemV2.parseFrom(payload);

assertEquals("SKU-100", newItem.getSku());
// quantity_v2 is absent in the old payload; the application must fall back
// to quantity according to the migration policy.
```

This is an illustrative example; the v2 adapter must apply the fallback from `quantity` to `quantity_v2` itself if required. The Protobuf parser does not automatically copy values between two fields with different numbers.

For type changes on the same field number, write tests explicitly demonstrating how old and new parsers interpret payloads; if results violate semantics, treat the change as incompatible and move to a new field number.

## 11. Using Schema Compatibility Checks in CI

`protoc` validates syntax and certain schema conflicts, but cannot infer whether every change corrupts business logic. A new schema will still compile cleanly even if you change `int32` to `sint32`, `float` to `fixed32`, or alter a field's semantics.

CI should include:

- Schema linting to enforce field, type, and naming conventions.
- Breaking-change detection against the released schema baseline.
- Generated code compilation across client/server modules.
- Tests running against fixtures serialized from old schemas.
- Integration tests covering critical version combinations.
- Mandatory review whenever field numbers, types, cardinality, or presence change.

Tools like Buf can run linting and breaking checks:

```bash
buf lint
buf breaking --against ".git#branch=main"
```

Rule sets must match your system's policy. A wire-compatibility-oriented rule set may allow certain same-wire-type changes, whereas stricter rule sets also check source/API compatibility. Inspect which rules are enabled; never treat a pass result as proof that business semantics remain unchanged.

## 12. Review Checklist When Changing Field Types

- Is the old field number preserved only when type and semantics are genuinely unchanged?
- What are the wire types before and after?
- If the wire type is the same, is the exact encoding identical?
- Have value ranges, signedness, precision, and validation changed?
- Have cardinality, packed behavior, presence, or `oneof` membership changed?
- Do generated Java APIs change types or method names?
- Are there JSON, reflection, `FieldMask`, database, or event log consumers depending on the schema?
- Have payloads from the old schema been used as test fixtures?
- If semantics must change, does the new field use a new number?
- Are migration, fallbacks, dual-read/write, and conflict-handling rules clearly defined?
- Will the old field's number/name be reserved once retired?
- Does CI run schema compatibility checks against the released baseline?

With **SPRING_GRPC**, field type changes cannot be evaluated solely by whether two types share a wire type. Wire type determines how bytes are framed and read; encoding, value range, presence, cardinality, and semantics determine whether the data stays correct. When changing meaning or data type is necessary, adding a new field number, migrating in phases, and testing against released schemas protect clients and servers running mismatched versions.
