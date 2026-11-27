# Trace Context via gRPC Metadata

A request often passes through multiple services before returning a result to the caller. Each service's logs can indicate where an error occurred, but without linking logs and spans to the same trace, tracking a request's path is difficult. gRPC carries information via HTTP/2 metadata; this is the right place to pass trace context between processes and continue a distributed trace.

**Trace context via gRPC metadata** is the practice of passing trace identifiers, parent spans, and propagation attributes between gRPC clients and servers using each RPC's metadata. This lesson belongs to the **Observability** chapter of the **SPRING_GRPC** module: developing gRPC services in the Spring ecosystem using Protocol Buffers contracts, generating Java code, and implementing client/server for unary or streaming RPCs; learners work with metadata, deadlines, statuses, interceptors, TLS, integration testing, and monitoring performance and reliability. The focus is on W3C Trace Context, OpenTelemetry propagators, client/server interceptors, context propagation across asynchronous tasks, and security limits for baggage.

## 1. What Problem Does Trace Context Solve?

A distributed trace represents the path of an operation across multiple processes. Each trace shares one `trace_id`; each span has its own `span_id` and can reference a parent span. When service A calls service B over gRPC, B needs to receive the operation's context to create a child span belonging to the same trace.

For example:

~~~text
HTTP request
  └── API service span
        ├── database span
        └── gRPC client span: Inventory.GetStock
              └── gRPC server span: Inventory.GetStock
                    └── downstream gRPC client span
~~~

If context is lost at the gRPC boundary, service B may start a new trace. The trace UI then shows two disconnected traces even though they belong to the same business request.

Trace context typically carries:

- Trace ID: trace identifier across services.
- Parent/span context: information about the span that initiated the outbound call.
- Trace flags: such as the `sampled` flag in W3C Trace Context.
- Trace state: vendor-specific information standardized by W3C.
- Baggage: key/value attributes propagated with the request if permitted by the application.

Trace context serves observability. It is not a user identity, credential, or proof of authorization.

## 2. gRPC Metadata as the Context Transport Channel

gRPC metadata is a set of key/value pairs attached to an RPC. The client typically sends metadata with request headers; the server can read metadata inside a `ServerInterceptor` or service context. Metadata can also be sent as response headers/trailers, but trace context flowing from caller to callee is usually injected into initial request metadata.

Some important rules:

- Metadata keys must be lowercase; standard trace context keys are `traceparent`, `tracestate`, and `baggage`.
- Text values use `Metadata.ASCII_STRING_MARSHALLER`.
- Keys ending in `-bin` use a binary marshaller for binary data.
- Do not create duplicate keys for the same trace field; the propagator must replace prior values per contract.
- Do not overwrite HTTP/2 pseudo-headers or transport-reserved metadata.
- Metadata has size limits on clients, servers, and proxies; oversized baggage can cause requests to be rejected.

Illustrative example of call metadata:

~~~text
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
tracestate: vendor=value
baggage: tenant-tier=gold,region=apac
~~~

Applications should not manually build `traceparent` strings or manually parse trace IDs. Use an OpenTelemetry propagator to handle formatting, validation, and sampling flags per specification.

## 3. W3C Trace Context and Baggage

W3C Trace Context defines how trace context is represented via the `traceparent` and `tracestate` fields:

- `traceparent` contains version, trace ID, parent ID, and trace flags.
- `tracestate` carries additional state in a vendor-neutral format, with rules on size and member count.
- `baggage` is a separate standard for propagating key/value attributes with an operation; it does not replace `traceparent`.

OpenTelemetry typically configures `W3CTraceContextPropagator` and `W3CBaggagePropagator`, which can be combined with a composite propagator. Upon receiving valid context, the SDK creates a span continuing the trace; when headers are missing or invalid, the SDK can create a new root context according to instrumentation configuration.

Do not use baggage to transport business payloads or large data. Baggage is often forwarded across many services, so a sensitive attribute can leak into many logging systems, proxies, and telemetry backends.

## 4. Inject and Extract Are Symmetric Operations

Propagation has two steps:

