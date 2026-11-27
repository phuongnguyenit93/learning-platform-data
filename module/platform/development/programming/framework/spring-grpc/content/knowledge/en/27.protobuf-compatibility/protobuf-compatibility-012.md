# Phased Schema Migration

## 1. Why Does Schema Migration Need Phases?

In **SPRING_GRPC**, a Protobuf schema is the contract between clients, servers, and data-processing components. These components rarely upgrade simultaneously: servers run rolling deployments across multiple replicas, mobile/desktop clients release on independent schedules, batch jobs may run for days, and serialized messages may reside in databases, event logs, queues, or backups.

If you change a schema all at once and deploy everything together, the system can easily end up with one side writing data in the new format while the other side only understands the old format. **Phased schema migration** breaks the change into coexisting steps: extend the schema, deploy compatible readers, transition writers and consumers, migrate stored data, and only then remove the old parts.

This approach is commonly known as **expand–migrate–contract**:

1. **Expand:** add the new structure while keeping the old structure.
2. **Migrate:** deploy code and shift traffic and data onto the new structure.
3. **Contract:** retire and delete the old structure, keeping reservations to prevent reuse.

This lesson focuses on organizing each phase for Protobuf and Spring gRPC, especially reader/writer deployment order, dual-read/dual-write, data backfills, rollback, and migration completion criteria.

## 2. Inventorying Producers, Consumers, and Data

Before editing a schema, know who writes and who reads the changing field. Producers and consumers go beyond direct clients and servers:

- Clients sending requests and servers reading requests.
- Servers producing responses and clients reading responses.
- Intermediary services parsing and forwarding messages.
- Consumers of events, queues, database snapshots, or caches reading stored payloads.
- Batch jobs, operational tools, and external integrations that may use old generated code.
- Gateways or adapters converting Protobuf to JSON and constructing new messages.

Build a table for each RPC/message:

| Subject | Version | Writes old field? | Reads old field? | Upgrade schedule |
| --- | --- | --- | --- | --- |
| Mobile client | v1 | Yes | Yes | Per release wave |
| Spring gRPC server | v1 | Possibly | Yes | Rolling deployment |
| Event consumer | v1 | No | Yes | Batch schedule |
| Data backfill job | Separate tool | Possibly | Yes | Maintenance window |

Identify both **live traffic** and long-lived stored data. v1 traffic dropping to zero does not prove backups, event logs, or database payloads no longer contain the old field.

Document the released schema baseline, field numbers, names, types, presence, semantics, and supported runtime versions. Never infer wire identity from Java getter names.

## 3. The expand–migrate–contract Principles

Each phase must maintain a verifiable invariant:

| Phase | Schema | Reader | Writer | Goal |
| --- | --- | --- | --- | --- |
| Expand | Has old and new fields | Reads both | Still writes old field | Extend without changing behavior |
| Migrate | Has old and new fields | Prefers new field, falls back to old | Dual-writes or gradually shifts | Transition consumers and data |
| Contract | Only new field; old field reserved | Needs only new field | Writes only new field | Remove the old path |

Do not advance to the next phase merely because new code has been merged. Require evidence from deployments, metrics, data checks, and compatibility tests.

A key principle is to **deploy reading capability before beginning to write new data**. During a rolling deployment, new requests may be routed to old replicas; new responses may be read by old clients. If a version pairing is unsupported, keep feature flags off or control routing to avoid that pairing.

## 4. Example: Migrating quantity from int32 to int64

Suppose contract v1 uses `int32` for quantity:

```proto
syntax = "proto3";

package inventory.v1;

message InventoryItem {
  string sku = 1;
  int32 quantity = 2;
}
```

Later, quantities may exceed the `int32` limit. Do not change the type directly at field number 2. Instead, add a new field with a never-used number and explicit presence:

```proto
syntax = "proto3";

package inventory.v1;

message InventoryItem {
  string sku = 1;
  int32 quantity = 2 [deprecated = true];
  optional int64 quantity_v2 = 5;
}
```

During the transition period:

- Field 2 preserves the old wire contract.
- Field 5 carries the new value and has presence to distinguish absent from 0.
- New readers prefer field 5 when `hasQuantityV2()` is true; otherwise they fall back to field 2.
- New writers can write both fields when the value fits within the `int32` range.
- Old writers do not know field 5 and continue writing field 2.

The `deprecated` option signals compilers/tooling and developers; it does not prevent old clients from sending the field or remove getters from the generated API.

Never force values exceeding `int32` bounds into the old field via truncation or casting. While v1 readers still exist, keep values within the old range or ensure requests carrying large values route only to v2-capable servers.

## 5. Expand Phase: Adding the Field While Keeping the Old Contract

In the initial phase, only extend the schema and deploy readers capable of understanding both old and new fields. Do not yet enable writers to send data representable only by the new field.

Example reading logic in a Spring service:

```java
long quantity;

if (request.hasQuantityV2()) {
    quantity = request.getQuantityV2();
} else {
    quantity = request.getQuantity();
}
```

