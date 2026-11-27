# Propagator via Metadata

**Chapter:** OpenTelemetry  
**Scope:** Spring gRPC (`SPRING_GRPC`) using Protocol Buffers contracts, generated Java code, and client/server implementations for unary or streaming RPCs. This lesson focuses on how OpenTelemetry propagators carry trace context through gRPC metadata so that spans across multiple services are linked into a single distributed trace.

## 1. Why Must Context Be Propagated?

When a client calls the Order service, and the Order service calls the Inventory service, each process can create its own spans. Without passing correlation information across the RPC boundary, the tracing backend may display those spans as independent traces. Operators will find it hard to tell that they belong to the same request.

OpenTelemetry `Context` carries current telemetry information, typically including the `SpanContext` of the active span and optionally baggage. A propagator converts the context data to be transmitted into fields on a protocol carrier. For gRPC, that carrier is the RPC `Metadata`.

Two core operations:

- **Inject:** the caller writes the trace context from OpenTelemetry `Context` into outbound metadata.
- **Extract:** the receiver reads inbound metadata and reconstructs the corresponding OpenTelemetry `Context`.

This flow transmits trace correlation context; it does not send the entire `Context` object over the network and does not replace authentication, authorization, or gRPC `Context`.

~~~mermaid
sequenceDiagram
    participant A as Order client
    participant M as gRPC metadata
    participant B as Inventory server
    A->>A: Current span / SpanContext
    A->>M: Propagator inject(traceparent, tracestate)
    M->>B: HTTP/2 metadata
    B->>B: Propagator extract
    B->>B: Create server span with remote parent
    B-->>A: RPC response
~~~

When context is propagated properly, the client span and server span share the same trace ID; the server span has a parent relationship to the client span according to instrumentation conventions.

## 2. What Does W3C Trace Context Include?

W3C Trace Context is a widely used format for propagating trace identity across systems. Two commonly encountered headers:

| Header | Role |
| --- | --- |
| `traceparent` | Carries version, trace ID, parent span ID, and trace flags |
| `tracestate` | Carries vendor-specific information standardized under W3C rules |

Example `traceparent` value:

~~~text
00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

This value contains the trace ID, the parent operation's span ID, and the sampling flag. Applications should not manually parse or concatenate this string. The W3C propagator is responsible for format validation, injection, and extraction according to the specification.

OpenTelemetry commonly uses the W3C Trace Context propagator. If you need to propagate baggage, you can enable the W3C Baggage propagator; propagate only small, non-sensitive, low-cardinality attributes.

## 3. gRPC Metadata Is the Carrier

gRPC metadata is a set of key/value pairs accompanying an RPC:

- The client sends request metadata when starting the call.
- The server may send initial response headers.
- The server sends trailers when the RPC finishes.

Outbound trace context is injected into request metadata. The server side extracts it from the received metadata before invoking the application handler or creating the server span according to the instrumentation.

W3C header names such as `traceparent` and `tracestate` fit gRPC ASCII metadata. Metadata key names must be lowercase. gRPC binary keys use the `-bin` suffix and a binary marshaller; `traceparent`/`tracestate` are text, so they do not use `-bin`.

Do not confuse request metadata with response headers/trailers. Injecting trace context on the client does not mean the server returns `traceparent` in the response; trace correlation is maintained because the server extracts the parent context and creates the appropriate span.

## 4. Using OpenTelemetry gRPC Instrumentation

In gRPC Java, the preferred approach is to use OpenTelemetry gRPC instrumentation. The client-side interceptor handles the client span and injects context; the server-side interceptor extracts context and creates the server span.

Example creating both interceptors from a shared OpenTelemetry instance:

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
    public ClientInterceptor tracingClientInterceptor(
            OpenTelemetry openTelemetry) {
        return GrpcTelemetry.create(openTelemetry)
                .newClientInterceptor();
    }

    @Bean
    public ServerInterceptor tracingServerInterceptor(
            OpenTelemetry openTelemetry) {
        return GrpcTelemetry.create(openTelemetry)
                .newServerInterceptor();
    }
}
~~~

