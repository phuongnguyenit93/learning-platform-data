# Testing Old Servers Against New Clients

## 1. Objectives

In a Spring gRPC system, clients and servers are typically built and deployed independently. A new client may be released before all servers are upgraded, or a new service may inadvertently connect to an old replica during a rolling deployment. In that situation, the new client must communicate with a server that only understands the old contract.

**Testing old servers against new clients** verifies that a client generated from the new schema still behaves safely when calling a server built from the old schema. This compatibility direction matters when clients deploy independently, when a load balancer still holds old replicas, or when a server rollback happens after new clients have been released.

What needs checking is not just whether requests parse. An old server can ignore new fields, process the request with old defaults, and return a successful response without executing the semantics the new client requested. Therefore, tests must verify both wire behavior and business outcomes.

After this lesson, you will be able to:

- Build a server fixture from an already published old schema/generated artifact.
- Call the old server with a new generated client over real gRPC transport.
- Verify new request fields ignored by the old server and assess their impact.
- Verify how the new client interprets responses missing new fields.
- Handle new enum values, oneof alternatives, and RPC methods unknown to the old server.
- Design capability detection, fallbacks, and safe rollouts.
- Integrate old-server/new-client tests into CI before releasing clients.

## 2. Test Scenario

Suppose Catalog v1 only supports query:

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

New clients are generated from a schema that adds category and pagination:

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
  string category = 2;
  optional int32 page_size = 3;
  string page_token = 4;
}

message SearchResponse {
  repeated string product_ids = 1;
  string next_page_token = 2;
}
```

The full method path stays identical:

```text
/catalog.v1.CatalogService/Search
```

The new client can build requests with `category` and `page_size`, while the old server only knows `query`. With Protobuf binary, the old parser usually reads known fields and keeps unfamiliar ones in unknown fields; old application code has no accessors to read `category` or `page_size`. The server may return a normal response following v1 search logic.

The new client parses the v1 response, though `next_page_token` is missing from the bytes. The new field's value will be its default; if it is an optional scalar, presence will be false. Hence the client must not assume a successful response means the server supported pagination.

## 3. Distinguishing Wire Compatibility from Feature Compatibility

| Question | Wire Compatibility | Feature/Behavior Compatibility |
|---|---|---|
| Can the request be parsed? | Potentially yes | Insufficient to conclude |
| Does the server understand new fields? | Not guaranteed | Must be verified |
| Does the server execute new semantics? | Not guaranteed | Must be verified |
| Can the client parse old responses? | Usually yes if additive | May not satisfy business requirements |
| Is a new method registered on the old server? | No if server lacks the method | Usually receives `UNIMPLEMENTED` |

An additive schema change may allow new clients to send requests to old servers without parse errors. Yet the old server does not automatically implement the new feature. If the client needs accurate pagination, category filtering, or a new security rule, ignored fields can produce wrong results or unexpected data exposure.

Classify each change before writing tests:

- **New optional fields:** old servers may ignore them; the client must know whether the server supports them.
- **New response fields:** old servers do not send them; the new client must handle absence.
- **New enum values:** old servers can parse numeric values in proto3, yet old code does not know their meaning.
- **New oneof alternatives:** old servers may see the oneof as unset.
- **New RPC methods:** old servers have no handler and typically return `UNIMPLEMENTED`.
- **Renamed package/service/method:** full method path changes; new clients call a new path unregistered on old servers.

## 4. How Old Servers Handle Requests with Unknown Fields

In Protobuf binary format, fields are identified by field number and wire type. If the parser encounters a field number missing from the old schema, the Protobuf runtime usually stores it as an unknown field instead of treating it as an error.

This allows a new message with added fields to still be parsed by old code, provided old fields retain their field numbers and wire types. However:

- The old handler only sees fields defined in the old generated code.
- Unknown fields never trigger new logic on their own.
- If the server converts the message into a domain object and builds another message, unknown fields may not survive that conversion.
- Gateways/proxies or custom parsers may enforce their own rules; test the actual path.
- Never reuse a removed field number for a different meaning.

Example of a new client sending:

```java
var request = NewSearchRequest.newBuilder()
        .setQuery("keyboard")
        .setCategory("electronics")
        .setPageSize(10)
        .build();
```

The old server only has generated classes with `query`:

```java
LegacySearchRequest legacyRequest =
        LegacySearchRequest.parseFrom(request.toByteArray());

assertEquals("keyboard", legacyRequest.getQuery());
assertTrue(legacyRequest.getUnknownFields()
        .hasField(2));
assertTrue(legacyRequest.getUnknownFields()
        .hasField(3));
