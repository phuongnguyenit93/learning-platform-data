# Verifying Backward Compatibility

In Spring gRPC, backward compatibility is the ability of a new version to keep serving older clients according to the published contract. During a rolling deployment, servers and clients are not upgraded at the exact same moment: new servers may receive requests from older clients, while older servers may still receive traffic from newer clients. Therefore, a change that compiles successfully is not enough to conclude the API is compatible.

Compatibility testing must inspect protobuf wire format, generated Java APIs, gRPC method paths/cardinality, statuses, and metadata semantics. This lesson focuses on evaluating both old-client/new-server and new-client/old-server directions, designing additive changes, organizing rollouts, and integrating checks into CI.

## 1. Two Compatibility Directions Must Be Checked

Call the running version v1 and the version about to be deployed v2:

| Client | Server | Question to Answer |
| --- | --- | --- |
| v1 | v2 | Does the new server still understand requests and return responses that older clients can handle? |
| v2 | v1 | Does the new client still work when the older server does not yet know new fields/methods? |
| v2 | v2 | Do new features work properly according to the new contract? |

Backward compatibility usually emphasizes v1 client with v2 server. However, during rolling deployments, the v2 client with v1 server direction is also critical: a new client may be released ahead of some new server instances or accidentally route to an un-upgraded zone.

Not every change has to be compatible in both directions. Policy must clearly define the compatibility target: wire compatibility, source compatibility, JSON compatibility, or behavior compatibility. A field rename can preserve the binary wire format while breaking generated Java sources or JSON field names.

## 2. Protobuf Wire Contract and Field Numbers

Protocol Buffers uses field numbers along with wire types to encode fields on the wire. Field names primarily affect the source API, descriptors, and JSON mapping; changing a number causes readers to interpret bytes as a different field.

Example v1:

```proto
syntax = "proto3";

package shop.catalog.v1;

message GetProductRequest {
  string product_id = 1;
}

message Product {
  string product_id = 1;
  string display_name = 2;
  int32 available_quantity = 3;
}
```

An additive change in v2 can add new field numbers:

```proto
message GetProductRequest {
  string product_id = 1;
  string locale = 2;
}

message Product {
  string product_id = 1;
  string display_name = 2;
  int32 available_quantity = 3;
  optional string description = 4;
}
```

A v1 client unaware of fields 2/4 ignores new fields when parsing. A v2 server receiving a request from a v1 client sees `locale` absent and must use a default or compatible policy. A v2 client calling a v1 server may receive a response without `description`; the new client must handle the absent/default case per the contract.

Mandatory rules:

- Never change already-released field numbers.
- Never reuse deleted field numbers or names.
- When deleting a field, reserve both the number and the name.
- Never assume new fields are always understood by older clients/servers.
- Never rely on default values to represent a business state if you need to distinguish absent from an explicit default.

Example removing an old field:

```proto
message Product {
  string product_id = 1;
  reserved 2;
  reserved "legacy_name";
  int32 available_quantity = 3;
}
```

If the old field was already released, keep the slot reserved in subsequent versions. This prevents a new field from accidentally reusing a number older clients still send.

## 3. Field Name, Type, Cardinality, and Presence

Not every change that preserves the field number is fully compatible:

| Change | Binary wire | Source/API and behavior |
| --- | --- | --- |
| Rename field, keep number/type | Usually still parses | Can break generated Java getters/setters, descriptor consumers, and JSON field names |
| Add new field with new number | Usually compatible | New consumers must accept absent values from older servers |
| Delete field and reserve | Old readers ignore field if still receiving bytes | Clients/servers relying on that field no longer share equivalent behavior |
| Change scalar type | Depends on wire type and encoding | Can change semantics even with the same wire type; treat as breaking by default |
| Singular to repeated or vice versa | Should not assume compatibility | Generated API and cardinality semantics change |
| Move field into `oneof` or between `oneof`s | Can lose/change presence semantics | Usually a behavior change that must be treated as breaking |
| Change implicit presence to explicit presence | Can preserve bytes | Generated API and absent/default distinction change |

For example, renaming `product_name` to `display_name` while keeping number 2 typically does not cause protobuf binary readers to lose data. However, the generated Java API changes from `getProductName` to `getDisplayName`; older client source code may fail to compile if regenerated from the new schema. JSON transcoding may also use a different JSON name. Therefore, wire compatibility does not equal source or JSON compatibility.

