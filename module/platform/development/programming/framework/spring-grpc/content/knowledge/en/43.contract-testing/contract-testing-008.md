# Verifying Backward Compatibility

In Spring gRPC, backward compatibility is the ability of a new version to keep serving consumers that use an older contract. During a rolling update, clients and servers are not upgraded simultaneously: a new server may receive requests from older clients, while older servers are still receiving traffic from newer clients. Therefore, proto compiling successfully or two Java modules building together is not enough to prove the API is compatible.

Backward compatibility testing must examine protobuf wire format, generated Java APIs, gRPC method paths and cardinality, statuses, metadata, and business semantics. This lesson focuses on both directions of interaction between old and new clients/servers, designing additive changes, testing with released artifacts, and rolling out safely in the Spring gRPC ecosystem.

## 1. Identify Which Compatibility Needs Protection

Compatibility has multiple layers and can yield different outcomes:

| Layer | Question |
| --- | --- |
| Wire compatibility | Can older clients parse messages sent by the new server and vice versa? |
| Source compatibility | Do consumers still compile with the new generated Java API? |
| JSON compatibility | Are field names, enums, and JSON mapping rules preserved? |
| RPC compatibility | Are the full method path and RPC type unchanged? |
| Behavioral compatibility | Do statuses, metadata, ordering, validation, and side effects preserve semantics? |
| Operational compatibility | Do deadlines, retries, TLS, authentication, and rollouts work with the running version? |

A change can be wire-compatible yet break the source API. For example, renaming a field while keeping the same field number and type usually does not cause binary protobuf readers to lose data, but generated Java getters/setters and JSON field names can change.

Before reviewing a change, identify the supported consumers, the baseline version, and the types of compatibility the module commits to. For public APIs, wire, RPC, and behavior must usually be evaluated together; source compatibility also matters if consumers compile directly from proto artifacts.

## 2. Check Both Client/Server Directions

Call the running version v1 and the version ready for release v2:

| Client | Server | What to Verify |
| --- | --- | --- |
| v1 | v2 | New server still understands old requests and returns responses old clients can handle |
| v2 | v1 | New client tolerates missing new fields and does not call unavailable methods |
| v2 | v2 | New features work properly per the new contract |
| v1 | v1 | Old baseline still passes to compare behavior |

Backward compatibility usually emphasizes v1 client with v2 server. However, during rolling deployments, the v2 client with v1 server direction is also critical. A new client may be released while part of the server pool has not yet upgraded; if the client immediately calls a new method, older servers may return `UNIMPLEMENTED`.

Not every change has to support every version pair indefinitely. Document a clear support window, for example that new servers must support the two most recent client versions. This policy determines which artifacts must be retained as fixtures and which matrix must run in CI.

## 3. Keep Protobuf Field Numbers and Wire Semantics Stable

Protocol Buffers uses field numbers along with wire types to encode fields on the wire. Field names primarily affect the source API, descriptors, and JSON mapping. Changing a field number can cause readers to interpret bytes as a different field.

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

A v1 client unaware of new fields ignores them when parsing. A v2 server receiving a request from a v1 client must handle missing `locale` using a default or published policy. A v2 client calling a v1 server may receive a response without `description`; the new client must accept absent/default values per the field's semantics.

Rules to uphold:

- Never change already-released field numbers.
- Never reuse deleted field numbers or names.
- When deleting a field, reserve both the number and the name.
- Never assume new fields are always understood by older clients/servers.
- Never use a default value to represent a business state if you need to distinguish absent from an explicit default.

Example removing an old field:

```proto
message Product {
  string product_id = 1;
  reserved 2;
  reserved "legacy_name";
  int32 available_quantity = 3;
}
```

Reserving prevents the old slot from being reused in the future. If older clients still send field number 2, reusing that number can cause the new server to interpret old data with a different meaning.

## 4. Evaluate Field Types, Cardinality, Presence, and Enums

Not every change that keeps the field number is fully compatible:

| Change | Risk |
| --- | --- |
| Rename field, keep number/type | May keep binary wire but breaks generated Java API and JSON mapping |
| Add new field number | Usually additive; new clients must accept missing fields from older servers |
| Change scalar type | Must check wire type, encoding, range, and semantics; do not infer safety from wire type alone |
| Singular to repeated or vice versa | Changes cardinality and generated API; treat as breaking if consumers depend on it |
| Move field into/out of `oneof` | May change presence and behavior when multiple branches are set |
| Change implicit/explicit presence | May keep bytes but changes how the generated API distinguishes absent/default |

