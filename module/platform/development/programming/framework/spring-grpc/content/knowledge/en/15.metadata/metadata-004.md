# Correlation ID and Trace Context

A gRPC call may pass through a gateway, order service, inventory service, and payment service before completing. When an error occurs or latency spikes, each service's logs often live in different systems. A **Correlation ID** helps identify logs belonging to the same processing flow; **trace context** helps a distributed tracing system connect *spans* into a *trace* to show execution paths and durations.

In **Spring gRPC**, both types of information can be transmitted via gRPC **metadata**, while OpenTelemetry and observability systems use them for distinct purposes. Proper design helps track unary RPCs, streaming RPCs, and downstream calls, while avoiding confusing a correlation ID with authentication proof or a trace ID.

After this lesson, you will be able to:

- Distinguish correlation ID, request ID, trace ID, span ID, and W3C trace context.
- Understand how `traceparent`, `tracestate`, and `baggage` are transmitted in gRPC metadata.
- Design rules for generating, validating, propagating, and logging correlation IDs across multiple services.
- Write Java client/server interceptors to pass a correlation ID per RPC.
- Integrate gRPC tracing with OpenTelemetry in Spring, including when using executors or streaming.
- Test correlation continuity and parent–child relationships between spans; mitigate risks of spoofing, data leakage, and metadata size.

## 1. Concepts to Distinguish

| Concept | Meaning | Typical lifecycle | Example |
| --- | --- | --- | --- |
| **Correlation ID** | Application ID used to link logs/events of a task or business workflow | May span multiple RPCs, queues, and async processes | `corr-6d3a...` |
| **Request ID** | Identifier for a specific HTTP/gRPC request; sometimes used as a correlation ID | Typically per RPC/request | `req-0042` |
| **Trace ID** | Identifier of a distributed trace | Shared across spans in the same trace | 32 hex chars for 16 bytes |
| **Span ID** | Identifier of a specific operation/span | Each span has its own ID | 16 hex chars for 8 bytes |
| **Trace context** | Information needed for the receiving service to continue tracing relationships properly | Injected/extracted at RPC boundaries | `traceparent`, `tracestate` |
| **Baggage** | Application key–value pairs explicitly propagated alongside context between services | Depends on propagator and processing scope | `tenant-tier=standard` if policy allows |

**A correlation ID does not have to equal a trace ID.** One business task can involve multiple traces—for example, processing a request immediately and continuing work the next day via a queue. Conversely, one trace has many spans but only one trace ID; each span still requires its own span ID.

`x-correlation-id` and `x-request-id` are **metadata naming conventions** used by many applications, not mandatory headers of gRPC or W3C Trace Context. Choose a consistent convention, clearly document the ID scope, and avoid creating multiple headers with the same purpose simultaneously without precedence rules.

## 2. Metadata Carrying Correlation and Trace Context

gRPC carries auxiliary call information via request headers and response headers/trailers. For short text values, the `grpc-java` API uses `Metadata.Key<String>` and `Metadata.ASCII_STRING_MARSHALLER`.

Common keys:

| Metadata key | Purpose | Who creates/manages it? |
| --- | --- | --- |
| `x-correlation-id` | Correlate logs and events across a business processing chain | Application or gateway with clear policy |
| `traceparent` | Carries version, trace ID, parent span ID, and trace flags per W3C | Tracing instrumentation/propagator |
| `tracestate` | Carries extended W3C state for tracing backends | Propagators and tracing vendors |
| `baggage` | Carries key–value pairs permitted to propagate across service boundaries | Propagators and application |

These are **ASCII metadata**. Custom keys with the `-bin` suffix are only appropriate when raw binary bytes are genuinely required. Never rename `traceparent` to `traceparent-bin`; that is not a W3C Trace Context header name.

Example metadata of a call:

```text
x-correlation-id: corr-8b31f43a
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
```

`tracestate` and `baggage` are conditional components, so examples do not necessarily include them. The tracing library can automatically add `traceparent` once properly configured.

## 3. Reading the W3C `traceparent` Structure

For version `00` of W3C Trace Context, the typical format is:

```text
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
             │  │                                │                │
             │  └─ trace-id: 16 bytes, 32 hex    │                │
             │                                   │                │
             └─ version                          └─ parent-id      └─ flags
                                                     8 bytes, 16 hex  1 byte, 2 hex
```

