# Field Renaming and Wire Compatibility

## 1. Does Renaming a Field Change Data on the Wire?

In **SPRING_GRPC**, Protobuf schemas are used to generate Java messages, client stubs, and APIs for inter-service communication. When a field needs to be renamed for clarity, the key question is whether that change prevents clients and servers running different versions from exchanging binary messages.

For **binary Protobuf**, field names are not written into tags on the wire. A tag is built from the field number and wire type. Therefore, if you only rename a field while keeping the same field number, data type, and encoding semantics, binary payloads can still be read by clients and servers using the previous schema.

However, renaming can still break other surfaces:

- The generated Java API renames getters, setters, builder methods, and constants.
- Protobuf JSON by default uses the field name converted to lowerCamelCase.
- Descriptors/reflection and tools relying on field names see the new identifier.
- `FieldMask` paths, TextFormat, mappings, validation rules, and API documentation may reference the old name.

Hence, you must distinguish **binary wire compatibility** from **source/API compatibility and JSON compatibility**. This lesson focuses on controlled renaming, preserving the wire format, and identifying contracts that depend on field names.

## 2. Why Does Binary Protobuf Not Depend on Field Names?

In binary encoding, each field is written with a tag:

```text
tag = (field_number << 3) | wire_type
```

Example old schema:

```proto
syntax = "proto3";

package catalog.v1;

option java_multiple_files = true;
option java_package = "dev.example.catalog.v1";

message Product {
  string sku = 1;
  string display_name = 2;
  int64 price_cents = 3;
}
```

The new schema renames `display_name` to `label`, while keeping the same number and type:

```proto
syntax = "proto3";

package catalog.v1;

option java_multiple_files = true;
option java_package = "dev.example.catalog.v1";

message Product {
  string sku = 1;
  string label = 2;
  int64 price_cents = 3;
}
```

In both schemas, field number 2 has the length-delimited wire type because it is a `string`. The payload for field 2 still has the same tag and encoding. A v1 client can parse payloads created by a v2 server and read the value via `getDisplayName()`; a v2 client can parse payloads created by a v1 server and read the same bytes via `getLabel()`.

Conditions for this conclusion to hold:

- Preserve the field number.
- Preserve the field's type and encoding rules.
- Preserve cardinality, presence semantics, and data meaning.
- Do not change message/package/service wire identity in other ways.
- Do not modify other fields in the same batch in ways that affect compatibility.

Renaming a field alone does not change the tag. If you simultaneously change `string` to another type, change `repeated`/`optional`, modify `oneof`, or alter semantics, evaluate each change separately. Do not use "renaming does not change the wire" to justify a larger schema change.

## 3. Example with Old Client and New Server

Suppose client v1 is generated from the schema containing field `display_name`. Old Java code:

```java
Product product = catalogStub.getProduct(
    GetProductRequest.newBuilder()
        .setSku("SKU-100")
        .build()
);

String displayName = product.getDisplayName();
```

Server v2 is generated from the schema containing field `label`:

```java
Product product = Product.newBuilder()
    .setSku("SKU-100")
    .setLabel("Wireless keyboard")
    .setPriceCents(4900)
    .build();

responseObserver.onNext(product);
responseObserver.onCompleted();
```

Because field 2 is still a `string`, client v1 parses the response and `getDisplayName()` receives `"Wireless keyboard"`. Likewise, server v2 can parse requests/messages created by client v1 as long as the relevant fields keep their wire contract.

This is compatibility at the **binary serialization layer**. Client v1 does not need code regeneration just to parse messages with the renamed field, though client v1's source code cannot call `getLabel()` because the old generated API lacks that method.

In tests, two versions of a generated class normally share the same fully qualified Java class name if they share the same `java_package` and message name. To run both simultaneously in one test suite, place the old and new fixtures in two separate Java modules/packages or use separate artifacts/classloaders; keep the Protobuf `package` and field numbers identical so wire identity is tested accurately.

## 4. Generated Java API Is Still a Source-Breaking Change

The Protobuf compiler generates Java methods based on field names. Changing:

```proto
string display_name = 2;
```

to:

```proto
string label = 2;
```

changes the generated API from methods such as:

- `getDisplayName()`
- `setDisplayName(...)`
- `clearDisplayName()`
- `hasDisplayName()` if the field has presence

to the corresponding methods with `Label`.

Modules compiling directly against the new generated source must update import usage and method calls. Therefore, a change can be **wire-compatible yet not source-compatible**.

This matters when publishing a shared contract JAR:

- Applications that have not upgraded the JAR version continue compiling with the old API.
- Applications upgrading the JAR must update code calling getters/setters.
- Do not publish a new contract artifact without announcing that the generated API changed.
- If multiple teams consume the contract, provide versioning and a source-code migration guide.

