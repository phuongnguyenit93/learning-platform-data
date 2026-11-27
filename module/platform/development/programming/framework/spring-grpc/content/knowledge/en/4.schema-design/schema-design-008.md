# Deleting Fields Safely With `reserved`

When a field in Protocol Buffers is no longer used, simply deleting its declaration line from the `.proto` file is not enough. Published field numbers can still appear in legacy requests, stored records, or replayed events. If another developer later accidentally reuses that number for a different meaning, protobuf can decode old data into a brand-new field without raising an obvious error.

In **Spring gRPC**, this affects both the wire contract and the Java code generated from the schema. The safeguard is the `reserved` keyword, which permanently claims retired field numbers and field names. This lesson covers the syntax, when to apply it, and how to verify safe field deletion.

## 1. Why Must You Reserve After Deletion?

Binary protobuf identifies fields by **field number** and wire type, not by field name. Suppose an older version declares:

```proto
message Product {
  string product_id = 1;
  string display_name = 2;
  string legacy_description = 3;
}
```

After removing `legacy_description`, a newer schema version might look like:

```proto
message Product {
  string product_id = 1;
  string display_name = 2;
}
```

If number 3 is not reserved, someone else might later declare `int64 supplier_id = 3;`. An old client sends `legacy_description` with tag 3; the new server interprets that tag as `supplier_id` if the wire types happen to align. The result can be corrupted data with no obvious parse error.

`reserved` builds a guardrail at schema compilation time: the compiler rejects any reuse of a reserved number or name within the same message. Two things need protection:

- **Field numbers** protect binary protobuf data from being decoded with a new meaning.
- **Field names** protect identifiers in schemas, source code, descriptors, and name-based representations such as ProtoJSON or TextFormat.

Therefore, when removing a published field, the safe rule is to reserve **both its number and its name**.

## 2. `reserved` Syntax in a Message

Place numbers and names in two separate `reserved` statements:

```proto
message Product {
  reserved 3, 7 to 9;
  reserved "legacy_description", "old_price";

  string product_id = 1;
  string display_name = 2;
  string summary = 10;
}
```

In this example:

- `3` is a deleted field number.
- `7 to 9` is a reserved range of numbers; both endpoints are inclusive.
- `legacy_description` and `old_price` are retired field names.
- `summary = 10` uses a fresh, unreserved number.

**Do not mix numbers and names in the same `reserved` statement.** Write one statement for a list of numbers or ranges, and another statement for a list of names. These declarations are scoped to their enclosing message; reserving number 3 in `Product` does not automatically reserve number 3 in any other message.

You can reserve up to the maximum field number with `to max`:

```proto
message LegacyPayload {
  reserved 20 to max;
  reserved "obsolete_value";

  string id = 1;
}
```

Use wide ranges only when all numbers in that range were actually used or genuinely need protection. Do not reserve a range covering active fields, and never delete an in-use field merely to make a `reserved` statement compile.

### Deleting a Field and Replacing It With a New One

If `legacy_description = 3` is replaced by `summary = 10`, the resulting schema must keep the old tag and name reserved:

```proto
message Product {
  reserved 3;
  reserved "legacy_description";

  string product_id = 1;
  string display_name = 2;
  string summary = 10;
}
```

Do not assign number 3 to `summary` just because the old field was removed from source. The entire point of `reserved` is to prevent reusing that number.

## 3. `reserved` for Enum Values

Enums also carry numeric values on the wire. If you delete a published enum value, reserve both its number and its name:

```proto
enum ProductState {
  PRODUCT_STATE_UNSPECIFIED = 0;
  PRODUCT_STATE_ACTIVE = 1;
  PRODUCT_STATE_ARCHIVED = 2;

  reserved 3, 7 to 9;
  reserved "PRODUCT_STATE_LEGACY";
}
```

This example assumes numbers 3 and 7–9 along with the name `PRODUCT_STATE_LEGACY` were previously used before being removed. Never reuse number 2 for a different state just because `PRODUCT_STATE_ARCHIVED` was deleted; that number must remain reserved if it was ever published.

When a Java consumer receives an enum number unknown to its generated code version, proto3 represents it as `UNRECOGNIZED` while still allowing access to the raw integer value. Accordingly, adding new enum values also requires evaluating how older clients behave; `reserved` protects only retired values from reuse.

## 4. Safe Field Deletion Workflow

Never delete a field merely because one code location was updated. First determine who still sends, reads, or persists that field.

1. **Confirm the field's end of life.** Locate all clients, servers, event consumers, stored records, reports, and `FieldMask` paths that still reference the field.
2. **Mark as deprecated if a transition period is needed.** You can use `[deprecated = true]` to warn callers while the field remains declared:

   ```proto
   message Product {
     string legacy_description = 3 [deprecated = true];
   }
   ```

   `deprecated = true` is only a hint to tooling and developers; it does not stop data transmission, delete the field, or prevent code from using it.
3. **Stop writing and migrate consumers.** The server can stop populating the old field once clients read its replacement. If a new replacement field exists, run dual-read/dual-write for a defined transition window and avoid conflicting data sources.
4. **Remove the declaration once no dependencies remain.** Delete the old field from the message or enum after stakeholders have migrated as planned.
5. **Reserve the number and name.** Add `reserved` inside the exact message or enum that contained the deleted field.
6. **Regenerate code and verify.** Update Java handlers, mappers, tests, and consumers; verify the new schema does not accidentally reuse old tags.

If a field was never released externally and no serialized or persisted data exists, deletion can be simpler. For any published contract, however, never infer that a field is unused simply because one repository no longer references it.

## 5. What Does `reserved` Protect—and What Does It Not?

