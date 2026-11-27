# Changing Published Field Numbers

## 1. Field numbers are part of the wire contract

In **SPRING_GRPC**, Protocol Buffers define the request and response structure across client/server versions. Each field in a message has a name, a data type, and a field number. When serializing to binary, Protobuf does not send field names; it writes the field number together with the wire type into a tag so the parser can identify the data.

Example:

```proto
message Order {
  string order_id = 1;
  int64 total_cents = 2;
  string customer_id = 3;
}
```

If `order_id` is changed from field number `1` to `4`, the new code still compiles and may work when both client and server are built from the new schema. However, binary payloads sent by older clients still carry tag number `1`. The new server will not read those bytes into field `order_id` at number `4`; it may treat them as an unknown field and return an empty/default `order_id`. Conversely, when the new server sends field `4`, older clients do not recognize that field.

This is a wire-format compatibility bug, not a Java naming issue. **A published field number is the long-lived identifier of a field in the binary contract. Never change numbers and never reuse deleted numbers.**

## 2. Wire tags consist of field number and wire type

Each field is encoded with a tag:

```text
tag = (field_number << 3) | wire_type
```

The wire type tells the parser how to read the payload bytes that follow, for example:

| Wire type | Common data types |
| ---: | --- |
| 0 | varint: int32, int64, bool, enum |
| 1 | fixed 64-bit: fixed64, double, sfixed64 |
| 2 | length-delimited: string, bytes, embedded message, packed repeated |
| 5 | fixed 32-bit: fixed32, float, sfixed32 |

Field names do not appear in binary tags. The parser relies on the field number to find the corresponding field in the schema and the wire type to read the bytes.

When a field number changes, the parser no longer maps old data to the new field even if the data type stays the same. When changing the data type at the same field number, the wire type may change or semantics may diverge even if the wire type happens to match. Both cases require compatibility review.

## 3. Example failure when changing a field number

Published schema:

```proto
message CreateOrderRequest {
  string customer_id = 1;
  int64 amount_cents = 2;
}
```

A later version changes the field number:

```proto
message CreateOrderRequest {
  string customer_id = 7;
  int64 amount_cents = 2;
}
```

Older clients serialize `customer_id` with field number `1`. The new server only declares `customer_id` at number `7`, so number `1` data is not assigned to `customer_id`. When a new client sends number `7` to an older server, the older server does not recognize that field either.

The consequence may not be an obvious parse error. Protobuf typically ignores unknown fields at the application layer, causing requests to be processed with default values. For `customer_id`, `amount`, `account_id`, or access permissions, this bug can lead to corrupted business data or hard-to-spot failures.

Do not judge compatibility solely by whether new code compiles or tests pass between two processes on the same version. You must test communication between old and new schemas in both directions: old client / new server and new client / old server.

## 4. Do not reuse deleted field numbers

Suppose an older schema once had:

```proto
message Customer {
  string customer_id = 1;
  string legacy_code = 2;
  string display_name = 3;
}
```

After removing `legacy_code`, number `2` must not be assigned to another field such as `phone_number`. Older clients may still send field `2` containing `legacy_code` data. The new server would interpret those bytes as `phone_number` if the wire types are compatible, causing data misinterpretation.

The right approach is to reserve the deleted number and name:

```proto
message Customer {
  string customer_id = 1;
  string display_name = 3;

  reserved 2;
  reserved "legacy_code";
}
```

`reserved` protects future schemas from accidentally reusing old numbers or names. It does not make the new server automatically understand old data; it only prevents conflicting reuse. Published fields should be treated as immutable history.

If multiple fields are removed, you can reserve a range:

```proto
message Customer {
  string customer_id = 1;
  reserved 2 to 5;
  reserved "legacy_code", "old_phone", "old_status";
}
```

Field names should also be reserved because ProtoJSON and some tooling/schema mappings use field names, even though the binary wire format relies primarily on numbers.

## 5. Rules for assigning field numbers from the start

Choose numbers deliberately before publishing:

- Use lower numbers for frequently populated fields if compact encoding is desired; field numbers 1 through 15 have shorter tags.
- Reserve ranges by group if the schema follows clear conventions, without leaving arbitrarily huge gaps.
- Avoid the range `19000` to `19999`, as Protobuf reserves it for its own implementation.
- The maximum valid field number is `2^29 - 1`.
- Never use negative numbers.
- Never change numbers after a schema has been used by clients/servers.
- Clearly mark deprecated fields and reserve them upon removal.

