# Attaching a Correlation ID

When a request travels through a gateway, a Spring gRPC service, and multiple backends, logs across those places are often scattered. A **correlation ID** lets components record the same reference identifier so logs for a processing flow can be grouped together. In gRPC, the common approach is to pass this ID in metadata, place it into gRPC `Context` on the server, and automatically re-attach it to downstream calls.

A correlation ID exists for log traceability. It is not an authentication credential, does not prove caller identity, and does not replace distributed tracing. This lesson covers the lifecycle of an ID across client, server, downstream calls, retries, and streaming.

## 1. How does a correlation ID differ from a trace ID?

Observability systems can use several kinds of identifiers:

| Identifier | Scope | Purpose |
| --- | --- | --- |
| **Correlation ID** | A business request or agreed-upon processing flow | Find related logs across multiple services |
| **Trace ID** | A distributed trace | Group spans belonging to the same trace |
| **Span ID** | One operation/span in a trace | Identify each processing segment and parent/child relationships |
| **Local Request ID** | One received request at a single service | Diagnose issues locally at one hop |

A correlation ID can stay constant across multiple services. A trace ID is also typically propagated end-to-end, but a tracing SDK additionally creates a new span ID for each operation and manages parent/child relationships, sampling, and timing. If your system already uses OpenTelemetry, continue propagating W3C Trace Context through the tracing mechanism; a correlation ID can complement it for log lookup by business convention.

Do not put tokens, emails, phone numbers, or personal data into a correlation ID. The ID should be an opaque string with no business meaning and no secrets.

## 2. Choosing the metadata key and formatting rules

gRPC metadata consists of headers/trailers attached to an RPC. Use a lowercase key, such as `x-correlation-id`:

```java
import io.grpc.Metadata;

public final class CorrelationMetadata {
    private CorrelationMetadata() {
    }

    public static final Metadata.Key<String> CORRELATION_ID =
            Metadata.Key.of(
                    "x-correlation-id",
                    Metadata.ASCII_STRING_MARSHALLER);
}
```

For metadata keys:

- Key names must be lowercase.
- String values use the ASCII marshaller; binary data requires a key ending in `-bin` and a binary marshaller.
- Metadata is meant for short IDs and control information, not business payloads.
- Enforce length limits and an allowed character set to prevent log injection, oversized headers, or malformed data.

The example below uses a string UUID. If your system uses gateway-issued IDs, you can use another opaque format as long as services agree on the validation rules.

## 3. Generating or validating the ID at the server boundary

A server interceptor is the right place to read the ID from incoming metadata, validate its format, and generate one if absent. Then the interceptor puts the ID into gRPC `Context` so service methods can retrieve it without adding fields to every protobuf request.

```java
package com.myshop.grpc.observability;

import io.grpc.Context;
import io.grpc.Contexts;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;
import java.util.UUID;
import java.util.regex.Pattern;

public final class CorrelationIdServerInterceptor
        implements ServerInterceptor {

    public static final Context.Key<String> CORRELATION_ID_CONTEXT =
            Context.key("correlation-id");

    private static final Pattern SAFE_ID =
            Pattern.compile("[A-Za-z0-9][A-Za-z0-9._:-]{0,63}");

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String correlationId =
                headers.get(CorrelationMetadata.CORRELATION_ID);

        if (correlationId == null) {
            correlationId = UUID.randomUUID().toString();
        } else if (!SAFE_ID.matcher(correlationId).matches()) {
            call.close(Status.INVALID_ARGUMENT
                    .withDescription("invalid x-correlation-id"),
                    new Metadata());
            return new ServerCall.Listener<>() {};
        }

        Context context = Context.current()
                .withValue(CORRELATION_ID_CONTEXT, correlationId);
        return Contexts.interceptCall(context, call, headers, next);
    }
}
```

Rules in the example:

- If the metadata is absent, the server generates a new UUID for the RPC.
- If the caller sends an ID, the server only accepts strings matching an allowlist and length limit.
- Invalid IDs are rejected before the service implementation runs.
- `Contexts.interceptCall` ensures the context is bound to the callbacks of the forwarded call.

The policy for caller-supplied IDs depends on your trust boundary. For internal APIs behind a trusted gateway, you can keep the gateway-generated ID after validation. For public endpoints, caller-supplied IDs remain untrusted data; you may choose to log them as an external correlation hint and generate a separate internal ID. Either way, never use a correlation ID as proof for authentication or authorization.

## 4. Reading the ID in the service and logging

In the service implementation, read the value from the context:

```java
String correlationId =
        CorrelationIdServerInterceptor.CORRELATION_ID_CONTEXT.get();

log.info("catalog lookup started correlation_id={} product_id={}",
        correlationId, request.getProductId());
```

