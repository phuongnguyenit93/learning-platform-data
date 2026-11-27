# Context and Metadata in the Adapter

In **SPRING_GRPC**, the gRPC service adapter receives protobuf requests, reads call-associated information, converts data into application commands, and invokes use cases. Two key mechanisms at this boundary are **gRPC Metadata** and **gRPC Context**. Metadata carries information over the wire alongside the RPC; Context holds call-scoped data inside the processing process.

Adapters commonly use interceptors to read Metadata, authenticate or normalize information, and place verified values into Context. Service implementations and callbacks can read Context to obtain the request ID, tenant, principal, deadline, or cancellation state without passing transport parameters through every method.

## 1. How Do Metadata and Context Differ?

**Metadata** is a collection of key-value pairs sent with an RPC as HTTP/2 headers or trailers. Clients use metadata to send authorization tokens, trace context, request IDs, or tenant hints. The server reads metadata in an interceptor before dispatching to the service.

**Context** is gRPC Java's internal propagation mechanism. Context holds call-scoped values while also supporting deadlines and cancellation. Context is not serialized and sent over the network; it is propagated during RPC processing within a single process.

| Characteristic | Metadata | Context |
| --- | --- | --- |
| Scope | Travels over the wire with the RPC | Internal to the handling process |
| Where typically read | Client/server interceptors, call listeners | Service methods, callbacks, interceptors |
| Data | Key-value pairs with marshallers | Typed key-values and cancellation/deadline |
| Purpose | Transmit headers/trailers | Propagate request-scoped state |
| Automatic bridging | Does not automatically appear in Context | Not automatically sent to another peer |

A metadata key such as `x-request-id` can be read by an interceptor and placed into `io.grpc.Context`. That is an explicit bridge performed by the application; gRPC does not automatically turn all metadata into Context values.

## 2. Metadata Key Conventions and Data Types

Metadata keys must use lowercase ASCII. Custom keys typically use hyphens, such as `x-request-id` or `x-tenant-id`. Keys containing binary data must end with `-bin` and use a binary marshaller.

Declare keys once as constants:

```java
import io.grpc.Metadata;

public final class GrpcMetadataKeys {
    private GrpcMetadataKeys() {}

    public static final Metadata.Key<String> REQUEST_ID =
            Metadata.Key.of("x-request-id",
                    Metadata.ASCII_STRING_MARSHALLER);

    public static final Metadata.Key<String> TENANT_HINT =
            Metadata.Key.of("x-tenant-id",
                    Metadata.ASCII_STRING_MARSHALLER);

    public static final Metadata.Key<byte[]> BINARY_CONTEXT =
            Metadata.Key.of("x-context-bin",
                    Metadata.BINARY_BYTE_MARSHALLER);
}
```

Use a marshaller matching the data type. Do not manually encode byte arrays into arbitrary strings and place them in an ASCII key when the protocol already supports binary metadata.

Metadata is not the place to carry large business payloads. Keep headers small and avoid sending JSON objects or long permission lists through metadata. Business payloads belong in protobuf requests; metadata is for control information and context.

## 3. Bridging Metadata into Context with a ServerInterceptor

An interceptor runs before the service method and can create a new Context containing data read from metadata. Use `Contexts.interceptCall` so the Context takes effect during dispatch and server call callbacks.

```java
import io.grpc.Context;
import io.grpc.Contexts;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;

public final class RequestContextInterceptor
        implements ServerInterceptor {

    public static final Context.Key<String> REQUEST_ID =
            Context.key("request-id");
    public static final Context.Key<String> TENANT_HINT =
            Context.key("tenant-hint");

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String requestId = headers.get(GrpcMetadataKeys.REQUEST_ID);
        String tenantHint = headers.get(GrpcMetadataKeys.TENANT_HINT);

        Context context = Context.current();
        if (requestId != null) {
            context = context.withValue(REQUEST_ID, requestId);
        }
        if (tenantHint != null) {
            context = context.withValue(TENANT_HINT, tenantHint);
        }

        return Contexts.interceptCall(context, call, headers, next);
    }
}
```

