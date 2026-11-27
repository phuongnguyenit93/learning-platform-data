# Trace Span for Each RPC

**Chapter:** OpenTelemetry  
**Scope:** Spring gRPC (`SPRING_GRPC`) using Protocol Buffers contracts, generated Java code, and client/server implementations for unary or streaming RPCs. This lesson focuses on creating a trace span for each RPC, linking client spans with server spans, propagating trace context through metadata, and observing processing time across services.

## 1. Why Do We Need a Span for Each RPC?

A business request often traverses multiple components. For example, a client calls the Order service; the Order service checks inventory via the Inventory service and then writes data. Measuring only the total time at the client does not tell us where a slowdown occurs.

Distributed tracing describes a request as a **trace** consisting of multiple **spans**:

- A trace is the entire journey of a request across one or more services.
- A span represents an operation with start/end timestamps, a name, attributes, a status, and parent/child relationships.
- A parent span represents the calling operation; a child span represents the work invoked inside it.

With gRPC, you typically need a client span for an outbound RPC and a server span for an inbound RPC. If the server calls another downstream gRPC service, that call creates a child client span under the current server span.

~~~mermaid
flowchart TD
    A["Trace: CreateOrder"] --> B["Client span: orders.v1.OrderService/CreateOrder"]
    B --> C["Server span: orders.v1.OrderService/CreateOrder"]
    C --> D["Child span: validate order"]
    C --> E["Client span: inventory.v1.InventoryService/Reserve"]
    E --> F["Server span: inventory.v1.InventoryService/Reserve"]
    C --> G["Child span: persist order"]
~~~

By inspecting the trace tree, operators can determine whether time is spent at the RPC boundary, validation, database, or a downstream service. A span is only useful when it has the right relationship to the trace and is ended at the right time.

## 2. Where Are Trace Spans Created in gRPC?

You do not need to manually write a span in every service method. The standard approach is to use OpenTelemetry gRPC instrumentation:

- A **client interceptor** creates a client span around the outbound RPC and injects trace context into the request metadata.
- A **server interceptor** extracts trace context from the metadata and creates a server span as a child of the client span.
- The instrumentation ends the span when the RPC completes, fails, or is cancelled; it also records the status according to the instrumentation version's capabilities.

For streaming RPCs, the span typically covers the entire call lifecycle, from start until a terminal event (`onCompleted`, `onError`, or cancellation). Do not create a new server span for every message if the goal is to track a single RPC; message-level work can be recorded with events or separate child spans when truly needed.

## 3. Adding OpenTelemetry gRPC Instrumentation

For the gRPC Java 1.6 API, instrumentation can be used via the **opentelemetry-grpc-1.6** artifact and the **GrpcTelemetry** class. Manage its version alongside your application's OpenTelemetry BOM so that the API and runtime are compatible.

Example of creating interceptors from an OpenTelemetry instance configured with an SDK/exporter:

~~~java
import io.grpc.ClientInterceptor;
import io.grpc.ServerInterceptor;
import io.opentelemetry.api.OpenTelemetry;
import io.opentelemetry.instrumentation.grpc.v1_6.GrpcTelemetry;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class GrpcTracingConfiguration {

    @Bean
    public ServerInterceptor openTelemetryServerInterceptor(
            OpenTelemetry openTelemetry) {
        return GrpcTelemetry.create(openTelemetry)
                .newServerInterceptor();
    }

    @Bean
    public ClientInterceptor openTelemetryClientInterceptor(
            OpenTelemetry openTelemetry) {
        return GrpcTelemetry.create(openTelemetry)
                .newClientInterceptor();
    }
}
~~~

The two beans above create the interceptors; they are only used when registered in the interceptor chain. With a direct gRPC Java server builder:

~~~java
NettyServerBuilder.forPort(port)
        .intercept(openTelemetryServerInterceptor)
        .addService(orderGrpcService)
        .build();
~~~

With a client channel:

~~~java
ManagedChannel channel = NettyChannelBuilder
        .forAddress(host, port)
        .intercept(openTelemetryClientInterceptor)
        .build();
~~~

