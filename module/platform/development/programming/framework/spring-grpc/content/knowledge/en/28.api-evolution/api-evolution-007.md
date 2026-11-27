# Version Negotiation via Metadata

## 1. Objectives

A Spring gRPC application may call multiple server versions during a rolling deployment. Clients can also be released independently and support different contract levels. If clients still call the same RPC path, metadata can carry version or capability information so the server selects the appropriate behavior for each RPC.

**Version negotiation via metadata** is the process where a client sends the API version it wants to use in the metadata of a gRPC call; the server checks support, selects the appropriate version, and may respond with the chosen version. This mechanism is useful when the same RPC path and message shape can serve multiple compatible semantics.

After this lesson, you will be able to:

- Distinguish API version, client build version, and RPC method version.
- Send version/capability via per-RPC metadata.
- Validate and select the version on the server using a `ServerInterceptor`.
- Use `Context` to pass the selected version to the handler.
- Return the selected version or supported version list in response metadata/trailers.
- Keep compatible defaults for old callers that omit version metadata.
- Recognize when metadata negotiation is insufficient and a separate service/package version is needed.
- Test negotiation, rollouts, and cases where client and server share no common version.

## 2. Where Does Metadata Live in an RPC?

gRPC transmits metadata alongside the headers/trailers of an HTTP/2 stream. Metadata is control information accompanying an RPC, such as request IDs, authentication credentials, or version info. It is not a field inside the Protobuf message.

Example of what a client sends:

```text
x-api-version: v2
x-client-version: 4.8.1
x-request-id: 7c1...
```

The three values have distinct meanings:

| Metadata | Meaning | Used to Select Contract? |
|---|---|---|
| `x-api-version` | API version requested by client for the RPC | Yes |
| `x-client-version` | Build version of the application/client | Not automatically; primarily for observability |
| `x-request-id` | Correlation ID of a request | No |

Do not infer API version from `x-client-version`. One client build can support multiple API versions; conversely, many different client builds may use the same API version.

Metadata keys must be lowercase. ASCII values use `Metadata.ASCII_STRING_MARSHALLER`; binary keys carry the `-bin` suffix and use a binary marshaller. Do not define custom keys starting with `grpc-`, as that prefix is reserved for the gRPC protocol. Keep metadata small; do not use it to transmit payloads or huge capability lists.

Metadata belongs to each individual RPC stream, not the entire `ManagedChannel`. Multiple RPCs with different versions can multiplex over the same channel and HTTP/2 connection.

## 3. Choosing a Negotiation Strategy

Before writing an interceptor, specify exactly what the server and client will negotiate.

### Requesting a Specific Version

This is the simplest strategy:

```text
x-api-version: v2
```

The server accepts `v2` if it has a matching implementation; otherwise, it returns a clear error. This works well when the client already knows the exact contract version it needs.

### Sending a List of Client-Supported Versions

A client can send a prioritized list:

```text
x-api-versions: v2,v1
```

The server picks the first version in the list that it supports and returns `x-api-selected-version`. Both sides must agree on parsing rules, precedence order, version formatting, and how invalid values are handled.

Do not compare arbitrary version strings lexicographically. If using ranges or semantic versions, define clear grammar and selection algorithms. For RPC contracts, explicit major versions like `v1`, `v2` are typically easier to operate.

### Capability Negotiation

If only a few independent features need toggling, the client can send capabilities:

```text
x-api-capabilities: pagination,sort-v2
```

The server validates supported capabilities and responds with the selected set. This avoids creating excessive major versions for small features, though combinations can grow quickly. Only use this when capabilities have independent semantics, can be tested, and have clear compatibility rules.

In this lesson, examples use an exact version request `x-api-version` to keep the algorithm straightforward.

## 4. Compatibility Rules for Old Callers

An old client may not send version metadata because the API did not require it previously. If the new server requires the header immediately upon deploy, old callers will fail even though their Protobuf requests remain valid.

Define explicit defaults:

