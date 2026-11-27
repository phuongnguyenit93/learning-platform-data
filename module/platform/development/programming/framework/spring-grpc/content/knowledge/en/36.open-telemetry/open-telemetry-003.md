# Client Span and Server Span

**Chapter:** OpenTelemetry  
**Scope:** Spring gRPC (`SPRING_GRPC`) using Protocol Buffers contracts, generated Java code, and client/server implementations for unary or streaming RPCs. This lesson focuses on the two spans representing a gRPC call: the client span on the caller side and the server span on the receiver side. Properly understanding their roles, parent/child relationship, and lifecycle helps you read distributed traces and pinpoint sources of latency or errors.

## 1. One RPC Has Two Perspectives

A gRPC call traverses two processes. The client knows when the call started, when the request was sent, and when the result arrived. The server knows when the call arrived, how long the handler ran, and when the response completed. The two perspectives complement each other:

- The **client span** records the time on the caller side executing the RPC, typically with span kind `CLIENT`.
- The **server span** records the time on the receiver side processing the RPC, typically with span kind `SERVER`.

The client span includes client-observed overhead such as sending the call, waiting for the response, and receiving the terminal status. The server span includes call time on the server side, which may include waiting for an application executor, handler execution, downstream operations, and sending the response as measured by the instrumentation.

You should not subtract the server span duration from the client span and assume the remainder is exact network latency. Both spans can be affected by clock skew, scheduling, buffering, and different instrumentation intervals. Use them to identify slow regions and cross-reference with metrics/network telemetry.

## 2. Parent/Child Relationship Between Client and Server Spans

When the client already has an active current span, gRPC client instrumentation creates the client span as a child of that span. The propagator injects the client span's `SpanContext` into request metadata. On the server, instrumentation extracts the metadata and creates a server span with the same trace ID, with the client span as its remote parent.

~~~mermaid
flowchart TD
    A["Parent span: checkout workflow"] --> B["CLIENT: OrderService/CreateOrder"]
    B --> C["SERVER: OrderService/CreateOrder"]
    C --> D["Child span: validate order"]
    C --> E["CLIENT: InventoryService/Reserve"]
    E --> F["SERVER: InventoryService/Reserve"]
~~~

In the trace tree:

- The client span and server span belong to the same trace.
- The server span links to the client span via the parent span ID propagated in trace context.
- The server span becomes the parent of internal business spans inside the handler.
- If the server calls another gRPC service, the downstream client span is a child of the current span on the server.

If trace context is absent from metadata or the server fails to extract the context, the server span may become the root of a new trace. Two spans with the same method name but different trace IDs do not form a distributed trace.

## 3. Which Perspective Does Span Kind Represent?

OpenTelemetry defines span kinds to describe the role of an operation:

| Span kind | Meaning in gRPC | Example |
| --- | --- | --- |
| `CLIENT` | The current process invokes an RPC on another process | Order service calls Inventory service |
| `SERVER` | The current process receives and handles an RPC | Inventory service receives Reserve |
| `INTERNAL` | Internal work within a single process | Validate request, calculate price |
| `PRODUCER` / `CONSUMER` | Producing/receiving messages in a messaging system | Publish/consume events via a broker |

Do not create span kind `SERVER` on the client or `CLIENT` on the server merely because of a method name. The kind must reflect the communication direction from the perspective of the process creating the span.

## 4. Creating Client and Server Spans with gRPC Instrumentation

For gRPC Java, OpenTelemetry provides instrumentation that can create both span types and propagate context via interceptors:

~~~java
import io.grpc.ClientInterceptor;
import io.grpc.ServerInterceptor;
import io.opentelemetry.api.OpenTelemetry;
import io.opentelemetry.instrumentation.grpc.v1_6.GrpcTelemetry;

public final class GrpcTracingInterceptors {

    private final GrpcTelemetry grpcTelemetry;

    public GrpcTracingInterceptors(OpenTelemetry openTelemetry) {
        this.grpcTelemetry = GrpcTelemetry.create(openTelemetry);
    }

    public ClientInterceptor clientInterceptor() {
        return grpcTelemetry.newClientInterceptor();
    }

    public ServerInterceptor serverInterceptor() {
        return grpcTelemetry.newServerInterceptor();
    }
}
~~~

The client interceptor must be attached to the channel:

