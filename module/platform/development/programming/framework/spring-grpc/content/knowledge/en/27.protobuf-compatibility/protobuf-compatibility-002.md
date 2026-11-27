# Never Reusing Removed Field Numbers

## 1. Why Must Removed Field Numbers Be Retained?

In **SPRING_GRPC**, a Protobuf schema is the wire contract between clients, servers, and intermediary components. Versions may be deployed at different times; old payloads can also persist in databases, event logs, caches, backups, or message queues long after a field has been removed from source code.

When removing a field, **you must never reuse its field number for another field in the same message**. If reused, payloads serialized with the old schema can be interpreted by the new schema as data for the new field. When the two fields share the same wire type, parsing may succeed while carrying the wrong meaning, making data corruption hard to detect.

For example: the old version used field number 4 for display name; the new version removes that field and reuses number 4 for payment reference. An old payload still contains the display name string at tag 4. When reading that payload with the new schema, that string may be interpreted as a payment reference. The parser does not necessarily report an error because the binary structure remains valid.

This lesson focuses on:

- The relationship between field numbers, wire types, and payload decoding.
- The risks of reusing numbers, even when wire types are compatible.
- How to declare `reserved` for removed fields and enum values.
- The scope of reserved declarations and what they do not protect against.
- Effects on stored payloads, rolling deployments, JSON mapping, and generated code.
- Testing to prevent new schemas from reusing old field numbers.

## 2. Field Numbers Are Part of the Wire Contract

Protobuf binary format does not transmit field names. Each field is encoded as a tag with the form:

```text
tag = (field_number << 3) | wire_type
```

`field_number` identifies the field within the message; `wire_type` tells the parser how to read the value according to wire structure. Field names are not included in binary tags, so renaming a field does not change the tag as long as the number is preserved.

Example version 1 schema:

```proto
syntax = "proto3";

package billing.v1;

message Invoice {
  string invoice_id = 1;
  string display_name = 4;
  int64 amount_cents = 5;
}
```

Server v1 can serialize an `Invoice` containing `display_name` into a tag carrying field number 4. The name `display_name` is not written into the binary payload; the tag only carries the number and wire type.

Field numbers are scoped **within each individual message**. Number 4 in `Invoice` is not the same field as number 4 in `Customer`. When removing a field, you must reserve the number in the exact message where that field was declared.

Several notes regarding field numbers:

- Valid field numbers range from 1 to 536,870,911.
- The range 19,000 through 19,999 is reserved by Protobuf for internal implementation; do not use it for fields.
- Numbers 1 through 15 have shorter tag encodings, but optimizing size is not a reason to change already-released numbers.
- Field numbers and wire semantics must be treated as long-term stable once a schema has been used to exchange or store data.

## 3. Reusing Numbers Can Cause Data Misinterpretation

Suppose version 2 deletes `display_name` and reuses number 4:

```proto
syntax = "proto3";

package billing.v1;

message Invoice {
  string invoice_id = 1;
  string payment_reference = 4;
  int64 amount_cents = 5;
}
```

Both `display_name` and `payment_reference` are `string`, so they share the length-delimited wire type. An old payload containing `display_name = "Priority customer"` can be read by the new schema's parser as:

```java
Invoice invoice = Invoice.parseFrom(oldPayload);

String reference = invoice.getPaymentReference();
// May receive "Priority customer" from a payload created under the old schema.
```

This is a dangerous bug because:

- Parsing can succeed.
- The getter returns a value that looks valid for its data type.
- The application might write the old string into a database column or forward it as a payment reference.
- The bug only appears with old payloads, so tests using newly constructed messages may miss it.

If a number is reused with a different wire type, the parser may treat that tag as unknown, skip it, or fail depending on the structure and field type. Regardless of the exact runtime behavior, reusing a number breaks the contract and is never considered compatible.

**Do not rely on changing the type to make an old number "safe."** Some types share the same wire type with different semantics; other cases may be handled by the parser as unknown instead of raising an error. The safe rule is to never reuse a released number.

## 4. Using reserved to Lock Removed Field Numbers and Names

After removing a field from a message, add a reserved declaration directly inside that message:

```proto
syntax = "proto3";

package billing.v1;

message Invoice {
  string invoice_id = 1;
  int64 amount_cents = 5;

  reserved 4;
  reserved "display_name";
}
```

If someone accidentally declares field number 4 or the name `display_name` again in message `Invoice`, `protoc` will fail with a schema error. This turns the "do not reuse" rule into a build-time verifiable constraint.

You can reserve multiple numbers or a range:

```proto
message Invoice {
  string invoice_id = 1;

  reserved 4, 7, 9 to 12;
  reserved "display_name", "legacy_note";
}
```

The range `9 to 12` is inclusive on both ends. You can use `to max` when you want to reserve from a number up to the maximum valid field number, though only do so when you genuinely intend to close off the remainder of the number range.