This example puts the request ID and tenant hint into Context. A client-supplied tenant hint is still untrusted data. Authentication or the application service must verify that the tenant falls within the authenticated principal's scope before using it to access data. Never turn a client-sent header into a verified identity.

If required metadata is missing or malformed, the interceptor can close the call with an appropriate status before dispatch. Request IDs are usually for observability, so the server may generate a fallback ID; required tenants or credentials must be validated according to the security contract.

## 4. Reading Context in the Service Implementation

After the interceptor sets Context, the service method can read the defined keys:

```java
@Override
public void getStock(
        StockRequest request,
        StreamObserver<StockReply> observer) {

    String requestId =
            RequestContextInterceptor.REQUEST_ID.get();

    String tenantHint =
            RequestContextInterceptor.TENANT_HINT.get();

    GetStockQuery query = new GetStockQuery(
            verifiedTenantFor(tenantHint), request.getSku());

    StockView result = applicationService.getStock(query);
    observer.onNext(replyMapper.toProto(result));
    observer.onCompleted();
}
```

This example illustrates reading Context in the adapter. In a layered architecture, convert the required values into a plain Java application context type, such as `RequestMetadata` or `ExecutionContext`, and pass it explicitly to the use case. Do not let application/domain import `io.grpc.Context` solely to read a tenant or request ID.

A service method must never store Context in a field of a singleton Spring bean. Context belongs to a specific RPC; storing it in a field can cause two concurrent requests to see each other's data.

## 5. A Tenant Hint Is Not a Verified Tenant

The `x-tenant-id` header is only a client-suggested value. If the server uses it to select a database schema, tenant partition, or access rights, it must verify the caller has permissions for that tenant.

A safe flow:

1. The authentication interceptor verifies the token or client certificate.
2. The server extracts the principal and claims from the trusted authentication result.
3. The adapter checks whether the tenant hint is within the set of tenants the principal is allowed to access.
4. Only the verified tenant is placed into Context or converted into the application request context.
5. The application service still performs any required business authorization checks.

Do not trust headers such as `x-user-id`, `x-role`, or `x-is-admin` if they are merely sent by the client. Identity and permissions must come from verified authentication/authorization mechanisms.

The ordering and composition of the authentication interceptor and context interceptor must be consistent. If a context interceptor runs before authentication finishes, it should only hold raw data; verified principals/tenants must be placed into Context after verification.

## 6. Sending Metadata from a gRPC Client

A client can attach fixed metadata to a channel using an interceptor—for example, workload name or client version:

```java
Metadata headers = new Metadata();
Metadata.Key<String> clientName = Metadata.Key.of(
        "x-client-name", Metadata.ASCII_STRING_MARSHALLER);
headers.put(clientName, "order-worker");

ManagedChannel channel = ManagedChannelBuilder
        .forTarget("inventory.internal:9090")
        .useTransportSecurity()
        .intercept(MetadataUtils.newAttachHeadersInterceptor(headers))
        .build();
```

This interceptor attaches the same set of headers to calls over the channel. Do not use this approach for a request ID that must vary per RPC, because the request ID would stay fixed to the attached metadata object.

For per-call dynamic values, use a client interceptor that builds metadata in `start`, or use `CallCredentials` for authentication credentials. Request ID interceptor example:

```java
public final class RequestIdClientInterceptor
        implements ClientInterceptor {

    private final Supplier<String> requestIdSupplier;

    public RequestIdClientInterceptor(
            Supplier<String> requestIdSupplier) {
        this.requestIdSupplier = requestIdSupplier;
    }

    @Override
    public <ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
            MethodDescriptor<ReqT, RespT> method,
            CallOptions callOptions,
            Channel next) {

        return new ForwardingClientCall
                .SimpleForwardingClientCall<>(
                        next.newCall(method, callOptions)) {
            @Override
            public void start(
                    Listener<RespT> listener,
                    Metadata headers) {
                headers.put(
                        GrpcMetadataKeys.REQUEST_ID,
                        requestIdSupplier.get());
                super.start(listener, headers);
            }
        };
    }
}
```

The example requires the corresponding gRPC Java imports and a `Supplier` generating a fresh ID per call. Do not overwrite a request ID already generated by a tracing framework; align on a single generation source and propagation rules across the application.