The interceptors must be registered into the channel/server interceptor chains. In Spring gRPC, use your starter's extension point to register the global server interceptor; the client interceptor must be attached to the `ManagedChannel` or the corresponding channel customizer. Simply declaring a bean does not automatically guarantee that every channel and server will use that bean.

With a directly constructed client channel:

~~~java
ManagedChannel channel = NettyChannelBuilder
        .forAddress(host, port)
        .intercept(tracingClientInterceptor)
        .build();
~~~

A direct server builder can register a server interceptor via the builder's `intercept` API. In a Spring application, do not create a second server just to add an interceptor if the starter already manages the existing server.

If the application already uses the OpenTelemetry Java agent with gRPC auto-instrumentation, the agent can create spans and propagate context automatically. Do not add manual interceptors for the same boundary without verifying duplicate-span prevention. Choose one instrumentation mechanism per client/server boundary.

## 5. How Does an OpenTelemetry Propagator Work?

The main API is `TextMapPropagator`. It is independent of gRPC; it accepts a carrier along with a setter/getter provided by the protocol:

- The setter writes a key/value pair into the carrier during injection.
- The getter reads a value from the carrier during extraction and lists readable keys.

For gRPC, the carrier is the `Metadata` object. The gRPC instrumentation already provides suitable adapters; therefore applications typically do not need to write their own setter/getter. Implementing a custom carrier is only useful when integrating a custom transport or when you need to understand the inject/extract boundary in detail.

## 6. Metadata Setter/Getter Example

The example below illustrates a carrier for text metadata. Keys are normalized to lowercase and use the ASCII marshaller:

~~~java
import io.grpc.Metadata;
import io.opentelemetry.context.propagation.TextMapGetter;
import io.opentelemetry.context.propagation.TextMapSetter;
import java.util.Locale;
import java.util.Set;

public final class GrpcMetadataCarrier {

    private GrpcMetadataCarrier() {}

    public static final TextMapSetter<Metadata> SETTER =
            (carrier, key, value) -> {
                if (carrier == null || key == null || value == null) {
                    return;
                }
                String normalizedKey = key.toLowerCase(Locale.ROOT);
                Metadata.Key<String> metadataKey =
                        Metadata.Key.of(
                                normalizedKey,
                                Metadata.ASCII_STRING_MARSHALLER);
                carrier.put(metadataKey, value);
            };