You should reserve both:

- **Number:** prevents old binary data from being interpreted as a new field.
- **Name:** prevents reusing removed names in schemas, generated APIs, and tools that rely on field names.

Both kinds of reservations serve different purposes; reserving a name does not replace reserving a number.

## 5. What Does a Reserved Declaration Protect and Not Protect?

`reserved` is a schema/compiler-level rule. It causes `protoc` to reject a new schema if a reserved number or name is reused within the same message. It does not alter old payloads, delete stored data, or prevent a program from manually constructing binary tags.

Therefore, you should combine:

1. Reserved declarations in `.proto`.
2. Schema compatibility checks in CI.
3. Tests parsing data serialized from previously released schemas.
4. Schema change review processes.
5. Version management of contract artifacts and generated code.

Reserved declarations are locally scoped. For instance, `Invoice` reserving number 4 does not forbid `Customer` from using number 4; the two messages have separate wire schemas. Conversely, if the same field number was previously used across multiple different messages, reservations must be managed separately in each message.

Do not remove a reserved declaration just because several releases have passed. Old payloads may remain in backups or be restored months or years later. When data retention has no guaranteed upper bound, reservations should likewise be kept indefinitely.

## 6. Enum Values Must Not Reuse Removed Numbers Either

Protobuf enums also have numeric values on the wire. If you delete an enum value and reassign its number to a different meaning, old clients or stored data may interpret the old numeric value as the new state.

Example old schema:

```proto
enum PaymentState {
  PAYMENT_STATE_UNSPECIFIED = 0;
  PAYMENT_STATE_PENDING = 1;
  PAYMENT_STATE_LEGACY_REVIEW = 4;
}
```

If value 4 is no longer used, the new schema should reserve both the number and the name:

```proto
enum PaymentState {
  PAYMENT_STATE_UNSPECIFIED = 0;
  PAYMENT_STATE_PENDING = 1;

  reserved 4;
  reserved "PAYMENT_STATE_LEGACY_REVIEW";
}
```

Do not assign number 4 to `PAYMENT_STATE_REFUNDED`. If an old payload contains numeric value 4, a new client could misinterpret a legacy review state as refunded.

This rule applies specifically to enums: use `reserved` inside the enum declaration. Reservations on a message do not automatically reserve numeric values of nested or referenced enums.

## 7. Removing Fields in oneof, Renaming, and JSON Mapping

### 7.1. Fields Previously Inside a oneof

If you remove a member from a `oneof`, you must still reserve that member's field number and name on the enclosing message:

```proto
message PaymentMethod {
  oneof method {
    string card_token = 1;
    string bank_account = 2;
  }

  reserved 3;
  reserved "legacy_wallet_token";
}
```

In this example, number 3 and the name `legacy_wallet_token` were a removed member. The reservation is placed at the message level, not inside the `oneof` block.

Old clients may still send the removed member in payloads. The new server will no longer have generated APIs to access that member; the field becomes unknown. Do not reuse that member's number for another `oneof` option, because old payloads could be interpreted as the new option.

### 7.2. Renaming a Field While Keeping Its Number

Renaming a field in `.proto` while keeping its number usually preserves binary compatibility, since names are not part of tags. However, renaming can affect:

- Getter/setter names in generated Java APIs.
- Property names when serializing to Protobuf JSON.
- Clients using reflection, descriptors, or name-based mapping.
- Documentation and code referencing field names directly.

If you only want a source-level rename, evaluate JSON/API surfaces before making the change. If the field has been completely removed, reserve the old name along with the old number to prevent unintentional reuse.

### 7.3. JSON Does Not Follow the Same Rules as Binary Tags

Protobuf JSON represents fields using JSON names, typically the lowerCamelCase form of the field name or the name specified in `json_name`. Consequently, renaming can change the JSON contract even if the binary field number remains unchanged.

Reserved names help prevent reusing removed names in the schema, but they do not automatically guarantee compatibility across every JSON gateway, mapper, or API consumer. If messages pass through REST transcoding, test the JSON contract separately.

## 8. Old Payloads Can Outlive Service Lifecycles

Running clients are not the only places holding data encoded with old schemas. A Protobuf payload may reside in:

- BLOBs/byte arrays in a database.
- Event stores or audit logs.
- Kafka, message brokers, or dead-letter queues.
- Caches, export files, and backups.
- Batch jobs or data restored from snapshots.

A new service may read these bytes long after the field has been removed from `.proto`. Therefore, "all replicas have been upgraded" is not sufficient justification to reuse a number.

If old data must be purged, a dedicated migration is required: identify all data sources, convert using the old schema, verify results, and manage backup/retention. Even when primary data has been migrated, old backups may still be restored in the future. Reserving numbers is how you keep the schema safe against those payloads.

