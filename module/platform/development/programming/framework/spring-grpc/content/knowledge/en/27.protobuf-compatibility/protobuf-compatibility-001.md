# Adding a New Field That Old Clients Can Still Read

## 1. Compatibility Challenges When Extending Protobuf

In a **SPRING_GRPC** system, clients and servers may be built, deployed, and upgraded at different times. A new server may run alongside old clients for some time; multiple replicas may also not switch to the same version simultaneously. Therefore, extending a Protocol Buffers contract must ensure that new messages are still parsed correctly by old clients.

A common change is **adding a new field to a message**. If the new field uses a field number that has never been used before, old clients can read the fields they know and ignore the unknown field. This is the foundation of binary compatibility when evolving Protobuf schemas.

This lesson focuses on:

- Why field numbers and wire types determine how Protobuf reads messages.
- How to add a field to a response so old clients continue reading existing fields.
- Default values and field presence on new clients when interacting with old servers.
- Differences between adding a field to a request versus a response.
- Changes that appear compatible on the surface but can corrupt data semantics.
- Rollout order, testing with old generated clients, and limitations when going through JSON/API gateways.

## 2. Field Numbers Are Identifiers on the Wire

Protobuf does not send field names in binary messages. Each field is encoded with a tag containing the **field number** and **wire type**. Names like `product_name` primarily serve source code, descriptors, and JSON mapping; the field number is the identifier used to decode the binary payload.

Example initial schema:

```proto
syntax = "proto3";

package catalog.v1;

option java_multiple_files = true;
option java_package = "dev.example.catalog.v1";

message ProductReply {
  string sku = 1;
  string name = 2;
}
```

Suppose the new version needs to add a product category:

```proto
syntax = "proto3";

package catalog.v1;

option java_multiple_files = true;
option java_package = "dev.example.catalog.v1";

message ProductReply {
  string sku = 1;
  string name = 2;
  string category = 3;
}
```

The field `category = 3` has a new field number. Old clients generated from the first schema only know fields 1 and 2. When parsing the binary payload from the new server:

1. The client receives the tag for field 1 and reads `sku`.
2. The client receives the tag for field 2 and reads `name`.
3. The client encounters the tag for field 3, which is not defined in the old generated code.
4. The Protobuf runtime recognizes this as an unknown field and skips its value when constructing the object according to the old schema.

Result: the old client can still read `sku` and `name`; it cannot access `category` through the old generated API, but the new field does not shift or corrupt the positions of existing fields.

**Never add a field by reusing a number that was previously used.** Field numbers are part of the wire contract and must be managed for the long term.

## 3. How Are Unknown Fields Handled?

A message parsed by an old schema may contain fields that the schema does not yet know about. Protobuf calls these **unknown fields**.

With binary Protobuf, the generated runtime is typically able to skip unknown fields and continue reading known fields. In Java Protobuf, unknown fields are usually retained in the message's unknown fields section and can be re-serialized. However, applications should not assume that unknown fields always survive every processing step.

Unknown fields can be lost if the application:

- Converts the Protobuf message into another DTO and then reconstructs a new message from only the known fields.
- Converts through JSON or an intermediate format that does not preserve unknown fields.
- Uses a manual mapper that only copies properties present in the old model.
- Builds a new message from a builder instead of re-serializing the parsed message.

Therefore, if a component acts as a proxy and must forward fields it does not yet understand intact, verify the parse/serialize behavior of the exact Protobuf runtime and the entire path. **The fact that old clients can read old fields does not mean every intermediary preserves new fields.**

## 4. Old Clients Reading Responses from a New Server

This is the most direct scenario for this topic. The new server returns an additional field in the response; the old client only reads the fields present in the schema it was compiled against.

Suppose server v2 returns:

```json
{
  "sku": "SKU-100",
  "name": "Wireless keyboard",
  "category": "ACCESSORY"
}
```

On the wire, the payload is binary Protobuf rather than the JSON above. The JSON only helps visualize the contents. A v1 client generated from the schema without `category` parses the two familiar fields and ignores field number 3.

Example old client code:

```java
ProductReply reply = catalogStub.getProduct(
    ProductRequest.newBuilder()
        .setSku("SKU-100")
        .build()
);

String sku = reply.getSku();
String name = reply.getName();

// Generated client v1 does not have getCategory().
System.out.println(sku + " - " + name);
```

The old client does not need source code changes or code regeneration to continue reading the two existing fields, provided the server preserves their semantics and field numbers.

This also means the old client **cannot use new features** that rely on `category`. If the application requires the category to make business decisions, a compatible fallback is needed, or new clients must be deployed before making that data mandatory.

## 5. Adding Fields to Requests vs. Responses Has Different Compatibility Directions

Adding a field to either a request or a response can be binary-compatible if a new field number is used, but the behavior between old and new versions differs:

| Version combination | What happens to the new field |
| --- | --- |
| Old client → new server, new field is in request | Client does not send the field; new server receives default value/no presence |
| New client → old server, new field is in request | Old server does not know the field and ignores it |
| New server → old client, new field is in response | Old client ignores the unknown field and reads the old fields |
| Old server → new client, new field is in response | New client does not receive the field; getter returns default value or reports absent depending on field type |

Therefore, "wire-compatible" does not mean "the new feature works across all version combinations."

For example, a new client sends `include_stock=true` in the request, but an old server ignores that field. The RPC may still parse successfully, yet the old server does not fulfill the include-stock request. If the client depends on that behavior, it must check whether the server supports it before enabling the feature.

When adding a field to a response, old servers do not know about the new field and cannot return it. New clients must handle the absent/default case until all required servers have been upgraded.

## 6. Default Values and Field Presence in proto3

When a new client receives a message from an old server, the new field does not appear on the wire. How the client observes that field depends on the field type and presence rules.

### 6.1. Scalars Without optional

With proto3 implicit presence, scalar fields such as `string`, `bool`, and `int32` have default values when omitted:

| Type | Default getter value |
| --- | --- |
| `string` | Empty string |
| `bool` | `false` |
| `int32`, `int64` | `0` |
| `float`, `double` | `0.0` |
| enum | First enum value with number 0 |

Example:

```proto
message ProductReply {
  string sku = 1;
  string category = 3;
  bool discontinued = 4;
}
```

If an old server only sends `sku`, the new client receives an empty string from `getCategory()` and `false` from `getDiscontinued()`. The application must treat those values as valid fallbacks, not interpret them as data explicitly sent by the old server.

### 6.2. Using optional When Distinguishing Absent from Default

If you need to distinguish between "the server did not provide the field" and "the server explicitly provided an empty string," declare `optional`:

```proto
message ProductReply {
  string sku = 1;
  optional string category = 3;
}
```

The generated Java API supports checking presence, for example:

```java
if (reply.hasCategory()) {
    useCategory(reply.getCategory());
} else {
    useLegacyCategoryFallback();
}
```

With proto3 implicit-presence scalars, you cannot reliably distinguish an omitted field from a field sent with its default value through the getter alone. `optional` adds presence tracking. For message fields, repeated fields, and map fields, presence/default rules differ; check the corresponding generated API rather than assuming every field has `hasX()`.

If the new field affects business decisions, clearly design the semantics of absent, empty, and default before releasing.

## 7. Rules for Ensuring a New Field Is Truly Compatible

When adding a field, follow these rules:

1. **Choose a field number that has never been used.** Do not reuse the number of a deleted or renamed field.
2. **Preserve the field number and meaning of old fields.** Do not change the data semantics while keeping the same tag.
3. **Choose the appropriate data type.** Some types share the same wire type but are interpreted differently; do not change a type merely because the parser can read the bytes.
4. **Ensure default values have safe meanings.** Old clients/servers do not send the new field; newer versions must handle that situation.
5. **Do not add proto2 `required` fields.** Old senders do not send the new field, and messages may fail initialization requirements.
6. **Ensure old clients can ignore the field and still process old fields properly.** Do not alter existing semantics in a way that depends on the new field.
7. **Test paths through intermediaries.** Proxies or adapters may parse and rebuild messages, losing unknown fields.

Field numbers 1 through 15 generally have shorter tag encodings, making them suitable for frequently occurring fields during initial schema design. When adding a field to an already released schema, the higher priority is using a new, valid, never-used number; do not change old numbers just to optimize size.

## 8. Removing Old Fields and Reserved Numbers

When a field is no longer used, do not delete it and reuse its number for a new field. Old binary payloads may still contain that tag; clients or servers on another version may interpret the tag with its old meaning and misinterpret the data.

For example, if field number 2 and the name `legacy_name` have been removed:

```proto
message ProductReply {
  string sku = 1;

  reserved 2;
  reserved "legacy_name";

  string category = 3;
}
```

`reserved` helps the compiler detect if anyone accidentally reuses a removed number or name. Reserve both the number and the name when removing a field from a shared schema.

Renaming a field while keeping the same number is usually compatible with the binary wire format, because names are not sent in binary tags. However, renaming can break JSON field names, generated Java APIs, clients using reflection, or contract documentation. Therefore, renaming should not be treated as a zero-impact change.

## 9. Cases Where Adding a Field Can Cause Problems

### 9.1. Changing Type While Keeping the Number

Do not change an existing field's type just because two types share the same wire type. For example, `int32` and `sint32` both use varint, but `sint32` applies zig-zag encoding; the data may be parsed into a different number. `string` and `bytes` are both length-delimited, yet their meaning and validation differ.

Changing `int32` to `int64` may preserve the wire type, but old clients cannot represent the full new value range. The fact that a wire parser accepts the bytes does not mean the data retains its semantics.

### 9.2. Adding a Member to a oneof