1. **Inject on the client:** read OpenTelemetry `Context.current()` and write propagation fields into gRPC `Metadata` before sending the call.
2. **Extract on the server:** read propagation fields from inbound `Metadata` to establish the current context for the server span and downstream calls.

~~~mermaid
sequenceDiagram
    participant A as gRPC Client
    participant M as HTTP/2 Metadata
    participant B as gRPC Server
    A->>A: Read current OTel context
    A->>M: Inject traceparent/tracestate/baggage
    M->>B: Send request metadata
    B->>B: Extract remote context
    B->>B: Create server span as child
    B->>B: Propagate context to downstream calls
~~~

The client interceptor only injects; the server interceptor only extracts. Do not generate a new trace ID in each service when the goal is to link spans within the same distributed trace.

## 5. Configuring the OpenTelemetry Propagator

In Java applications, the OpenTelemetry API provides `TextMapPropagator` to inject/extract context over any carrier. For gRPC, the carrier is `io.grpc.Metadata`.

Example initializing a propagator with W3C Trace Context and Baggage:

~~~java
import io.opentelemetry.api.baggage.propagation.W3CBaggagePropagator;
import io.opentelemetry.api.trace.propagation.W3CTraceContextPropagator;
import io.opentelemetry.context.propagation.TextMapPropagator;

TextMapPropagator propagator =
        TextMapPropagator.composite(
                W3CTraceContextPropagator.getInstance(),
                W3CBaggagePropagator.getInstance());
~~~

In a Spring Boot application, use a centrally managed `OpenTelemetry` instance provided by the OpenTelemetry SDK/autoconfiguration or corresponding starter. Do not create a separate SDK inside each interceptor; having multiple SDKs/tracer providers can split trace contexts and export to different pipelines.

## 6. Creating TextMapGetter and TextMapSetter for Metadata

OpenTelemetry propagators do not depend on gRPC directly. We provide an adapter to read/write `Metadata`:

~~~java
import io.grpc.Metadata;
import io.opentelemetry.context.propagation.TextMapGetter;
import io.opentelemetry.context.propagation.TextMapSetter;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Locale;

public final class GrpcMetadataTextMap {

    private GrpcMetadataTextMap() {}

    public static final TextMapSetter<Metadata> SETTER =
            new TextMapSetter<>() {
                @Override
                public void set(
                        Metadata carrier,
                        String key,
                        String value) {
                    if (carrier == null) {
                        return;
                    }
                    Metadata.Key<String> metadataKey =
                            Metadata.Key.of(
                                    key.toLowerCase(Locale.ROOT),
                                    Metadata.ASCII_STRING_MARSHALLER);
                    carrier.discardAll(metadataKey);
                    carrier.put(metadataKey, value);
                }
            };

    public static final TextMapGetter<Metadata> GETTER =
            new TextMapGetter<>() {
                @Override
                public Iterable<String> keys(Metadata carrier) {
                    if (carrier == null) {
                        return Collections.emptyList();
                    }
                    List<String> textKeys = new ArrayList<>();
                    for (String key : carrier.keys()) {
                        if (!key.endsWith("-bin")) {
                            textKeys.add(key);
                        }
                    }
                    return textKeys;
                }

                @Override
                public String get(Metadata carrier, String key) {
                    if (carrier == null || key == null) {
                        return null;
                    }
                    Metadata.Key<String> metadataKey =
                            Metadata.Key.of(
                                    key.toLowerCase(Locale.ROOT),
                                    Metadata.ASCII_STRING_MARSHALLER);
                    return carrier.get(metadataKey);
                }
            };
}
~~~

The setter discards existing values for the same key before putting the new value to avoid multiple `traceparent` or `tracestate` entries in one carrier. The getter returns available metadata keys; the propagator reads only the keys it supports.

This adapter is intended for ASCII propagation fields. Do not use an ASCII marshaller for `-bin` keys; W3C trace context and baggage are text fields. Metadata keys must conform to gRPC rules; do not allow arbitrary data to create binary or reserved keys.

## 7. Injecting Trace Context on the gRPC Client

`ClientInterceptor` reads the OpenTelemetry context when the call starts and injects it into metadata:

~~~java
import io.grpc.CallOptions;
import io.grpc.Channel;
import io.grpc.ClientCall;
import io.grpc.ClientInterceptor;
import io.grpc.ForwardingClientCall;
import io.grpc.Metadata;
import io.grpc.MethodDescriptor;
import io.opentelemetry.context.Context;
import io.opentelemetry.context.propagation.TextMapPropagator;

public final class TraceContextClientInterceptor
        implements ClientInterceptor {

    private final TextMapPropagator propagator;

    public TraceContextClientInterceptor(
            TextMapPropagator propagator) {
        this.propagator = propagator;
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
                    Listener<RespT> responseListener,
                    Metadata headers) {
                propagator.inject(
                        Context.current(),
                        headers,
                        GrpcMetadataTextMap.SETTER);
                super.start(responseListener, headers);
            }
        };
    }
}
~~~

Reading `Context.current()` inside `start()` captures the active context at the moment the stub actually invokes the RPC. If you inject when creating the channel or stub, the context will not belong to the current request.

Attach the interceptor to the channel via `ManagedChannelBuilder.intercept(...)` or the Spring gRPC starter's extension point. If OpenTelemetry gRPC instrumentation already injects metadata automatically, do not add a second manual interceptor doing the same thing; duplicate propagation headers can cause unpredictable behavior.

## 8. Extracting Trace Context on the gRPC Server

`ServerInterceptor` extracts context from metadata before invoking the service handler. The OTel context must remain active while the handler runs and inside listener callbacks:

~~~java
import io.grpc.ForwardingServerCallListener;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.opentelemetry.context.Scope;
import io.opentelemetry.context.propagation.TextMapPropagator;

public final class TraceContextServerInterceptor
        implements ServerInterceptor {

    private final TextMapPropagator propagator;

    public TraceContextServerInterceptor(
            TextMapPropagator propagator) {
        this.propagator = propagator;
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        io.opentelemetry.context.Context extracted =
                propagator.extract(
                        io.opentelemetry.context.Context.current(),
                        headers,
                        GrpcMetadataTextMap.GETTER);

        ServerCall.Listener<ReqT> delegate;
        try (Scope ignored = extracted.makeCurrent()) {
            delegate = next.startCall(call, headers);
        }

        return new ForwardingServerCallListener
                .SimpleForwardingServerCallListener<>(delegate) {
            @Override
            public void onMessage(ReqT message) {
                try (Scope ignored = extracted.makeCurrent()) {
                    super.onMessage(message);
                }
            }

            @Override
            public void onHalfClose() {
                try (Scope ignored = extracted.makeCurrent()) {
                    super.onHalfClose();
                }
            }

            @Override
            public void onReady() {
                try (Scope ignored = extracted.makeCurrent()) {
                    super.onReady();
                }
            }

            @Override
            public void onCancel() {
                try (Scope ignored = extracted.makeCurrent()) {
                    super.onCancel();
                }
            }

            @Override
            public void onComplete() {
                try (Scope ignored = extracted.makeCurrent()) {
                    super.onComplete();
                }
            }
        };
    }
}
~~~

The example above uses OpenTelemetry `Context` and `Scope`; do not confuse them with `io.grpc.Context`, which is a separate context system in gRPC Java. This interceptor only extracts and attaches the parent context; the propagator itself does not create a server span. In production, you need OpenTelemetry gRPC instrumentation to create a server span from the extracted parent, or create the span manually with `Tracer` and attach the context containing that span. If the service handler invokes a downstream gRPC call inside the callback, the attached context will be read and injected onward by the client interceptor.

If creating the server span manually, the logical order is: extract the remote parent, create a span with kind `SERVER` and parent set to the extracted context, create the server context with `extracted.with(serverSpan)`, attach the server context across handler/listener callbacks, and end the span exactly once when the call completes/cancels. Use an atomic guard across terminal callbacks so the span is not ended twice. Do not treat calling `propagator.extract` as having created a server span.

In production systems, prefer proven OpenTelemetry gRPC instrumentation if it automatically creates server/client spans and manages callback contexts. The manual code here illustrates the metadata propagation mechanism; do not run it alongside auto-instrumentation without clearly establishing which component is responsible for span creation and inject/extract.

## 9. Context Propagation Across Executors and Async Tasks

