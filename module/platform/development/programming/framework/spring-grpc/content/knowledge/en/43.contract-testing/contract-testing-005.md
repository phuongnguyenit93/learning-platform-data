# Verifying Metadata Contracts

In Spring gRPC, protobuf defines request/response bodies, while gRPC metadata carries control information accompanying the RPC such as correlation ID, tenant context, authentication credentials, tracing context, and supplemental information in response headers/trailers. Metadata does not have its own proto schema, so key names, value types, or send timing can change while code still compiles.

Metadata contract tests protect the keys/values agreed upon between client and server: keys have the right names and types, required metadata is present, values are validated properly, duplicates have clear semantics, response headers/trailers are sent at the right time, and sensitive data is not exposed. This lesson focuses on testing metadata at the Spring gRPC transport boundary.

## 1. Where Does Metadata Live in an RPC?

An RPC has three main metadata regions:

| Region | Direction | Timing | Common API |
| --- | --- | --- | --- |
| Request headers | Client → Server | When the call starts, before the first message | `ClientCall.start` and server interceptors |
| Initial response headers | Server → Client | Before the first response message | `ServerCall.sendHeaders`; client listener `onHeaders` |
| Trailers | Server → Client | When the call finishes, with the final status | `ServerCall.close`; client listener `onClose` |

Request metadata typically carries correlation ID, tenant ID, credentials, or trace context. Initial response headers can carry server version or request ID for client log correlation. Trailers are suitable for call-completion info such as error reason or quota metadata if that is part of the contract.

Metadata differs from protobuf messages:

- Metadata belongs to the transport and can be processed by interceptors before the service receives the request body.
- Protobuf messages are business data with schemas, field numbers, types, and compatibility rules.
- Do not move business fields such as `product_id`, `quantity`, or payload content into metadata just so interceptors can read them.

## 2. Rules for Naming Metadata Keys and Value Types

gRPC metadata keys use lowercase ASCII names, typically formatted like `x-request-id`, `x-tenant-id`, or `authorization`. Keys for binary values must end with `-bin`. Do not create keys starting with `grpc-`; that prefix is reserved for the protocol/runtime.

In gRPC Java, the key's marshaller type determines how values are encoded/decoded:

```java
static final Metadata.Key<String> REQUEST_ID =
        Metadata.Key.of("x-request-id", Metadata.ASCII_STRING_MARSHALLER);

static final Metadata.Key<String> TENANT_ID =
        Metadata.Key.of("x-tenant-id", Metadata.ASCII_STRING_MARSHALLER);

static final Metadata.Key<byte[]> SIGNATURE =
        Metadata.Key.of(
                "x-payload-signature-bin",
                Metadata.BINARY_BYTE_MARSHALLER);

static final Metadata.Key<String> WARNING =
        Metadata.Key.of("x-warning", Metadata.ASCII_STRING_MARSHALLER);
static final Metadata.Key<String> SERVER_VERSION =
        Metadata.Key.of("x-server-version", Metadata.ASCII_STRING_MARSHALLER);
static final Metadata.Key<String> SERVICE_REGION =
        Metadata.Key.of("x-service-region", Metadata.ASCII_STRING_MARSHALLER);
```

ASCII metadata uses `ASCII_STRING_MARSHALLER`; do not assume this marshaller accepts arbitrary Unicode. Binary metadata uses `BINARY_BYTE_MARSHALLER`; the gRPC runtime handles the wire representation, so there is no need to manually base64-encode values before putting them.

Metadata usually has size limits at the client, server, or proxy. Only include short values needed for transport; large data, long lists, or business objects belong in the protobuf body or a referenced resource.

## 3. Defining Cardinality and Semantics for Each Key

A metadata key may appear multiple times. The contract must specify whether a key is single-valued or multi-valued:

| Key | Suggested Cardinality | Semantics |
| --- | --- | --- |
| `x-request-id` | Single value | Unique ID for an RPC |
| `x-tenant-id` | Single value | Authenticated tenant context |
| `authorization` | Single value | Credentials per the security contract |
| `x-feature-flag-bin` | Multiple values if defined | Binary option; requires ordering/duplicate rules |
| `x-warning` | Multiple values | Independent warnings |