Type changes must be evaluated under specific protobuf rules, not just by comparing wire types. Two types with the same wire type can still interpret bytes differently. For public APIs, the safe approach is adding a new field, migrating data and consumers, and then reserving the old field upon removal.

## 4. Presence, Defaults, and New Enum Values

Proto3 scalars use implicit presence by default. If a field is not sent, the getter returns the default value; new clients calling old servers therefore cannot assume the new field always has a value. When the contract needs to distinguish absent from an explicit default, use `optional` or an appropriate message wrapper.

Example:

```proto
message SearchRequest {
  string query = 1;
  optional int32 page_size = 2;
}
```

The server can distinguish a client omitting `page_size` from a client explicitly sending 0 using `hasPageSize()`. Contract tests should cover both cases and define the default policy for older servers.

Adding enum values is usually wire-compatible, though older consumers may receive unknown numeric values. Enums need a zero value with a neutral/unspecified meaning and already-released numbers must not be changed:

```proto
enum ProductState {
  PRODUCT_STATE_UNSPECIFIED = 0;
  PRODUCT_STATE_ACTIVE = 1;
  PRODUCT_STATE_ARCHIVED = 2;
}
```

When v2 adds `PRODUCT_STATE_PENDING = 3`, older consumer Java code must handle unknown enums. With generated Java enums, check `UNRECOGNIZED` and use `getStateValue()` if you need to preserve the numeric value. Do not use a default switch branch that treats every unknown value as `ACTIVE` or a success state.

## 5. RPC Identity and Cardinality Are Also Part of the Contract

The protobuf package, service name, and method name form the full gRPC method path. Changing any of these components can cause older clients to call a path the server no longer registers.

Example method path:

```text
/shop.catalog.v1.CatalogService/GetProduct
```

The following changes usually break compatibility:

- Changing the package or service name.
- Renaming a method.
- Deleting a method still used by consumers.
- Changing unary to server/client/bidirectional streaming or vice versa.
- Changing request/response message types without keeping the old method.

Do not turn an already-released unary method into streaming simply by editing its proto signature. Add a new method with a clear name, such as `WatchProducts`, keep the old method during the transition period, and release a new package/service version when major contract changes are needed.

Adding a new RPC method usually does not break older clients because older clients do not call it. However, newer clients calling the new method on an older server can receive `UNIMPLEMENTED`. This is a scenario to handle via rollout ordering and capability/version negotiation, not a message wire error.

## 6. Status, Metadata, and Behavior Must Also Stay Stable

Protobuf schemas do not describe the entire contract. Consumers may depend on:

- Status codes such as `NOT_FOUND`, `INVALID_ARGUMENT`, `RESOURCE_EXHAUSTED`, or `UNAVAILABLE`.
- Metadata keys such as `x-request-id`, `x-tenant-id`, and their ASCII/binary types.
- Initial response headers and trailers.
- Ordering, pagination, idempotency, and side effects.
- Deadline, cancellation, and retry semantics.

For example, changing `NOT_FOUND` to `INTERNAL` for the same missing-product case can cause clients to display system errors or retry incorrectly. Renaming a metadata key can break correlation IDs or security context. A new server must preserve old status/metadata semantics for v1 methods while v1 consumers still exist.

If behavior changes are needed, add new statuses/details or metadata additively while keeping older clients working. Do not put sensitive data into trailers as a substitute for authentication mechanisms.

## 7. Testing Compatibility with an Artifact Matrix

Contract tests are most valuable when using generated code from two real versions. Keep v1 proto/generated clients as fixtures or versioned artifacts; build the v2 provider and run tests with the v1 client.

| Test | Client artifact | Provider artifact | What to Verify |
| --- | --- | --- | --- |
| Backward wire test | v1 | v2 | Old requests parse properly, new responses remain readable |
| Forward rollout test | v2 | v1 | Client handles missing new fields and unavailable new methods |
| Current contract test | v2 | v2 | New fields, statuses, metadata, and behavior are correct |
| Removed API guard | v1 | v2 | v1 method still exists if within the support window |
| Unknown enum test | v1 | v2 | Older client does not crash when receiving new enum values |

A provider test with an in-process server can use a v1 generated stub to call the v2 provider. Crucially, the client stub must genuinely be generated from v1 proto; if both client and server tests are built from the new proto, the test does not verify backward compatibility.

For new-client/old-server, run the v2 client against a v1 server and verify fallbacks or `UNIMPLEMENTED` handling for new methods. If a new feature is mandatory, the client must check capabilities or only be released after the entire server pool has been upgraded.