| Request Metadata | Server Handling |
|---|---|
| No `x-api-version` | Select legacy semantics, e.g. `v1` |
| `x-api-version: v1` | Select `v1` |
| `x-api-version: v2` | Select `v2` if server supports it |
| Empty or invalid version | Return `INVALID_ARGUMENT` |
| Well-formed version not supported by server | Return negotiation error along with supported versions list |

The default for missing metadata is part of the behavioral contract. Do not change the default from `v1` to `v2` before callers opt in. If the default must change, run a planned caller migration or use a separate service version.

## 5. Sending Version from a Spring gRPC Client

Create a metadata key with a lowercase name and ASCII marshaller:

```java
private static final Metadata.Key<String> API_VERSION =
        Metadata.Key.of(
                "x-api-version",
                Metadata.ASCII_STRING_MARSHALLER);
```

A gateway can attach the version per call:

```java
@Component
public class CatalogGateway {
    private final CatalogServiceGrpc.CatalogServiceBlockingStub baseStub;

    public CatalogGateway(
            @Qualifier("catalogChannel") ManagedChannel channel) {
        this.baseStub = CatalogServiceGrpc.newBlockingStub(channel);
    }

    public SearchResponse searchV2(SearchRequest request) {
        Metadata headers = new Metadata();
        headers.put(API_VERSION, "v2");

        var versionedStub = baseStub.withInterceptors(
                MetadataUtils.newAttachHeadersInterceptor(headers));

        return versionedStub
                .withDeadlineAfter(800, TimeUnit.MILLISECONDS)
                .search(request);
    }
}
```

The example uses gRPC Java's `MetadataUtils.newAttachHeadersInterceptor`. Utility APIs may differ or be marked deprecated depending on dependency versions; in that case, use your project's equivalent `ClientInterceptor`. Metadata must be scoped appropriately to the call/version and not mutated concurrently across threads.

Generated stubs are immutable; `withInterceptors` and `withDeadlineAfter` produce derived stubs. You do not need to create separate `ManagedChannel` instances just to send `v1` or `v2`. Channels remain reusable when target and transport/security configurations match.

Never put bearer tokens or secrets into `x-api-version`. Authentication should use call credentials or dedicated secure metadata mechanisms; client-sent version info is merely a request hint, not proof of authorization.

## 6. Validating and Selecting Version on the Server

A `ServerInterceptor` can inspect metadata before the request reaches the handler. The example below:

- Selects `v1` when the caller omits the version.
- Accepts `v1` and `v2`.
- Rejects unsupported versions before running the handler.
- Stores the selected version in gRPC `Context`.
- Adds the selected version to response headers.

```java
package dev.example.catalog.server;

import io.grpc.Context;
import io.grpc.Contexts;
import io.grpc.ForwardingServerCall;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;
import java.util.Set;

public final class ApiVersionInterceptor implements ServerInterceptor {
    static final Context.Key<String> API_VERSION_CONTEXT =
            Context.key("api-version");

    private static final Metadata.Key<String> REQUESTED_VERSION =
            Metadata.Key.of(
                    "x-api-version",
                    Metadata.ASCII_STRING_MARSHALLER);

    private static final Metadata.Key<String> SELECTED_VERSION =
            Metadata.Key.of(
                    "x-api-selected-version",
                    Metadata.ASCII_STRING_MARSHALLER);

    private static final Metadata.Key<String> SUPPORTED_VERSIONS =
            Metadata.Key.of(
                    "x-api-supported-versions",
                    Metadata.ASCII_STRING_MARSHALLER);

    private static final Set<String> SUPPORTED = Set.of("v1", "v2");
    private static final String LEGACY_DEFAULT = "v1";

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata requestHeaders,
            ServerCallHandler<ReqT, RespT> next) {

        String requested = requestHeaders.get(REQUESTED_VERSION);
        String selected = requested == null
                ? LEGACY_DEFAULT
                : requested;

        if (!selected.matches("v[1-9][0-9]*")) {
            call.close(
                    Status.INVALID_ARGUMENT.withDescription(
                            "API version must use the vN format"),
                    new Metadata());
            return new ServerCall.Listener<ReqT>() {};
        }

        if (!SUPPORTED.contains(selected)) {
            Metadata trailers = new Metadata();
            trailers.put(SUPPORTED_VERSIONS, "v1,v2");
            call.close(
                    Status.FAILED_PRECONDITION.withDescription(
                            "Requested API version is not supported"),
                    trailers);
            return new ServerCall.Listener<ReqT>() {};
        }

        ServerCall<ReqT, RespT> forwardingCall =
                new ForwardingServerCall.SimpleForwardingServerCall<>(call) {
                    @Override
                    public void sendHeaders(Metadata responseHeaders) {
                        responseHeaders.put(SELECTED_VERSION, selected);
                        super.sendHeaders(responseHeaders);
                    }
                };

        Context context = Context.current()
                .withValue(API_VERSION_CONTEXT, selected);
        return Contexts.interceptCall(
                context, forwardingCall, requestHeaders, next);
    }
}
```