If a key is only allowed once, the server should reject duplicates or clearly define which value is used. Do not rely on accidental ordering of duplicates. If a key is multi-valued, read it via `Metadata.getAll(key)` and check the set/order per the contract instead of only calling `Metadata.get(key)`.

Example reading repeated metadata:

```java
Iterable<String> warnings = headers.getAll(WARNING);
List<String> received = warnings == null
        ? List.of()
        : StreamSupport.stream(warnings.spliterator(), false).toList();

assertEquals(List.of("stale-cache", "partial-result"), received);
```

Do not use the same key sometimes as an ASCII string and sometimes as binary bytes. The key and marshaller are part of the contract; changing the `-bin` suffix or value type can make clients/servers unable to read metadata.

For single-valued keys such as request ID, tests should verify the value count is exactly one rather than only reading an arbitrary value:

```java
Iterable<String> requestIds = headers.getAll(REQUEST_ID);
List<String> values = requestIds == null
        ? List.of()
        : StreamSupport.stream(requestIds.spliterator(), false).toList();
assertEquals(1, values.size());
assertFalse(values.get(0).isBlank());
```

## 4. Attaching Request Metadata from a Client Interceptor

A client interceptor is the right place to add cross-cutting metadata such as request ID or trace context:

```java
public final class RequestIdClientInterceptor implements ClientInterceptor {
    private final Supplier<String> requestIds;

    public RequestIdClientInterceptor(Supplier<String> requestIds) {
        this.requestIds = requestIds;
    }

    @Override
    public <ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
            MethodDescriptor<ReqT, RespT> method,
            CallOptions callOptions,
            Channel next) {
        ClientCall<ReqT, RespT> delegate = next.newCall(method, callOptions);
        return new ForwardingClientCall.SimpleForwardingClientCall<>(delegate) {
            @Override
            public void start(Listener<RespT> listener, Metadata headers) {
                if (headers.get(REQUEST_ID) == null) {
                    headers.put(REQUEST_ID, requestIds.get());
                }
                super.start(listener, headers);
            }
        };
    }
}
```

An interceptor may be shared across multiple RPCs; therefore do not store the current request ID in a mutable field. Generate the ID in `start` or retrieve a call-scoped value from `Context`. If the caller already supplied a request ID, preserve that value per published policy; if the interceptor always overwrites it, document that clearly as contract behavior.

For authentication, prefer `CallCredentials` or the framework's security integration to supply per-call credentials and support asynchronous refresh. Do not hard-code bearer tokens into singleton interceptors and do not log authorization metadata.

## 5. Verifying Request Metadata on the Server

Server interceptors observe request metadata before the handler receives messages:

```java
public final class RequestMetadataInterceptor implements ServerInterceptor {
    static final Context.Key<String> REQUEST_ID_CONTEXT =
            Context.key("request-id");

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {
        String requestId = headers.get(REQUEST_ID);
        String tenantId = headers.get(TENANT_ID);

        if (requestId == null || requestId.isBlank()) {
            call.close(Status.INVALID_ARGUMENT.withDescription(
                    "x-request-id is required"), new Metadata());
            return new ServerCall.Listener<>() {};
        }
        if (tenantId == null || tenantId.isBlank()) {
            call.close(Status.INVALID_ARGUMENT.withDescription(
                    "x-tenant-id is required"), new Metadata());
            return new ServerCall.Listener<>() {};
        }

        Context context = Context.current().withValue(REQUEST_ID_CONTEXT, requestId);
        return Contexts.interceptCall(context, call, headers, next);
    }
}
```

This is an example contract requiring two metadata keys. In a real application, the tenant ID must be bound to the authenticated principal; do not trust a client-supplied tenant ID without checking access permissions. Missing/invalid metadata returns the contract status, while internal details are only recorded in controlled server logs.

## 6. Checking Initial Response Headers and Trailers

The server sends initial headers via `ServerCall.sendHeaders(headers)` before the first response message. Trailers are sent when closing the call via `ServerCall.close(status, trailers)`. Low-level client listeners receive them via `onHeaders` and `onClose`.

A server interceptor can attach metadata at both points:

```java
ServerCall<ReqT, RespT> forwarding =
        new ForwardingServerCall.SimpleForwardingServerCall<>(call) {
            @Override
            public void close(Status status, Metadata trailers) {
                trailers.put(SERVICE_REGION, "ap-southeast");
                super.close(status, trailers);
            }
        };

ServerCall.Listener<ReqT> listener = next.startCall(forwarding, headers);
Metadata initialHeaders = new Metadata();
initialHeaders.put(SERVER_VERSION, "catalog-v2");
forwarding.sendHeaders(initialHeaders);
return listener;
```

In this example, server version goes in initial headers and region goes in trailers. Only add metadata at the proper point; do not call `sendHeaders` multiple times and do not modify trailers after `close` has been called.

The generated `StreamObserver` API does not directly expose response headers/trailers to callers. If clients need to inspect them, use a `ClientInterceptor` wrapping `ClientCall.Listener` or a client API with explicit metadata support.

## 7. Client Interceptor Capturing Metadata for Contract Tests

A client interceptor can record initial headers and trailers into a test-specific holder:

```java
final class MetadataCaptureInterceptor implements ClientInterceptor {
    final AtomicReference<Metadata> responseHeaders = new AtomicReference<>();
    final AtomicReference<Metadata> responseTrailers = new AtomicReference<>();

    private static Metadata copy(Metadata source) {
        Metadata target = new Metadata();
        target.merge(source);
        return target;
    }

    @Override
    public <ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
            MethodDescriptor<ReqT, RespT> method,
            CallOptions callOptions,
            Channel next) {
        ClientCall<ReqT, RespT> delegate = next.newCall(method, callOptions);
        return new ForwardingClientCall.SimpleForwardingClientCall<>(delegate) {
            @Override
            public void start(Listener<RespT> listener, Metadata headers) {
                super.start(
                        new ForwardingClientCallListener.SimpleForwardingClientCallListener<>(listener) {
                            @Override
                            public void onHeaders(Metadata received) {
                                responseHeaders.set(copy(received));
                                super.onHeaders(received);
                            }

                            @Override
                            public void onClose(Status status, Metadata trailers) {
                                responseTrailers.set(copy(trailers));
                                super.onClose(status, trailers);
                            }
                        },
                        headers);
            }
        };
    }
}
```

Metadata is copied because objects received in callbacks should not be retained and shared outside the call's lifecycle. Each test should have its own capture holder; do not share a single `AtomicReference` across concurrent RPCs without keying results per call.

## 8. Provider Contract Testing for Requests, Headers, and Trailers

An in-process test can verify required request metadata, initial response headers, and trailers:

```java
@Test
void metadataContractIsPreservedAcrossRpc() {
    MetadataCaptureInterceptor capture = new MetadataCaptureInterceptor();
    ManagedChannel testChannel = InProcessChannelBuilder
            .forName(serverName)
            .intercept(MetadataUtils.newAttachHeadersInterceptor(requestHeaders))
            .intercept(capture)
            .build();

    CatalogServiceGrpc.CatalogServiceBlockingStub testStub =
            CatalogServiceGrpc.newBlockingStub(testChannel)
                    .withDeadlineAfter(2, TimeUnit.SECONDS);

    Product response = testStub.getProduct(
            GetProductRequest.newBuilder().setProductId("P-100").build());

    assertEquals("P-100", response.getProductId());
    assertEquals("req-123", serverCapture.requestId.get());
    assertEquals("tenant-7", serverCapture.tenantId.get());
    assertEquals("req-123", capture.responseHeaders.get().get(REQUEST_ID));
    assertEquals("catalog-v2", capture.responseHeaders.get().get(SERVER_VERSION));
    assertEquals("ap-southeast", capture.responseTrailers.get().get(SERVICE_REGION));
    testChannel.shutdownNow();
}
```

This is an illustrative test skeleton; `serverName`, `requestHeaders`, `serverCapture`, and server-side interceptors are created in the fixture. `requestHeaders` contains `REQUEST_ID=req-123` and `TENANT_ID=tenant-7`. `serverCapture` is a test-local holder recording the two values received by the server interceptor. If using `MetadataUtils.newAttachHeadersInterceptor`, ensure request metadata has the right keys/types. You can use the custom client interceptor in section 4 to test dynamically generated request metadata.

