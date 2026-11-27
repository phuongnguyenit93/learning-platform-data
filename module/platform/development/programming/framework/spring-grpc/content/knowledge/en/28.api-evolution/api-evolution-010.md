# Testing Old Clients Against New Servers

## 1. Objectives

In Spring gRPC, clients and servers are usually built, released, and deployed independently. A server may be upgraded first to support new fields or behaviors while many clients still run generated code from an old contract. Even an apparently additive Protobuf change can cause old clients to fail at runtime or receive unexpected results.

**Testing old clients against new servers** verifies that a client built from the old schema and generated code can still call the upgraded server over real gRPC transport with compatible requests, responses, statuses, and semantics. This is a critical test before rolling out a new server broadly.

After this lesson, you will be able to:

- Build a client fixture from an already published old Protobuf version.
- Call a new Spring gRPC server via a real channel and old generated stubs.
- Verify full method paths, old requests, and defaults for new fields.
- Verify old clients handle responses containing new fields or new enum values.
- Distinguish wire compatibility from runtime and behavioral compatibility.
- Test statuses, deadlines, authorization, and regressions of old methods.
- Design CI so old clients are never accidentally regenerated from new schemas.

## 2. Scenario to Test

Suppose Catalog previously published contract v1:

```proto
syntax = "proto3";

package catalog.v1;
option java_package = "dev.example.catalog.v1";
option java_multiple_files = true;

service CatalogService {
  rpc Search(SearchRequest) returns (SearchResponse);
}

message SearchRequest {
  string query = 1;
}

message SearchResponse {
  repeated string product_ids = 1;
}
```

Old clients were built from this schema. Later, the server is upgraded to support page limits and tokens:

```proto
syntax = "proto3";

package catalog.v1;
option java_package = "dev.example.catalog.v1";
option java_multiple_files = true;

service CatalogService {
  rpc Search(SearchRequest) returns (SearchResponse);
}

message SearchRequest {
  string query = 1;
  optional int32 page_size = 2;
  string page_token = 3;
}

message SearchResponse {
  repeated string product_ids = 1;
  string next_page_token = 2;
}
```

The full method path remains:

```text
/catalog.v1.CatalogService/Search
```

Old clients send `query` at tag 1. The new server parses the request; the two new fields are absent from the bytes and must be handled with compatible defaults. The new server's response may include tag 2 unknown to old clients; the old parser must read the fields it knows and safely ignore unknown fields.

Testing must prove both directions: **old request → new server** and **new response → old client**.

## 3. What Must Stay Unchanged

### Full Method Path

gRPC routes by package, service, and method name. Adding fields to messages does not change the path if these names stay the same. If the new server changes the package to `catalog.v2` or renames the service/method, old clients still call the v1 path and may receive `UNIMPLEMENTED`.

### Field Numbers and Wire Types

Old clients send known field numbers. The new server must continue interpreting those fields per published wire types and semantics. Never reuse removed field numbers; reserve both numbers and names in the new schema.

Do not assume two types sharing the same wire type can be swapped safely. For instance, `int32` and `int64` both use varint yet have different value ranges; `int32` and `sint32` both use varint wire type yet encode negative numbers differently. Changing field types or meanings must be evaluated separately.

### Defaults When New Fields Are Absent

Old requests cannot send fields that did not exist when they were generated. The new server must handle absence:

- Implicit-presence scalars return the Protobuf default value.
- `optional` scalars can use `hasX()` to detect the field was not sent.
- Message fields have presence; the server can check `hasX()`.
- Absent `repeated`/`map` fields appear as empty collections.

If the new `page_size` is `optional`, the server can apply a business default of 25 when `hasPageSize()` is false. Never require old callers to send new fields.

### New Response Fields

Old clients parsing new responses will lack accessors for new fields. They only use known fields. Unknown fields are typically retained in Protobuf Java's `UnknownFieldSet` and can survive parse/re-serialize round trips, yet applications must not rely on old clients understanding or executing semantics of new fields.

## 4. Freezing the Old Generated Client

This is the most critical condition of the test. If CI regenerates the client fixture from the new schema, the test no longer verifies an old client.

A trustworthy fixture should:

1. Take proto files from an actually released tag/version.
2. Use the exact old generated Java artifact or regenerate with the exact pinned old compiler/plugin versions.
3. Never update the fixture's proto source when the new server schema changes.
4. Record the version and source commit/release of the fixture so tests remain reproducible.
5. Confirm the fixture's classpath uses a runtime compatible with the old generated code.