This is an illustrative interceptor for a service with a fixed set of versions. In production, scope the interceptor to the exact services/methods needing negotiation and source the supported list from controlled configuration. If a service only supports `v1`, do not advertise `v2` in its supported set.

`FAILED_PRECONDITION` expresses that the server cannot execute the call with the requested version under its current configuration. Another status can be used if the API publishes a specific convention; what matters is keeping the mapping stable. `UNIMPLEMENTED` is generally appropriate when the full method path has no handler, whereas failed negotiation on an existing method is a different situation.

Register the interceptor using the global/server interceptor mechanism of your Spring gRPC starter. Annotation names or registration configs vary by starter and version; do not manually create an extra gRPC server when the framework owns the server.

## 7. Passing the Selected Version into the Handler

The handler reads the version from `Context` to choose a policy:

```java
@Override
public void search(
        SearchRequest request,
        StreamObserver<SearchResponse> observer) {
    String apiVersion =
            ApiVersionInterceptor.API_VERSION_CONTEXT.get();

    try {
        SearchResponse response;
        if ("v1".equals(apiVersion)) {
            response = searchService.searchLegacy(request);
        } else if ("v2".equals(apiVersion)) {
            response = searchService.searchV2(request);
        } else {
            observer.onError(Status.INTERNAL
                    .withDescription("API version context is missing")
                    .asRuntimeException());
            return;
        }

        observer.onNext(response);
        observer.onCompleted();
    } catch (IllegalArgumentException ex) {
        observer.onError(Status.INVALID_ARGUMENT
                .withDescription("invalid search request")
                .asRuntimeException());
    }
}
```

`Contexts.interceptCall` binds the context to the RPC's listener and callbacks. If the application offloads work to an executor, ensure the context is propagated to asynchronous tasks using the proper gRPC/Context mechanism; never store the version in a mutable field on a singleton service.

Important: this dispatch pattern is only suitable when both semantics can share the same method path and compatible request/response shapes. If `v2` needs a structurally different Protobuf message, create a separate service/package version or a new method. Metadata does not make an old server understand fields absent from its schema, nor does it change the full method path.

## 8. Returning the Selected Version to the Client

The server can reply with:

```text
x-api-selected-version: v2
```

This header informs the client which version the server actually applied. This is valuable when the client sends a prioritized list of versions or when the server falls back to a default for old callers.

If negotiation is rejected, the server can return a trailer:

```text
x-api-supported-versions: v1,v2
```

The client can read trailers from `StatusRuntimeException`:

```java
try {
    return versionedStub.search(request);
} catch (StatusRuntimeException ex) {
    Metadata trailers = Status.trailersFromThrowable(ex);
    String supported = trailers == null
            ? null
            : trailers.get(SUPPORTED_VERSIONS);

    log.warn("API negotiation failed: status={}, supported={}",
            ex.getStatus().getCode(), supported);
    throw ex;
}
```

To read `x-api-selected-version` in response headers of a successful call, the client can use a `ClientInterceptor` wrapping `ClientCall.Listener.onHeaders`. Do not rely on error trailers to determine the version of a successful call.