## 7. Propagating Metadata When Calling Downstream Services

An intermediary service sometimes receives an RPC and then calls another gRPC service. Do not blindly copy all inbound metadata to downstream calls.

Propagate only meaningful keys permitted to be shared:
- Trace context following OpenTelemetry/W3C standards.
- Internal correlation/request IDs.
- Verified tenant accepted by the downstream contract.
- Credentials appropriate for the identity the intermediary service uses when calling downstream.

Do not forward the caller's raw authorization token if the architecture requires the intermediary service to use its own service identity or token exchange. Do not forward internal keys, hop-by-hop headers, or keys of unknown origin. With multiple downstream services, each target may have a different audience and credentials.

Tracing should use OpenTelemetry instrumentation and the corresponding propagator to inject/extract trace context. Do not invent custom headers to replace `traceparent` if the system has standardized on W3C Trace Context.

## 8. Context Holds Deadlines and Cancellation

gRPC Context does not only hold application-added data. The current RPC Context can also carry the deadline and cancellation status.

Reading the deadline:

```java
Context context = Context.current();
Deadline deadline = context.getDeadline();

if (deadline != null && deadline.isExpired()) {
    throw new IllegalStateException("RPC deadline expired");
}
```

Checking cancellation before continuing resource-intensive work:

```java
if (Context.current().isCancelled()) {
    return;
}
```

You can register a listener to stop work when the client cancels the RPC or the deadline expires:

```java
Context context = Context.current();
context.addListener(
        cancelledContext -> cancellationToken.cancel(),
        Runnable::run);
```

Here `cancellationToken` is an application abstraction that signals running work to stop. The listener does not automatically roll back the database or undo already-committed side effects. The use case must check cancellation at safe points and release resources appropriately.

Do not treat deadlines as a client-declared metadata value. A gRPC deadline is part of call options/protocol propagation and is reflected in the server's Context.

## 9. Propagating Context to Async Executors

The current Context is accessible inside callbacks managed by gRPC. However, when the application offloads work to an executor, do not assume every executor automatically carries Context across threads.

Capture Context when receiving the call and wrap the task:

```java
Context grpcContext = Context.current();

executor.execute(grpcContext.wrap(() -> {
    String requestId =
            RequestContextInterceptor.REQUEST_ID.get();
    worker.process(requestId);
}));
```

You can use `Context.currentContextExecutor(executor)` if you want the executor to automatically wrap tasks submitted under the current Context. Choose an approach suited to the lifecycle and ensure tasks do not keep running and producing side effects after the request has been cancelled.

Context propagation does not imply propagation of all other thread-locals. MDC logging, Spring SecurityContext, and transaction context have their own mechanisms. If you need to carry them across executors, configure the corresponding mechanism; do not assume `io.grpc.Context` copies everything automatically.

## 10. Context and Transactions Are Not the Same Mechanism

Context propagates request-scoped data and cancellation/deadlines; Spring transactions manage transactional resources. They have different lifecycles and propagation rules.

- `Context.current()` does not open a database transaction.
- `@Transactional` does not automatically inject gRPC metadata into the application service.
- Context cancellation does not automatically roll back a committed transaction.
- JDBC/JPA transactions are typically thread-bound; Context can be wrapped across an executor, but transactions do not automatically follow along.
- When calling an application method on a worker thread, open the transaction via the Spring proxy on that thread if the operation needs a transaction.

If a use case needs a request ID or tenant, pass an explicit application context. If a use case needs a transaction, place the transaction boundary on the application service. Do not use Context as a service locator to access repositories, Spring beans, or every request dependency.

## 11. Protecting Data and Bounding Metadata

Metadata can be recorded in logs, proxies, or tracing systems. Therefore:

- Do not send passwords, private keys, refresh tokens, or secrets in metadata.
- Do not log raw Authorization headers or access tokens.
- Do not trust unverified tenant/user/role headers.
- Keep metadata small; oversized headers may be rejected by transport/proxies.
- Use binary keys ending in `-bin` for binary data.
- Maintain an allowlist of keys permitted to be forwarded downstream.
- Use request IDs for tracing, not as credentials or proof of authorization.
- Avoid placing sensitive personal data into correlation IDs or baggage.