Proto3 implicit-presence scalar example:

```proto
message SearchRequest {
  string query = 1;
  optional int32 page_size = 2;
}
```

Clients can distinguish an omitted `page_size` from a `page_size` sent as 0 via `hasPageSize()`. Older servers may not know this field; new clients must define the default policy when the field is absent.

Adding enum values is usually wire-compatible, though older consumers may receive unknown numeric values. Keep already-released enum numbers unchanged and have a neutral zero value:

```proto
enum ProductState {
  PRODUCT_STATE_UNSPECIFIED = 0;
  PRODUCT_STATE_ACTIVE = 1;
  PRODUCT_STATE_ARCHIVED = 2;
}
```

If v2 adds `PRODUCT_STATE_PENDING = 3`, older Java consumers need to handle `UNRECOGNIZED` and can use `getStateValue()` when needing to preserve the numeric value. Do not default unknown enums to a success state. When deleting an enum value, reserve both its number and name.

## 5. Keep RPC Identity and Cardinality Stable

The protobuf package, service name, and method name form the full gRPC method path. Changing one of those components can cause older clients to call a path the new server does not register.

Example:

```text
/shop.catalog.v1.CatalogService/GetProduct
```

Changes that typically break compatibility include changing the package/service, renaming or deleting a method used by consumers, changing request/response types, and changing unary to streaming or vice versa.

Do not change an already-released unary method to streaming in place. Add a new method with a clear name, keep the old method during the transition period, and release a new package/service version if major changes are required.

Adding a new RPC method usually does not break older clients because older clients do not call it. However, newer clients calling the new method on an older server may receive `UNIMPLEMENTED`. If the new feature is mandatory, the client needs capability/version negotiation or should only be released after compatible providers are ready.

## 6. Keep Published Statuses, Metadata, and Behavior

Schemas do not describe the whole contract. Consumers may depend on:

- Status codes such as `NOT_FOUND`, `INVALID_ARGUMENT`, `RESOURCE_EXHAUSTED`, or `UNAVAILABLE`.
- Metadata keys such as `x-request-id`, `x-tenant-id`, and their ASCII/binary types.
- Initial response headers and trailers.
- Ordering, pagination, idempotency, and side effects.
- Deadline, cancellation, and retry semantics.

For example, changing `NOT_FOUND` to `INTERNAL` for the same missing-product case can cause clients to show system errors or retry incorrectly. Renaming a metadata key can lose correlation IDs or security context. A new server must preserve old status and metadata semantics on v1 methods while v1 consumers remain supported.

If behavior changes are needed, prefer adding capabilities additively. Keep the old contract stable and provide a new method/version for differing semantics. Do not add credentials or sensitive data to trailers as a substitute for authentication mechanisms.

## 7. Test Compatibility with Versioned Artifacts

Contract tests are only meaningful if client and server are built from the exact schema versions they represent. Retain the generated v1 client or released v1 proto artifact as a fixture; build the v2 provider and call that provider using the v1 stub.

| Test | Client artifact | Provider artifact | What to Verify |
| --- | --- | --- | --- |
| Backward wire test | v1 | v2 | Old requests parse properly, new responses remain readable |
| Forward rollout test | v2 | v1 | Client handles missing new fields and unavailable methods |
| Current contract test | v2 | v2 | New fields, statuses, metadata, and behavior are correct |
| Removed API guard | v1 | v2 | v1 method still exists within the support window |
| Unknown enum test | v1 | v2 | Older client does not crash when receiving new enum values |

Provider tests can use an in-process server to run the v2 service implementation, yet the client stub must genuinely be generated from v1 proto. If both client and server tests use v2 proto, the test only verifies the new version against itself and misses issues for older consumers.

For v2 client/v1 server, verify the client does not rely on new response fields always being present. If the client calls a v2-only method, test fallbacks or `UNIMPLEMENTED` status and clearly decide the rollout order. Never turn `UNIMPLEMENTED` into infinite retries.

## 8. Use Buf and Descriptor Artifacts in CI

Buf provides linting and breaking-change detection for protobuf. Example:

```bash
buf lint
buf breaking --against '.git#branch=main'
```