| Component | Example | Meaning |
| --- | --- | --- |
| Version | `00` | traceparent format version |
| Trace ID | `4bf92f3577b34da6a3ce929d0e0e4736` | Identifies the same distributed trace |
| Parent ID | `00f067aa0ba902b7` | ID of the span on the metadata-sending side, forming the basis of parent–child relationships |
| Trace flags | `01` | The `sampled` sampling bit is enabled in this example |

Trace ID and parent ID **must not be all zeros** in a valid format. The trace ID/span ID format is a standardized hex string; never take an arbitrary UUID and concatenate it directly into `traceparent` without normalization and format validation.

**The sampled flag is not a guarantee that the trace will appear in storage.** Samplers, collection policies, and collectors can decide which data gets recorded or exported. Services should follow the configured tracing system's context handling rather than manually altering sampling flags.

When service B receives a valid `traceparent`, instrumentation can use it as the remote parent and create a **new span with a new span ID**. The Trace ID is preserved within the same trace. When B calls C, outgoing metadata reflects the active span on B's side; therefore `parent-id` on the wire typically differs from the A → B call.

`tracestate` adds W3C-standard information to help multiple tracing systems interoperate. `baggage` carries application data that may propagate; do not use it as a secret store or authorization source, as downstream services can read and forward this data.

## 4. Flow Across Multiple Services

Suppose Spring gRPC operates three services:

```text
User Application
    |
    | x-correlation-id: corr-42
    | traceparent: trace=T1, parent=P1
    v
API Gateway
    |  Server span G1, trace T1
    |  Client span G2, trace T1
    |
    | x-correlation-id: corr-42
    | traceparent: trace=T1, parent=G2
    v
OrderService
    |  Server span O1, trace T1
    |  Client span O2, trace T1
    |
    | x-correlation-id: corr-42
    | traceparent: trace=T1, parent=O2
    v
InventoryService
       Server span I1, trace T1
```

The names `T1`, `G2`, and `O2` in the diagram are illustrative symbols, **not hex strings to put into traceparent**.

What to observe:

1. **Business Correlation ID** is `corr-42`, kept consistent across the hops required by policy.
2. **Trace ID** remains the same if the entire call chain belongs to one trace and context is propagated properly.
3. **Span ID** differs per operation. A server span typically has a child relationship to the upstream client span if trace context is extracted successfully.
4. If context is lost between the gateway and OrderService, the tracing system may start a new trace. Logs can still be found via the correlation ID, but a single trace's timeline will be broken.

Correlation IDs help search logs; tracing reveals call structure, durations, errors, and span relationships. A strong observability setup typically uses both rather than choosing only one.

## 5. Designing the Correlation ID Lifecycle

You must agree on: **who has authority to create IDs, when to reuse them, and when to generate new ones**.

### 5.1. Generating at the System Boundary

At a trusted entry point, such as the application's gateway, you can:

- Generate a sufficiently unpredictable random ID, such as `UUID.randomUUID()`, for each new request.
- If receiving an ID from an **authenticated and trusted** upstream, validate format/length before retaining it.
- If receiving an ID from a public client, prefer generating a system-managed ID so clients cannot inject someone else's ID and pollute logs.
- Only propagate the correlation ID across services tasked with handling the same operation; when launching a new independent task, clearly decide whether to generate a new correlation ID or link back to the previous task.

Example application format:

```text
x-correlation-id: 2a29a1f7-3a20-4ab7-9f94-f147524728c1
```

UUID is just one option. IDs should not contain usernames, emails, phone numbers, or sensitive information; the ID itself **does not prove identity or access rights**.

### 5.2. Format Validation and Limits

An illustrative policy is accepting only `[A-Za-z0-9._-]` with length 1 to 64 characters. This policy:

- Prevents control characters and newlines that could break log structure.
- Avoids overly long IDs bloating metadata.
- Reduces the risk of arbitrary client data entering observability systems.

This is an **application-defined** rule, not a mandatory gRPC rule. A validly formatted value can still be spoofed if it originates from an untrusted source.

### 5.3. Propagating Across Hops and Async Boundaries

When OrderService calls InventoryService to serve the same request, preserve the correlation ID or map it to a system-controlled context. For async jobs or queues, the correlation ID can be placed in message metadata according to the queue contract; **do not assume gRPC automatically propagates context across a message broker**.