Test missing or invalid metadata separately:

```java
StatusRuntimeException error = assertThrows(
        StatusRuntimeException.class,
        () -> stubWithoutTenant.getProduct(request));
assertEquals(Status.Code.INVALID_ARGUMENT, error.getStatus().getCode());
```

Besides status, verify the business handler is not invoked when required request metadata is invalid. With Spring integration tests, start the application context to verify the interceptor is actually registered on the server.

## 9. Security, Privacy, and Compatibility of Metadata

Metadata often passes through many intermediaries such as proxies, gateways, tracing agents, and log interceptors. Therefore:

- Do not log authorization, cookies, tokens, signatures, or metadata containing sensitive data.
- Do not use metadata as a substitute for authentication mechanisms; verify credentials and principals at the security boundary.
- Do not trust `x-tenant-id` without verifying the tenant belongs to the principal's permissions.
- Do not put personal information or large payloads in headers/trailers.
- Use an allowlist of logged keys; redact sensitive values.
- Set limits on value size and count; test behavior when limits are exceeded.

Metadata keys are a contract requiring versioning just like proto fields. Changing key `x-request-id` to `request-id` can cause older clients to lose correlation. When changing keys, support both old and new keys concurrently during the transition period, define precedence if both appear, and remove the old key after consumers upgrade.

Do not use reserved HTTP/2/gRPC protocol headers or keys starting with `grpc-`. Avoid assuming all proxies preserve arbitrary metadata; integration tests through gateways/proxies need to verify which keys are actually forwarded.

## 10. Metadata Contract Checklist

- [ ] Request headers, initial response headers, and trailers are clearly distinguished.
- [ ] Each key has a lowercase name, marshaller type, and `-bin` suffix where appropriate.
- [ ] Single-valued/multi-valued cardinality and duplicate behavior are defined.
- [ ] Required metadata is validated before running the use case.
- [ ] Client interceptors add call-scoped metadata without storing request state in mutable fields.
- [ ] Tenant/identity metadata is bound to the authenticated principal.
- [ ] Response headers are sent before the first message; trailers are sent only on close.
- [ ] Tests capture headers/trailers via `ClientCall.Listener` and copy `Metadata`.
- [ ] Tests verify status for missing/invalid metadata and ensure no side effects.
- [ ] Credentials or sensitive metadata are never logged.
- [ ] Size/count limits exist and are tested through gateways/proxies when present.
- [ ] Metadata key changes have a compatibility/deprecation plan.

**Self-Check**

**Question 1.** How does metadata differ from the protobuf request body?

*Answer:* Metadata is transport-level information accompanying the call and can be read by interceptors before the service processes messages. The protobuf body holds business data with its own schema and field compatibility rules.

**Question 2.** When must a metadata key end with `-bin`?

*Answer:* When the value is binary bytes using `BINARY_BYTE_MARSHALLER`. For ASCII strings, use `ASCII_STRING_MARSHALLER`; do not manually base64-encode bytes before inserting into binary metadata.

**Question 3.** How do initial response headers differ from trailers?

*Answer:* Initial headers are sent before the first response message; trailers are sent at the same time the server closes the RPC with the final status. Clients receive them in `onHeaders` and `onClose`.

**Question 4.** Why should you not only use `headers.get(key)` for potentially repeated metadata?

*Answer:* A key can have multiple values. Multi-valued contracts should read via `getAll(key)` and check cardinality/order; if single-valued, duplicates must be validated.

**Question 5.** Should you trust a client-sent tenant ID in metadata?

*Answer:* Not unless it is bound to an authenticated principal. Metadata is just client input; the server must verify the caller is authorized to act within that tenant.

Metadata contract testing protects the information accompanying RPCs across all three moments: request headers, initial response headers, and trailers. Clearly define keys/types/cardinality, validate in interceptors, test via generated stubs and `ClientCall` listeners, and protect credentials/tenant context. This enables Spring gRPC clients and servers to maintain correlation, security context, and metadata semantics across upgrades.