In Spring gRPC, the server is typically created by a starter/auto-configuration. Register the server interceptor via the extension point or global interceptor registration supported by your project's starter version; simply declaring a bean does not guarantee that the interceptor is automatically attached to the server. Similarly, the client interceptor must be attached to the channel or channel customization mechanism used by the application.

Another option is the OpenTelemetry Java agent with auto-instrumentation for gRPC. When the agent already creates client/server spans, do not also add manual interceptors for the same RPC without verifying a mechanism to prevent duplicate spans. Choose one instrumentation mechanism per boundary.

## 4. Configuring the SDK, Exporter, and Propagator

Interceptors require a configured OpenTelemetry instance. In production environments, applications typically use the OpenTelemetry SDK with an OTLP exporter to send spans to a collector:

~~~java
OpenTelemetrySdk openTelemetry = OpenTelemetrySdk.builder()
        .setTracerProvider(sdkTracerProvider)
        .setPropagators(ContextPropagators.create(
                W3CTraceContextPropagator.getInstance()))
        .build();
~~~

Here, `sdkTracerProvider` is a provider already configured with a resource, sampler, and span processor/exporter. You should not create an independent SDK inside each service bean; manage a single shared instance across the application lifecycle.

Key components:

- **Resource:** identifies the service, for example `service.name=orders`, the environment, and the deployment version.
- **Sampler:** decides which traces are recorded.
- **Span processor/exporter:** processes finished spans and sends data to a collector/backend.
- **Propagator:** injects/extracts trace context across process boundaries; W3C Trace Context typically uses `traceparent` and `tracestate`.

The SDK/exporter can be configured via a Spring Boot starter, Java agent, or code. What matters is that the gRPC interceptors and business spans use the same OpenTelemetry provider/context.

## 5. How Does Trace Context Travel Through Metadata?

The current client span has a `SpanContext` containing a trace ID, span ID, and sampling flags. The client propagator injects the context into the outbound RPC's metadata. The server interceptor extracts that metadata to create a server span with the same trace ID and corresponding parent.

General flow:

1. The client starts a client span.
2. The propagator writes the W3C trace context into metadata, typically the `traceparent` header and, depending on the case, `tracestate`.
3. The server interceptor reads the metadata and creates a server span linked to the client span.
4. If the server calls a downstream service, the client interceptor creates a child span and injects the context onward.
5. Every service in the same journey can be stitched into a single trace.

Do not generate a new trace ID in each service. If metadata is not propagated, the tracing backend will display disconnected traces even though the RPCs belong to the same request.

Do not trust trace context metadata as authentication data. A trace ID is only for correlating telemetry; it does not prove caller identity and must not be used in place of authorization.

## 6. Naming Spans and Adding Useful Attributes

RPC instrumentation typically generates span names and attributes automatically according to the library version's semantic conventions. Useful attributes can include:

- The RPC system as gRPC.
- The service and method name, for example `orders.v1.OrderService/CreateOrder`.
- The RPC status code or completion status.
- Network peer/server address at the level permitted for collection.
- Resource attributes such as service name, service version, and deployment environment.

Prefer attributes produced by standard instrumentation. Semantic convention names can change between versions; avoid overwriting the same meaning with multiple different keys.

Custom attributes should have low cardinality and help answer operational questions:

~~~java
span.setAttribute("app.operation", "reserve_inventory");
span.setAttribute("app.region", regionCode);
~~~

Do not add order ID, email, account ID, tokens, or arbitrary request values as span names/attributes. High-cardinality values increase storage costs and can expose personal data.

## 7. Creating Child Spans for a Business Step

Instrumentation already creates the RPC span. If you need to know the time spent specifically on validation or a repository call, create a child span inside the handler/use case rather than creating a second sibling RPC span.

~~~java
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.StatusCode;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.context.Scope;
import org.springframework.stereotype.Service;

@Service
public class ReserveInventoryUseCase {

    private final Tracer tracer;
    private final InventoryRepository repository;

    public ReserveInventoryUseCase(
            Tracer tracer,
            InventoryRepository repository) {
        this.tracer = tracer;
        this.repository = repository;
    }