When a new job needs its own trace, you can keep the business correlation ID for related search and use span links or appropriate tracing semantics. Never manually overwrite the trace ID of a span already created by OpenTelemetry.

## 6. Server Interceptor: Receiving and Storing Correlation ID in gRPC Context

On the server, a `ServerInterceptor` can read incoming metadata, validate the value, and store it in `io.grpc.Context`. The example below allows configuring `trustUpstream`: only use the sender's ID when upstream lies within the **trust boundary**; otherwise the server generates an ID.

```java
import io.grpc.Context;
import io.grpc.Contexts;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;
import java.util.Iterator;
import java.util.UUID;

public final class CorrelationIdServerInterceptor implements ServerInterceptor {

    private static final Metadata.Key<String> CORRELATION_HEADER =
        Metadata.Key.of(
            "x-correlation-id",
            Metadata.ASCII_STRING_MARSHALLER);

    public static final Context.Key<String> CURRENT_ID =
        Context.key("correlation-id");

    private final boolean trustUpstream;

    public CorrelationIdServerInterceptor(boolean trustUpstream) {
        this.trustUpstream = trustUpstream;
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        Iterable<String> all = headers.getAll(CORRELATION_HEADER);
        String received = null;
        if (all != null) {
            Iterator<String> iterator = all.iterator();
            if (iterator.hasNext()) {
                received = iterator.next();
            }
            // Avoid ambiguous values from multiple headers with the same name.
            if (iterator.hasNext()) {
                call.close(
                    Status.INVALID_ARGUMENT.withDescription(
                        "Multiple correlation IDs"),
                    new Metadata());
                return new ServerCall.Listener<ReqT>() {};
            }
        }

        String effectiveId = trustUpstream && isValid(received)
            ? received
            : UUID.randomUUID().toString();

        Context callContext =
            Context.current().withValue(CURRENT_ID, effectiveId);

        return Contexts.interceptCall(
            callContext, call, headers, next);
    }

    private static boolean isValid(String value) {
        return value != null
            && value.matches("[A-Za-z0-9._-]{1,64}");
    }
}
```

This example highlights three important points:

1. `Metadata.Key<String>` pairs with `ASCII_STRING_MARSHALLER` because the correlation ID is an ASCII string.
2. `Contexts.interceptCall(...)` binds `CURRENT_ID` to the call's context for server-side processing.
3. `trustUpstream` is an illustrative configuration. **Do not enable it simply because a request arrives from an internal network address**; evaluate authentication, service access controls, and the possibility of client-injected headers.

Inside the service implementation, retrieve the active value with:

```java
String correlationId = CorrelationIdServerInterceptor.CURRENT_ID.get();
// Example: logger.info("ReserveStock correlationId={}", correlationId);
```

`Context` is scoped to the gRPC execution of a call, not a global variable across all RPCs. If work shifts to a self-managed executor, propagate context across the executor so the ID is not lost.

## 7. Client Interceptor: Sending a Correlation ID for Each RPC

A client can pass the ID via `CallOptions` on a **stub for a specific call**. The interceptor reads the option, attaches request metadata, and generates a new ID if none is present.

```java
import io.grpc.CallOptions;
import io.grpc.Channel;
import io.grpc.ClientCall;
import io.grpc.ClientInterceptor;
import io.grpc.ForwardingClientCall;
import io.grpc.Metadata;
import io.grpc.MethodDescriptor;
import java.util.UUID;

public final class CorrelationIdClientInterceptor implements ClientInterceptor {

    public static final CallOptions.Key<String> CORRELATION_OPTION =
        CallOptions.Key.create("correlation-id");

    private static final Metadata.Key<String> CORRELATION_HEADER =
        Metadata.Key.of(
            "x-correlation-id",
            Metadata.ASCII_STRING_MARSHALLER);

    @Override
    public <ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
            MethodDescriptor<ReqT, RespT> method,
            CallOptions callOptions,
            Channel next) {

        ClientCall<ReqT, RespT> delegate =
            next.newCall(method, callOptions);

        return new ForwardingClientCall.SimpleForwardingClientCall<ReqT, RespT>(
                delegate) {
            @Override
            public void start(
                    ClientCall.Listener<RespT> responseListener,
                    Metadata headers) {

                String id = callOptions.getOption(CORRELATION_OPTION);
                if (id == null || id.isBlank()) {
                    id = UUID.randomUUID().toString();
                }
                headers.put(CORRELATION_HEADER, id);
                super.start(responseListener, headers);
            }
        };
    }
}
```