Two common organizational approaches exist:

| Approach | When Suitable | Notes |
|---|---|---|
| Separate fixture module | Monorepo that can build multiple modules | Package old generated client as a test-only artifact |
| Separate process | Wanting to mirror independent deployments close to production | Run old client with its old classpath and runtime |

If two schemas share the same Protobuf package and service name, avoid putting two sets of generated source with identical Java fully qualified class names into one source set. You can build the old fixture as a separate module/artifact using a separate Java package while keeping the Protobuf package/service/method identical so the full method path matches; or run the old client in a separate process. The Java package does not determine the gRPC method path.

If the goal is testing the exact released client binary, prefer running a separate process with the exact old JAR and runtime dependencies. Changing `java_package` alone to a test-only package makes in-process tests convenient without altering the wire path, yet that fixture is no longer the original binary Java artifact; treat it as supplemental wire/generated-shape testing, not a substitute for testing the real artifact.

Never use a new client and merely omit new fields from the request to simulate an old client. That fails to test the generated API, parser, and runtime of the actual old client version.

## 5. Runtimes on Both Sides Do Not Need the Same Version

Client and server are two independent processes. Old clients can use the Protobuf Java runtime and gRPC Java runtime from an old release; the new server can use newer runtimes. Both sides communicate over the wire protocol and do not share a Java classpath.

What must be ensured:

- Old generated client is compatible with the runtime in the old client process.
- New generated server is compatible with the runtime in the new server process.
- Both sides adhere to the same wire contract and gRPC protocol.
- TLS, compression, message size limits, and transport settings are supported on both sides.

You do not need to force the new server to use the same Java library version as the old client just because they communicate. However, if you put both sets of generated code into a single test process, you must manage classpaths and class names to avoid collisions.

## 6. Running an Old Client Against a New Spring gRPC Server

The test should start a real Spring server with the new service implementation. The client fixture uses blocking or async stubs generated from the old schema.

Example invocation from a test:

```java
ManagedChannel channel = ManagedChannelBuilder
        .forAddress("localhost", serverPort)
        .usePlaintext()
        .build();

try {
    var oldStub =
            dev.example.catalog.legacy.CatalogServiceGrpc
                    .newBlockingStub(channel)
                    .withDeadlineAfter(2, TimeUnit.SECONDS);

    var oldRequest =
            dev.example.catalog.legacy.SearchRequest.newBuilder()
                    .setQuery("keyboard")
                    .build();

    var oldResponse = oldStub.search(oldRequest);

    assertFalse(oldResponse.getProductIdsList().isEmpty());
} finally {
    channel.shutdown();
    if (!channel.awaitTermination(5, TimeUnit.SECONDS)) {
        channel.shutdownNow();
    }
}
```

The example assumes the old generated client is packaged in a separate test-only package, while its schema keeps the old package/service/method so the full method path matches the server. `serverPort` must be the actual port of the Spring gRPC test server; random port configuration and port retrieval depend on the starter/version in use. Never start an extra server manually alongside the server managed by Spring.

The `dev.example.catalog.legacy` package in the example is an isolated fixture package to avoid class collisions with the generated server. If using the exact old artifact with the same fully qualified class names as the new generated server, run the client in a separate process instead of altering the published artifact's package.

In integration tests, use real transport and real service beans. You may mock repositories or external dependencies behind the application service, but do not mock stubs or bypass gRPC server registration when testing transport compatibility.

## 7. Testing Old Requests and New Defaults

The new server may receive old requests lacking `page_size`. The handler must apply a compatible default:

```java
int pageSize = request.hasPageSize()
        ? request.getPageSize()
        : LEGACY_DEFAULT_PAGE_SIZE;
```

With requests generated from the new schema, unit tests can check both states:

```java
var absent = SearchRequest.newBuilder()
        .setQuery("keyboard")
        .build();

assertFalse(absent.hasPageSize());

var explicitZero = SearchRequest.newBuilder()
        .setQuery("keyboard")
        .setPageSize(0)
        .build();

assertTrue(explicitZero.hasPageSize());
```

Old-client integration tests prove the server accepts requests missing the new field and selects the published default. Testing only with the new builder creating an absent request is insufficient because it does not prove the old generated client actually sends the expected wire payload.

Do not let the new server return `INVALID_ARGUMENT` solely because `page_size` is absent if old clients cannot know about that field. If new business logic requires a mandatory input, keep a compatible default, add a new method, or version the contract.