~~~java
ManagedChannel channel = NettyChannelBuilder
        .forAddress(host, port)
        .intercept(grpcTracingInterceptors.clientInterceptor())
        .build();
~~~

The server interceptor must be attached to the server chain. In Spring gRPC, the server is typically managed by the starter; register the interceptor using the extension point/global interceptor registration provided by your starter version. Declaring an interceptor bean alone does not automatically prove it has been applied to the server and every channel.

If the application already uses the OpenTelemetry Java agent with gRPC auto-instrumentation, the agent may already create client/server spans. Avoid adding manual interceptors for the same boundary without checking for duplicate spans. Choose one instrumentation mechanism per RPC boundary.

## 5. Attributes of Client Spans and Server Spans

gRPC instrumentation can record the method name, service, peer/server, and status. The exact attribute set depends on the instrumentation version and the enabled semantic conventions version. Some versions use the `rpc.system`, `rpc.service`, `rpc.method` group; newer semantic convention versions may use differently standardized attribute names.

Useful information during analysis:

- RPC system is gRPC.
- Service and method, for example `orders.v1.OrderService/CreateOrder`.
- Span kind is `CLIENT` or `SERVER`.
- Status code or completion status of the RPC.
- Server/peer address if telemetry policy permits.
- Resource attributes such as `service.name`, `service.version`, and deployment environment.

Do not manually write a differently named key set for the same information when instrumentation already provides the corresponding semantic conventions. When upgrading versions, check semantic convention changes so dashboards and queries do not break.

Do not put order ID, customer ID, email, tokens, or raw requests in span names/attributes. High-cardinality values increase backend costs and may contain sensitive data. If correlation with business logs is needed, use an approved correlation identifier with data protection policies.

## 6. Client Span Lifecycle

For a unary RPC, the client span typically starts when client instrumentation initiates the call and ends when gRPC delivers a terminal outcome:

1. Client instrumentation creates a span of kind `CLIENT`.
2. The propagator injects context into request metadata.
3. The stub sends the request.
4. The client waits for a response or error.
5. When the call completes, is cancelled, or fails, instrumentation records the outcome and ends the span.

With an async stub, the Java method may return immediately after starting the call; that does not mean the client span has ended. The span must cover the call until the terminal callback occurs.

For client-streaming or bidirectional streaming, the span typically covers the entire RPC stream. Finishing sending the final message on one side does not necessarily mean the call has ended; the client span ends only when the RPC has a terminal result per gRPC semantics.

## 7. Server Span Lifecycle

The server span starts when server instrumentation receives the call and can extract the remote parent context from metadata. The span covers call processing time across the server lifecycle:

- Invoking the service method and processing the request.
- Receiving additional messages in client-streaming/bidirectional streaming.
- Sending response messages in server-streaming/bidirectional streaming.
- Handling exceptions, cancellation, or deadlines.
- Finishing the call with completion or an error status.

For a unary RPC, the handler typically sends one response and calls `onCompleted()`. For a streaming RPC, the service method may return the inbound observer as soon as the stream begins; the server span must not end merely because the Java method returned the observer.

Server instrumentation should end the span when the call reaches a terminal state. If you write custom instrumentation, you must wrap callbacks and properly handle `onComplete`, `onCancel`, errors, and races between terminal branches. Prefer tested interceptor instrumentation over manual lifecycle management unless there is a special requirement.

## 8. Downstream RPCs Create Nested Spans

Suppose the Order service receives `CreateOrder` and then calls the Inventory service:

1. Order's client creates a `CLIENT` span for `CreateOrder`.
2. Order server creates a `SERVER` span for `CreateOrder`.
3. When Order calls Inventory, client instrumentation creates a `CLIENT` span for `Reserve` under the Order server span.
4. Inventory server extracts metadata and creates a `SERVER` span for `Reserve`.

Because of this relationship, the trace shows both Order's processing time and the time spent waiting on Inventory. If Order also queries a database, JDBC auto-instrumentation can create a child database span; otherwise, you can selectively add internal child spans.

Do not manually create a span named `CreateOrder` inside the handler if server instrumentation already creates the server span for the RPC itself. Custom spans should represent distinct business steps such as `validate_order` or `reserve_inventory`.

## 9. Recording Status and Exceptions

The client and server can observe the same RPC outcome from two different sides. For example, the server returns `NOT_FOUND`; the server span records the server-side processing outcome, and the client span records the error received by the caller.