Suppose a `GreeterGrpc` client has been generated from `.proto` and a `channel` is ready:

```java
GreeterGrpc.GreeterBlockingStub baseStub =
    GreeterGrpc.newBlockingStub(channel)
        .withInterceptors(new CorrelationIdClientInterceptor());

// When code is handling a server RPC with an active correlation ID:
String inherited = CorrelationIdServerInterceptor.CURRENT_ID.get();

GreeterGrpc.GreeterBlockingStub callStub =
    baseStub.withOption(
        CorrelationIdClientInterceptor.CORRELATION_OPTION,
        inherited);

// callStub.sayHello(...) passes the same correlation ID downstream.
```

`GreeterGrpc` and `sayHello` are sample names for a stub/method from a Protobuf contract. In real applications, configure the client interceptor in one central place; derive a call-specific stub via `withOption(...)` whenever you need to pass the ID corresponding to each request.

**Note:** the option value is reused if the same configured stub is shared. Avoid storing User A's correlation ID on a singleton stub and reusing it for User B. Ensure the ID comes from a validated context or is system-generated, rather than taken directly from unverified input.

The code above **only propagates the correlation ID**; it does not create or connect OpenTelemetry spans. Tracing instrumentation must be configured separately; then both mechanisms can attach metadata to the same RPC.

## 8. Trace Context with OpenTelemetry in Spring gRPC

In distributed tracing, propagating trace context involves two steps:

1. **Inject on the client:** take the active span's context and populate headers according to the configured propagator.
2. **Extract on the server:** read context from metadata, create a server span linked to the remote parent, and make the new span active in scope.

If the system standardizes on **W3C Trace Context**, the propagator manages `traceparent` and, when present, `tracestate`. If W3C Baggage is used, the corresponding propagator must be enabled and governed by policy. **Do not assume gRPC automatically propagates trace context merely because OpenTelemetry libraries are on the classpath.**

### 8.1. Choosing a Clear Instrumentation Mechanism

In a Spring gRPC application, common integration approaches include:

- The OpenTelemetry Java agent supporting the corresponding gRPC version, or platform-provided auto-instrumentation.
- OpenTelemetry interceptors/instrumenters for `grpc-java` attached to client and server according to the documentation for the library version in use.
- Manual instrumentation via OpenTelemetry APIs and propagators when there is a specific reason.

For any approach, verify **both client and server** are instrumented and use compatible propagators. Do not attach two separate instrumentation layers that each create independent spans for the same operation unintentionally, as this causes duplicate spans and skews timing measurements.

When needing to retrieve active identifiers for logging, the OpenTelemetry Java API provides:

```java
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.SpanContext;

SpanContext spanContext = Span.current().getSpanContext();
if (spanContext.isValid()) {
    String traceId = spanContext.getTraceId();
    String spanId = spanContext.getSpanId();

    // Log per policy: correlationId, traceId, spanId.
    // Do not log authorization metadata or sensitive baggage.
}
```

`Span.current()` only returns a valid span when instrumentation and context propagation are active at the execution point. If the span is invalid, do not fabricate a fake `traceparent` just to fill log fields.

### 8.2. Distinguishing Types of Context in Java

| Type | Scope | Example |
| --- | --- | --- |
| `io.grpc.Context` | gRPC lifecycle context; can carry correlation ID or cancellation state | `CorrelationIdServerInterceptor.CURRENT_ID.get()` |
| `io.opentelemetry.context.Context` | OpenTelemetry context; can carry spans and baggage | `Span.current()` via current context |
| `org.slf4j.MDC` | Extra fields added to logs, typically thread-bound | `correlation_id`, `trace_id` |

These three mechanisms are not the same object. Instrumentation libraries may bridge contexts to execution threads, but **never assume data automatically appears in all three places**. In particular, passing `io.grpc.Context` across an executor does not guarantee MDC or OpenTelemetry context is also propagated unless the executor is instrumented.

### 8.3. Across Executors and Streaming

If the server offloads processing to an executor:

```java
import io.grpc.Context;
import java.util.concurrent.Executor;

// Inside a gRPC callback while the call's context is still active:
Context grpcContext = Context.current();
Executor executor = /* application's executor */;

executor.execute(grpcContext.wrap(() -> {
    String id = CorrelationIdServerInterceptor.CURRENT_ID.get();
    // Business processing; id is inherited via gRPC Context.
}));
```

This snippet illustrates **propagating `io.grpc.Context` only**. For OpenTelemetry, use an instrumented executor or the corresponding OpenTelemetry context wrapper. If the application logs via MDC, set and restore MDC values within the callback scope to avoid leaking one request's data onto a reused thread.

For **server streaming**, **client streaming**, and **bidirectional streaming**, metadata is sent when the RPC starts. Data varying **per message** belongs in the Protobuf message. A long-lived stream may have multiple events or child spans within the same trace according to your observability strategy, but there is no new `traceparent` header sent automatically per stream message.

## 9. Logging and Monitoring Properly

A well-structured log entry might contain:

```text
timestamp=2026-11-19T02:00:00Z
service=inventory-service
rpc=ReserveStock
correlation_id=2a29a1f7-3a20-4ab7-9f94-f147524728c1
trace_id=4bf92f3577b34da6a3ce929d0e0e4736
span_id=00f067aa0ba902b7
grpc_status=OK
duration_ms=18
```

These are **illustrative** values. Logs can be stored as JSON or key–value structures suited to your observability platform. Troubleshooting typically follows:

1. Search logs by `correlation_id` to gather events related to the task.
2. Grab `trace_id` from logs at the time of failure and open the trace to inspect spans, latency, and service call relationships.
3. Cross-reference `grpc_status`, deadlines, and errored spans to pinpoint which service or operation to investigate.
4. If the trace is broken, check instrumentation/propagators at service boundaries and context propagation across executors, jobs, or queues.

Do not use `trace_id` or `correlation_id` as a **metric label** per request in time-series metrics systems: each unique ID creates very high cardinality and easily increases storage costs. Use trace/span attributes, log fields, or exemplars depending on your observability platform's capabilities; metric labels should have bounded cardinality.

The correlation ID can be returned by the server to the client via response metadata per the application contract if useful for technical support. Only return an ID created/validated under policy and never include secrets. Returning trace context in responses is not required by default for W3C propagators to work.

## 10. Security and Trust Boundaries

Metadata is control data that can originate from a client. **Never treat any header as proof of identity or authorization.**

| Risk | Mitigation |
| --- | --- |
| Client chooses an ID colliding with someone else's | Generate a fresh correlation ID at public boundaries or accept only from trusted upstreams |
| Log injection via IDs containing newlines or control chars | Restrict allowed characters and length; use structured logging |
| Invalid or spoofed trace context | Use standard W3C propagators for validation; enforce trust policies at entry points |
| `baggage` containing tokens, emails, or personal data | Allow only non-sensitive keys, limit size and propagation scope |
| Metadata exceeding HTTP/2 header limits | Send concise values; do not stuff large messages into headers |
| Tokens or secrets accidentally appearing in logs | Do not dump entire `Metadata`; use an allowlist of logged fields |
| Losing context in async/streaming flows | Propagate context with library APIs and test on actual execution paths |
| Multiple tracing libraries creating duplicate spans | Check agent, Spring observability, and gRPC instrumentation config to avoid overlap |

`traceparent` and `baggage` are context-carrying headers; even over TLS, their values are visible to downstream services and TLS-terminating proxies. Never place secrets into baggage. Use proper authentication/authorization and TLS/mTLS per security policy, independent of the tracing system.

## 11. Testing Context Propagation

In Spring gRPC, test interceptors step by step first, then run cross-service integration tests. You can use `InProcessServerBuilder` and `InProcessChannelBuilder` to test metadata attachment without opening network ports; TLS, proxies, load balancers, and production propagator setups require a production-like environment.