    public static final TextMapGetter<Metadata> GETTER =
            new TextMapGetter<>() {
                @Override
                public Iterable<String> keys(Metadata carrier) {
                    return carrier == null
                            ? Set.of()
                            : carrier.keys();
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

This is an illustrative example for W3C text headers. In production code, include the `Locale` import, validate keys, and ensure you do not unintentionally overwrite metadata of the same name. Do not use this carrier to read/write binary metadata; binary keys require a separate marshaller and the `-bin` suffix.

With a freshly created `Metadata` for an outbound call, the setter can write `traceparent`/`tracestate` into the carrier. If reusing a carrier that already contains keys, clearly define whether to replace or reject duplicates; never allow multiple conflicting `traceparent` entries in the same RPC.

## 7. Injecting on the Client and Extracting on the Server

To understand how the propagator is invoked, the example below demonstrates the two operations at the RPC boundary. This is a manual integration pattern; when using the `GrpcTelemetry` interceptors, do not repeat the same operations.

Inject the current context into request metadata:

~~~java
import io.grpc.Metadata;
import io.opentelemetry.api.OpenTelemetry;
import io.opentelemetry.context.Context;
import io.opentelemetry.context.propagation.TextMapPropagator;

TextMapPropagator propagator =
        openTelemetry.getPropagators().getTextMapPropagator();

Metadata outboundHeaders = new Metadata();
propagator.inject(
        Context.current(),
        outboundHeaders,
        GrpcMetadataCarrier.SETTER);
~~~

Extract context from inbound metadata:

~~~java
import io.grpc.Contexts;
import io.grpc.Metadata;
import io.opentelemetry.api.OpenTelemetry;
import io.opentelemetry.context.Context;
import io.opentelemetry.context.propagation.TextMapPropagator;

Context extracted = propagator.extract(
        Context.current(),
        inboundHeaders,
        GrpcMetadataCarrier.GETTER);
~~~

The server interceptor needs to make the extracted context the current context when gRPC invokes the handler/listener. In gRPC Java, you can use `Contexts.interceptCall`:

~~~java
return Contexts.interceptCall(
        extracted,
        call,
        headers,
        next);
~~~

When writing a complete custom interceptor, ensure extraction happens at the right position in the interceptor chain before instrumentation creates the server span. Interceptor ordering depends on how the builder/starter registers them; avoid both manually extracting and using self-extracting server instrumentation without a clear reason.

## 8. Should Baggage Be Propagated via Metadata?

Baggage is a set of key/value pairs attached to OpenTelemetry `Context` that can be propagated between services. It is useful for small, non-sensitive operational information, such as an anonymized tenant category or an approved rollout cohort.

Do not use baggage to transmit:

- Access tokens, session IDs, or credentials.
- Emails, phone numbers, account IDs, or PII.
- Business payloads or large data.
- Data requiring integrity guarantees or used for authorization.

Baggage can travel across many services and appear in telemetry backends. It increases metadata size and can introduce high cardinality. Propagate only explicitly allowed keys; limit count, length, and retention.

If baggage is not needed, enable only the W3C Trace Context propagator. If baggage is needed, configure the W3C Baggage propagator alongside trace context and explicitly test which keys are actually sent.

## 9. Async Boundaries and Context Propagation

After the server extracts trace context, OpenTelemetry instrumentation attaches the appropriate context while invoking the handler. When the application offloads work to a custom executor, context does not always follow automatically to the new thread.

Capture context at submission time and wrap the task:

~~~java
import io.opentelemetry.context.Context;

Context captured = Context.current();
workerExecutor.execute(captured.wrap(() -> {
    Span child = tracer.spanBuilder("repository.load")
            .startSpan();
    try (Scope scope = child.makeCurrent()) {
        repository.loadData();
    } finally {
        child.end();
    }
}));
~~~

This allows the child span created in the worker to inherit the RPC's parent span. Capture the context belonging to the right call; never store `Context` in a mutable field of a singleton service.

gRPC `Context` and OpenTelemetry `Context` are two different context types. If the worker needs deadline, cancellation, or principal, the application must also propagate gRPC `Context`/`SecurityContext` via its corresponding mechanism. Wrapping OpenTelemetry `Context` only solves telemetry propagation; it does not automatically propagate access permissions or cancel JDBC.

## 10. Streaming RPCs and Trace Context Lifecycle

For server streaming or bidirectional streaming, context is extracted once when the RPC starts. The server span typically covers the entire call, not just the method returning the observer. Callbacks receiving messages and sending responses belong to the same RPC context according to the instrumentation mechanism.

When handing off individual messages to a worker:

- Capture the context of the RPC or message-processing span before submitting.
- Do not reuse the previous message's context for a subsequent message if callbacks run concurrently.
- Create a child span for a batch/message only when it provides clear diagnostic value.
- End the child span when the task completes, even on error or cancellation.
- End the RPC span when the stream reaches a terminal event: completion, error, or cancellation.

Do not create a new root trace for each message if all messages belong to the same RPC. If the system processes messages after the RPC has already ended, create a new trace and link it with a span link where appropriate, rather than keeping an already-ended parent span as if the call were still open.

## 11. Propagation Failures and Trust Boundaries

Not all metadata is valid. A propagator may fail to extract context when headers are missing, malformed, or truncated. In that case, the server typically continues with a context having no remote parent and starts a new trace according to the sampler; you should not fail a business RPC solely because `traceparent` is invalid.

Principles:

- Do not manually parse `traceparent` with custom substrings or regex.
- Do not trust trace context as user identity.
- Do not allow arbitrary tracing metadata to exceed gRPC size limits.
- Do not echo all baggage or metadata into logs.
- Propagate only across defined boundaries; consider stripping untrusted baggage at public gateways.
- Across cross-process boundaries, use standard propagators to handle version, flags, and validation.

A trace ID sent by a caller can be used as parent context according to tracing policy, but it is not proof of a trustworthy request. Authorization must rely on independently verified credentials and principals.

## 12. Testing Inject/Extract

Propagator tests should verify that data passes through the carrier and is extracted accurately:

~~~java
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.SpanContext;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.context.Context;
import io.opentelemetry.context.propagation.TextMapPropagator;
import io.grpc.Metadata;
import org.junit.jupiter.api.Test;

@Test
void injectsAndExtractsW3cTraceContext() {
    TextMapPropagator propagator =
            openTelemetry.getPropagators().getTextMapPropagator();
    Tracer tracer = openTelemetry.getTracer("propagation-test");

    Span parent = tracer.spanBuilder("client-call").startSpan();
    Context parentContext = Context.root().with(parent);
    Metadata headers = new Metadata();

    propagator.inject(
            parentContext,
            headers,
            GrpcMetadataCarrier.SETTER);

    assertNotNull(headers.get(
            Metadata.Key.of(
                    "traceparent",
                    Metadata.ASCII_STRING_MARSHALLER)));

    Context extracted = propagator.extract(
            Context.root(),
            headers,
            GrpcMetadataCarrier.GETTER);

    SpanContext remoteParent = Span.fromContext(extracted).getSpanContext();
    assertTrue(remoteParent.isValid());
    assertEquals(
            parent.getSpanContext().getTraceId(),
            remoteParent.getTraceId());

    parent.end();
}
~~~

The test above checks the propagator and carrier. Integration tests should spin up an in-process gRPC server/channel with tracing interceptors on both ends, invoke the generated stub, and verify that the client/server spans have the same trace ID and the right parent-child relationship.

Recommended test matrix:

| Case | Expectation |
| --- | --- |
| Metadata with valid `traceparent` | Server span joins the trace from the client |
| Metadata missing `traceparent` | RPC still runs; server starts a new trace per configuration |
| Malformed `traceparent` | Does not break the RPC; does not create a valid parent context from the bad header |
| Valid `tracestate` | Propagated according to W3C rules |
| Baggage enabled | Only allowed keys are sent and extracted |
| Async worker | Child span retains the right trace ID/parent |
| Streaming | Span covers until the terminal event |
| Duplicate client/server interceptor registration | Test detects duplicate spans |

Shut down the channel, server, and tracer provider after tests. For asynchronous callbacks, use a future/latch with a timeout instead of `Thread.sleep`.

## 13. Common Mistakes

| Mistake | Consequence | Resolution |
| --- | --- | --- |
| Creating spans without injecting metadata | Trace breaks when crossing to another service | Use client propagator/interceptor |
| Server does not extract metadata | Server span becomes a new root trace | Register server instrumentation |
| Manually parsing `traceparent` | Error-prone against spec and misses validation | Use the W3C propagator |
| Using a binary marshaller for `traceparent` | Incompatible metadata | Use ASCII key/value |
| Using `-bin` for `tracestate` | Wrong metadata type | Keep text metadata key |
| Java agent and interceptor both instrumenting | Duplicate spans | Choose one mechanism per boundary |
| Switching executors without wrapping `Context` | Child span loses parent | Use `Context.wrap`/`fixedContextExecutor` |
| Putting credentials in baggage | Secret leakage across multiple services | Never propagate auth data in baggage |
| Using trace ID as user identity | Authorization vulnerability | Authenticate independently via credentials |

## 14. Practice Exercises

1. Describe how the client injects `traceparent` into gRPC request metadata and how the server extracts it to create a server span.
2. Why do `traceparent`/`tracestate` use ASCII metadata instead of binary keys with the `-bin` suffix?
3. An RPC is handed off to a worker executor. What must be done so that a child span still belongs to the RPC's trace?
4. Distinguish OpenTelemetry `Context` from gRPC `Context` when passing deadlines and principals to a worker.
5. Why should baggage not contain tokens, PII, or large business payloads?
6. Design an integration test proving that a client span and a server span share the same trace ID.

**Key Takeaway:** Propagators transfer trace context across processes by injecting into gRPC request metadata on the client and extracting on the server. Prefer OpenTelemetry gRPC instrumentation with W3C Trace Context; use custom carriers only when necessary. Propagate context across executors, maintain proper streaming span lifecycles, restrict baggage, and never use trace context in place of authentication/authorization.
