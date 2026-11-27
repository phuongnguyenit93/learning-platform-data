# Evaluating Schema Evolution Before Finalizing Proto

A Protocol Buffers contract often outlives a single application version. During that time, the Spring gRPC server, Java clients, mobile apps, gateways, and integrating services may be upgraded at different times. Therefore, a change to a .proto file must be evaluated based on how old and new versions exchange data together, not just whether the code compiles.

Evaluating schema evolution before finalizing a proto helps the team identify what can be extended safely, what needs a migration with a transition window, and what requires creating a new API version. This is a contract-design step, not cleanup work after release.

## Objectives

After this lesson, you can:

- Distinguish binary wire, ProtoJSON, generated source, and semantic compatibility.
- Evaluate a change when an old client calls a new server and when a new client calls an old server.
- Design field numbers, field presence, enums, oneofs, services, and RPCs to support evolution.
- Plan a phased rollout when clients and servers are on skewed versions.
- Use Buf, protoc, and integration tests to catch breaking changes before release.

## 1. Why Evaluate a Schema Before Finalizing?

A .proto file defines message structures and RPC signatures. From this contract, protoc generates the data types and stubs used by Java applications. At runtime, gRPC transmits Protobuf messages between processes; the two sides may be running code generated from two different schema versions.

For example, an upgraded server may receive requests from un-updated clients for weeks. An old batch worker may continue calling an RPC after the service has deployed a new version. If a schema change prevents one side from reading data sent by the other, failures will surface at runtime even though both versions compiled fine independently.

A schema must be evaluated across at least four layers:

| Compatibility Layer | Question to Answer |
| --- | --- |
| Binary wire | Can messages serialized with the old schema be read properly by the new schema, and vice versa? |
| ProtoJSON / TextFormat | Are field names, enums, and JSON shapes still accepted by older parsers or gateways? |
| Generated source API | Does Java and other language code still compile after regenerating stubs? |
| Business semantics | Do both versions interpret the same value with the same units, meaning, defaults, and processing rules? |

A change can be safe on the binary wire while still breaking Java source code or altering data meaning. Therefore, do not use the phrase "backward compatible" without specifying which layer and which direction of compatibility you are examining.

## 2. Identify the Compatibility Direction to Protect

In distributed systems, you cannot assume all clients and servers deploy simultaneously. Evaluate at least two scenarios:

1. **Old client calls new server:** the server must read old requests and the old client must understand responses returned by the new server.
2. **New client calls old server:** the old server must handle new requests safely and the new client must tolerate responses lacking new fields.

For changes that only add fields, the binary wire usually lets both schemas exchange messages. Still, business logic can remain incompatible. For example, a new client sends an added region field, but the old server ignores it and queries on a default region. The RPC may succeed yet return data for the wrong scope.

Scenarios requiring separate analysis:

- New client calls a new RPC on an old server: the old server typically returns UNIMPLEMENTED status.
- New server returns an enum value unknown to the old client: client enum-handling code must have a fallback branch.
- New client needs a new response field that the old server does not yet send: the client must handle the absent field state.
- A gateway that parses Protobuf to JSON and re-serializes it may handle unknown fields differently from a proxy that only forwards raw bytes.

Document a supported version matrix, such as which current and prior client versions can connect to the current server and for how long. This policy determines review strictness and when old APIs may be removed.

## 3. Keep Field Numbers and Field Definitions Stable

### 3.1. Field Numbers Are the Wire Identifier

Protobuf uses field numbers to encode data. Field names help humans read the schema and affect generated source code, but the field number is the field's identity in the binary wire format.

~~~proto
syntax = "proto3";

package catalog.v1;

option java_package = "com.example.catalog.v1";

message GetBookRequest {
  string isbn = 1;
}

message Book {
  string isbn = 1;
  string title = 2;
  int64 price_micros = 3;
}
~~~

Once a field is used in a real environment:

- Do not change the field number of an existing field.
- Do not reuse the number of a deleted field.
- Do not change the type merely because a new type is more convenient in Java.
- Do not assign the same number to two fields in the same message.
- Prefer numbers 1 through 15 for frequently appearing fields because they have a shorter encoding.

Numbers 19000 through 19999 are reserved for Protobuf implementations and must not be used in schemas.

### 3.2. Deleting a Field Must Reserve Both Number and Name

When a field is no longer used, delete it after migration completes and reserve both its number and name:

~~~proto
message Book {
  string isbn = 1;
  string title = 2;

  reserved 3;
  reserved "price_micros";
}
~~~

Reserving the number prevents a future change from accidentally assigning the old number to data with a different meaning. Reserving the name avoids conflicts when using ProtoJSON or TextFormat. Never reuse a number just because the old field has vanished from the current codebase.

