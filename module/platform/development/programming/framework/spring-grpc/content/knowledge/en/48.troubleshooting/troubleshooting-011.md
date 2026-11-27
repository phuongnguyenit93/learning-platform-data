# Missing Headers or Trace Context

In gRPC, information commonly referred to as "headers" is transmitted as RPC **metadata**. Metadata accompanies each individual call over HTTP/2; it does not automatically become a Servlet request header, nor is it automatically forwarded when a service calls another service. Trace context is a special case: values such as W3C **traceparent**, **tracestate**, and **baggage** are also transmitted via metadata, typically by OpenTelemetry instrumentation.

When headers or trace context disappear, you need to pinpoint the exact hop where they are lost: when the client creates the RPC, when the server receives the RPC, when the application switches to an asynchronous execution thread, or when the service initiates a downstream RPC. Checking each boundary helps locate the missing interceptor or context propagation.

## 1. Identify Which Type of Data Is Being Lost

Before fixing anything, distinguish between these three kinds of data:

| Data | Where It Lives and How It Travels | Questions to Check |
|---|---|---|
| Custom request metadata, e.g. **x-request-id** or **x-tenant-id** | **io.grpc.Metadata**, sent with an RPC | Does the client attach metadata to the call? Does the server read the exact key? |
| Application gRPC Context | **io.grpc.Context**, attached to RPC processing | Does the interceptor place the value into Context? Is Context still present inside callbacks or executors? |
| Trace context | OpenTelemetry Context, injected/extracted via metadata such as **traceparent** | Is instrumentation active on both client and server? Is the current span propagated across async boundaries? |

These three mechanisms are related but not identical. **io.grpc.Context** is not **io.opentelemetry.context.Context**. Storing **requestId** in gRPC Context does not automatically create or propagate OpenTelemetry trace context.

Common symptoms:

- Server receives the request yet **headers.get(...)** returns **null**: check outbound metadata, key name, and client interceptor registration.
- Server reads metadata yet downstream calls do not forward it: check how values move from inbound metadata to context and check the outbound channel interceptor.
- Logs from two services share the same request ID yet traces are split: check OpenTelemetry extraction/injection and OTel Context propagation across executors.
- **traceparent** is present on the server yet the trace does not appear in the observability UI: check sampling, exporters, and the backend before concluding propagation failed.

## 2. Isolate by RPC Hop

For a flow where A calls B and B calls C, inspect four checkpoints in order:

1. **A before sending:** was metadata added to **ClientCall**?
2. **B on receipt:** did **ServerInterceptor** see the metadata?
3. **B during processing:** was the value placed into the appropriate context and preserved inside callbacks or async tasks?
4. **B before calling C:** can the outbound channel interceptor read context and inject metadata into the new RPC?

Log a safe test value, such as **x-request-id**, at each checkpoint. For tracing, compare **traceId** and **spanId**: calls in the same trace typically keep the same **traceId**, while each service or operation creates its own span with a distinct **spanId**.

If metadata exists at A yet vanishes before B, focus on the client interceptor, the active channel, and proxies along the path. If B receives it yet C does not, focus on forwarding inside B. If it only disappears after switching to an async thread, inspect context propagation for the executor or framework in use.

## 3. Check Metadata Keys and Marshallers

Metadata key names must be lowercase. Text values use **Metadata.ASCII_STRING_MARSHALLER**; binary data uses keys suffixed with **-bin** alongside a binary marshaller.

~~~java
public final class GrpcMetadataKeys {
    private GrpcMetadataKeys() {}

    public static final Metadata.Key<String> REQUEST_ID =
            Metadata.Key.of("x-request-id", Metadata.ASCII_STRING_MARSHALLER);
}
~~~

Common mistakes:

- Using different key names on sender and receiver, e.g. **x-request-id** vs. **request-id**.
- Using an ASCII marshaller for binary data or forgetting the **-bin** suffix on binary keys.
- Naming application metadata with the **grpc-** prefix, which is reserved for the gRPC protocol.
- Putting metadata into a **Metadata** instance without passing it to **ClientCall.start**.
- Creating a fresh **Metadata** instance inside an interceptor and accidentally overwriting values added by earlier interceptors.

Do not use metadata to carry large payloads. Metadata has size limits across components on the path; proxies or servers may reject requests if metadata exceeds limits. Never log full metadata, as it may contain tokens, identity information, or sensitive data.

## 4. Attach Metadata on the Client with ClientInterceptor

A **ClientInterceptor** is the right place to add metadata to outbound RPCs. The example below reads the request ID from gRPC Context when the call starts:

~~~java
public final class RequestIdClientInterceptor implements ClientInterceptor {

    @Override
    public <ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
            MethodDescriptor<ReqT, RespT> method,
            CallOptions callOptions,
            Channel next) {

        return new ForwardingClientCall.SimpleForwardingClientCall<>(
                next.newCall(method, callOptions)) {

            @Override
            public void start(Listener<RespT> listener, Metadata headers) {
                String requestId = RequestContext.REQUEST_ID.get();

                if (requestId != null && !requestId.isBlank()) {
                    headers.put(GrpcMetadataKeys.REQUEST_ID, requestId);
                }

                super.start(listener, headers);
            }
        };
    }
}
~~~

Shared context key in the example:

~~~java
public final class RequestContext {
    private RequestContext() {}

    public static final Context.Key<String> REQUEST_ID =
            Context.key("request-id");
}
~~~

When starting an execution flow with a request ID, set the value in context around the stub call:

~~~java
OrderReply reply = Context.current()
        .withValue(RequestContext.REQUEST_ID, requestId)
        .call(() -> blockingStub.getOrder(request));
~~~

**Context.call(...)** can throw **Exception**, so handle it according to the calling method's signature. With asynchronous stubs, initiate the RPC while the context is still active; the interceptor needs to read context when **ClientCall** is created and started.

In a Spring gRPC application, the example above illustrates grpc-java's mechanism. You must verify that the interceptor is actually attached to the channel used by the stub, via the configuration point or interceptor registration mechanism of your project's Spring gRPC version. Simply declaring a **ClientInterceptor** bean is insufficient if the channel factory does not register or use that bean. If the application uses multiple channels, inspect the exact channel of the failing RPC.

## 5. Read Metadata on the Server and Place It in gRPC Context

The server interceptor receives inbound metadata. If the service or an outbound interceptor needs the request ID later, place the value into gRPC Context before handing off to the handler:

~~~java
public final class RequestIdServerInterceptor implements ServerInterceptor {

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String requestId = headers.get(GrpcMetadataKeys.REQUEST_ID);
        Context context = Context.current();

        if (requestId != null) {
            context = context.withValue(RequestContext.REQUEST_ID, requestId);
        }

        return Contexts.interceptCall(context, call, headers, next);
    }
}
~~~

**Contexts.interceptCall(...)** attaches the context to RPC processing, including listener callbacks. If you only read metadata in the interceptor and store it in a local variable, downstream processing components will not automatically see that variable.

Register **ServerInterceptor** on the gRPC server using the integration mechanism your application uses. Verify whether the interceptor is applied to the right service or registered globally per project configuration. An interceptor declared as a class yet omitted from the server interceptor chain will never observe requests.

When B calls C, **RequestIdClientInterceptor** on the outbound channel can read **RequestContext.REQUEST_ID** and resend the **x-request-id** key. This is an explicit forwarding step between two RPCs. gRPC does not automatically copy all metadata from an inbound RPC to an outbound RPC.

Forward only the keys the application genuinely needs. Do not forward raw **authorization**, cookies, or internal metadata to another service without clearly establishing trust boundaries and access rights.

## 6. Handle Context Loss in Asynchronous Tasks

gRPC Context is scoped to the current execution thread. When the application hands work off to an arbitrary executor, **CompletableFuture** using the common pool, **@Async**, or a Reactor scheduler, the context may no longer be current on the new thread.

Several ways to handle this:

- With a Java executor, use **Context.currentContextExecutor(executor)** or **context.fixedContextExecutor(executor)** at task submission, depending on desired context semantics.
- With a specific **Runnable** or **Callable**, use **Context.current().wrap(runnable)** or **Context.current().wrap(callable)**.
- With Reactor or Spring asynchronous processing, use a context propagation mechanism compatible with your framework and library versions; never assume **ThreadLocal** is copied automatically.
- With OpenTelemetry, ensure OTel Context is also propagated across async boundaries. Propagating **io.grpc.Context** does not replace propagating **io.opentelemetry.context.Context**.

Example of wrapping a task with the current gRPC Context:

~~~java
Context grpcContext = Context.current();

executor.execute(grpcContext.wrap(() -> {
    // Operations inside the task can read RequestContext.REQUEST_ID.
    downstreamStub.process(request);
}));
~~~

If **downstreamStub** is called inside this task, the outbound interceptor can read the request ID from gRPC Context. When errors appear only under load or inside one async branch, compare context values right before submitting the task and inside the task to identify the boundary losing context.

## 7. Check OpenTelemetry Trace Context

With W3C Trace Context, the common fields are:

- **traceparent**: carries trace ID, parent span ID, and trace flags.
- **tracestate**: carries vendor-specific state if any.
- **baggage**: carries properties allowed to propagate between services.

If using OpenTelemetry instrumentation for grpc-java, instrumentation must be present on both client and server sides. The client injects the current OTel Context into outbound metadata; the server extracts inbound metadata and restores OTel Context before creating or processing spans. Verify instrumentation is attached to the exact channel and running server. Enabling tracing on only one side does not ensure context propagates across both sides.

If the project uses Spring Boot observability or Micrometer Tracing combined with OpenTelemetry, verify the complete configuration of bridges, propagators, and gRPC instrumentation for your exact version. Do not assume HTTP/Servlet tracing automatically covers the gRPC server or every **ManagedChannel**.

Do not hand-assemble **traceparent** via string concatenation if OpenTelemetry already manages propagation. Having two inject/extract mechanisms active together can overwrite metadata, produce unlinked spans, or split traces. Choose a single unified propagation path and check interceptor ordering if the application has custom interceptors reading OTel Context.

Distinguish propagation failures from trace recording failures:

- If **traceparent** does not appear on the server, check client instrumentation, metadata in transit, and server extraction.
- If the server has trace context yet the backend displays no trace, check sampling, exporters, collectors, and backend filters.
- If **traceId** changes between two services, check extraction/injection or whether a root span is being created outside the current context.
- If **traceId** stays the same yet parent-child relationships are wrong, check whether spans are created before or after context restoration and whether context is replaced in async tasks.

An unsampled trace may not be exported even though propagation works. Therefore, inspect metadata/context at the receiving point before concluding that a missing trace in the observability UI means a missing header.

## 8. Check Proxies, Gateways, and Metadata Limits

If the client sends metadata properly yet the server does not receive it, try calling the server directly in a test environment to determine whether a proxy or gateway is dropping metadata. Check header allowlist/denylist rules, HTTP/2 forwarding rules, request header size limits, and how the gateway handles gRPC trailers.

Key points to note:

- Application metadata maps to HTTP/2 headers or trailers on the wire. Proxies may apply their own filtering rules.
- Do not use gRPC-reserved keys or invalidly formatted keys.
- Distinguish initial metadata from trailing metadata. Data sent by the server in trailers will not appear in inbound request metadata.
- Some gateways require explicit configuration to forward custom metadata or baggage.
- Compare results through the gateway against direct calls while keeping client, server, and request versions identical so the test is meaningful.

## 9. Tests to Prevent Regression

An integration test should verify sending, receiving, and forwarding:

1. Create a test gRPC server with a **ServerInterceptor** recording **x-request-id**.
2. Create a client channel with a **ClientInterceptor** and call an RPC with a known request ID.
3. Assert the server receives the exact value.
4. Inside the server handler, call a mock downstream service using a channel with an outbound interceptor.
5. Assert the downstream receives the same request ID.
6. Repeat the test when the handler offloads work to an executor to verify context propagates properly.
7. If testing tracing, assert trace context is extracted and the downstream span belongs to the same trace; do not just check that a header string is present.

You can use an in-process gRPC server/channel to test interceptors without opening network ports. However, in-process tests do not cover proxies, gateways, or HTTP/2 metadata limits; run a test across real infrastructure when transit loss is suspected.

In diagnostic logs, log only permitted fields such as RPC method, sanitized request ID, and trace-context present/absent status. Avoid logging tokens, payloads, entire baggage, or the entire **Metadata** object.

## 10. Quick Troubleshooting Checklist

- [ ] Identify whether the lost item is application metadata, gRPC Context, or OTel Context.
- [ ] Confirm the client calls the exact channel with the **ClientInterceptor**.
- [ ] Confirm the interceptor adds metadata to the exact **headers** passed to **ClientCall.start**.
- [ ] Check that keys are lowercase, spelled accurately, and use the right marshaller.
- [ ] Confirm the server interceptor is registered on the exact server/service.
- [ ] Place needed data into the appropriate context before invoking the handler.
- [ ] Check context across every executor, **@Async**, **CompletableFuture**, or Reactor boundary.
- [ ] For downstream RPCs, confirm the outbound interceptor re-injects required metadata.
- [ ] For tracing, check OpenTelemetry instrumentation and propagators on both client and server.
- [ ] If failing only through a gateway, inspect forwarding rules and metadata limits.
- [ ] Distinguish successful propagation from sampling or export failures.

Once you have pinpointed the hop where data is lost, fix the exact interceptor registration or context propagation point, and keep integration tests covering both direct and downstream RPCs.