Generated Java names can change even while the binary payload remains compatible. These two concepts must be evaluated independently during review.

## 5. Protobuf JSON Can Break on Rename

Binary tags do not contain field names, but Protobuf JSON uses field names. Under the default mapping, snake_case names in `.proto` are converted to lowerCamelCase during JSON serialization.

Example old field:

```proto
message Product {
  string display_name = 2;
}
```

Serialized JSON typically looks like:

```json
{
  "displayName": "Wireless keyboard"
}
```

After renaming to `label`, default JSON becomes:

```json
{
  "label": "Wireless keyboard"
}
```

A REST consumer, gateway, frontend, or JSON fixture expecting `displayName` can break, even though binary gRPC clients still parse successfully.

### Keeping the Old JSON Key Using json_name

If you must rename a field in `.proto` while preserving the published JSON name, explicitly declare `json_name`:

```proto
message Product {
  string label = 2 [json_name = "displayName"];
}
```

When using the standard Protobuf JSON printer, the field is still emitted under the key `displayName`. The JSON parser also accepts the configured JSON name according to Protobuf JSON mapping rules. Test with actual parsers/gateways, especially if the system uses custom transcoding or a non-standard Protobuf JSON serializer.

`json_name` only controls the JSON name; it does not restore the generated Java method `getDisplayName()` and does not change the field name in descriptors. Nor does it make a custom REST consumer automatically support both old and new aliases.

If an API previously enabled preserving proto field names instead of lowerCamelCase, check the exact published JSON key and preserve that key with the appropriate configuration. Do not assume the old JSON key was always lowerCamelCase.

## 6. Reserve the Old Name After Renaming

After changing a field identifier, reserve the old name to prevent another field from accidentally reusing that name in the future. The new field retains number 2, while the old name is reserved:

```proto
message Product {
  string sku = 1;
  string label = 2;
  int64 price_cents = 3;

  reserved "display_name";
}
```

This is valid: `label` continues using number 2; the name `display_name` is reserved so it cannot be assigned to another field later.

Do not reserve number 2 in this example, because number 2 still belongs to `label`. Only reserve a number when that field number has been completely removed from the message. Key rule to remember:

| Change | Appropriate reservation |
| --- | --- |
| Rename field, keep number | Reserve old name |
| Remove field, no replacement | Reserve old number and name |
| Remove enum value | Reserve enum number and name |
| Remove `oneof` member | Reserve number and name at message level |

Reserving the old name protects the schema source. It does not keep the old generated API and does not preserve the old JSON key automatically; to preserve the JSON contract, use `json_name` and test separately.

## 7. Other Contracts Relying on Field Names

Beyond binary format and generated Java APIs, field names may be used in many places:

| Component | Impact of rename | Action required |
| --- | --- | --- |
| Protobuf descriptor/reflection | `FieldDescriptor.getName()` returns new name | Update name-based lookup code |
| Protobuf JSON | Default JSON key may change | Use `json_name` if key must be kept |
| FieldMask | Paths reference field names | Update paths and test mapping |
| TextFormat/TextProto | Field name in text representation changes | Update text fixtures/configs |
| Gateway/OpenAPI | Property names may change | Regenerate specs and check consumers |
| Validation/mapping rules | Rules may reference field names | Update annotations/configs after codegen |
| Logs, metrics, audit mappings | Labels/tags may rely on descriptor names | Review dashboards and queries |

### Paying Attention to FieldMask

`FieldMask` represents a list of field paths to read or update. If a client sends the path `display_name` while the new server only recognizes `label`, name-based `FieldMask` handling logic may stop matching.

If an API exposes `FieldMask` publicly, plan to translate old paths to new paths during a compatibility period, or maintain an adapter accepting both forms. Do not assume a binary message containing a `FieldMask` automatically maps old names to new names.

## 8. Renaming Fields Inside a oneof

Renaming a member inside a `oneof` also does not change binary tags if the number and type remain the same. However, the generated Java API for the `oneof` changes the corresponding method names and case enum.

Example:

```proto
message PaymentMethod {
  oneof method {
    string card_token = 1;
    string bank_account = 2;
  }
}
```

If `card_token` is renamed to `card_credential` while keeping number 1:

```proto
message PaymentMethod {
  oneof method {
    string card_credential = 1;
    string bank_account = 2;
  }

  reserved "card_token";
}
```

Both old and new binary clients can still read tag 1 with the same wire encoding. However, the old Java API has `getCardToken()` and the old `METHOD` case; the new generated API uses `CardCredential` accordingly. Reflection code, JSON mapping, and validation must also be updated.