### 3.3. Renaming a Field Affects Multiple Layers

Renaming a field while keeping the number and wire type usually does not change the binary wire format. However, field names are used in JSON, TextFormat, and generated APIs. Thus, renaming isbn to book_code can break clients parsing JSON or Java code calling the old getter.

If the new name only makes code clearer, consider keeping the current wire name and improving variable names in the mapping/domain layer. If renaming on the contract is mandatory, separately evaluate every consumer of ProtoJSON, gateways, and the generated source API.

### 3.4. Do Not Change Type to Reuse a Field

Some Protobuf types share the same wire type at the encoding level, but that does not guarantee the same meaning or value range. For example, switching between numeric types can lose data when values fall outside the representable range; changing how a number is interpreted can turn the exact same bytes into a different value.

If a new data type or meaning is needed, the safe path is usually adding a new field with a new number, converting at the application layer, and retiring the old field only after migration completes. Never treat "it parses" as proof that the data is still right.

## 4. Evaluate Presence, Defaults, and Cardinality

### 4.1. Distinguish Absent from Default Value

In proto3, a scalar field without optional uses implicit presence. Default values like 0, false, or an empty string do not tell whether the client explicitly sent that value.

If business logic must distinguish "not provided" from "set to 0", use explicit presence:

~~~proto
message UpdateInventoryRequest {
  string sku = 1;
  optional int32 reorder_level = 2;
}
~~~

In Java generated code, a field with explicit presence provides a method to check whether the field was set alongside the getter returning the value. This is useful for PATCH-like updates, optional configuration, and cases where the current value must be preserved if the client omits the field.

Decide presence before release. If a field means "keep current value when omitted" but code treats 0 as a command to set it to 0, the API can cause data loss even though the wire format is completely valid.

### 4.2. Be Careful When Changing Cardinality

Changing between singular, repeated, and map can affect generated code, JSON shape, and how applications process data. A map is represented on the binary wire as a repeated entry message, yet JSON represents a map as an object whereas repeated is an array. Therefore, a change that looks readable on the binary wire can still break JSON consumers.

Do not convert a published field from singular to repeated or map solely to expand storage capacity. Add a new field or create a new message/version if the data shape must change significantly.

## 5. Evolving Enums and Oneofs

### 5.1. Enums Need an Explicit Default Value

In proto3, reserve numeric value 0 for the unspecified state:

~~~proto
enum BookState {
  BOOK_STATE_UNSPECIFIED = 0;
  BOOK_STATE_DRAFT = 1;
  BOOK_STATE_PUBLISHED = 2;
}
~~~

When adding a new state, preserve existing values' numbers and assign only new numbers:

~~~proto
enum BookState {
  BOOK_STATE_UNSPECIFIED = 0;
  BOOK_STATE_DRAFT = 1;
  BOOK_STATE_PUBLISHED = 2;
  BOOK_STATE_ARCHIVED = 3;
}
~~~

The binary wire can carry an enum number unknown to an older client. How the runtime represents unknown values depends on the language and Protobuf version; in Java generated proto3 enums, there is an UNRECOGNIZED value and an API to retrieve the numeric value. Client code needs a fallback branch rather than assuming every received enum belongs to the compile-time list.

Do not change enum value numbers and never reassign deleted numbers. When deleting an enum value, reserve both the number and name:

~~~proto
enum BookState {
  reserved 1;
  reserved "BOOK_STATE_DRAFT";

  BOOK_STATE_UNSPECIFIED = 0;
  BOOK_STATE_PUBLISHED = 2;
  BOOK_STATE_ARCHIVED = 3;
}
~~~

The example above only illustrates reserve syntax; in an existing schema, keep the numbers of values still in use unchanged. Do not renumber enums just to make a contiguous list.

If an enum is serialized via ProtoJSON, the enum name is also part of the contract. Check JSON consumers and gateways before renaming or deleting values.

### 5.2. Oneof Changes How State Is Interpreted

oneof expresses that at most one of its member fields has a value at any given time:

~~~proto
message PaymentMethod {
  message CardPayment {
    string token = 1;
  }

  message BankTransfer {
    string account_reference = 1;
  }

  oneof method {
    CardPayment card = 1;
    BankTransfer bank_transfer = 2;
  }
}
~~~

When a parser encounters multiple members of the same oneof on the wire, the member appearing last can overwrite an earlier one. If an older client does not know about a new member, it may see the oneof as unset even though the actual data contains a member the older version does not recognize.

Therefore:

- Do not arbitrarily move existing fields into or out of a oneof.
- Do not change the oneof group of an existing field.
- Do not split or merge oneofs in a single release without a transition plan.
- When adding a new member, verify how older clients handle the unknown state and how gateways preserve unknown fields.