The baseline must be a stable or released contract, not a temporary output of the same build. Choose breaking rules per organizational policy: public API, package versioning, or compatibility targets. If a breaking change is intentional, release a new API version and review migration; do not disable the checker just to make the pipeline green.

You can generate a descriptor set to store the built schema:

```bash
protoc \
  -I src/main/proto \
  --include_imports \
  --descriptor_set_out=build/contracts/catalog-v2.pb \
  src/main/proto/shop/catalog/v1/catalog.proto
```

Descriptor artifacts help trace which schema clients/servers used and supply input for contract analysis tools. Do not compare raw descriptor bytes as the sole criterion; use a descriptor-aware diff or Buf to evaluate protobuf semantics.

CI should run schema checks before compilation/testing, then run provider verification using generated v1 and v2 clients. Store proto/descriptor artifacts alongside the release version so during incidents you can identify which schema each side used.

## 9. Roll Out via Expand-Migrate-Contract

A safe migration typically has three phases:

1. **Expand:** deploy servers that understand both old and new requests; new fields have clear defaults, and new responses only add fields additively.
2. **Migrate consumers:** release new clients, monitor remaining old clients and usage of old fields/methods.
3. **Contract:** remove the old API only after the support window and once telemetry confirms no consumers depend on it; reserve deleted field numbers/names.

Example adding `locale` to `GetProductRequest`:

- Servers are updated first to accept `locale` if present and use a default when older clients omit it.
- New clients begin sending `locale` after compatible server pools are ready.
- Monitor the share of requests with `locale` and verify no traffic reaches older servers that do not understand the new semantics.
- If the old field is later removed, reserve its number/name and re-evaluate still-supported consumers.

Do not rely on an atomic deploy in multi-instance systems. During rolling deployments, load balancers may send requests to any server version. Test rollbacks as well: new servers may have written data under new semantics that older servers do not understand. Schema compatibility does not automatically guarantee compatible database/storage migrations; apply expand-contract to stored data as well.

## 10. Backward Compatibility Checklist

- [ ] Compatibility targets are defined: wire, source, JSON, RPC, and behavior.
- [ ] v1 client/v2 server and v2 client/v1 server are checked when rollout requires it.
- [ ] Field numbers remain unchanged; deleted numbers and names are reserved.
- [ ] Fields are added additively and absent/default cases are handled.
- [ ] Consumers handle unknown enum values.
- [ ] Field renames/type/cardinality/oneof/presence changes are evaluated as API changes.
- [ ] Package, service, method paths, and RPC cardinality remain stable.
- [ ] Old methods are not deleted while consumers remain within the support window.
- [ ] Published status, metadata, ordering, and idempotency semantics are preserved.
- [ ] Buf breaking checks use a released baseline.
- [ ] Provider tests use generated clients from real v1 artifacts.
- [ ] Rollouts follow expand-migrate-contract with a rollback plan.
- [ ] Proto/descriptor artifacts are versioned for release traceability.

**Self-Check**

**Question 1.** Why is adding a protobuf field usually compatible with older clients?

*Answer:* The new field uses a new number; older clients unfamiliar with that field ignore it when parsing. Newer clients must still tolerate older servers omitting the field and returning absent/default values.

**Question 2.** Does renaming a field while keeping its number break binary compatibility?

*Answer:* Usually it does not break the binary wire format if number and type stay the same, though it can break generated Java source APIs, descriptor consumers, and JSON field names. You must define the compatibility target.

**Question 3.** Why should you not change a unary method to server-streaming in place?

*Answer:* RPC cardinality is part of the contract and alters generated stubs and client interactions. Add a new method, keep the old method during the transition period, or release a new API version.

**Question 4.** Why must v1 client vs. v2 server tests use real v1 generated artifacts?

*Answer:* If both sides are generated from the v2 proto, the test only verifies the new version against itself and fails to catch how older clients parse or call the new API.

**Question 5.** When can an old field or method be deleted?

*Answer:* After the support window ends, consumers have migrated, and telemetry confirms it is no longer used. For deleted fields, still reserve the number and name so they are never reused in the future.

Backward compatibility testing must simulate versions coexisting in production. Keep wire identities and RPC shapes stable, introduce changes additively, test with older client artifacts, and roll out via expand-migrate-contract. That enables Spring gRPC to release new servers and clients without disrupting un-upgraded consumers.