Context is only active within the current scope. If a handler offloads work to an executor, the new thread does not automatically inherit the OTel context:

~~~java
io.opentelemetry.context.Context captured =
        io.opentelemetry.context.Context.current();

executor.execute(captured.wrap(() -> {
    inventoryClient.getStock(request);
}));
~~~

`captured.wrap(...)` attaches the captured context when the task runs and restores the previous context once the task completes. This ensures the client interceptor injects the right trace context for downstream RPCs.

When using `CompletableFuture`, reactive pipelines, or framework schedulers, use the framework's official context propagation integration or capture context at task submission time. Do not store a global `Context` in a singleton service; context must be scoped to each request/call.

For streaming RPCs, `onMessage`, `onHalfClose`, `onReady`, and cancellation callbacks can run on different threads. Ensure context is attached in each callback or use instrumentation that handles this lifecycle. Attaching context only around `next.startCall` is not sufficient for future callbacks to see the context.

## 10. Spring gRPC and OpenTelemetry: Choosing One Propagation Mechanism

In a Spring application, there are usually two options:

1. **Automatic instrumentation:** the OpenTelemetry Java agent or a gRPC instrumentation library creates spans and injects/extracts context automatically.
2. **Manual interceptors:** the application registers its own client/server interceptors and uses `TextMapPropagator`.

Automatic instrumentation is usually the first choice because it already handles call lifecycles, context, and semantic conventions for the library version. Manual interceptors fit when the runtime lacks suitable instrumentation or the application needs custom integration.

Do not enable both mechanisms without checking. Doing so can produce duplicate spans, duplicate metadata injection, or broken parent-child relationships. Verify that:

- Exactly one component creates the client/server span at each RPC boundary.
- Outbound calls carry the trace context of the current span.
- Inbound calls extract context before the server span is created or attach the proper parent.
- Streaming callbacks and async tasks still see the context.
- Traces export to the expected collector/backend.

With Spring Boot, configure the OpenTelemetry SDK/agent according to the application lifecycle. Do not instantiate a new SDK or `TracerProvider` inside an interceptor.

## 11. Baggage: Useful but Needs Control

Baggage carries key/value pairs across the service graph. For example, `tenant-tier=gold` or `region=apac` can help apply sampling/diagnostic policies, but baggage can also be forwarded to many downstream services.

Operational rules:

- Allow only an explicit allowlist of keys with clear purposes.
- Do not put access tokens, session cookies, emails, phone numbers, personal data, or business payloads into baggage.
- Limit the number of keys, value length, and total size.
- Do not use baggage as an authentication/authorization source; clients can craft metadata themselves.
- Do not turn baggage values into metric labels if cardinality is unbounded.
- Consider stripping baggage at trust domain boundaries or when calling external services.

Trace context is also untrusted for access control decisions. A caller can fabricate `traceparent`; it only identifies a trace/span, not that the request comes from a valid principal.

## 12. Metadata Limits, Validation, and Propagation Errors

Metadata passes through clients, servers, proxies, and load balancers; each component may enforce total size limits. Oversized baggage or excessive metadata can cause requests to be rejected before reaching the handler.

Some principles:

- Transmit only the standard propagation fields required by the system.
- Do not blindly copy all inbound metadata to downstream calls.
- Use the propagator to validate `traceparent`/`tracestate` instead of manual parsing.
- Keep trace context as ASCII metadata; use separate `-bin` keys for binary application metadata.
- Do not log raw metadata because it may contain tokens or sensitive data.
- If trace context is missing or malformed, let the propagator handle it (typically creating a new context) and do not break business RPCs just because a tracing header is invalid.

If you need to pass a custom correlation ID outside W3C trace context, define a dedicated metadata key, bound its format/length, and clarify trust boundaries. Do not use a custom ID in place of OpenTelemetry trace/span IDs.

## 13. Observing Successful Propagation

You can verify trace propagation with a request spanning two services:

1. Client A creates a root/server span for an incoming request.
2. A calls gRPC service B; the client span is a child of the current context.
3. The client interceptor injects `traceparent` into metadata.
4. Server B's interceptor extracts context; B's server span joins A's trace.
5. B calls downstream C; the client interceptor continues injecting context from the current span.
6. The trace backend shows spans under the same trace ID with proper parent-child relationships.