This is an illustrative mapping; place it in a dedicated adapter so every RPC applies the same rule. If the new field uses implicit presence, you cannot check absence via `hasQuantityV2()`; choose `optional` or a construct with explicit presence if the migration needs to distinguish absent from zero.

Expand sequence:

1. Add the new field with a never-used number; keep the old field untouched.
2. Mark the old field `deprecated` if project policy permits.
3. Generate Java code and compile all dependent modules.
4. Deploy new server readers across all replicas.
5. Update event consumers, batch jobs, and gateways to understand the new field.
6. Keep old writers or old-field-only write mode active.
7. Run request/response tests from generated v1 clients.

After this step, new servers must reliably read payloads created by old writers. There is not yet any reason for clients to begin sending values representable only in the new field.

## 6. Migrate Phase: Dual-Read and Dual-Write

Once all required readers understand the new field, you can begin shifting writers. For a period, new writers can write both the old and new fields simultaneously so v1 readers continue functioning.

Example response construction:

```java
InventoryItem.Builder builder = InventoryItem.newBuilder()
    .setSku(item.sku())
    .setQuantityV2(item.quantity());

if (item.quantity() >= Integer.MIN_VALUE
        && item.quantity() <= Integer.MAX_VALUE) {
    builder.setQuantity((int) item.quantity());
}

return builder.build();
```

This example dual-writes the old field only when the value can be represented accurately in `int32`. If the value exceeds the old range, v1 clients cannot be guaranteed to read it accurately. Therefore, before permitting out-of-range data, confirm no v1 consumers remain or route such requests exclusively to supporting versions.

### Precedence Rules When Both Fields Are Present

New readers must apply deterministic rules:

- If the new field is present, use the new field.
- If the new field is absent, fall back to the old field.
- If both are present with conflicting values, detect the conflict and handle it according to an explicit policy.

Never silently pick one value when two fields contradict each other. You can reject the request, emit metrics, and log in a controlled manner to catch buggy producers. During a migration, conflicts are data-quality signals that must be investigated.

Dual-writing should exist only for a bounded, purposeful window. Writing two fields indefinitely increases complexity, introduces another source of drift, and makes retiring the old field harder.

## 7. Migrating Consumers and Stored Data

Serialized Protobuf data can outlive the service version that created it. Classify data by mutability:

- **Mutable data:** can be backfilled by reading old payloads, populating the new field, and rewriting under the new schema.
- **Immutable events:** usually should not be edited in place; consumers can read historical events via adapters or rebuild projections.
- **Caches:** can be evicted and repopulated as long as the authoritative data source remains intact.
- **Backups/archives:** require keeping the old schema or corresponding decoder for the retention window.
- **`Any` and descriptors:** must retain the ability to resolve old type URLs as long as data still references those types.

A backfill requires checkpoints, idempotent re-runnability, and record-count reconciliation. Typical workflow:

1. Read payloads using a schema that understands the stored format.
2. Convert to the canonical domain model.
3. Build the new message with the new field populated.
4. Validate invariants and boundary values.
5. Write the new record using an appropriate atomic/transactional strategy.
6. Persist progress and error counts so runs can resume.

Do not parse and re-serialize every payload with a new schema if the conversion step could strip unknown fields or data unfamiliar to the current version. For immutable events, keeping original bytes intact and translating inside projections or consumers is usually safer.

## 8. Contract Phase: Retiring the Old Field and Reserving

Contract only once you have proven:

- No v1 writers remain in live traffic.
- No v1 readers still require the old field.
- Batch jobs, gateways, integrations, and queue consumers have migrated.
- Mutable data has been backfilled; immutable data still has appropriate decoders.
- No rollback to binaries understanding only the old field remains possible or needed.
- Metrics for old-field usage and fallbacks have stayed at acceptable levels over the defined observation window.

Then delete the old field declaration and reserve both its field number and name:

```proto
message InventoryItem {
  string sku = 1;
  optional int64 quantity_v2 = 5;

  reserved 2;
  reserved "quantity";
}
```

The reservation sits inside the enclosing message. Never reserve field number 5 because the new field is still using it. Retain the reservation in subsequent schema versions so old identifiers are never reused.

Deleting a field is a source/API change for old consumers. The new parser treats the old tag as unknown; the server no longer has a getter to read that value. Hence, contracting is safe only once old writers and consumers depending on the old field have been retired or isolated in a separate API version.

## 9. Rollback in Each Phase

Rollback plans must be designed before beginning to write new data.

| Phase | Rollback feasible? | Conditions |
| --- | --- | --- |
| Expand | Usually easy | New writer not yet enabled; can revert to old server if schema is additive |
| Dual-read/dual-write | Conditional | Old field is still written and new values remain representable in old range |
| New-only write | Harder | Old readers cannot read new data; requires keeping compatible servers or restoring from converted data |
| Contract | Usually requires forward-fix | Old field was removed from generated API and number/name were reserved |