| Test case | Setup | Expectation |
| --- | --- | --- |
| Missing correlation ID | Send RPC without `x-correlation-id` | Server generates a new ID and binds it to context |
| ID from trusted upstream | Send valid ID with `trustUpstream=true` | Server reads the exact ID, downstream reuses the same ID |
| Public client picks its own ID | `trustUpstream=false` | Server generates its own ID and does not trust the incoming ID |
| Malformed ID | Send ID with newline or over 64 chars | Replaced with a valid ID or rejected per chosen policy |
| Duplicate key | Send two `x-correlation-id` headers | Server handles per policy, e.g., rejects with `INVALID_ARGUMENT` |
| Two independent RPCs | Reuse stub without setting option | Client interceptor generates a new ID for each RPC |
| Two RPCs in the same task | Use stub with `withOption` sharing correlation ID | ID is inherited accurately across hops |
| Valid trace context | Instrument both client/server with W3C propagator | Spans share the same trace; parent–child link is accurate |
| Missing or invalid `traceparent` | Call through an uninstrumented hop | Creates new context per policy, without crashing or trusting invalid headers |
| Across executor | Run work outside gRPC callback | Correlation ID and span context preserved via configured propagation |
| Streaming | Send multiple messages in one RPC | Headers belong to the RPC, not treated as per-message metadata |
| Sensitive data check | Enable logging/tracing in tests | No tokens or sensitive baggage appear |

### Unit Test Illustration for Metadata Rules

The JUnit 5 test below demonstrates that multiple values for the same key must be handled explicitly:

```java
import static org.junit.jupiter.api.Assertions.*;

import io.grpc.Metadata;
import java.util.Iterator;
import org.junit.jupiter.api.Test;

class CorrelationMetadataTest {
    private static final Metadata.Key<String> KEY =
        Metadata.Key.of(
            "x-correlation-id",
            Metadata.ASCII_STRING_MARSHALLER);

    @Test
    void repeatedKeyMustNotBeSilentlyAssumedUnique() {
        Metadata headers = new Metadata();
        headers.put(KEY, "corr-first");
        headers.put(KEY, "corr-second");

        assertEquals("corr-second", headers.get(KEY));
        Iterator<String> values = headers.getAll(KEY).iterator();
        assertEquals("corr-first", values.next());
        assertEquals("corr-second", values.next());
        assertFalse(values.hasNext());
    }
}
```

This test only checks `Metadata` operations. To confirm the interceptor runs and the server actually rejects duplicate headers, test via an RPC with `CorrelationIdServerInterceptor` registered. To verify **trace continuity**, use real instrumentation, a test span exporter, and assert trace ID and parent–child relationships; seeing `traceparent` as a string is not enough.

## 12. Practical Scenario: Root-Causing a Slow RPC

An e-commerce application uses Spring gRPC: `CheckoutService` calls `InventoryService` to reserve stock and `PaymentService` to process payment. A user reports a slow transaction; logs from the three services are interleaved with many other users.

**Implementation requirements:**

1. At the gateway, generate a valid correlation ID for the transaction; only retain an upstream ID if it satisfies trust policy.
2. Attach the correlation ID to gRPC metadata when calling `CheckoutService`. Calls down to inventory and payment reuse that ID within the transaction scope.
3. Configure OpenTelemetry instrumentation on client/server with compatible propagators. Verify spans are created and trace ID is preserved across hops.
4. Emit structured logs containing `correlation_id`, `trace_id`, `span_id`, RPC name, `grpc_status`, and duration. Do not log payment info, bearer tokens, or sensitive baggage.
5. Test a normal RPC, an RPC exceeding deadline, a call offloading across an executor, and a scenario missing trace context between two services.
6. Use the trace to locate the slow span; cross-reference the correlation ID to find error logs or async events outside the same trace.

**Self-check questions:**

- How does a correlation ID differ from a trace ID and a span ID?
- Why can the parent ID in `traceparent` change as a request traverses multiple services?
- When should a new correlation ID be generated at the gateway instead of trusting a client-sent ID?
- If logs share the same correlation ID but have different trace IDs, what scenarios could explain this?
- Why is `baggage` unsuitable for passing access tokens?
- Why is passing `io.grpc.Context` across an executor insufficient to guarantee OpenTelemetry context and MDC are also transferred?
- In gRPC streaming, does metadata automatically change per Protobuf message?

**Key takeaway:** Correlation IDs link logs by task; trace context links spans in distributed tracing. With Spring gRPC, pass correlation IDs in a controlled manner via `Metadata` and interceptors, let OpenTelemetry manage `traceparent`/`tracestate` and spans, and test propagation across service boundaries and async execution. Tracing IDs aid observability but never replace authentication, authorization, or data protection.