When authentication info must be transmitted, use TLS and appropriate credential mechanisms such as gRPC CallCredentials or Spring gRPC's security integration. Metadata is merely a carrier for credentials, not a credential verifier itself.

## 12. Testing Metadata and Context

An adapter test suite should verify both metadata transmission and context isolation:

1. Send `x-request-id` from the client; verify the service reads the same value via the Context key.
2. Omit the request ID; verify the server generates a fallback or handles it per contract.
3. Send an unauthorized tenant hint; verify the request is rejected before accessing tenant data.
4. Send two concurrent RPCs with different request IDs; verify no Context leaks between calls.
5. Cancel an RPC or let its deadline expire; verify the listener/cancellation signal fires.
6. Dispatch work to an executor; verify Context is wrapped and the request ID remains intact.
7. Call downstream; verify only allowlisted metadata is propagated.
8. Verify logs do not contain raw tokens or secrets.

Context-bridge tests can use an in-process server/channel to send metadata and assert the values received by the service. In-process transport suits interceptor/context logic; it does not replace integration tests verifying TLS, HTTP/2, or proxy propagation.

## 13. Common Pitfalls

| Symptom/mistake | Cause | Fix |
| --- | --- | --- |
| Service cannot read metadata | Header not sent or key/marshaller mismatch | Use shared constant keys and inspect interceptors |
| `Context.Key.get()` returns `null` | Interceptor did not attach value or metadata absent | Check registration order and fallback policy |
| Multiple calls share the same request ID | Fixed metadata attached channel-wide | Generate metadata per call |
| Spoofed tenant header | Trusting client-sent data as identity | Verify against principal/claims before use |
| Context lost in executor | Task runs on an unwrapped thread | Use `Context.wrap` or a context-aware executor |
| Context leaks across requests | Storing request state in a singleton field or improper attach/detach | Use `Contexts.interceptCall` and per-RPC Context keys |
| Downstream receives inappropriate token | Forwarding all inbound metadata | Allowlist keys and use audience/identity-scoped credentials |
| Client times out while server keeps running | Work does not check cancellation | Propagate cancellation signals to the operation |
| Logs expose tokens | Logging all metadata | Redact Authorization and secret keys |

## 14. Practice Exercises

1. Create `Metadata.Key` constants for request ID and tenant hint using the ASCII marshaller.
2. Write a `ServerInterceptor` that puts the request ID into a `Context.Key`.
3. Read the request ID in the generated service implementation and pass it as a plain Java application request context.
4. Add an authentication interceptor; put only verified principal/tenant into Context after authentication.
5. Write a client interceptor that generates a distinct request ID per RPC.
6. Wrap an executor task with `Context.current().wrap(...)` and verify the request ID is preserved.
7. Register a cancellation listener and stop work when the RPC is cancelled.
8. Write a test with two concurrent RPCs to prove Context does not leak across requests.
9. Write a downstream client that propagates only trace context and the verified tenant.
10. Inspect logs/tracing to ensure tokens, secrets, and sensitive data are not recorded.

### Key takeaway

**Metadata is data traveling with the RPC over the wire; Context is call-scoped state inside the process.** Interceptors read Metadata and place verified values into Context for services/callbacks to use. Keep Context in the adapter, pass plain Java application context into use cases, propagate explicitly across executors, and forward only allowlisted metadata. Deadlines/cancellation, authentication, transactions, and tracing have separate mechanisms; combine them intentionally rather than treating everything as one kind of context.

## References

- [gRPC — Metadata](https://grpc.io/docs/guides/metadata/)
- [gRPC Java — Context](https://grpc.github.io/grpc-java/javadoc/io/grpc/Context.html)
- [gRPC Java — ServerInterceptor](https://grpc.github.io/grpc-java/javadoc/io/grpc/ServerInterceptor.html)
- [gRPC Java — MetadataUtils](https://grpc.github.io/grpc-java/javadoc/io/grpc/stub/MetadataUtils.html)
- [gRPC — Deadlines](https://grpc.io/docs/guides/deadlines/)
- [gRPC — Cancellation](https://grpc.io/docs/guides/cancellation/)
- [OpenTelemetry — Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/)