## 8. Buf Breaking Checks and Descriptor Artifacts in CI

Buf supports linting and breaking-change detection. Pipeline example:

```bash
buf lint
buf breaking --against '.git#branch=main'
```

The baseline must be a stable/released contract, not a temporary output of the same build. Choose breaking rules per organizational policy: package versioning, public API, or compatibility target. If a breaking change is intentional, create a new API version and review migration; never turn off the checker just to make the pipeline green.

You can generate a descriptor set to store the built contract:

```bash
protoc \
  -I src/main/proto \
  --include_imports \
  --descriptor_set_out=build/contracts/catalog-v2.pb \
  src/main/proto/shop/catalog/v1/catalog.proto
```

Descriptor artifacts help trace which schema clients/servers used and enable contract analysis tools. Do not compare raw descriptor bytes as the sole criterion; use a descriptor-aware diff or Buf to understand protobuf semantics.

CI should run schema checks before compilation/testing, then run provider tests with generated v1 and v2 clients. Store contract artifacts alongside release versions so that during incidents you can identify the exact schema both sides used.

## 9. Expand-Contract Rollouts

A safe migration typically has three phases:

1. **Expand:** deploy servers that understand both old and new requests; new responses only add optional/additive fields without altering old semantics.
2. **Migrate consumers:** release new clients, monitor remaining old clients and usage of old fields/methods.
3. **Contract:** remove the old API only after the support window ends and no consumers depend on it; reserve deleted field numbers/names.

Example adding `locale` to `GetProductRequest`:
- First, servers are updated to accept `locale` if present and use a default when older clients omit it.
- New clients start sending `locale`.
- Monitor the share of requests carrying `locale` and verify older servers no longer receive traffic from newer clients if they do not understand the field.
- If the old field is later removed, reserve its number/name and re-evaluate compatibility with any still-supported consumers.

Do not rely on an atomic deploy in multi-instance systems. During rollout, load balancers can route requests to any server version. Test rollbacks too: new servers may have written data under new semantics that older servers do not understand. Schema compatibility alone does not guarantee compatible database/storage migrations; apply expand-contract to stored data as well.

## 10. Backward Compatibility Checklist

- [ ] Compatibility targets are defined: wire, source, JSON, and behavior.
- [ ] Both v1 client/v2 server and v2 client/v1 server are tested if rollout requires it.
- [ ] Field numbers are preserved; deleted numbers and names are reserved.
- [ ] Fields are added additively and absent/default cases are handled.
- [ ] Consumers handle unknown enum values.
- [ ] Field renames/type/cardinality/oneof/presence changes are evaluated as API changes.
- [ ] Package, service, method paths, and RPC cardinality remain stable.
- [ ] Old methods are not deleted while supported consumers remain.
- [ ] Published status, metadata, ordering, and idempotency semantics are preserved.
- [ ] Buf breaking checks run against a released baseline.
- [ ] Provider tests use generated clients from real v1 artifacts.
- [ ] Rollouts follow expand-migrate-contract with a rollback plan.
- [ ] Descriptor/proto artifacts are versioned for release traceability.

**Self-Check**

**Question 1.** Why is adding a protobuf field usually compatible with older clients?

*Answer:* The new field uses a new number; older clients unfamiliar with that field ignore it when parsing. However, newer clients must handle older servers not sending the field and returning default/absent values.

**Question 2.** Does renaming a field while keeping its number break binary compatibility?

*Answer:* Usually it does not break the protobuf binary wire format if number and type stay unchanged, but it can break generated Java source APIs, descriptor consumers, and JSON field names. That is why defining the compatibility target matters.

**Question 3.** Why should you not change a unary method to server-streaming in place?

*Answer:* RPC cardinality is part of the contract and changes generated stubs and client interactions. Add a new method, keep the old method during the transition period, or release a new API version.

**Question 4.** Why must v1 client vs. v2 server tests use real v1 generated artifacts?

*Answer:* If both sides are generated from the v2 proto, the test only verifies the new version against itself and fails to catch how older clients parse or call the new API.

**Question 5.** When can an old field or method be deleted?

*Answer:* After the support window ends, consumers have migrated, and telemetry confirms it is no longer used. For deleted fields, still reserve the number and name so they are never reused in the future.

Backward compatibility testing must simulate versions coexisting in production. Keep wire identities and RPC shapes stable, introduce changes additively, test with older client artifacts, and roll out via expand-contract. That enables Spring gRPC to release new servers and clients without disrupting un-upgraded consumers.