```

This example uses two message classes from old and new schemas in a test fixture. In real applications, client and server are two processes; the test above only illustrates parser behavior. Unknown fields are preserved inside a Protobuf message if parsed and re-serialized directly, yet the application cannot filter by category from a field undefined in old generated code.

## 5. Risks When Old Servers Silently Ignore New Fields

This is the hardest bug to detect. The client sends a request successfully, the server returns status `OK`, yet results fail to honor the new options.

Examples:

- Client sends `category = electronics`; old server searches across all categories.
- Client sends `page_size = 10`; old server returns the entire list under the old limit.
- Client sends `sort_order = NEWEST`; old server still sorts by relevance.
- Client sends `include_archived = false`; old server uses a different default policy.

Do not infer feature support from status `OK`. The status only indicates the RPC completed under the server's current logic.

New clients need one of these mechanisms before relying on new fields:

1. **Capability check:** query the server via a stable RPC known to both old and new servers, if a capability contract was deployed earlier.
2. **Versioned endpoint/routing:** route new clients to a fleet guaranteed to support the required contract.
3. **Controlled feature rollout:** enable the feature only after server rollout finishes and all replicas are verified.
4. **Semantic fallback:** use the old calling pattern when business-equivalent and proven safe.

Metadata like `x-api-version` does not conjure capabilities out of thin air. Old servers may ignore unfamiliar metadata; clients must not treat sending a header as proof the server read or accepted that version.

## 6. New Clients Reading Responses from Old Servers

The old server only returns known fields:

```java
LegacySearchResponse response =
        LegacySearchResponse.newBuilder()
                .addProductIds("product-1")
                .addProductIds("product-2")
                .build();
```

The new client parses response bytes:

```java
NewSearchResponse response =
        NewSearchResponse.parseFrom(
                legacyResponse.toByteArray());

assertEquals(2, response.getProductIdsCount());
assertEquals("", response.getNextPageToken());
```

If `next_page_token` is an implicit-presence string, the getter returns an empty string when absent. If declared `optional`, the client can call `hasNextPageToken()` to distinguish absent from explicit empty.

The client must clearly define what a response missing a new field means:

- If absence means there is no next page, pagination can stop.
- If the feature requires the server to return a token, absence must be treated as unsupported server or invalid response.
- Never fabricate fake tokens or loop repeating the same request indefinitely.
- Never convert an old response into a new response with unguaranteed semantics.

For numeric or boolean fields, default values can look like valid business values. Use explicit presence when clients must distinguish “server omitted it” from “server sent `0`/`false`”.

## 7. New Enums and New Oneofs

### New Enum Values

Proto3 uses open enum semantics. When an old server receives a numeric enum value unknown to old generated code, the runtime may preserve the numeric value; Java enum getters return `UNRECOGNIZED` and numeric getters read the raw number. Yet old business logic may:

- Treat any unknown value as `UNSPECIFIED`.
- Fall into a `switch` default branch.
- Return `INVALID_ARGUMENT` even though the wire parser read it.
- Apply old behavior not equivalent to the new choice.

Therefore, do not send new enum values to old servers if the server must execute that value's semantics. Enable only after a capability check or routing to supporting servers.

### New Oneof Alternatives

Suppose the new client adds an alternative to a `oneof`. The old server does not recognize that new field; when parsed, the old `oneof` may appear in the `NOT_SET` state. If the old handler interprets `NOT_SET` as a default selection, the request may take another branch silently without error.

Tests must verify new clients do not send new alternatives to old servers before capability is confirmed. Do not test merely that the request serializes cleanly.

## 8. Calling New RPC Methods Against Old Servers

If a new client calls a method unregistered on an old server, gRPC typically returns:

```text
UNIMPLEMENTED
```

For example, the client stub already has:

```java
var response = newStub.getRecommendations(request);
```

yet the old server only registers `Search`. The server has no handler for the new full method path and terminates the call with `UNIMPLEMENTED`.

The client may fall back to an old method if the old method provides equivalent results. Fallbacks must:

- Have explicit conditions, never applying to every status.
- Run only while the old method remains supported.
- Preserve semantics, authorization, and data boundaries.
- Emit metrics showing fallbacks are occurring.
- Have an expiration or removal condition.

Never fall back automatically on `UNAVAILABLE`, `DEADLINE_EXCEEDED`, or `PERMISSION_DENIED`. These statuses have different causes; blind retry/fallback can create duplicate side effects or mask outages.

## 9. Capability Detection and Version Routing

A reliable approach is for the server to expose a pre-existing capability RPC:

```proto
message GetCapabilitiesRequest {}