Failure indicators:

| Symptom | Common Cause | How to Check |
| --- | --- | --- |
| Service B starts a new trace ID | Metadata was not injected or server did not extract. | Inspect traceparent at client/server boundaries. |
| Two server spans share a trace but have wrong parent | Context attached at the wrong time or span created before extract. | Check interceptor ordering and auto-instrumentation. |
| Two server spans appear for one RPC | Manual and automatic instrumentation both create spans. | Check agent, starter, and interceptor registration. |
| Downstream span becomes a root | Context lost across executor/thread switch. | Capture and wrap OTel Context for the task. |
| Baggage does not reach downstream | Propagator did not enable baggage or policy filtered keys. | Check composite propagator and allowlist. |
| RPC rejected due to large metadata | Baggage/metadata exceeds proxy or server limits. | Measure metadata size and remove unnecessary fields. |

## 14. Testing Trace Context via gRPC Metadata

Integration tests should verify both metadata contents and trace relationships:

1. Create an OTel context with a valid trace/span, invoke the client stub, and verify outbound metadata contains `traceparent`.
2. Send `traceparent` metadata to a test server; verify the handler executes under the extracted trace ID.
3. Invoke a downstream gRPC call inside the handler; verify context is propagated onward.
4. Offload handler work via an executor; verify `Context.wrap` preserves trace context on the worker thread.
5. Test server-streaming/bidirectional callbacks to verify context is present in `onMessage` and `onHalfClose`.
6. Send malformed `traceparent`; verify the propagator does not break the business RPC and tracing creates an appropriate context.
7. Send disallowed or oversized baggage; verify policy filters/rejects it properly.
8. Enable auto-instrumentation alongside manual interceptors in a test environment; verify no duplicate spans are created, then choose one mechanism for production.

You can use an in-process gRPC server/channel to test propagation logic. Add tests over TCP/TLS and proxies when verifying metadata size limits or real infrastructure behavior. Do not merely check that a header exists; verify the trace ID and parent-child relationships in the backend or test exporter.

## 15. Common Pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Each service creates its own trace | Missing inject/extract or wrong metadata carrier. | Use W3C propagator in client/server interceptors. |
| traceparent duplicated in metadata | Setter appends without replacing old value. | discardAll on the key before put or use standard instrumentation. |
| Context lost in async tasks | Thread/executor does not automatically inherit OTel Context. | Capture and wrap tasks or use framework context propagation. |
| Streaming callbacks lack trace context | Context only attached during startCall. | Attach context in every listener callback or use auto-instrumentation. |
| Two spans created for one RPC | Agent and manual interceptor both instrument. | Choose one span creation/propagation mechanism. |
| Baggage makes metadata too large | Passing too many key/values or payloads. | Enforce allowlists and size limits. |
| Using trace ID for authorization | Confusing observability context with security identity. | Authenticate principals with a dedicated authentication mechanism. |
| Logging raw metadata leaks data | Metadata may contain credentials or PII. | Redact and log only explicitly permitted fields. |

## 16. Hands-On Exercises

1. Create a W3C `TextMapPropagator` combining Trace Context and Baggage.
2. Write `TextMapGetter`/`TextMapSetter` adapters for gRPC `Metadata`.
3. Write a `ClientInterceptor` that injects trace context into outbound RPC metadata.
4. Write a `ServerInterceptor` that extracts context and attaches it across handler/listener callbacks.
5. Build two Spring gRPC services calling each other in sequence; verify spans share the same trace ID.
6. Run a downstream call on an executor; use `Context.wrap` to preserve the parent context.
7. Test baggage allowlists, metadata size limits, and invalid `traceparent` cases.
8. Check auto-instrumentation and manual interceptors to ensure no duplicate spans are produced.

After this lesson, you should know how to inject/extract W3C trace context via gRPC metadata, preserve OTel context across listener callbacks and executors, and restrict baggage according to trust/security policies. When propagation is configured properly, the trace backend can stitch client, server, and downstream spans into a unified distributed trace across a Spring gRPC system.