## 9. Testing to Detect Field Number Reuse

### 9.1. Keeping Old Schemas as Fixtures

CI should maintain a fixture or v1 contract module containing previously released schemas. When schema v2 is updated:

1. Serialize a message using schema v1 containing the field about to be removed.
2. Parse the payload using schema v2.
3. Verify that the old field is not mistakenly assigned to any new field.
4. Check that schema v2 reserves the removed number/name.
5. Run schema breaking checks to catch incompatible changes.

Illustrative message-level test example:

```java
// Generated types are placed in two separate fixture packages/modules.
InvoiceV1 oldInvoice = InvoiceV1.newBuilder()
    .setInvoiceId("INV-42")
    .setDisplayName("Priority customer")
    .setAmountCents(2500)
    .build();

byte[] oldPayload = oldInvoice.toByteArray();

InvoiceV2 parsed = InvoiceV2.parseFrom(oldPayload);

assertEquals("INV-42", parsed.getInvoiceId());
assertEquals(2500, parsed.getAmountCents());

// Schema V2 no longer has display_name and does not reuse number 4.
// Number 4 is reserved, so no payment_reference receives the old string.
```

The example assumes v1/v2 generated types are created in different packages to avoid colliding fully qualified class names. If v2 reuses number 4 with a string type, the test can catch old data appearing in the new field's getter; however, you should not rely solely on runtime tests. `protoc` itself must reject schemas containing reserved numbers.

### 9.2. Schema Checks in CI

A pipeline can perform these steps:

- Compile all `.proto` files with the exact `protoc` version.
- Run a schema linter to enforce field/enum conventions and reservations.
- Compare the new schema against the released baseline using a compatibility checker tool.
- Run tests against serialized fixtures from old schemas.
- Generate Java sources and compile client/server modules that depend on the contract.

Tools such as Buf can assist with linting and breaking-change detection. Configure baselines and rule sets to match your organization's compatibility policy; do not assume every default rule set catches every application-specific data requirement.

## 10. Safe Field Removal Process

When a field is no longer needed:

1. **Identify usage scope:** locate clients/servers, consumers, persistence layers, and pipelines still reading or writing the field.
2. **Stop business dependency:** deploy code that no longer requires the field before removing it from the schema if older versions are still active.
3. **Remove the field from the message:** do not change the numbers of other fields.
4. **Reserve the number and name:** add `reserved` in the exact message.
5. **For enums:** reserve the removed numeric value and enum name inside that enum itself.
6. **Generate and verify code:** run `protoc` and compile contract/client/server modules.
7. **Test old payloads:** parse fixtures from previous schemas with the new schema.
8. **Roll out:** deploy in a compatible order, monitoring parse errors and business behavior.
9. **Keep reservations:** do not delete reservations in future releases simply because the field no longer appears in current code.

If you need to replace a field, it is usually best to add a new field with a new number, deploy logic that reads both old and new formats during a transition period, migrate data, and then remove the old field and reserve its number/name. Do not "change meaning in place" by reusing the number.

## 11. Common Mistakes

| Change | Risk | Remediation |
| --- | --- | --- |
| Removing a field without reserving its number | Someone may reuse the number in the future | Reserve the number immediately in the same message |
| Reserving only the name | Old number can still be reused and misinterpret payloads | Reserve both number and name |
| Reusing a number with the same wire type | Old payloads may parse into the new field with wrong meaning | Use a new number; keep the reservation |
| Changing field type while keeping the number | Parser may misread semantics or skip/error depending on wire type | Never change released types/numbers |
| Removing an enum value without reserving it | Old numeric value may take on a new enum meaning | Reserve the enum number and name |
| Removing a oneof member and reusing its number | Old payloads may be interpreted as the new option | Reserve at the message level |
| Testing only the new schema | Fails to detect old data being misinterpreted | Maintain serialized fixtures/baseline schemas |
| Deleting reservations after a few releases | Backups or old events may still contain the tag | Keep reservations long-term |

## 12. Checklist Before Merging Schema Changes

- Removed field number is reserved in the exact message.
- Removed field name is also reserved.
- Removed enum number and enum name are reserved in the corresponding enum.
- Removed `oneof` member is reserved at the message level.
- No new field reuses any previously released number.
- Remaining fields keep their numbers, wire semantics, and business meanings.
- Tests parsing v1 payloads with generated v2 types have passed.
- Schema lint/breaking checks ran against the proper baseline.
- JSON mapping and API gateways have been verified if used.
- Reservations are preserved in the schema across subsequent releases.

In **SPRING_GRPC**, field numbers are a permanent part of the binary contract. Removing a field from source code does not make old payloads disappear. Keeping removed numbers and names in `reserved`, testing with data from previous schemas, and maintaining schema checks in CI prevent old data from being misinterpreted as a new field with the wrong meaning.