message GetCapabilitiesResponse {
  repeated string capabilities = 1;
}

service CatalogService {
  rpc Search(SearchRequest) returns (SearchResponse);
  rpc GetCapabilities(GetCapabilitiesRequest)
      returns (GetCapabilitiesResponse);
}
```

If `GetCapabilities` already existed in the old contract, old servers can return legacy capabilities; new servers additionally return `pagination` or `category-filter`. New clients call this RPC before enabling new features.

If the capability RPC itself was only added in the new version, old servers will not know that method either and will return `UNIMPLEMENTED`. In that case, an established out-of-band discovery mechanism, versioned endpoints, or rollout configuration is needed.

Server reflection can help discover service/method descriptors if enabled and accessible, yet it does not prove the server supports the right business semantics or capabilities. Reflection is also not always enabled in production.

A capability response should describe features usable on that specific endpoint. If a load balancer distributes requests across replicas with differing capabilities, discovery must reflect the entire route or the system must enforce capability-based routing. Never let a new replica advertise v2 capabilities and then route the client's next call to an old replica.

## 10. Designing Safe Fallbacks in New Clients

A gateway can inspect capabilities and pick the right call:

```java
public SearchResult search(SearchCriteria criteria) {
    Capabilities capabilities = capabilityProvider.forTarget();

    if (capabilities.supports("category-filter")) {
        return callSearchWithCategory(criteria);
    }

    if (criteria.requiresCategoryFilter()) {
        throw new UnsupportedOperationException(
                "Target server does not support category filtering");
    }

    return callLegacySearch(criteria);
}
```

This is an illustrative skeleton; the capability provider needs per-target/endpoint caching, expiration, and refresh handling when the fleet changes. Never cache capabilities indefinitely because servers can be upgraded or rolled back.

If old servers do not support capability discovery, clients can be explicitly configured to use only the legacy contract for that endpoint. Avoid probing every new method and catching errors on every request to detect capabilities; that increases latency and generates intentional errors in telemetry.

Fallbacks are only valid when clients can express the request with the old API without losing critical semantics. If category filtering is mandatory, calling v1 `Search` without filters and filtering client-side is only safe when the client receives all relevant data, has proper authorization, and results were not truncated before filtering.

## 11. Building the Old-Server Fixture Properly

Tests are only valid when the server fixture is genuinely built from the old contract:

1. Fetch protos and generated server artifacts from an actual published release/tag.
2. Pin the exact `protoc`, gRPC Java plugin, and runtime of the old server.
3. Never regenerate the server fixture from the new schema.
4. Run the old server in a separate process if class names or runtimes collide with the new server.
5. Use the new generated client in another test process or an isolated fixture module.
6. Connect via localhost/container using a real gRPC channel.
7. Record versions, commits, and artifact checksums so the fixture is reproducible.

If a test runs both the old server and new client in the same JVM, generated classes may share identical fully qualified names. Changing the Java package in a fixture isolates classes, though it no longer represents the exact released binary artifact. For deployment-fidelity testing, prefer separate processes and the exact old artifacts/runtimes.

## 12. Old Server/New Client Integration Test

A basic test calls an old method that still exists:

```java
ManagedChannel channel = ManagedChannelBuilder
        .forAddress("localhost", oldServerPort)
        .usePlaintext()
        .build();