## 8. Testing New Responses with Old Parsers

The new server may additionally return `next_page_token`. Old clients lack a getter for this field, yet must parse successfully and still read `product_ids`:

```java
var response = oldStub.search(oldRequest);

assertEquals(
        List.of("product-1", "product-2"),
        response.getProductIdsList());
```

To verify the server actually emits the new field, use a new client in a separate test or inspect response bytes with a new parser. You cannot ask an old generated client to read an accessor that does not exist.

An independent wire test can verify:

1. New server builds a response with both old and new fields.
2. Serialize response to bytes.
3. Old generated parser reads bytes successfully.
4. Old fields retain their exact values.
5. New parser reads the new fields.

Unknown fields should not be used to pass mandatory semantics to old clients. Old clients will have no idea what to do with those fields.

## 9. New Enum Values and Old Client Assumptions

If the new server returns a numeric enum value unknown to old clients, generated Java Protobuf usually represents the enum getter as `UNRECOGNIZED`; numeric accessors like `getStatusValue()` allow reading the raw value. Old client code must handle this case instead of assuming enums only contain known values.

Example old schema:

```proto
enum OrderState {
  ORDER_STATE_UNSPECIFIED = 0;
  ORDER_STATE_PENDING = 1;
  ORDER_STATE_COMPLETED = 2;
}
```

New server adds:

```proto
enum OrderState {
  ORDER_STATE_UNSPECIFIED = 0;
  ORDER_STATE_PENDING = 1;
  ORDER_STATE_COMPLETED = 2;
  ORDER_STATE_ON_HOLD = 3;
}
```

An old client receiving numeric value 3 may return the `UNRECOGNIZED` enum constant. If old code uses a `switch` and defaults to treating every unknown value as an unrecoverable error, the new response can cause business failures even though wire parsing succeeded.

Therefore, before the server begins returning new enum values, verify all relevant old clients have safe fallback behavior. For critical states, keep a legacy response mapping or only emit new enum values after callers have upgraded.

## 10. Testing Method Paths and Service Registration

Old clients call the full method path derived from the Protobuf package, service, and method. Tests should verify this path still exists on the new server.

Scenarios:

| Server Change | Impact on Old Clients |
|---|---|
| Add fields to request/response, keep package/service/method | Path unchanged; can be wire-compatible |
| Add new method, keep old method | Old clients keep calling old method |
| Change Protobuf package | Full method path changes; old clients may get `UNIMPLEMENTED` |
| Change service name | Full method path changes |
| Change method name | Full method path changes |
| Remove old handler | Old clients may get `UNIMPLEMENTED` |

Do not only check generated descriptors at compile time. Call through a running Spring server to prove the bean is registered and the route actually exists.

## 11. Testing Statuses, Deadlines, and Authorization

Compatibility is not just receiving a successful response. Old clients may rely on statuses and metadata returned by the old server.

Minimum checks:

- Malformed requests still return the committed status, typically `INVALID_ARGUMENT`.
- Non-existent resources still have stable status mappings.
- Unauthorized callers still receive `PERMISSION_DENIED` or `UNAUTHENTICATED` as appropriate.
- Short deadlines still terminate per contract; the server stops unintended side effects after cancellation.
- Old clients omitting new version metadata are still handled with legacy defaults.
- New response metadata/trailers do not break old parsers.

Never switch a status to a different code just because server code was refactored. Callers may branch, retry, or display messages based on it.

## 12. Testing Behavioral Regressions

An old request may parse flawlessly yet the new server returns different results. Characterization tests for old semantics are needed:

| Behavior | What to Verify |
|---|---|
| Defaults | Absent new fields still apply old defaults |
| Ordering | Result order is unchanged if promised by the old contract |
| Empty results | Empty lists keep the same status and shape as before |
| Pagination | New token/page semantics are not applied unexpectedly to old callers |
| Validation | Valid v1 requests are not rejected by v2-only rules |
| Idempotency | Retrying old requests produces no duplicate side effects |
| Authorization | Permissions are neither broadened nor narrowed unexpectedly |

If the new server changes default sorting or validation for all callers, old-client tests catch regressions that a schema diff cannot reveal.

## 13. Organizing Tests in CI

A pipeline can be structured into layers:

1. **Proto compatibility check:** inspect schema changes, field numbers, wire types, and method paths.
2. **Old client fixture build:** build the old client artifact from frozen protos or use a published binary artifact.
3. **New server build:** generate code from the new schema and build the Spring gRPC application.
4. **Integration test:** boot the new server and call it using old generated stubs.
5. **Behavioral regression:** verify old defaults, responses, statuses, and side effects.
6. **Mixed-version matrix:** test client/server combinations needed during rollout.
7. **Release gate:** block releasing the new server if mandatory old-client tests fail.

Do not take old protos from the current folder, run code generation with a new plugin, and call that an old client. The fixture must represent an already released artifact. If you must regenerate, pin the exact old schema and toolchain, record provenance, and inspect generated diffs.

An old client test running in the same JVM as the new server suffices if generated classes do not collide and runtimes on each side are cleanly managed. Otherwise, run the client fixture in a separate process over localhost/container to reproduce independent classpaths and runtimes.

## 14. Test Matrix

| Client | Server | Goal |
|---|---|---|
| Old | Old | Pre-upgrade baseline |
| Old | New | Core test: old client/new server |
| New | New | Verify new contract |
| New | Old | Verify new fields/methods behave as planned, typically unknown fields or `UNIMPLEMENTED` |

For server-before-client rollouts, the old/new pair is especially critical. Old clients must continue working against the new server throughout the support window. If new clients must also run against old servers, that is a separate backward-compatibility requirement needing its own tests.

## 15. Common Pitfalls

| Symptom | Cause | How to Fix |
|---|---|---|
| Test passes but isn't actually an old client | Fixture was regenerated from new schema | Freeze old artifact/proto and old toolchain |
| Old client receives `UNIMPLEMENTED` | Server changed package/service/method or dropped handler | Keep old full method path and handler |
| Old client fails to parse response | Changed wire type or incompatible payload | Check field numbers/wire types and schema history |
| Old client reads new field as default | Server expects caller to understand new field | Keep legacy defaults; don't require old callers to send new fields |
| Results change despite successful wire parse | Server changed defaults or semantics | Add behavioral regression tests |
| Old client breaks on new enum | Switch logic assumes exhaustive enum | Add `UNRECOGNIZED`/fallback branch or keep old mapping |
| Generated class collisions in tests | Two schemas share Java package/class name | Separate modules, Java packages, or processes |
| Tests rely on hardcoded ports | Parallel tests or port conflicts | Use random ports and read port from test server |
| Runtime mismatch in fixture | Old generated code runs with wrong runtime in test process | Pin matching runtime or run a separate process |
| Unit tests pass yet server doesn't route | Only mocked handlers/stubs | Run Spring gRPC server integration tests |

## 16. Hands-On Exercise

**Scenario:** Catalog v1 clients are widely deployed. The new server adds optional `page_size` and `next_page_token` while preserving the `Search` RPC. Some old clients cannot upgrade this month.

Perform the following:

1. Fetch the exact released v1 proto/generated artifact and freeze it as the old-client fixture.
2. Build the new Spring gRPC server from the schema containing `page_size` and `next_page_token`.
3. Verify Protobuf package, service name, method name, and full method path are unchanged.
4. Boot the new server on a random test port; call it using the old blocking stub over a real `ManagedChannel`.
5. Verify the server handles requests missing `page_size` with a compatible default.
6. Verify the old client reads `product_ids` even when responses include the new `next_page_token`.
7. Test v1 statuses, deadlines, authorization, ordering, and empty-result behavior.
8. If the new server adds enum values, test that old clients receive `UNRECOGNIZED` and handle it safely.
9. Run old client/old server baseline and old client/new server in CI; enforce as a release gate.
10. Roll out the server only after old-client integration and behavioral regression tests pass.

**Completion criteria:** the fixture genuinely uses old generated code; the client calls the new Spring server over real transport; old requests are handled with proper defaults; new responses parse cleanly; method paths, statuses, and old semantics are preserved; CI can reproduce the test.

## 17. Key Takeaways

Testing old clients against new servers must use truly old generated client artifacts rather than regenerating fixtures from new schemas. Keep the Protobuf package/service/method so the full method path stays unchanged; the new server must handle absent new fields with compatible defaults, and old clients must parse responses containing unknown fields. Test new enums, statuses, deadlines, authorization, and behavioral regressions—not merely serialize/parse. Client and server Java runtimes can differ in version because they talk over the wire, yet generated code must stay compatible with the runtime inside its own process. A Spring gRPC integration test over a real channel, paired with a frozen old fixture, provides a reliable release gate before rolling out new servers.