    public Reservation reserve(String sku, int quantity) {
        Span span = tracer.spanBuilder("inventory.validate_and_reserve")
                .startSpan();
        try (Scope scope = span.makeCurrent()) {
            span.setAttribute("app.operation", "reserve_inventory");
            validate(sku, quantity);
            return repository.reserve(sku, quantity);
        } catch (RuntimeException failure) {
            span.recordException(failure);
            span.setStatus(StatusCode.ERROR);
            throw failure;
        } finally {
            span.end();
        }
    }
}
~~~

The child span automatically inherits its parent from the current OpenTelemetry `Context` when the RPC instrumentation has attached the server span. `makeCurrent` makes the new span the current span within the scope; `finally` ensures the span is ended even if the business logic throws an error.

Do not record exception messages containing sensitive data in attributes. `recordException` may record exception type/message/stack depending on the SDK; configure a redaction policy or only record controlled exceptions. If the RPC instrumentation already records error status, the child span should only describe its business step, avoiding duplicating the RPC span.

## 8. Propagating Context When Switching to Another Executor

OpenTelemetry `Context` is typically attached while the server interceptor invokes the handler. When the application submits work to a custom executor, do not assume the new thread automatically has the RPC's context.

Capture the context at submission time and wrap the task:

~~~java
import io.opentelemetry.context.Context;

Context captured = Context.current();
workerExecutor.execute(captured.wrap(() -> {
    Span span = Span.current();
    span.addEvent("blocking-work-started");
    processBlockingOperation();
}));
~~~

As a result, child spans created in the worker still maintain their relationship with the parent RPC span. Capture the context belonging to the right RPC; never store the context in a singleton field and reuse it for another request.

gRPC `io.grpc.Context` and OpenTelemetry `io.opentelemetry.context.Context` are two different context types. Some instrumentation integrates propagation for gRPC callbacks, but when switching to an application-managed executor, ensure both required gRPC data (deadline/cancellation/principal by design) and OpenTelemetry context are propagated properly. Do not confuse propagating trace context with propagating security identity.

## 9. Status, Exceptions, and Span Lifecycle

An RPC span must end when the RPC ends:

- Successful unary: ends after the response completes.
- Failed unary: ends with the error status.
- Client/server/bidirectional streaming: the span covers the whole call and ends when the stream completes, errors, or is cancelled.
- Deadline/cancellation: records the corresponding outcome without leaving the span open indefinitely.

gRPC instrumentation typically handles status and exceptions in the interceptor. If you instrument manually, ensure every terminal branch ends the span exactly once. Do not end the span immediately when the server method returns for a streaming RPC; the method can return an observer early while the stream is still active.

gRPC statuses such as `INVALID_ARGUMENT`, `NOT_FOUND`, `PERMISSION_DENIED`, `UNAVAILABLE`, and `DEADLINE_EXCEEDED` help classify errors on spans. Not every business status must be treated as a programming error; apply error status conventions consistent with your instrumentation and how your backend displays errors.

## 10. Sampling and Tracing Cost

You do not always need to store every trace. Sampling decides which traces are recorded:

- **Always-on:** suitable for dev/test environments or low traffic; cost grows rapidly under high traffic.
- **Probability/parent-based sampling:** retains traces at a configured ratio and respects the parent's sampling decision.
- **Tail sampling at the collector:** can retain slow/errored traces after the collector observes enough of the trace, but requires appropriate infrastructure and buffering.

With microservices, parent-based propagation ensures services in the same trace follow a consistent sampling decision. If each service performs random sampling independently, traces may miss spans in the middle.

Measure overhead and consider sampling based on traffic, data sensitivity, retention, and investigation requirements. Sampling does not replace metrics; metrics are still needed to represent latency/error rates across all traffic.

## 11. Security and Privacy

Traces can travel across multiple services and be stored in a centralized backend. Before adding data to a span:

- Do not record access tokens, authorization metadata, passwords, or secrets.
- Avoid recording raw protobuf requests/responses.
- Do not put PII, message contents, or high-cardinality identifiers into span names.
- Limit baggage; baggage is propagated across services and can increase metadata size.
- Export only to controlled collectors/backends; use TLS and exporter authentication when deploying over a network.
- Set telemetry retention and access controls appropriate for operational data.