With oneof changes, test with messages serialized by both the old and new schemas; check both the parsed data and the data after re-serializing.

## 6. Evaluate Services, Packages, and RPC Signatures

A gRPC call is identified by the full service name and method name. Therefore, changing the Protobuf package, service name, or method name changes the RPC path that clients call.

~~~proto
package catalog.v1;

message GetBookRequest {
  string isbn = 1;
}

message Book {
  string title = 1;
}

service CatalogService {
  rpc GetBook(GetBookRequest) returns (Book);
}
~~~

Distinguish the effects of each change:

| Component | Primary Impact |
| --- | --- |
| Protobuf package | Changes the full name of services/messages and can change the RPC path |
| Service or method name | Old clients call the old path; the new server may no longer have that method |
| RPC request/response type | Changes the generated signature and can make client/server incompatible |
| Unary to client/server/bidirectional streaming or vice versa | Changes the exchange protocol, generated stubs, and RPC lifecycle |
| Java java_package | Changes the package of generated Java code, though it does not directly change binary messages |
| java_multiple_files and codegen options | Can change class structure and imports in Java applications |

Do not change package catalog.v1 just to reorganize Java folders. package is part of the Protobuf and gRPC identity; java_package is a Java code-generation setting. The two values can differ and must be reviewed independently.

When you need to change an RPC signature or incompatible semantics, consider creating a new versioned service or package, such as catalog.v2. You can maintain v1 and v2 side-by-side during a transition period, then retire v1 per your published support policy.

## 7. Plan Rollouts When Clients and Servers Are Version-Skewed

Safe schema evolution requires a deployment order aligned with data direction. The expand-and-contract pattern allows old and new versions to coexist during the transition period.

### 7.1. When Adding a Field to a Request

If new clients will send a new request field, the server must be deployed first to understand it:

1. Add the new field with an unused number; keep existing behavior when the field is absent.
2. Deploy servers capable of handling both old and new requests.
3. Test and monitor the server with old clients.
4. Once servers are ready, deploy clients that begin sending the new field.
5. Monitor the percentage of upgraded clients and confirm the default handling branch still works.

If clients send the new field before servers understand its meaning, old servers may ignore it and process using defaults. The RPC succeeds, yet the outcome may not match the client's intent.

### 7.2. When Adding a Field to a Response

If new clients need to read a new response field:

1. Add the field to the schema and deploy clients that handle both present and absent cases.
2. Deploy new clients first, ensuring they still work with responses from old servers.
3. Deploy servers that begin populating the new field.
4. Monitor field usage and confirm old clients ignore the new data safely.

This order prevents new clients from assuming every server has already upgraded and returns the new field.

### 7.3. When Changing Semantics or RPC Signatures

If a change cannot stay compatible by adding fields:

1. Create a new field or RPC, or create a new versioned package/service.
2. Deploy servers supporting both the old and new paths.
3. Upgrade clients in cohorts and measure usage of the new path.
4. Stop writing or calling the old path after consumers have migrated.
5. Delete old definitions only after the support window ends, logs/telemetry are checked, and field numbers/names are reserved if deleting fields.

Never reuse an old field to carry a new meaning. A field like amount should not represent dollars at one time and cents at another just to keep the same number. Create a new field with a clear name and unit, such as amount_minor_units alongside currency information, then migrate in a controlled manner.

## 8. Automated Breaking-Change Checks with Buf

Manual reviews easily miss changes across many .proto files. Buf provides linting and breaking-change detection to enforce contract rules in CI.

### 8.1. Choose the Appropriate Check Level

Buf provides four main categories:

| Category | Check Scope |
| --- | --- |
| FILE | Strictest; detects changes affecting generated source APIs per file |
| PACKAGE | Detects changes affecting generated source APIs per package |
| WIRE_JSON | Detects changes affecting binary wire or JSON |
| WIRE | Focuses only on binary wire encoding |

For schemas shared across multiple consumers with generated Java code, FILE is a conservative choice suited for catching source code changes as well. If the goal is only encoding control, WIRE_JSON is the minimum worth considering when JSON consumers exist. WIRE does not protect source APIs or JSON contracts.

### 8.2. Policy Configuration

Example Buf v2 configuration using the FILE category:

~~~yaml
version: v2

breaking:
  use:
    - FILE
~~~

Then run lint and compare the current schema against a released baseline:

~~~bash
buf lint
buf breaking --against '.git#branch=main'
~~~

This example uses the main branch as a baseline; in CI, replace it with the branch, tag, commit, or artifact that actually represents the released schema currently used by consumers. Do not compare against an unstable branch and conclude the production contract has no breaking changes.

### 8.3. Buf Does Not Replace Semantic Testing