If rollback requires an old server to read newly written data, dual-write must guarantee the old field holds an accurate value. Once values exceed the old range, rolling back to server v1 is no longer safe.

Do not delete the old field in the very first release that switches writers to the new field. Split contracting into a later release to allow observation time and preserve a rollback path.

## 10. Testing Migration Against a Version Matrix

Testing the new schema solely with new generated code is insufficient. Retain fixtures/artifacts from the old schema and test every combination that can occur during rollout:

| Writer | Reader | What to verify |
| --- | --- | --- |
| v1 | v2 | New reader falls back properly when new field is absent |
| v2 dual-write | v1 | Old reader uses old field with accurate value |
| v2 dual-write | v2 | New reader prefers new field and detects conflicts |
| v2 new-only | v1 | Must be prevented while old readers remain supported |
| Old stored payload | Backfill v2 | Data converts losslessly |
| Old event/backup | Current consumer | Old decoder remains available when needed |

Example fallback test:

```java
InventoryItem oldPayload = InventoryItem.newBuilder()
    .setSku("SKU-10")
    .setQuantity(25)
    .build();

long resolved = oldPayload.hasQuantityV2()
    ? oldPayload.getQuantityV2()
    : oldPayload.getQuantity();

assertEquals(25L, resolved);
```

Additional tests should cover:

- `0`, negative values, and `Integer.MIN_VALUE`/`Integer.MAX_VALUE` boundaries.
- Values exceeding the `int32` range.
- Both fields present with conflicting values.
- New field absent and old field absent.
- Parse/serialize round-trips through proxies or gateways.
- Old client/new server and new client/old server via gRPC integration tests.
- Resuming backfill after interruption.

## 11. Observing Migration via Metrics and Logs

You cannot decide to contract based solely on deployments finishing. Measure where the old field is still being used.

Useful metrics:

- Requests containing only the old field.
- Requests containing the new field.
- Requests containing both fields.
- Conflicts where both fields are present with differing values.
- Fallbacks from the new field to the old field.
- Clients invoking older RPC/service versions.
- Historical payloads remaining un-backfilled or failing backfill.
- Parse errors and migration-related domain errors.

Use bounded-cardinality metric labels such as API version, service, and migration state. Never put user IDs, payloads, or arbitrary field values into metric labels. Logs should capture enough context for tracing while avoiding sensitive data.

Define exit criteria before the migration begins—for example: zero old writers over a window exceeding the longest batch/job cycle; zero fallbacks; no known v1 consumers; backfill completed and reconciled.

## 12. CI and Schema Governance

CI must verify both schemas and migration logic:

- Lint/format Protobuf schemas.
- Run breaking checks against the released baseline.
- Confirm new fields use never-used numbers.
- Confirm old fields are marked deprecated during migrate and reserved upon contract.
- Generate code using pinned `protoc`/plugin versions.
- Compile server/client adapters.
- Run compatibility tests with generated v1/v2 fixtures.
- Run integration tests for all supported client/server combinations.
- Test backfill and conflict handling against representative data fixtures.

Static breaking checks cannot prove no old writers remain in production. That condition requires metrics, consumer inventories, and release approvals. Similarly, passing CI does not prove historical data has been migrated; backfills need separate reporting and reconciliation.

## 13. When Should You Use a Versioned Service Instead of Field Migration?

Expand–migrate–contract fits when the old and new contracts can coexist within one message and clear fallbacks and mappings can be defined.

Consider a versioned service/message when:

- Request/response semantics change deeply and cannot safely dual-read/write.
- Multiple fields depend on each other and cannot evolve independently.
- Old clients would misinterpret new payloads even when parsing succeeds.
- RPC paths, authorization boundaries, or workflows must change.
- Multiple consumer groups have upgrade schedules that cannot be coordinated via a field migration.

In such cases, keep service v1 and create service v2; the server can dual-register both services and use adapters delegating to shared domain logic. Field migration within v1 and a versioned service v2 are different tools; choose based on the scope of contract change.

## 14. Migration Completion Checklist

- Producers, consumers, intermediaries, and stored data have been inventoried.
- Schema baseline and compatibility matrix are documented.
- New field uses a new number; old field remains intact during expand.
- New readers support both old and new fields before writers switch.
- Presence/defaults and precedence between the two fields are defined.
- Dual-write runs only when conversion is lossless.
- Out-of-range values are blocked until no old readers remain.
- Backfill supports checkpoints, retries, reconciliation, and unknown-field handling.
- Metrics confirm old writers/readers and fallbacks have dropped to zero per exit criteria.
- Rollback was verified before stopping writes to the old field.
- Old field is deleted only once no dependent consumers remain.
- Old number and name are reserved; CI breaking checks still use the proper baseline.

In **SPRING_GRPC**, phased schema migration lets clients, servers, and data consumers upgrade on staggered timelines while keeping contracts operational. Expand first, deploy compatible readers, transition writers and data in controlled steps, and only then contract the old field. End the migration only when metrics, fixtures, stored data, and compatibility tests prove no dependency on the old schema remains.