Clients should not automatically downgrade on every error. Only consider choosing an alternate version when status and supported-version metadata indicate negotiation failed, the alternate version is supported, and fallback semantics are appropriate.

## 9. How Does Metadata Negotiation Differ from Service Versioning?

| Criterion | Metadata Negotiation | Versioned Service/Package |
|---|---|---|
| RPC path | Preserves path | Differs by package/service |
| Protobuf request/response | Must share compatible shape or deliberate envelope | Can have distinct messages per version |
| Semantic selection | Based on per-RPC metadata | Determined by method path |
| Old client omitting version | Server needs a legacy default | Client explicitly calls v1 path |
| Observability | Must log/record selected version | Distinguishable directly from full method name |
| Best suited for | Negotiable semantic/capability changes on same contract | Breaking schemas or major semantic shifts |

If v1 and v2 have different request/response structures, a versioned service is usually clearer and safer. For example, `/catalog.v1.CatalogService/Search` and `/catalog.v2.CatalogService/Search` already carry the version in the method path; adding `x-api-version` could become redundant or conflicting.

Metadata negotiation is also not automatic content negotiation like in HTTP frameworks. gRPC does not auto-select versions simply because a client sends a header; the application must validate, decide, dispatch, and respond.

## 10. Negotiation with Capabilities or Version Lists

When clients support multiple versions, a prioritized list can be used instead of a single version. The algorithm should be explicitly defined:

1. Client sends `x-api-versions: v2,v1` in preference order.
2. Server validates the list is well-formed and contains no anomalous duplicates.
3. Server selects the first version supported by the current service/method.
4. Server attaches the selected version to `Context` and response headers.
5. If no common version exists, return `FAILED_PRECONDITION` with the supported list.

Do not parse the list by picking the string with the largest number unless a formal versioning rule is established. For capabilities, the server must reply with the accepted capability set; the client must check whether its required capabilities are included.

Do not cram a huge feature matrix into metadata. When capabilities depend on one another or alter request/response shapes, a Protobuf negotiation RPC or versioned service can be easier to test.

## 11. Metadata Negotiation in Streaming RPCs

Metadata is sent when the RPC starts. For client streaming, server streaming, or bidirectional streaming, the version is selected for the entire stream.

- Do not switch API versions between messages within the same stream.
- If the client needs to change versions, close/cancel the old stream and open a new RPC with new metadata.
- For long-lived streams, account for version support windows and when servers stop serving old versions.
- If a stream needs to resume, cursors/resume tokens must maintain semantics compatible with the chosen version.

A stream can outlive a server rollout window. Do not retire a version while valid streams are still running if doing so violates the committed contract; use clear drain policies and time limits.

## 12. Limits, Security, and Operations

Metadata is suited for small control information, not payload storage:

- Keep keys short, lowercase, and values bounded.
- Do not pass Protobuf JSON, large data lists, or personal info in version headers.
- Do not use the protocol-reserved `grpc-` prefix.
- Respect header/metadata size limits across clients, proxies, and servers.
- Avoid logging all metadata indiscriminately as it may contain tokens or sensitive data.

Client-sent version metadata is untrusted input. The server must validate it and select only deployed versions. API version does not replace authentication/authorization; never grant elevated privileges simply because a caller requested `v2`.

Metrics to record:

| Metric/Dimension | Purpose |
|---|---|
| Full method name | Know which RPC is being called |
| Requested API version | Know what callers request |
| Selected API version | Know what the server actually applies |
| Negotiation failure/status | Detect when client and server lack a common version |
| Client version | Isolate caller cohorts needing migration |
| Latency by selected version | Compare performance across semantics |

Version is a low-cardinality dimension when values are controlled. Never use request IDs, user IDs, or arbitrary metadata values as metric labels.

## 13. Rollout and Testing

Safe rollout order:

1. Deploy servers supporting the new version while keeping legacy defaults for requests without metadata.
2. Confirm every replica behind the load balancer supports the new version.
3. Test old clients omitting metadata and verify they still receive old semantics.
4. Enable new clients sending explicit versions in small cohorts.
5. Monitor requested/selected versions, negotiation failures, statuses, and latency.
6. Expand rollout as metrics stabilize; keep time-boxed fallback if needed.
7. Only retire the old version after callers and old streams have migrated, per support policy.