A breaking checker can catch many errors in field numbers, types, cardinality, enums, packages, and RPC signatures. However, the tool cannot know that amount changed from dollars to cents, or that timeout_seconds is now interpreted as milliseconds. Semantic changes require design review and business-logic tests.

Similarly, if the system uses ProtoJSON, REST transcoding, or a gateway that transforms data, test the JSON path directly. A schema passing a binary wire check does not prove every gateway and JSON parser is compatible.

## 9. Testing Schema Evolution in a Spring gRPC Project

A reliable pipeline should check both code generation and cross-version communication.

### 9.1. Build-Time Checks

- Run protoc or the Protobuf/gRPC codegen plugin using a compiler version pinned in the build.
- Compile all generated Java code and modules consuming the stubs.
- Run Buf lint and breaking checks against the released baseline.
- Check other consumer languages if they share the same .proto files.
- Review diffs of .proto files and generated APIs whenever package or codegen options change.

### 9.2. Two-Way Compatibility Checks

Keep a set of old schemas as fixtures and generate messages with both old and new schemas. Verify these scenarios:

| Writer | Reader | What to Confirm |
| --- | --- | --- |
| Old schema | New schema | Old fields are read properly; new fields have proper defaults/presence |
| New schema | Old schema | Unknown fields are handled safely; business logic is not corrupted |
| Old client | New server | Old requests still work and responses do not break old clients |
| New client | Old server | Clients tolerate absent fields, unknown enums, or unsupported RPCs |

When messages pass through an intermediary process, also test parsing and re-serializing. If an application converts messages into DTOs, JSON, or builds new messages by copying fields individually, unknown fields may be dropped even though the Protobuf runtime preserves them during direct parse/serialize.

### 9.3. Testing Over Real gRPC Transport

Unit tests for serialize/parse validate wire format, but do not test the full service path. With Spring gRPC, write integration tests running server and client over the application's real transport to confirm:

- Method paths and service registration remain valid.
- Unary/streaming signatures work per contract.
- The status returned when calling an RPC not yet supported by the server is appropriate.
- Clients handle responses with missing fields and unknown enums.
- Deadlines, cancellation, and error mapping have not changed unexpectedly.

Include at least one test using stubs generated from the previous release's schema calling the new server. If the system supports new clients connecting to old servers, include a test for the reverse direction.

## 10. Checklist Before Finalizing Proto

### Contract and Semantics

- [ ] Consumers, client/server versions, and legacy version support windows are defined.
- [ ] Field names, units, timezones, defaults, and absence rules are clear.
- [ ] Fields needing explicit presence are identified.
- [ ] Enums have a 0 value meaning unspecified and client code has fallbacks for unknown values.
- [ ] Meanings of published fields or enum numbers have not changed.

### Binary Wire and Generated API

- [ ] Existing field numbers are preserved and not reused.
- [ ] Deleted fields/enum values have both numbers and names reserved.
- [ ] Types, cardinality, or oneof structures are not changed arbitrarily.
- [ ] Protobuf package, service, method, and Java package are evaluated separately.
- [ ] Request/response types and streaming shape of every RPC are verified.

### Rollout and Testing

- [ ] Deployment order is defined upfront for new request or response fields.
- [ ] New clients handle responses from old servers.
- [ ] New servers handle requests from old clients.
- [ ] CI runs lint, breaking checks, and code generation.
- [ ] Integration tests exist using schemas/stubs from the previous version.
- [ ] A plan exists to monitor usage and retire old APIs before removing contracts.

## Conclusion

Finalizing a .proto file means locking in how independent processes interpret data and invoke RPCs across multiple release cycles. Evaluate binary wire, JSON, generated source API, and business semantics as separate layers; identify the compatibility directions to protect; then design rollouts for version-skewed clients and servers. Immutable field numbers, reserving on deletion, enum fallbacks, and CI breaking-change checks let contracts evolve without forcing the entire system to upgrade at once.

## References

- [Protocol Buffers — Updating A Message Type](https://protobuf.dev/programming-guides/proto3/#updating): changing messages, wire-safe changes, field numbers, and unknown fields.
- [Protocol Buffers — Deleting Fields](https://protobuf.dev/programming-guides/proto3/#deleting): reserving field numbers and names after deletion.
- [Protocol Buffers — Enum](https://protobuf.dev/programming-guides/proto3/#enum): enum values, unknown values, and reserved values.
- [Protocol Buffers — Proto Best Practices](https://protobuf.dev/best-practices/dos-donts/): principles for keeping schemas and enums stable.
- [Buf — Detecting Breaking Changes](https://buf.build/docs/breaking/): FILE, PACKAGE, WIRE_JSON, and WIRE categories.
- [Buf — Breaking Change Rules](https://buf.build/docs/breaking/rules/): rules for checking fields, enums, oneofs, and RPCs.