| Case | Does `reserved` help? | Explanation |
| --- | --- | --- |
| A developer adds a new field reusing a reserved number in the same message | **Yes** | `protoc` rejects the schema |
| A developer reuses a reserved field name in the same message | **Yes** | The compiler rejects the reserved name |
| An old client still sends the deleted field's tag to a new server | **Does not block at runtime** | The new server normally treats that tag as an unknown field and ignores it |
| Old data decoded as a new field due to reusing the number in another schema version | **Prevented on the schema that declares `reserved`** | `reserved` is not an arbitrary runtime payload filter |
| A Java client still calls the deleted field's accessor | **Does not auto-fix client code** | Generated APIs drop the accessor; dependent source code must be updated |
| A JSON client still sends the old field name | **Does not guarantee identical JSON parser behavior** | Check ProtoJSON/gateway rules and unknown-key settings separately |

Crucial point: `reserved` is a **schema/compile-time rule**, not a runtime directive causing servers to throw errors on legacy tags. When a new server parses a binary request carrying an old field, that field may simply be treated as unknown. Therefore, if the application needs to detect clients still sending a retired field, put observability or migration tracking in place before deletion; do not expect `reserved` to do that.

In protobuf Java, generated messages have mechanisms to retain unknown fields. However, do not rely on unknown fields surviving every processing layer: converting to other DTOs, rebuilding messages, serializing to JSON, or passing through gateways can drop fields unrecognized by the schema.

## 6. Impact on Spring gRPC and Clients

When a field is deleted from `.proto` and Java code is regenerated:

- Accessors such as `getLegacyDescription()` and builders like `setLegacyDescription(...)` disappear from the newly generated classes. Java modules still calling them fail to compile until updated.
- The new server no longer populates that field in responses. Old clients can still parse remaining fields, though legacy getters may return default values.
- Old clients continue sending the deleted field in binary payloads; the new server may ignore the unknown field. The RPC returning `OK` does not prove the old data was acted upon.
- `FieldMask` paths, DTO mappers, ProtoJSON keys, logs, or event consumers referencing the old name must be migrated separately.

`reserved` does not rename services, RPCs, or packages, nor does it create a new API version. If deleting a field changes behavior that clients rely on, use a transition period or an appropriate API version rather than editing the schema and deploying everything at once.

### Before and After Example

**Before deletion:**

```proto
message Product {
  string product_id = 1;
  string display_name = 2;
  string legacy_description = 3;
}
```

**After deletion:**

```proto
message Product {
  reserved 3;
  reserved "legacy_description";

  string product_id = 1;
  string display_name = 2;
  string summary = 10;
}
```

New clients use `summary`; the server no longer reads or writes `legacy_description`. Old clients must migrate beforehand or remain supported during transition. Number 3 and the old name stay in the schema as reserved so nobody accidentally reuses them.

## 7. Post-Deletion Verification

A schema review should confirm:

- `reserved` resides inside the right message or enum.
- Every deleted field has both its number and name reserved; ranges have exact bounds and do not overlap active fields.
- No active field or enum value collides with a reserved number or name.
- Replacement fields use new numbers rather than reclaiming old tags.
- Related Java accessors, mappers, `FieldMask` paths, and consumers have been updated.
- Old clients sending payloads with the deleted field behave as expected; parsing success is never confused with applying the old data.
- JSON gateways and ProtoJSON have been tested if the API supports them.

Helpful tests:

| Test | What to verify |
| --- | --- |
| Compile the new schema | `protoc` accepts the valid `reserved` declarations |
| Attempt to redeclare a reserved field number | Compiler rejects it |
| Attempt to redeclare a reserved field name | Compiler rejects it |
| Parse a binary fixture from the old schema with the new schema | Remaining fields preserve exact values; old tag is never misread as a new field |
| Call the new server with an old client | RPC exhibits the published transition behavior; old field is never silently interpreted as different data |
| Compile dependent Java modules | No leftover calls to the deleted field's accessors |
| Test ProtoJSON / `FieldMask` | No unintended reliance on the old field name |

There is no need to write tests proving `reserved` rejects old tags at runtime: that is not its job. What you must prove is that the new schema cannot reuse the old number/name and that all places depending on the field have migrated.

## 8. Self-Check

**Question 1.** A published message has `string old_code = 5;`. After deleting this field, what should the new schema declare?

**Answer:** `reserved 5;` and `reserved "old_code";` inside that same message. Never assign number 5 to another field.

**Question 2.** Which numbers are included in `reserved 4 to 8;`?

**Answer:** Both endpoints are inclusive: 4, 5, 6, 7, and 8.

**Question 3.** An old client sends a deleted field number to a new server. Does `reserved` cause the server to automatically return `INVALID_ARGUMENT`?

**Answer:** No. `reserved` prevents future schemas from redeclaring that number or name. The new server typically treats the old tag as an unknown field; detecting old clients still sending it requires dedicated observability or migration tracking.

**Question 4.** Is it possible to reserve only the number without reserving the name?

**Answer:** The syntax allows it, but for published fields you should reserve both the number and the name. The number protects the binary wire format; the name protects against reusing identifiers in schemas and name-based encodings.

**Question 5.** Can a field marked `[deprecated = true]` be deleted immediately?

**Answer:** Do not assume so. `deprecated` is only a warning and does not prove consumers have stopped using the field. Confirm migration is complete first, then delete the declaration and reserve both number and name.

Whenever you delete a published field, leave its footprint behind with `reserved`. This small rule keeps a seemingly harmless schema cleanup today from turning into hard-to-detect data decoding bugs across clients, servers, or consumers tomorrow.