try {
    var newStub = NewCatalogServiceGrpc.newBlockingStub(channel)
            .withDeadlineAfter(2, TimeUnit.SECONDS);

    var request = NewSearchRequest.newBuilder()
            .setQuery("keyboard")
            .setCategory("electronics")
            .setPageSize(10)
            .build();

    var response = newStub.search(request);

    assertFalse(response.getProductIdsList().isEmpty());
    // Separately verify whether the server actually applied category/page size.
} finally {
    channel.shutdown();
    if (!channel.awaitTermination(5, TimeUnit.SECONDS)) {
        channel.shutdownNow();
    }
}
```

This test only proves the RPC completes and the response parses. It **does not prove** the old server applied `category` or `page_size`. To verify semantics, use a data fixture with products across multiple categories and counts exceeding the limit, then confirm the old server's actual behavior matches what the client accepts.

If the test expects the old server to filter by category when the v1 schema has no such concept, the correct outcome is that the feature is unsupported. The test should verify the client does not enable the feature and does not report false success.

## 13. Required Test Matrix

| Client | Server | Expected Outcome |
|---|---|---|
| Old | Old | Baseline works |
| New, using only old fields/methods | Old | Works per old semantics |
| New sending new request fields | Old | Server ignores fields; client does not assume feature was applied |
| New reading new response fields | Old | New fields absent/default; client handles explicitly |
| New sending new enum/oneof values | Old | Not enabled before server support; verify unknown behavior |
| New calling new RPC method | Old | `UNIMPLEMENTED` or route/capability blocks the call |
| New | New | New feature works properly |

Beyond the matrix above, verify:

- Status mapping and error trailers.
- Deadlines, cancellations, and retries.
- Authentication/authorization.
- Message sizes, compression, and metadata.
- Idempotency if the RPC has side effects.
- Clients do not cache capabilities past expiration.
- Load balancer does not mix unsupported replicas after clients enable the feature.

## 14. CI and Rollout Gate

CI should maintain a stable old-server fixture:

1. Build the new client from the current schema.
2. Start the frozen old server artifact.
3. Call old RPCs using the new stub over real transport.
4. Send new fields and verify the old server ignores them per expected wire behavior.
5. Verify the client interprets responses missing new fields properly.
6. Verify new RPCs return `UNIMPLEMENTED` or are not called when capability is absent.
7. Run behavioral tests for flows the client claims to support against old servers.
8. Archive test results and artifact versions as release evidence.

Never substitute a mock server for the old-server fixture. Mocks rarely reproduce the parser, service registration, method paths, runtime dependencies, or unknown-field behavior of old generated code.

When the new client requires a feature supported only by new servers, server rollout must finish before enabling the client feature. You can release the new client early with a disabled feature flag; turn it on only after every target confirms capability.

## 15. Common Pitfalls

| Symptom | Cause | How to Fix |
|---|---|---|
| RPC returns `OK` yet new filter doesn't work | Old server ignores new request fields | Capability check or keep feature disabled |
| New client receives empty page token | Old server omits new response field | Handle absence per contract |
| Client sends new enum yet server takes default branch | Old server doesn't understand enum semantics | Send only after capability confirmation |
| New `oneof` treated as `NOT_SET` | Old server doesn't know new alternative | Do not send new alternatives to old servers |
| New RPC returns `UNIMPLEMENTED` | Old server has not registered method | Deploy server first or use controlled fallback |
| Test passes yet server fixture is actually new | CI regenerated old fixture from new schema | Pin old artifact/proto and provenance |
| Capability check reports support yet request hits old replica | Discovery and load balancing inconsistent | Route by capability or roll out whole fleet |
| Fallback masks server errors | Falling back on all statuses or lacking metrics | Conditional fallback, metrics, and expiry |
| Client reports feature succeeded though server ignored it | Only checking status `OK` | Check selected capability and business results |

## 16. Hands-On Exercise

**Scenario:** Catalog server v1 is deployed in several environments. Client v2 is generated from a schema adding category filtering, `page_size`, and the `GetRecommendations` method. Temporarily, a load balancer can route clients to either v1 or v2 servers.

Perform the following:

1. Freeze the v1 server artifact along with the old release's protos, generated code, and runtime.
2. Build client v2 from the new schema and keep its runtime compatible with the client's generated code.
3. Run the old server in a separate process; call `Search` from client v2 over a real `ManagedChannel`.
4. Send `category`/`page_size` and verify server v1 ignores them; the client must not claim the feature was applied.
5. Verify responses missing `next_page_token` are handled per the presence/default contract.
6. Call `GetRecommendations` against server v1 and verify `UNIMPLEMENTED`; test fallback if equivalent semantics exist.
7. Test that new enum/oneof values are not sent before capability confirmation.
8. Test capability discovery via a stable endpoint or route config; simulate mixed replicas.
9. Add old-server/new-client tests to the CI release gate.
10. Enable v2 features only once all target routes support them and metrics confirm selected capabilities.

**Completion criteria:** the server fixture is genuinely an old artifact; the new generated client calls over real transport; unknown request/response fields are handled accurately; new features are not marked successful when servers ignore them; new methods and enum/oneof values have clear handling; rollouts never send new features to unsupported replicas.

## 17. Key Takeaways

Testing old servers against new clients must use a genuinely old server artifact and a new generated client. With additive fields, old servers can parse requests and ignore unfamiliar fields; old responses omit new fields so new clients observe defaults or absent values. This can produce an `OK` RPC status without executing the feature the client requested. New enums/oneofs and new RPC methods carry their own risks; unregistered methods typically return `UNIMPLEMENTED`. Verify capabilities before enabling features, keep conditional fallbacks, test over real transport, and use an old-server fixture as a release gate. If new semantics require a new server, deploy/route supporting servers before clients depend on them.