An old client that does not know a new member of a `oneof` may treat that tag as unknown and see no option set through the old oneof API. This can cause the client to handle it as a "no option selected" case, even though the new server actually sent a new option.

If old clients must understand every option, do not add new members expecting them to automatically fall back properly. Explicit unknown/default behavior must be designed.

### 9.3. Adding an Enum Value

In proto3, adding an enum value can be wire-compatible, but old clients may receive an unknown numeric value. In Java generated enums, this case can be represented by `UNRECOGNIZED`; code must avoid calling `getNumber()` on that sentinel and can use the corresponding integer getter to handle unknown values.

If old code has a `switch` or default logic assuming the enum only contains known values, adding an enum value can cause business logic errors even though the message still parses.

### 9.4. JSON Transcoding and External APIs

Binary Protobuf and JSON mapping do not share the same unknown-field behavior across all parsers and gateways. A strict JSON consumer, schema validator, or API gateway may reject the new field even though old gRPC binary clients can still read the response. When gRPC is transcoded to JSON/REST, parser configuration and the public contract must be checked separately.

## 10. Safe Rollout Order

Suppose you want to add `category` to the response of `Catalog.GetProduct`:

1. **Release the new schema:** add the new field number, keeping old fields and the generated package/service unchanged.
2. **Upgrade the server:** the new server can return `category`; the server must still return all old fields with their old semantics.
3. **Test with old clients:** use a generated v1 client to call the v2 server and confirm `sku` and `name` are still read correctly.
4. **Upgrade new clients:** new clients can read `category`, but must handle absent/default when hitting old servers.
5. **Enable logic depending on the new field:** only enable it once the backend provides the data or an appropriate capability/rollout mechanism is in place.
6. **Observe:** monitor parse errors, RPC statuses, absent-field rates, and differences between replicas during the version transition.

If new clients strictly require the `category` value, deploy supporting servers first and verify that all endpoints behind the load balancer have been upgraded. During a rolling deployment, a channel may hit both v1 and v2 servers at the same time; clients must work properly with both.

Do not rely on an application version string as the sole proof that a field is present. If a feature depends on server capability, use a capability RPC, versioned metadata, or a controlled feature flag.

## 11. Testing Compatibility with Old Generated Clients

The most important test for this requirement is **using code generated from the old schema to parse responses produced by the new server**. Simply compiling new clients with the new schema does not test old client compatibility.

Tests can be organized in the following steps:

- Keep a fixture or test module containing generated Java code from schema v1.
- Use schema v2 to construct a response containing the added field.
- Serialize the v2 response into binary bytes.
- Parse the bytes using the generated v1 class.
- Assert that the old fields still have the expected values.
- If testing a proxy is needed, parse and re-serialize using client v1 and verify whether unknown fields are preserved according to the expected runtime/path.

Illustrative message-level test example:

```java
// ProductReplyV2 is the generated type from the new schema.
ProductReplyV2 replyV2 = ProductReplyV2.newBuilder()
    .setSku("SKU-100")
    .setName("Wireless keyboard")
    .setCategory("ACCESSORY")
    .build();

byte[] payload = replyV2.toByteArray();

// ProductReplyV1 is the generated type retained from the old schema.
ProductReplyV1 replyV1 = ProductReplyV1.parseFrom(payload);

assertEquals("SKU-100", replyV1.getSku());
assertEquals("Wireless keyboard", replyV1.getName());
// Schema v1 does not have getCategory(); field 3 is unknown to client v1.
```

The class names `ProductReplyV1` and `ProductReplyV2` here are illustrative. In practice, to avoid two schemas generating the same fully qualified class name, place generated code in separate test modules/packages or use separate fixture artifacts. Do not modify the wire package `catalog.v1` solely to resolve class name collisions in tests without evaluating contract impact.

In addition to message-level tests, include integration tests that invoke real RPCs from client v1 to server v2. Such tests verify serialization, transport, service registration, and generated stub behavior together.

## 12. Checklist Before Releasing a New Schema

- The new field uses a number that has never been used and is not in a reserved range.
- Existing fields retain their numbers, types, and semantics.
- The new field has clear default/presence behavior when either the server or client has not been upgraded.
- Old clients read the new response without errors and still process old fields correctly.
- Old servers ignore the new field in requests without breaking existing business logic.
- New clients have a fallback when old servers do not yet return the new field.
- Do not rely on unknown-field preservation if messages pass through JSON or are mapped to other DTOs.
- Enums, `oneof`, and JSON transcoding have been reviewed if the schema uses those constructs.
- CI includes tests with code generated from the old schema.
- Rolling deployment has been tested with multiple server versions coexisting.

With **SPRING_GRPC**, adding a new field is a schema change that can be deployed safely when new field numbers are properly managed, old clients can skip unknown fields, and all parties preserve the semantics of existing data. Wire compatibility must be verified using generated code from previously released schema versions, not merely by confirming that the new schema compiles cleanly.