Including the ID in every log record for the same call lets you query processing steps with a single key. If using SLF4J's MDC, you can place the ID into MDC for the scope of the callback and must clear it in a `finally` block to avoid leaking context across requests running on the same thread:

```java
String id = CorrelationIdServerInterceptor.CORRELATION_ID_CONTEXT.get();
try {
    MDC.put("correlation_id", id);
    handleRequest(request);
} finally {
    MDC.remove("correlation_id");
}
```

MDC is thread-local in many logging implementations. gRPC callbacks may run on different threads; therefore, do not rely on MDC set on one thread automatically appearing in every callback. Use gRPC Context as the call-scoped source of truth, and set/restore MDC at each execution boundary that needs logging.

Do not record correlation ID as a metric label if each request has its own ID. That creates nearly unbounded cardinality. Use the ID in controlled log/tracing attributes; metrics should group by method, status, and finite labels.

## 5. Automatically propagating the ID downstream with a client interceptor

If service A calls service B, a client interceptor can read the correlation ID from the current gRPC Context and add it to outbound metadata. That way, business code does not have to modify individual stub calls manually.

```java
package com.myshop.grpc.observability;

import io.grpc.CallOptions;
import io.grpc.Channel;
import io.grpc.ClientCall;
import io.grpc.ClientInterceptor;
import io.grpc.ForwardingClientCall;
import io.grpc.Metadata;
import io.grpc.MethodDescriptor;
import java.util.UUID;

public final class CorrelationIdClientInterceptor
        implements ClientInterceptor {

    @Override
    public <ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
            MethodDescriptor<ReqT, RespT> method,
            CallOptions callOptions,
            Channel next) {

        ClientCall<ReqT, RespT> delegate =
                next.newCall(method, callOptions);

        return new ForwardingClientCall.SimpleForwardingClientCall<>(delegate) {
            @Override
            public void start(Listener<RespT> listener, Metadata headers) {
                String id = headers.get(CorrelationMetadata.CORRELATION_ID);
                if (id == null) {
                    id = CorrelationIdServerInterceptor
                            .CORRELATION_ID_CONTEXT.get();
                }
                if (id == null) {
                    id = UUID.randomUUID().toString();
                }
                headers.put(CorrelationMetadata.CORRELATION_ID, id);
                super.start(listener, headers);
            }
        };
    }
}
```

ID selection order:

1. Preserve an outbound ID explicitly set by the caller, if present.
2. Otherwise, use the ID from the incoming RPC's gRPC Context.
3. If this is a standalone client call with no context, generate a new ID.

In production systems, share a common validation/normalization helper for outbound and inbound IDs, and avoid overwriting values already established by a trusted gateway. The client interceptor only propagates metadata; it does not create a distributed trace or span on its own.

## 6. Preserving Context during asynchronous execution

gRPC Context is active in callbacks attached to the call. When offloading work to a custom executor, the context does not automatically follow onto the new thread. If the client interceptor relies on context to propagate the correlation ID, losing context means downstream calls may generate a different ID.

Capture the current context and wrap the task:

```java
Context captured = Context.current();

executor.execute(captured.wrap(() -> {
    catalogStub.getProduct(request);
}));
```

For executors shared across many places, you can wrap the executor using gRPC's Context utilities or pass the ID as a call-scoped parameter in the application layer. Avoid storing the correlation ID in a mutable field of a singleton service: concurrent RPCs will overwrite each other's values.

If work is pushed onto a queue and processed after the RPC completes, serialize the correlation ID into the queue system's message envelope or message headers under a dedicated contract. gRPC Context does not automatically survive after the request-receiving process finishes.

## 7. Retries, fan-out, and streaming

**Retries:** attempts of the same logical operation should usually share the same correlation ID so logs can be grouped. Generate the ID at the application layer before starting retries or keep it in context across the operation. If an interceptor generates a new UUID per independent call, attempts may be split across multiple log groups.

Correlation IDs are only for linking observability data; they do not replace an idempotency key. For write operations with retries, the server still needs a dedicated idempotency mechanism to avoid executing the transaction twice.

**Fan-out:** when one request calls multiple backends concurrently, child calls typically inherit the same correlation ID. Trace instrumentation can create separate child spans per backend; do not generate a different correlation ID per branch if you want to group them under the same root request.

**Streaming:** one correlation ID usually applies to the entire RPC stream, not each individual message. Messages within the same stream can include a sequence number or message-specific ID if per-message analysis is needed. For long-lived streams, log event types and timestamps, while avoiding repeating sensitive payloads.