If a field in a `oneof` is completely removed rather than renamed, reserve both its number and name at the message level. If it is only renamed while keeping its field number, reserve the old name but do not reserve the number still in use.

## 9. Safe Renaming Process

Before renaming a field in a released contract:

1. **Identify all consumers:** Java clients, services in other languages, gateways, JSON/REST, `FieldMask`, reflection, and text-based data.
2. **Preserve wire identity:** do not change field number, type, cardinality, presence, or semantics.
3. **Update the identifier in `.proto`:** apply the new name and reserve the old name.
4. **Preserve JSON key if needed:** set `json_name` to the previously published JSON key.
5. **Regenerate code:** compile modules using the new contract and update getters/setters.
6. **Check non-upgraded consumers:** use old generated clients to parse binary messages from the new server and vice versa.
7. **Test JSON/FieldMask:** confirm keys and paths are handled according to your compatibility policy.
8. **Controlled release:** announce the source API change, bump contract artifacts, and update consumers on schedule.
9. **Monitor post-rollout:** watch parse errors, JSON mapping errors, and failures from mismatched paths/names.

If the goal is merely improving naming in internal code, consider keeping the `.proto` field name unchanged and creating an adapter/domain property with the desired name. That avoids altering generated APIs and public JSON contracts.

## 10. Testing Wire Compatibility Between Old and New Schemas

Do not merely compile the new schema. Keep generated types from both versions and test actual bytes:

- Build a message using generated class v1, serialize it, and parse it using generated class v2.
- Build a message using generated class v2, serialize it, and parse it using generated class v1.
- Assert that the corresponding field number still carries the same data.
- Verify the JSON printer/parser with the published key.
- Test `FieldMask` and descriptor-based mappings if the application uses them.
- Run integration tests through a gRPC server/client to verify service paths and serialization end-to-end.

Binary message-level example:

```java
// ProductV1 has getDisplayName(); ProductV2 has getLabel().
// Both generated types are built in separate fixtures/modules.

ProductV1 oldMessage = ProductV1.newBuilder()
    .setSku("SKU-100")
    .setDisplayName("Wireless keyboard")
    .build();

byte[] bytes = oldMessage.toByteArray();

ProductV2 newMessage = ProductV2.parseFrom(bytes);

assertEquals("SKU-100", newMessage.getSku());
assertEquals("Wireless keyboard", newMessage.getLabel());
```

Reverse-direction tests are also required: build `ProductV2` with `label`, serialize it, parse it using `ProductV1`, and assert `getDisplayName()` receives the right value. Both schemas must retain the same Protobuf package, message name, field number, and wire type to accurately verify wire identity; separate Java packages/fixture modules can avoid class collisions in tests.

If using a schema compatibility tool, select the appropriate rule set. A rename may not be flagged as binary wire-breaking yet still be flagged under source/JSON compatibility rules. Read the exact breaking-change category reported by the tool rather than relying solely on a coarse pass/fail result.

## 11. Common Mistakes

| Symptom | Cause | Remediation |
| --- | --- | --- |
| Java client fails to compile after upgrading contract JAR | Getters/setters changed with the new field name | Update source or keep old contract version during transition |
| Binary gRPC works but REST client fails | Default JSON key changed | Preserve `json_name` or version the JSON API |
| Reflection lookup cannot find field | Descriptor name changed | Update descriptor-based lookups and rules |
| FieldMask fails to update field | Path still uses old name | Adapt old/new paths and add tests |
| Schema checker reports breaking change | Rule set checks source/JSON names | Clarify compatibility target and document intent |
| Old payloads parse incorrectly | Field number/type was changed alongside rename | Restore wire identity and separate changes |
| Someone creates a field with the old name | Old name was not reserved | Add `reserved "old_name";` |
| Oneof generated API changes case | Member name changed | Update code and test oneof cases |

## 12. Review Checklist

- Field number is preserved.
- Data type and wire encoding are unchanged.
- Cardinality, presence, and semantics are unchanged.
- Old name is reserved if the field identifier changed.
- Number still in use by the renamed field is not reserved.
- JSON key is preserved via `json_name` if required by the API.
- Generated Java consumers are updated or covered by a versioning plan.
- `FieldMask`, reflection, TextFormat, gateways, and validation rules have been reviewed.
- Bidirectional tests exist between old and new generated schemas.
- Schema compatibility checker ran with the appropriate rule set.

With **SPRING_GRPC**, renaming a field can preserve binary wire compatibility when the field number, type, and semantics stay the same. However, generated Java APIs, JSON mappings, and name-based contracts can still change. Reviews must evaluate each surface independently, use `reserved` for the old identifier, and test with generated code from previously released versions.
