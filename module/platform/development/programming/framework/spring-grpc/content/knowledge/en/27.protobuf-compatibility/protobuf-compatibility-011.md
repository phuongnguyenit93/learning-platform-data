# Backward Compatibility and Forward Compatibility

## 1. Two Compatibility Directions in Schema Evolution

In **SPRING_GRPC**, clients and servers may be built, released, and deployed at different times. A new server may serve old clients; during a rolling deployment, a new client may also temporarily hit an old server replica. Therefore, evaluating a Protobuf change requires examining both data-reading directions.

Two commonly used concepts:

- **Backward compatibility:** a new reader can read data produced by an old writer. The new version continues understanding old payloads.
- **Forward compatibility:** an old reader can read data produced by a new writer. The old version can skip unfamiliar extensions and still process the familiar data.

In a writer/reader model:

| Direction | Writer | Reader | Question |
| --- | --- | --- | --- |
| Backward | v1 (old) | v2 (new) | Can the new schema read old payloads? |
| Forward | v2 (new) | v1 (old) | Can the old schema handle new payloads? |
| Full compatibility | v1 and v2 in both directions | v1 and v2 | Can versions exchange data in both directions? |

These terms describe the direction of compatibility between writer and reader. They do not by themselves guarantee correct business logic. A payload may parse cleanly while the application misinterprets state, uses an inappropriate default value, or ignores a mandatory requirement.

## 2. Mapping Both Directions onto gRPC Communication

In RPC communication, both client and server act as writers at times and readers at other times:

| Scenario | Writer → Reader | Compatibility direction |
| --- | --- | --- |
| Old client sends request to new server | Request v1 → server v2 | Backward |
| New client sends request to old server | Request v2 → server v1 | Forward |
| Old server returns response to new client | Response v1 → client v2 | Backward |
| New server returns response to old client | Response v2 → client v1 | Forward |

This explains why saying "schema v2 is compatible" is not specific enough. You must specify whether v2 reads v1 payloads, whether v1 reads v2 payloads, and whether you are examining requests or responses.

For example, when adding a new request field:

- Server v2 can accept a v1 request lacking that field: this is backward compatibility.
- Server v1 receives a v2 request containing the new field: the parser normally skips the unknown field; this is forward compatibility at the wire level.
- However, if client v2 requires the new field for the server to execute the right business logic, server v1 skipping that field may return the wrong result. Wire compatibility alone is not enough to allow client v2 to send requests before servers support the feature.

In Spring gRPC deployments, identify the writer/reader direction for each RPC before choosing the rollout order.

## 3. Basic Example: Adding a New Field

Schema v1:

```proto
syntax = "proto3";

package inventory.v1;

message StockRequest {
  string sku = 1;
}

message StockReply {
  string sku = 1;
  int32 available = 2;
}
```

Schema v2 adds an update timestamp:

```proto
syntax = "proto3";

package inventory.v1;

message StockReply {
  string sku = 1;
  int32 available = 2;
  int64 updated_at_epoch_ms = 3;
}
```

**Backward:** reader v2 parses responses created by writer v1. Field number 3 is absent; the generated field takes its default value according to its type and presence rules. The v2 application must account for the timestamp potentially not being provided.

**Forward:** reader v1 parses responses created by writer v2. Field number 3 is unknown to schema v1. The binary parser can skip it and still read `sku` and `available`. Client v1 cannot use the new timestamp, yet can still use the old fields.

This is a common extension pattern, provided:

- Field numbers or wire semantics of existing fields do not change.
- The new field is optional from a compatibility standpoint; old readers do not need it to understand existing fields.
- New readers have clear fallbacks when the new field is absent.
- Producers do not send the new field as a mandatory prerequisite for old consumers.
- Intermediaries and gateways are tested if they parse and rebuild messages.

## 4. How Default Values and Presence Affect Backward Compatibility

When a new reader reads an old payload, the new field is normally omitted. The application observes either a default value or an absent state depending on the field type and declaration.

With proto3 scalars using implicit presence, getters return `0`, `false`, or an empty string when the field was not sent. The application cannot distinguish "old writer did not know the field" from "new writer explicitly sent the default value" from the getter alone.

If distinguishing absent from a default value matters, use explicit presence such as `optional`, a message field, or an appropriate construct like `oneof`.

Example:

```proto
message UpdateStockRequest {
  string sku = 1;
  optional int32 reorder_level = 2;
}
```

The generated Java API can expose a presence accessor such as `hasReorderLevel()`. When a request arrives from an old client, the new server can check whether the field was sent and apply the appropriate policy.