Smaller field numbers save a byte or two on tags; this is a secondary optimization compared to contract stability. Never renumber published fields just to tidy up schema layout.

## 6. Renaming a field vs. changing its field number

Renaming a field while keeping the same number is usually binary wire-compatible:

```proto
// Version 1
message Order {
  string customer_id = 1;
}

// Version 2
message Order {
  string buyer_id = 1;
}
```

Binary payloads still carry field number `1`, and Protobuf servers/clients can read the same wire data. However, renaming can break ProtoJSON, generated source APIs, reflection, descriptor-based tooling, or code accessing fields by name.

Therefore, renaming is not always safe. If the API is consumed via ProtoJSON, REST transcoding, dynamic messages, JSON configs, or generated clients, check JSON names (including `json_name`), field names, and consumer migration.

Never change a field number just because you want to rename it for better terminology. If only a rename is needed, preserve the number and separately evaluate name-based contracts.

## 7. Data type changes cannot be judged by wire type alone

Some Protobuf types share a wire type, but that does not mean changing between them is semantically compatible.

For example, `int32`, `int64`, `uint32`, `uint64`, and `bool` all use the varint wire type. Changing `int32` to `int64` allows the parser to read wire bytes, yet values, ranges, sign semantics, and client behavior can differ. `string` and embedded messages are both length-delimited, yet their bytes cannot be arbitrarily reinterpreted as each other.

Changes requiring careful review:

- `int32` to `int64`: compatible wire type, but semantics/range change.
- `string` to `bytes`: same length-delimited wire type, but API and validation differ.
- `message A` to `message B`: same wire type, but inner fields may be misinterpreted.
- `singular` to `repeated`: encoding/semantics may change; do not assume compatibility.
- `packed`/`unpacked` repeated numeric fields: Protobuf supports some compatibility forms, but generated/runtime behavior and schema policy must be verified.
- `map` and repeated entry messages: wire representation follows specific rules; changes still require semantic checks.

Do not change a type at a published field number simply because a compatibility checker does not flag it as breaking. Wire-level compatibility does not guarantee application semantics.

## 8. Add a new field instead of changing an old field number

If new data must be added, use a previously unused field number:

```proto
message CreateOrderRequest {
  string customer_id = 1;
  int64 amount_cents = 2;
  string source_channel = 3;
}
```

Older clients do not send `source_channel`; the new server receives the default value per Protobuf semantics. Newer clients send `source_channel`; older servers do not recognize this field and usually ignore it at the application layer. This additive evolution is generally wire-compatible, but is only safe if the server has sensible default behavior and does not require older clients to send the new field.

When adding a field:

- Choose a new field number.
- Explicitly define default/absence semantics.
- Do not make the new server strictly depend on a field that older clients do not send.
- Check authorization, validation, and business behavior when the field is absent.
- Ensure proxies/adapters do not drop unknown fields if messages must be forwarded.

Adding a field does not automatically guarantee compatible API behavior. If the new field alters the meaning of the operation, a new RPC/version may be required.

## 9. Migration when a field truly must be replaced

You cannot change the number of an active field in place. Add a new field and transition gradually:

Transitional schema:

```proto
message Customer {
  string customer_id = 1;

  string legacy_reference = 2 [deprecated = true];
  string external_reference = 7;
}
```

A controlled rollout plan:

1. Add `external_reference` with a new number; keep `legacy_reference`.
2. Deploy servers that read both fields with clear precedence rules.
3. Servers may temporarily write both fields if older clients must be supported; ensure they stay consistent.
4. Deploy new clients reading/writing the new field.
5. Monitor usage of the old field and client versions still sending it.
6. Once no old consumers remain, stop writing the old field and deprecate/remove it per policy.
7. Remove the old field from the schema in a later release and reserve the old number/name.

Dual-writing should only be a time-boxed migration step. Writing two fields without a single source of truth or synchronization rule allows data to drift. Define which field is authoritative, how discrepancies are handled, and when dual-writing stops.

## 10. Rolling deployments and upgrade order

In multi-replica environments, client and server versions do not change simultaneously. A deployment can have old clients calling new servers, or new clients calling old servers.