## 8. Correlation ID and distributed tracing

If the application uses OpenTelemetry, tracing instrumentation usually propagates `traceparent` automatically via gRPC metadata. The Trace ID links spans; the Span ID identifies each segment. A correlation ID is a supplementary key by application convention that can be attached to log records or span attributes.

Do not fabricate a `traceparent` by putting the correlation ID inside it. W3C Trace Context has its own format and semantics; let the tracing SDK create spans, manage sampling, and propagate context. You can log both `correlation_id` and `trace_id` to support both lookup patterns.

If a gateway accepts a correlation ID from callers, limit its length and characters; if displayed to customers as a reference label, do not include internal data or sensitive resource IDs in its value. Retention policies and log access controls still apply just as with other observability metadata.

## 9. Registering interceptors and testing

Core gRPC Java lets you attach interceptors to server/channel builders:

```java
Server server = ServerBuilder.forPort(9090)
        .intercept(new CorrelationIdServerInterceptor())
        .addService(new CatalogGrpcEndpoint(catalogService))
        .build();

ManagedChannel channel = ManagedChannelBuilder
        .forAddress("catalog.internal", 9090)
        .useTransportSecurity()
        .intercept(new CorrelationIdClientInterceptor())
        .build();
```

In Spring gRPC, servers and channels are usually auto-configured by the framework. Register interceptors through the extension point supported by your project's Spring gRPC version; simply declaring a class as a bean does not prove it is attached to the server/channel. Verify with integration tests making calls through the application configuration.

| Test case | Expectation |
| --- | --- |
| Request has no metadata | Server generates a valid ID and handler reads it from Context |
| Request has a valid ID | Server preserves the ID per trust boundary policy |
| Request has an overly long ID or disallowed characters | Server returns `INVALID_ARGUMENT` before handler runs |
| Server A calls server B | Client interceptor propagates the same ID to B |
| Async task calls downstream | ID is preserved when the executor is wrapped with Context |
| Retrying the same operation | Attempts carry the same correlation ID |
| Two concurrent RPCs | IDs do not mix between the two Contexts |
| Streaming RPC | Messages in the same stream share the same ID |

Beyond unit-testing individual interceptors, add integration tests confirming that logs across multiple services can be queried using the same correlation ID without logging raw authorization headers or payloads.

## 10. Implementation checklist

- [ ] Metadata key is lowercase `x-correlation-id`, with short ASCII values.
- [ ] IDs are validated for length/character set at the trust boundary.
- [ ] Missing IDs are generated under a consistent policy.
- [ ] Correlation IDs are never used as credentials, authorization claims, or idempotency keys.
- [ ] Server stores the ID per call in gRPC Context.
- [ ] Client interceptor propagates the current ID downstream.
- [ ] Context is propagated explicitly across custom executors/threads.
- [ ] Retries of the same operation keep a stable ID if logs need to be grouped.
- [ ] Streaming keeps one ID for the whole call; per-message IDs are added only when needed.
- [ ] The ID appears in structured logs, not in high-cardinality metric labels.
- [ ] Distributed tracing continues to use W3C Trace Context/OpenTelemetry separately.
- [ ] Tests verify metadata, Context, async, retries, concurrency, and Spring registration.

**Self-check**

**Question 1.** How does a correlation ID differ from a trace ID?

*Answer:* A correlation ID is an agreed-upon key for grouping logs of a request/processing flow. A trace ID belongs to distributed tracing and links spans; a span ID distinguishes individual operations within a trace.

**Question 2.** Should the server trust a caller-sent correlation ID as an authenticated identity?

*Answer:* No. It is caller-provided metadata that must be validated and used only for correlation. Authentication/authorization require separate credentials and policies.

**Question 3.** Why does a client interceptor read the ID from gRPC Context?

*Answer:* It lets downstream calls inherit the incoming RPC's ID without adding extra parameters to every stub call.

**Question 4.** When offloading work to a separate executor, what can happen if Context is not propagated?

*Answer:* Context is not guaranteed to appear on the new thread; the client interceptor may fail to see the original ID and generate a different one. Wrap the task/executor with Context or pass the ID explicitly.

**Question 5.** Should you generate a new correlation ID for every retry attempt?

*Answer:* Usually not if attempts belonging to the same operation need to be investigated together. Keep a stable ID; use a separate idempotency key to protect write operations.

Attaching correlation IDs is effective when IDs are generated or validated at the boundary, stored per-RPC in Context, and forwarded via a client interceptor. Keep IDs stable across fan-out/retries, avoid mixing them with authentication credentials or trace IDs, and test asynchronous paths so logs across services link together reliably.