Never treat a default value as a business decision automatically. For example, `reorder_level = 0` might mean "do not restock," whereas an absent field might mean "keep existing configuration." If the two meanings differ, the schema and application mapping must be able to represent the distinction.

## 5. Unknown Fields and the Limits of Forward Compatibility

When an old parser encounters a field number unknown to its schema, the binary Protobuf runtime handles it as an unknown field instead of reading it through a non-existent getter. This lets the parser keep reading known fields.

In Java Protobuf, unknown fields are typically retained inside the message object and can be re-serialized. However, you should not assume unknown data always survives every path:

- Code converting a Protobuf message to a DTO and building a new message can drop unknown fields.
- Manual mappers copying only known fields will lose extensions.
- Gateways or intermediaries that parse and serialize via JSON may not retain unknown fields.
- A service converting to an internal model and emitting another message must explicitly decide whether to forward unknown data.

If a service acts as a proxy, relay, or event forwarder, test round-trip behavior using the actual runtime and adapters. Forward compatibility in the parser does not mean every intermediary layer preserves new payloads.

## 6. Changes That Commonly Break Both Directions

Some changes are unsafe even when looking at only backward or forward compatibility:

| Change | Risk |
| --- | --- |
| Reusing a removed field number | Old payloads can be misinterpreted as the new field |
| Changing a field number | Writers and readers associate data with different tags |
| Changing type or encoding in place | Same wire type can still differ in decoding and semantics |
| Changing field meaning while keeping type/number | Parsing succeeds yet business logic misinterprets data |
| Removing an enum number and reassigning it | Old numeric values get interpreted as a different state |
| Moving independent fields into a `oneof` | Old payloads may contain multiple members; new parser keeps only the last |
| Changing service/package/RPC identity | Clients may call a method path that is no longer registered |

When retiring a field, keep the reservation in the exact message:

```proto
message StockReply {
  string sku = 1;
  int32 available = 2;

  reserved 3;
  reserved "legacy_timestamp";
}
```

Never reuse released numbers or names. For enums, reserve numbers and names inside the enum declaration.

## 7. Backward and Forward Compatibility Are Not Behavioral Compatibility

Suppose server v2 adds enum value `ORDER_STATE_REVERSED`. A v1 proto3 client can parse the response, preserve the numeric value, and return `UNRECOGNIZED` via the generated Java enum API. Thus, the payload may be compatible at the wire level. Yet if client v1 maps any status other than `FAILED` to `CONFIRMED`, business logic will fail.

Similarly, client v2 might send `idempotency_key` in a request. Server v1 skips the unknown field and still parses the message. Yet if server v1 lacks idempotency logic, retries can create duplicate orders. Successful parsing does not mean old servers support new semantics.

Therefore, evaluate three distinct layers:

1. **Wire/schema compatibility:** do bytes parse and do old fields preserve their identities?
2. **Application compatibility:** do generated code and mappings handle absent/unknown values safely?
3. **Behavioral compatibility:** do both sides enforce the same business rules?

A change should only be enabled once every layer required for that flow has been verified.

## 8. Choosing Rollout Order Based on Compatibility Direction

Deployment order depends on which side will begin writing new data.

### Case A: New server returns an additional response field

New servers can be deployed first. Old clients usually skip unknown fields; new clients read the field when present. However, new clients need a fallback while still hitting old servers and receiving responses without the field.

### Case B: New client sends a new request field

Deploy servers supporting the new field first. Only enable clients to send the field once every server replica able to receive traffic understands and handles it. If a new client sends the field to an old server, the server may skip the field and execute old behavior.

### Case C: Changing semantics or adding new workflows

Use versioned services/messages or capability negotiation. Servers must advertise support before clients invoke new semantics. Never infer capability merely from a parser accepting a field.

A common rollout sequence:

1. Extend the schema and server code to read both old and new requests.
2. Deploy servers across all replicas.
3. Verify health, metrics, and capability readiness.
4. Release new clients in cohorts, enabling features in a controlled manner.
5. Monitor errors, fallbacks, and emitted data.
6. Retire the old path only once no dependent consumers remain.

## 9. Compatibility Matrix for Rolling Deployments

During a rolling deployment, not every request hits the same version. Build a matrix before releasing:

| Client | Server | Request | Response | Conclusion to verify |
| --- | --- | --- | --- | --- |
| v1 | v1 | v1 ↔ v1 | v1 ↔ v1 | Current baseline |
| v1 | v2 | Old writer → new reader | New writer → old reader | Backward request; forward response |
| v2 | v1 | New writer → old reader | Old writer → new reader | Forward request; backward response |
| v2 | v2 | v2 ↔ v2 | v2 ↔ v2 | Full new behavior |

The matrix shows why testing client v2 against server v2 alone is insufficient. During rollout, v1/v2 pairs coexist. If a combination is unsupported, ensure routing/deployment prevents that pairing or that clients can fall back safely.

For multi-replica services, verify readiness and version distribution before enabling new clients. A single v1 replica still receiving new requests can cause intermittent routing-dependent failures.

## 10. Testing Both Directions with Old and New Generated Code

Keep v1 schemas or generated artifacts as fixtures. Do not merely compile schema v2 and test solely with v2 generated code.

Core tests:

- **Backward:** serialize a v1 message, then parse with generated type v2.
- **Forward:** serialize a v2 message, then parse with generated type v1.
- Test absent/default/presence behavior for new fields.
- Test unknown enum values and new `oneof` members.
- Test unknown-field round-trips through intermediaries if payloads must be preserved.
- Test old client/new server and new client/old server over real gRPC.
- Test boundary values and business semantics, not just asserting that parsing succeeds.

Example message-level test:

```java
// ProductV1 and ProductV2 are generated from two schema fixtures.
ProductV1 oldWriter = ProductV1.newBuilder()
    .setSku("SKU-100")
    .setAvailable(12)
    .build();

byte[] oldPayload = oldWriter.toByteArray();

// Backward: new reader reads old payload.
ProductV2 newReader = ProductV2.parseFrom(oldPayload);
assertEquals("SKU-100", newReader.getSku());
assertEquals(12, newReader.getAvailable());

// Forward: new writer adds a field; old reader still reads familiar fields.
ProductV2 newWriter = ProductV2.newBuilder()
    .setSku("SKU-200")
    .setAvailable(8)
    .setUpdatedAtEpochMs(1730000000000L)
    .build();

ProductV1 oldReader = ProductV1.parseFrom(newWriter.toByteArray());
assertEquals("SKU-200", oldReader.getSku());
assertEquals(8, oldReader.getAvailable());
```

The example assumes v2 adds `updated_at_epoch_ms = 3` and v1 does not declare that field. Place generated fixtures in separate modules or Java packages to avoid colliding fully-qualified class names. Passing parser assertions is only the first step; adapter/service tests must verify defaults, fallbacks, and business outcomes.

## 11. Checking Schemas and Contracts in CI

A pipeline should check both structure and behavior:

- Run formatting and linting across all Protobuf modules.
- Run breaking-change detection against the released baseline.
- Pin versions of `protoc`, plugins, and Buf so results are reproducible.
- Generate Java code and compile client/server modules.
- Run backward and forward tests using generated v1/v2 fixtures.
- Run integration tests for all supported client/server combinations.
- Verify JSON/gateways, `Any`, reflection, and stored payloads if the system uses them.

Rule sets must match the contract. Some rules check wire compatibility, while stricter rules check JSON or source APIs. A passing result cannot prove behavioral compatibility; domain mapping tests and semantic reviews remain necessary.

Baselines must also be accurate: PRs typically compare against the target branch; releases should compare against the schema version actively used by consumers. Never update a baseline simply to bypass an unaddressed breaking change.

## 12. Checklist Before Release

- Writers and readers are identified for each request/response flow.
- Clarified whether the change requires backward, forward, or bidirectional compatibility.
- Existing field numbers and wire semantics remain unchanged.
- New fields have fallbacks when new readers receive old payloads.
- Old readers can skip new fields without breaking business logic.
- Unknown enums/`oneof` members are handled safely.
- Removed field/enum numbers or names are never reused.
- Presence and default values cannot be misinterpreted.
- Intermediaries/proxies have round-trip tests if unknown fields must survive.
- Generated v1/v2 fixtures and bidirectional tests are in place.
- Integration tests cover rolling deployments and all supported version pairings.
- CI breaking checks use the right baseline; generated code compiles cleanly.
- Rollout order aligns with whichever side (client/server) begins writing new data.

With **SPRING_GRPC**, backward compatibility protects new readers receiving old payloads; forward compatibility protects old readers receiving new payloads. In gRPC communication, both directions occur across requests and responses depending on which side writes the data. Schema design must preserve field identities, provide fallbacks for absent/unknown values, and maintain clear semantics; testing all four client/server pairings exposes bugs that only surface during rolling deployments.