Trace context is not a business data transport channel. Propagate only trace ID, span ID, sampling state, and minimal approved baggage.

## 12. Testing Trace Spans for RPCs

At least four properties should be tested:

1. Client/server RPCs create the corresponding spans.
2. The client span and server span share the same trace ID and have a parent-child relationship.
3. A downstream RPC creates a child span under the current server span.
4. Errors/cancellations still end the span and record an appropriate status.

The OpenTelemetry SDK provides `InMemorySpanExporter` in its test artifact to inspect spans without an external collector. Sample setup:

~~~java
InMemorySpanExporter exporter = InMemorySpanExporter.create();
SdkTracerProvider tracerProvider = SdkTracerProvider.builder()
        .addSpanProcessor(SimpleSpanProcessor.create(exporter))
        .build();

OpenTelemetry openTelemetry = OpenTelemetrySdk.builder()
        .setTracerProvider(tracerProvider)
        .setPropagators(ContextPropagators.create(
                W3CTraceContextPropagator.getInstance()))
        .build();

ServerInterceptor serverTracing =
        GrpcTelemetry.create(openTelemetry).newServerInterceptor();
ClientInterceptor clientTracing =
        GrpcTelemetry.create(openTelemetry).newClientInterceptor();
~~~

Attach the server interceptor to an in-process server builder and the client interceptor to an in-process channel, invoke the generated stub, and then retrieve `exporter.getFinishedSpanItems()` to verify:

| Case | Assertion |
| --- | --- |
| Successful unary | Client span and server span exist for the method |
| Context propagation | Both spans share the same trace ID; server span's parent is the client span |
| Downstream RPC | Child client span exists under the server span |
| RPC returns error status | Span ends and reflects the error outcome according to instrumentation |
| Streaming completes | Span only ends when the stream terminal event occurs |
| Cancellation/deadline | Span is ended and does not hang |
| Async worker | Child span in the worker still belongs to the RPC's trace |

Tests must shut down the channel/server and `tracerProvider` after running to release resources. For streaming tests, use a latch/future with a timeout to wait for the terminal event and span export; do not use `Thread.sleep` for synchronization.

## 13. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Creating spans only on the server without client propagation | Traces break at the RPC boundary | Attach both client and server instrumentation |
| Each service generates a new trace ID | Cannot stitch distributed traces | Use the W3C propagator and propagate context |
| Enabling Java agent and manual interceptors together | Duplicate RPC spans | Choose one instrumentation mechanism per boundary |
| Manually creating an RPC span on top of automatic spans | Extra spans in trace tree, hard to read | Only create child spans for business steps |
| Not ending the span of a streaming call | Long-lived or leaked spans | End the span on terminal events |
| Switching executors without propagating context | Child span becomes root or loses parent | Wrap tasks with OpenTelemetry `Context` |
| Recording raw requests/tokens in attributes | Data exposure and increased cardinality | Redact and record only minimal attributes |
| Using spans instead of metrics | No stable aggregate statistics | Combine traces, metrics, and logs |

## 14. Practice Exercises

1. A client calls the Order service and then Order calls the Inventory service. Describe the expected client/server spans and parent/child relationships.
2. Why is installing only a server interceptor not enough to connect a trace from an external client?
3. A handler submits a JDBC task to a separate executor. What must be done so that a child span in the worker keeps the right parent?
4. With bidirectional streaming, why should the span not end immediately when the method returns the inbound observer?
5. How do you avoid duplicate spans when the application is already running the OpenTelemetry Java agent?
6. What data should not be placed in span attributes or baggage?

**Key Takeaway:** Create client and server spans for each RPC using OpenTelemetry gRPC instrumentation, propagate W3C trace context through metadata, and create child spans for business steps that need analysis. Spans must accurately cover the unary/streaming call lifecycle, end on success/error/cancellation, preserve their parent across executor switches, and never contain secrets or PII. Combine traces with metrics/logs for full-system observability.