Minimum test matrix:

| Client Metadata | Server Supports | Expected Result |
|---|---|---|
| No header | v1, v2 | Selects legacy default v1 |
| `v1` | v1, v2 | Selects v1 |
| `v2` | v1, v2 | Selects v2 |
| `v3` | v1, v2 | `FAILED_PRECONDITION`, returns supported versions |
| Empty/invalid value | v1, v2 | `INVALID_ARGUMENT` |
| `v2` | v1 only | Negotiation fails; never silently pretend v2 ran |

Additional tests:

- Two concurrent RPCs on the same channel request different versions; verify context does not leak across calls.
- Server properly returns `x-api-selected-version`.
- Old callers without headers continue working after deploy.
- Unsupported versions are rejected before executing business logic.
- Streaming RPCs keep the same version from start to finish.
- Clients only fall back when negotiation status permits and fallback semantics are verified.
- Interceptor is properly registered in the Spring gRPC server and not registered twice.

## 14. Common Pitfalls

| Symptom | Cause | How to Fix |
|---|---|---|
| Old callers fail after enabling negotiation | Server requires header | Define legacy default when header is absent |
| Client sends v2 but server runs v1 | Old server ignores unrecognized metadata | Deploy supporting servers first or use capability routing |
| Version mixes up between concurrent requests | Stored version in mutable singleton field | Use per-call gRPC `Context` |
| Client assumes v2 ran while server used default | Neither returned nor checked selected version | Return and observe `x-api-selected-version` |
| Failed negotiation retried indefinitely | Not distinguishing version error from transient error | Use clear status codes and conditional fallback |
| Headers too large or contain sensitive data | Using metadata as payload/log context | Only send short version/capability values |
| Using metadata instead of schema versioning | Assuming server auto-understands new messages | Use service/package versions when shapes are incompatible |
| API version treated as access control | Trusting client-declared headers | Authenticate principals and authorize independently |
| Stream changes semantics mid-flight | Trying to update version after RPC starts | Select version at stream start; open new RPC to switch |

## 15. Hands-On Exercise

**Scenario:** Catalog has a `Search` RPC whose request/response shape can remain compatible. The new server supports two semantics: v1 sorts by relevance, while v2 allows sorting by date and category filtering. Old clients send no metadata; new clients want to request v2.

Perform the following:

1. Define `x-api-version`, `x-api-selected-version`, and `x-api-supported-versions` as ASCII metadata keys.
2. Implement a client gateway sending `v2` per RPC while reusing the channel.
3. Implement a server interceptor selecting `v1` when the header is absent, accepting `v1`/`v2`, and rejecting other versions.
4. Put the selected version in gRPC `Context`; have the handler dispatch to policy v1 or v2.
5. Return the selected version in response headers and supported versions in trailers when negotiation fails.
6. Test two concurrent RPCs on the same channel with different versions.
7. Test old callers without headers and new clients calling a server without v2 support.
8. Add metrics for requested/selected versions, statuses, and latency; avoid logging sensitive metadata.
9. Define the boundary: if v2 requires a Protobuf message with a different shape, switch to a versioned service/package instead of relying on metadata.

**Completion criteria:** version is selected per RPC, legacy defaults do not break old callers, server echoes the selected version, context never leaks across calls, unsupported versions yield clear statuses, and an appropriate strategy is chosen when schemas are incompatible.

## 16. Key Takeaways

Metadata negotiation lets clients request an API version or capability per RPC while sharing a `ManagedChannel`. Clients send the version via metadata; a server interceptor validates, picks the version, puts the choice into `Context`, and can reply via headers/trailers. Old callers omitting headers need a clear legacy default. Version metadata is client-controlled input, not authentication, and it does not make new schemas compatible with old servers. Use this mechanism when the same RPC path/message shape can support multiple semantics; if Protobuf contracts or method paths differ, a versioned service/package is usually clearer.