When adding a new field with compatible default behavior:

- New servers can usually handle requests from old clients.
- New clients can send the new field to old servers; the field may be ignored.
- If a new client requires the server to understand that field to behave correctly, you cannot rely on unknown-field behavior; capability negotiation or a new API version is required.

When making incompatible semantic changes, roll out via expand-and-contract:

1. Expand the schema/server to support both old and new contracts.
2. Deploy new consumers/clients.
3. Shift traffic and monitor usage.
4. Contract by retiring the old field/API once zero consumers are confirmed.
5. Only then remove and reserve the old field.

Never deploy new clients that require a new field before all servers support those semantics.

## 11. Unknown fields and proxies/adapters

Protobuf binary payloads can carry unknown fields that the current schema does not yet recognize. Parsers typically retain unknown fields in the generated message's `UnknownFieldSet`, but certain conversions can strip them, such as:

- Mapping a message to a DTO/domain object and constructing a new message solely from known fields.
- Converting through JSON without preserving unknown fields.
- Using custom serializers that only copy declared fields.
- Building a new message from scratch instead of modifying a builder from the original message.

If a gateway or service only acts as a proxy and must forward future data, test unknown-field preservation. If a service is a business boundary, dropping unknown fields may be intentional; do not assume preservation is always required.

Unknown-field preservation cannot rescue field number reuse. If the same number is reassigned a new meaning, old bytes may be misinterpreted as the new data rather than treated as unknown.

## 12. Field numbers in nested messages, `oneof`, and `map`

Field numbers are scoped to each message, not the entire `.proto` file. Two distinct messages can both use number `1` without conflict:

```proto
message Customer {
  string id = 1;
}

message Order {
  string id = 1;
  Customer customer = 2;
}
```

However, within the same message, numbers must be unique and never reused after deletion.

With `oneof`, each member still has its own field number within the enclosing message; never reuse deleted member numbers. With `map`, Protobuf encodes a map as a repeated entry message; the field number of the `map` field in the parent message remains an identifier that must stay stable.

Do not move a field from one message to another assuming its old number follows automatically. The wire path changes with nested structure; compatibility must be evaluated across the entire message hierarchy.

## 13. Testing schema compatibility

Do not only compile `.proto` files and run unit tests on the same version. Check compatibility across schema versions:

| Test | What to verify |
| --- | --- |
| v1 payload read by v2 code | Old fields still map accurately |
| v2 payload read by v1 code | New fields handled safely as unknown/default |
| Old client calls new server | Request retains intended meaning |
| New client calls old server | Does not depend on fields old server ignores |
| Rename keeping number | Binary still parses; ProtoJSON/source API reviewed |
| Delete field | Number and name are reserved |
| Enum/field evolution | Numbers are never reused |
| Proxy forwards message | Unknown fields preserved if required |
| Rolling deploy | Mixed versions operate per compatibility matrix |

Store golden binary fixtures from published schemas. When upgrading the compiler/runtime or schema, read old fixtures with newly generated code and vice versa when feasible.

Use Buf breaking change detection or an equivalent tool in CI to block schema changes that break compatibility. Tools must be configured with the proper baseline/version; they help catch structural changes, but do not replace semantic reviews and runtime tests.

## 14. Review checklist

- Published field numbers are never changed.
- Deleted field numbers are never reused.
- Deleted fields declare both `reserved` number and `reserved` name.
- Range `19000`–`19999` is not used.
- Field numbers are chosen within Protobuf limits.
- New fields are added with new numbers and clear default/absence semantics.
- Types at the same number are never changed without compatibility review.
- Renames preserve numbers while checking ProtoJSON, reflection, and generated source APIs.
- Migrations use expand-and-contract; dual-writes have a source of truth and an end date.
- Rolling deployments support mixed client/server versions.
- Proxy preservation of unknown fields is tested if needed.
- Buf breaking checks and golden wire compatibility tests are in place.
- New RPCs/versions are created when semantics cannot remain compatible.

In **SPRING_GRPC**, changing a published field number alters the wire tag that clients and servers use to identify data, causing older or newer payloads to be ignored or misinterpreted. Keep numbers immutable, reserve numbers and names upon deletion, and add new fields when extending contracts. When semantics must change incompatibly, use expand-and-contract or version the API; verify with compatibility checks and cross-version client/server tests.