Common statuses to analyze:

| gRPC status | Common meaning | What to inspect |
| --- | --- | --- |
| `OK` | RPC completed successfully | Latency and child spans |
| `INVALID_ARGUMENT` | Request violated contract | Boundary validation and client input |
| `NOT_FOUND` | Resource does not exist | Lookup result and API semantics |
| `PERMISSION_DENIED` | Caller is not permitted | Authorization policy |
| `UNAVAILABLE` | Service/dependency temporarily unavailable | Network, server availability, retry |
| `DEADLINE_EXCEEDED` | Time budget exhausted | Queueing, dependency latency, timeout propagation |
| `CANCELLED` | Caller or runtime cancelled the call | User cancellation, shutdown, or deadline flow |

Instrumentation typically attaches status and error attributes according to the library version. Do not automatically mark every non-`OK` status as a programming bug; business statuses should be classified consistently in dashboards. Do not record exception messages containing SQL, tokens, or PII in spans.

## 10. Retries and Multiple Attempts

A single logical operation from the application can lead to multiple RPC attempts due to retry policies or application retries. Distinguish between:

- Logical operation: the caller's business intent, such as creating an order.
- RPC call/attempt: a single execution of gRPC communication.

Depending on the gRPC runtime and instrumentation, a trace may represent one span for the logical call, separate attempts, or related spans in other ways. Do not assume every retry creates an independent client span in the exact same way; verify against your instrumentation version and actual traces.

When analyzing retries, observe the attempt count, each attempt's status, backoff, and total logical operation duration. An `UNAVAILABLE` attempt followed by an `OK` attempt can still cause high overall latency even though the server eventually succeeded.

Do not add payloads or sensitive idempotency keys to spans. If you need to identify retry groups, use a low-cardinality technical attribute without business identifiers.

## 11. Async Executors and Parent Context

If the server handler offloads work to a separate executor, OpenTelemetry `Context` must be captured and propagated to the worker. Otherwise, child spans created in the worker can become root spans or attach to the wrong parent:

~~~java
Context captured = Context.current();
workerExecutor.execute(captured.wrap(() -> {
    Span child = tracer.spanBuilder("order.load_inventory")
            .startSpan();
    try (Scope scope = child.makeCurrent()) {
        inventoryRepository.load();
    } catch (RuntimeException failure) {
        child.recordException(failure);
        child.setStatus(StatusCode.ERROR);
        throw failure;
    } finally {
        child.end();
    }
}));
~~~

Capture the context directly inside the RPC callback, before submitting the task. Never store the context in a mutable field of a singleton Spring service. If the worker needs gRPC deadline/cancellation or Spring `SecurityContext`, propagate those contexts using their respective mechanisms; OpenTelemetry `Context` only carries telemetry context.

## 12. Sampling and Trace Completeness

Client spans and server spans need the same sampling decision so traces do not break. A parent-based sampler typically preserves the sampling decision from propagated context. If each process samples randomly and independently, one side may retain a span while the other drops it.

In environments with collector tail sampling, the collector can decide whether to retain a trace based on the full trace received—for example, keeping slow or errored traces. You must account for buffering, trace-completion wait timeouts, and potential missing spans if a service fails to export.

Sampling does not replace metrics. Metrics must still measure latency, throughput, and error rate across all traffic, including requests not sampled into traces.

## 13. Testing Client Spans and Server Spans

Tracing tests should verify relationships rather than just counting spans:

1. A `CLIENT`-kind span exists for outbound RPCs.
2. A `SERVER`-kind span exists for inbound RPCs.
3. Both spans share the same trace ID when propagation is active.
4. The server span has a parent span ID matching the client span.
5. Downstream client spans are children of the current server span.
6. Spans end after the terminal event for streaming RPCs.
7. Errors/cancellations are recorded and do not leave spans open indefinitely.

The OpenTelemetry SDK can use `InMemorySpanExporter` in tests to collect spans without a collector. Test configuration must use the same OpenTelemetry instance for client/server interceptors:

~~~java
import io.opentelemetry.api.OpenTelemetry;
import io.opentelemetry.api.trace.SpanKind;
import io.opentelemetry.api.trace.propagation.W3CTraceContextPropagator;
import io.opentelemetry.context.propagation.ContextPropagators;
import io.opentelemetry.instrumentation.grpc.v1_6.GrpcTelemetry;
import io.opentelemetry.sdk.OpenTelemetrySdk;
import io.opentelemetry.sdk.testing.exporter.InMemorySpanExporter;
import io.opentelemetry.sdk.trace.SdkTracerProvider;
import io.opentelemetry.sdk.trace.data.SpanData;
import io.opentelemetry.sdk.trace.export.SimpleSpanProcessor;

import java.util.List;
import static org.junit.jupiter.api.Assertions.*;

InMemorySpanExporter exporter = InMemorySpanExporter.create();
SdkTracerProvider tracerProvider = SdkTracerProvider.builder()
        .addSpanProcessor(SimpleSpanProcessor.create(exporter))
        .build();

OpenTelemetry openTelemetry = OpenTelemetrySdk.builder()
        .setTracerProvider(tracerProvider)
        .setPropagators(ContextPropagators.create(
                W3CTraceContextPropagator.getInstance()))
        .build();

GrpcTelemetry grpcTelemetry = GrpcTelemetry.create(openTelemetry);
ClientInterceptor clientTracing =
        grpcTelemetry.newClientInterceptor();
ServerInterceptor serverTracing =
        grpcTelemetry.newServerInterceptor();
~~~

Attach the client interceptor to an in-process channel and the server interceptor to an in-process server, invoke the generated stub, and inspect `exporter.getFinishedSpanItems()`. Use `SpanKind.CLIENT`, `SpanKind.SERVER`, trace ID, and parent span ID to verify the relationship.

Example assertions after a unary RPC finishes:

~~~java
List<SpanData> spans = exporter.getFinishedSpanItems();
SpanData clientSpan = spans.stream()
        .filter(span -> span.getKind() == SpanKind.CLIENT)
        .findFirst()
        .orElseThrow();
SpanData serverSpan = spans.stream()
        .filter(span -> span.getKind() == SpanKind.SERVER)
        .findFirst()
        .orElseThrow();

assertEquals(
        clientSpan.getSpanContext().getTraceId(),
        serverSpan.getSpanContext().getTraceId());
assertEquals(
        clientSpan.getSpanContext().getSpanId(),
        serverSpan.getParentSpanContext().getSpanId());
~~~

With streaming, keep the test open until the stream completes before asserting exported spans. Use a latch/future with a timeout rather than `Thread.sleep()` to guess when spans finish. Close the channel, server, and tracer provider after the test.

## 14. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Only client span exists | Cannot see where server processing goes | Register server instrumentation |
| Only server span exists | Trace may lose relationship to caller | Client injects context and server extracts it |
| Wrong span kind | Trace tree misinterprets communication direction | Use `CLIENT` for outbound, `SERVER` for inbound |
| Server span ends when handler returns observer | Streaming duration is truncated | End at the terminal event |
| Manually creating extra RPC spans | Duplicate spans and cluttered trace tree | Only create child spans for business steps |
| Switching executors without propagating context | Child span loses parent | Wrap tasks with OpenTelemetry `Context` |
| Java agent and interceptor both instrumenting | Duplicate client/server spans | Choose one mechanism at each boundary |
| Treating duration difference as exact network latency | Wrong conclusions due to clock/scheduling | Cross-check traces with metrics and other timing |
| Recording raw requests or identifiers in attributes | Data exposure, high cardinality | Redact and limit attributes |

## 15. Practice Exercises

1. A client calls the Order service, and then Order calls Inventory. Sketch the parent/child relationships of the four `CLIENT`/`SERVER` spans.
2. Why do the client span and server span usually have the same trace ID but different span IDs?
3. A client-streaming handler returns the inbound observer immediately. When should the server span end?
4. When an RPC returns `UNAVAILABLE` and then a retry succeeds, what information must you inspect to understand total latency?
5. How do you test that the server span has the client span as its remote parent?
6. When offloading work to an executor, besides OpenTelemetry `Context`, what other application contexts must be propagated?

**Key Takeaway:** A client span describes an RPC from the caller's perspective and usually has kind `CLIENT`; a server span describes the same call from the receiver's perspective and usually has kind `SERVER`. W3C trace context links the server span to the client span through metadata. Inspect parent-child relationships, statuses, and lifecycles together; for streaming, spans must cover through the terminal event. Use standard instrumentation, avoid duplicate spans, and never put secrets/PII into telemetry.
