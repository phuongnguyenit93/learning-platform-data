# Logging Request ID and Method Name

When a request passes through multiple services, isolated logs are often insufficient to understand the full processing flow. One service may log "received request" and another may log "dependency timeout", yet without a shared correlation key and consistent method name it is hard to locate the exact log lines belonging to the same operation. With gRPC, a request ID can be passed through metadata, and the method name can be read directly from the Protobuf method descriptor. Combining these two fields makes logs searchable and correlatable across clients and servers.

**Logging request ID and method name** is the practice of writing a correlation identifier and the RPC name into structured logs at client/server boundaries while propagating the request ID across gRPC hops. This lesson belongs to the **Observability** chapter of the **SPRING_GRPC** module: developing gRPC services in the Spring ecosystem using Protocol Buffers contracts, generating Java code, and implementing client/server for unary or streaming RPCs; learners work with metadata, deadlines, statuses, interceptors, TLS, integration testing, and monitoring performance and reliability. The focus is on defining request ID lifecycles, validating inbound metadata, extracting full method names from descriptors, keeping MDC/context on the right threads, and avoiding sensitive data leaks in logs.

## 1. Request ID Is Used to Correlate Logs

A request ID is a correlation identifier for a request or logical operation. When a request flows from a gateway to service A, and A calls B and C, logs can share one request ID so operators can trace the entire path.

For example:

~~~text
request_id=01JQ8F7M2K grpc_method=orders.OrderService/CreateOrder event=started
request_id=01JQ8F7M2K grpc_method=inventory.Inventory/Reserve event=started
request_id=01JQ8F7M2K grpc_method=inventory.Inventory/Reserve event=completed status=OK
request_id=01JQ8F7M2K grpc_method=orders.OrderService/CreateOrder event=completed status=OK
~~~

A request ID does not have to be a UUID. It can be a ULID, UUID, or a random string with sufficient entropy. What matters is:

- It contains no personal information or business data.
- It is unpredictable if the identifier may appear in external environments.
- It has bounded length and character set.
- It stays stable within the scope of the logical operation being correlated.
- It is never used as a metric label because each request usually generates a new value.

A request ID helps locate logs; it does not automatically create a distributed trace and does not replace trace context.

## 2. Distinguishing Request ID from Trace ID and Span ID

These three identifiers serve different purposes:

| Field | Scope | Purpose |
| --- | --- | --- |
| request_id | One request/logical operation by application convention | Find related logs across multiple services. |
| trace_id | One distributed trace | Link spans belonging to a single trace. |
| span_id | One span within a trace | Identify a specific segment of work. |

One request ID can remain unchanged across multiple fan-out RPCs and retries within the same operation. Trace ID is also normally preserved within the same trace, whereas span ID changes per span. Sampling may omit full traces, while request IDs remain useful in logs.

Do not assign a request ID into the trace ID field or vice versa. When OpenTelemetry is present, logs should include `request_id`, `trace_id`, and `span_id` if those values exist. Request ID is an application correlation field; trace/span IDs follow W3C Trace Context and OpenTelemetry.

## 3. Defining the Scope and Lifecycle of a Request ID

Before implementing interceptors, agree on what the request ID represents:

- If a request enters through an HTTP gateway and then calls multiple gRPC services, the gateway can generate the request ID at ingress and propagate it across the operation.
- If a client invokes a standalone RPC, the client can generate a request ID when starting the logical call.
- If an operation calls multiple services in parallel, child RPCs can share the same request ID to correlate fan-out logs.
- If gRPC retries a logical call, attempts should retain the same request ID; attempt number is a separate attribute in traces/telemetry.
- If a message/event is processed independently after the initial operation ends, the event may need its own correlation ID or a parent operation ID per business convention.

Do not generate a new request ID at every service hop. Doing so prevents searching logs across the chain. Also do not reuse one global request ID across all requests; it must be created per logical operation.

At external trust boundaries, a caller-supplied request ID is untrusted input. A gateway may always generate a new internal ID and store a validated external correlation value in a separate field if genuinely needed. For internal traffic, a valid request ID generated at ingress can be preserved.

## 4. Propagating Request ID via gRPC Metadata

gRPC metadata is a key/value channel attached to an RPC. You can use an application key such as `x-request-id`:

~~~text
x-request-id: 01JQ8F7M2K
~~~

Metadata keys must be lowercase. Do not use the `grpc-` prefix for custom keys because that namespace is reserved for gRPC. For text request IDs, use `Metadata.ASCII_STRING_MARSHALLER`. Do not use a binary marshaller for string IDs.

Do not blindly forward all inbound metadata downstream. Propagate only explicitly permitted keys, including request ID and required propagation fields. Authorization metadata, cookies, or private information must follow separate security policies.

If metadata lacks a request ID or contains an invalid value, the service at the trust boundary should generate a new ID. Do not log the raw malformed value; caller-supplied strings may contain control characters or content intended for log injection.

## 5. Validating Request ID Before Logging

A straightforward rule is allowing ASCII letters, digits, dots, underscores, and hyphens, with a maximum length of 128 characters. Exact rules must be aligned between the gateway and services:

~~~java
import java.util.UUID;
import java.util.regex.Pattern;

public final class RequestIds {

    private static final Pattern SAFE_ID =
            Pattern.compile("[A-Za-z0-9._-]{1,128}");

    private RequestIds() {}

    public static boolean isValid(String value) {
        return value != null && SAFE_ID.matcher(value).matches();
    }

    public static String validOrNew(String candidate) {
        return isValid(candidate)
                ? candidate
                : UUID.randomUUID().toString();
    }
}
~~~

Validation does not turn a request ID into a credential. A caller can still pick any valid value; therefore, never use request ID for authentication, authorization, or data access. If spoofing of external correlation IDs must be prevented, the gateway must establish the internal ID and trust headers only from authenticated upstreams.

## 6. Getting the Method Name from the Protobuf Descriptor

There is no need to manually parse URLs or extract method names from payloads. gRPC provides the full method name through `MethodDescriptor`:

~~~java
String fullMethod =
        call.getMethodDescriptor().getFullMethodName();
~~~

Examples of full method names:

~~~text
inventory.Inventory/GetStock
orders.OrderService/CreateOrder
~~~

The full name includes package/service and method, distinguishing services that share method names. On the client, retrieve the same information from the `MethodDescriptor` parameter in `ClientInterceptor`.

Log a `grpc_method` field with the full method name. If grouping is needed, you can split `service` and `method` into two structured fields, but avoid logging only a short method name like `Get` because multiple services may share that name.

## 7. Structured Logging and MDC

Logs should be records with stable fields rather than prose sentences that must be parsed later:

~~~json
{
  "event": "grpc.server.completed",
  "request_id": "01JQ8F7M2K",
  "grpc_method": "inventory.Inventory/GetStock",
  "grpc_status": "OK",
  "duration_ms": 18
}
~~~

Useful fields:

- `event`: `rpc.started`, `rpc.completed`, `rpc.cancelled`, or a clear business event.
- `request_id`: validated correlation ID.
- `grpc_method`: full Protobuf method name.
- `grpc_status`: terminal status code when the call completes.
- `duration_ms`: duration at the exact measurement boundary.
- `trace_id`/`span_id`: if OpenTelemetry context is present.
- `service.name` and `deployment`/`environment`: provided by logging/telemetry resources.

SLF4J MDC lets you attach `request_id` to logs on the current thread. A JSON encoder can emit MDC fields as top-level properties. MDC is thread-local; it does not automatically follow tasks to another executor. Every attachment must restore the previous value in a `finally` block so subsequent requests on the same thread do not inherit the wrong ID.

## 8. Shared Context Holder for gRPC

You can store the request ID in `io.grpc.Context` so downstream interceptors and handlers can read it:

~~~java
import io.grpc.Context;
import io.grpc.Metadata;
import org.slf4j.MDC;

import java.util.UUID;
import java.util.function.Supplier;

public final class GrpcRequestContext {

    public static final Context.Key<String> REQUEST_ID =
            Context.key("request-id");

    public static final Metadata.Key<String> REQUEST_ID_HEADER =
            Metadata.Key.of(
                    "x-request-id",
                    Metadata.ASCII_STRING_MARSHALLER);

    private GrpcRequestContext() {}

    public static String resolve(String incoming) {
        return RequestIds.validOrNew(incoming);
    }

    public static <T> T call(
            Context grpcContext,
            String requestId,
            Supplier<T> action) {

        Context previous = grpcContext.attach();
        String previousMdc = MDC.get("request_id");
        try {
            MDC.put("request_id", requestId);
            return action.get();
        } finally {
            if (previousMdc == null) {
                MDC.remove("request_id");
            } else {
                MDC.put("request_id", previousMdc);
            }
            grpcContext.detach(previous);
        }
    }

    public static void run(
            Context grpcContext,
            String requestId,
            Runnable action) {
        call(grpcContext, requestId, () -> {
            action.run();
            return null;
        });
    }
}
~~~

The helper attaches gRPC `Context` and MDC for the exact block of code executing, then restores both. Never populate MDC with `put` and forget to remove/restore it. When thread pools reuse threads, that bug leaks a previous request's ID into the next request.

## 9. ServerInterceptor Logging Request ID and Method

`ServerInterceptor` is the right boundary to:

1. Read `x-request-id` from inbound metadata.
2. Validate or generate a new ID.
3. Extract the full method name from the descriptor.
4. Put the request ID into gRPC `Context`.
5. Log start and terminal events.
6. Attach context/MDC when listener callbacks run.

~~~java
import io.grpc.Context;
import io.grpc.ForwardingServerCall;
import io.grpc.ForwardingServerCallListener;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.concurrent.atomic.AtomicBoolean;
import java.util.function.Consumer;

public final class RequestLoggingServerInterceptor
        implements ServerInterceptor {

    private static final Logger log =
            LoggerFactory.getLogger(RequestLoggingServerInterceptor.class);

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String requestId = GrpcRequestContext.resolve(
                headers.get(GrpcRequestContext.REQUEST_ID_HEADER));
        String method =
                call.getMethodDescriptor().getFullMethodName();
        Context requestContext =
                Context.current().withValue(
                        GrpcRequestContext.REQUEST_ID,
                        requestId);
        long startedNanos = System.nanoTime();
        AtomicBoolean terminalLogged = new AtomicBoolean();

        Consumer<Status> logTerminal = status -> {
            if (terminalLogged.compareAndSet(false, true)) {
                long durationMs =
                        (System.nanoTime() - startedNanos) / 1_000_000;
                GrpcRequestContext.run(requestContext, requestId, () ->
                        log.info(
                                "grpc.server.completed request_id={} grpc_method={} grpc_status={} duration_ms={}",
                                requestId, method,
                                status.getCode().name(), durationMs));
            }
        };

        ServerCall<ReqT, RespT> monitoredCall =
                new ForwardingServerCall
                        .SimpleForwardingServerCall<>(call) {
                    @Override
                    public void close(
                            Status status,
                            Metadata trailers) {
                        logTerminal.accept(status);
                        super.close(status, trailers);
                    }
                };

        ServerCall.Listener<ReqT> delegate;
        try {
            delegate = GrpcRequestContext.call(
                    requestContext,
                    requestId,
                    () -> {
                        log.info(
                                "grpc.server.started request_id={} grpc_method={}",
                                requestId, method);
                        return next.startCall(monitoredCall, headers);
                    });
        } catch (RuntimeException failure) {
            logTerminal.accept(Status.fromThrowable(failure));
            throw failure;
        }

        return new ForwardingServerCallListener
                .SimpleForwardingServerCallListener<>(delegate) {
            @Override
            public void onMessage(ReqT message) {
                GrpcRequestContext.run(
                        requestContext, requestId,
                        () -> super.onMessage(message));
            }

            @Override
            public void onHalfClose() {
                GrpcRequestContext.run(
                        requestContext, requestId,
                        super::onHalfClose);
            }

            @Override
            public void onReady() {
                GrpcRequestContext.run(
                        requestContext, requestId,
                        super::onReady);
            }

            @Override
            public void onCancel() {
                logTerminal.accept(Status.CANCELLED);
                GrpcRequestContext.run(
                        requestContext, requestId,
                        super::onCancel);
            }

            @Override
            public void onComplete() {
                GrpcRequestContext.run(
                        requestContext, requestId,
                        super::onComplete);
            }
        };
    }
}
~~~

`AtomicBoolean` ensures the terminal log is written only once if `onCancel` and `close` occur close together. If `onCancel` arrives first, the server logs status `CANCELLED` because that is the state observed by the server; the client may see `DEADLINE_EXCEEDED` when a deadline expires. Do not interpret a server cancellation log as a definitive cause without additional evidence.

The example formats logs with placeholders for readability; in production, configure a JSON encoder to emit MDC as separate fields or use your logger's structured key/value logging. Do not log request payloads inside this interceptor.

## 10. ClientInterceptor Propagating Request ID to the Server

`ClientInterceptor` reads the ID from gRPC `Context` if the call is downstream of an active request. Otherwise, it creates a new ID for the logical call and puts it into metadata:

~~~java
import io.grpc.CallOptions;
import io.grpc.Channel;
import io.grpc.ClientCall;
import io.grpc.ClientInterceptor;
import io.grpc.Context;
import io.grpc.ForwardingClientCall;
import io.grpc.ForwardingClientCallListener;
import io.grpc.Metadata;
import io.grpc.MethodDescriptor;
import io.grpc.Status;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.concurrent.TimeUnit;

public final class RequestIdClientInterceptor
        implements ClientInterceptor {

    private static final Logger log =
            LoggerFactory.getLogger(RequestIdClientInterceptor.class);

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

                String requestId = GrpcRequestContext.resolve(
                        GrpcRequestContext.REQUEST_ID.get());
                String methodName = method.getFullMethodName();
                Context requestContext = Context.current().withValue(
                        GrpcRequestContext.REQUEST_ID,
                        requestId);
                long startedNanos = System.nanoTime();

                headers.discardAll(
                        GrpcRequestContext.REQUEST_ID_HEADER);
                headers.put(
                        GrpcRequestContext.REQUEST_ID_HEADER,
                        requestId);

                GrpcRequestContext.run(
                        requestContext, requestId,
                        () -> log.info(
                                "grpc.client.started request_id={} grpc_method={}",
                                requestId, methodName));

                Listener<RespT> monitored =
                        new ForwardingClientCallListener
                                .SimpleForwardingClientCallListener<>(
                                        responseListener) {
                            @Override
                            public void onHeaders(Metadata responseHeaders) {
                                GrpcRequestContext.run(
                                        requestContext, requestId,
                                        () -> super.onHeaders(responseHeaders));
                            }

                            @Override
                            public void onMessage(RespT message) {
                                GrpcRequestContext.run(
                                        requestContext, requestId,
                                        () -> super.onMessage(message));
                            }

                            @Override
                            public void onReady() {
                                GrpcRequestContext.run(
                                        requestContext, requestId,
                                        super::onReady);
                            }

                            @Override
                            public void onClose(
                                    Status status,
                                    Metadata trailers) {
                                long durationMs = TimeUnit.NANOSECONDS
                                        .toMillis(System.nanoTime()
                                                - startedNanos);
                                GrpcRequestContext.run(
                                        requestContext, requestId,
                                        () -> {
                                            log.info(
                                                    "grpc.client.completed request_id={} grpc_method={} grpc_status={} duration_ms={}",
                                                    requestId, methodName,
                                                    status.getCode().name(),
                                                    durationMs);
                                            super.onClose(status, trailers);
                                        });
                            }
                        };
                GrpcRequestContext.run(
                        requestContext, requestId,
                        () -> super.start(monitored, headers));
            }
        };
    }
}
~~~

If a request ID was already placed in `Context` at ingress, downstream calls retain the same ID. If not, the interceptor generates one for the call. In an operation that makes multiple independent RPCs, the application should establish a `Context` scope at the operation boundary so those calls share one ID rather than each call generating a different ID.

With gRPC's internal retries, the logical call's metadata is generally reused across attempts of that call; do not generate a new request ID per attempt. If you need to identify individual attempts, use an attempt span/attribute or a dedicated telemetry field, without changing the operation's request ID.

## 11. Propagating Context Across Executors and Streaming Callbacks

gRPC `Context` and MDC are not automatically guaranteed across arbitrary custom executors. If a handler offloads work to a thread pool, capture the context when submitting the task:

~~~java
Context captured = Context.current();
executor.execute(captured.wrap(() -> {
    inventoryClient.getStock(request);
}));
~~~

When the callback runs inside the wrapped context, `ClientInterceptor` can read the request ID and continue propagating it to the next service. If the task needs MDC for logging, use the `GrpcRequestContext.run` helper or appropriate logging context propagation.

Streaming listeners have multiple callbacks such as `onMessage`, `onHalfClose`, `onReady`, `onCancel`, and `onComplete`. Each callback may execute on a different thread; attaching MDC only around `startCall` is not enough. The server interceptor above wraps these callbacks so the request ID is available in service logs whenever a callback runs.

Never use a static mutable variable to hold the current request ID. Multiple RPCs can run concurrently in the same process; a static field would cause one request to log another request's ID.

## 12. Spring gRPC: Registering Interceptors via Lifecycle

In a Spring application, you can declare interceptors as beans and register them through the extension point provided by the starter in use:

~~~java
@Configuration
class GrpcRequestLoggingConfiguration {

    @Bean
    RequestLoggingServerInterceptor requestLoggingServerInterceptor() {
        return new RequestLoggingServerInterceptor();
    }

    @Bean
    RequestIdClientInterceptor requestIdClientInterceptor() {
        return new RequestIdClientInterceptor();
    }
}
~~~

The snippet above only creates the beans. Verify whether your starter/version auto-discovers interceptor beans or requires explicit server/channel builder configuration. Register them on the server/channel managed by the starter; do not create an extra parallel server or `ManagedChannel` just to add logging.

If using the OpenTelemetry agent or a gRPC instrumentation library, keep request ID propagation independent from trace context propagation. They can share the interceptor chain, but do not overwrite `traceparent` or manually fabricate trace IDs inside the request ID interceptor.

## 13. Log Lifecycle, Not Every Message at INFO Level

For unary RPCs, logging one start event and one end event is usually sufficient:

- started: request ID, method, caller/service if a safe field exists.
- completed: request ID, method, status, duration.
- failed: request ID, method, status, and appropriate error category.

For streaming RPCs, log when the stream starts and ends. Do not emit an `INFO` log line for every message; high-volume streams can generate massive log volumes, drive up costs, and obscure critical errors. Message count, byte count, and active streams should be measured with separate metrics.

Do not log raw request/response payloads in a general-purpose interceptor. Payloads may contain tokens, personal data, business secrets, or payment information. If payload debugging is necessary, use sampled logging, schema-based redaction, and restricted access controls.

## 14. Combining Request ID with Trace Context

Request ID helps search logs; trace context builds span relationships and timing across services. A good log entry can include:

~~~json
{
  "request_id": "01JQ8F7M2K",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "grpc_method": "inventory.Inventory/GetStock",
  "grpc_status": "OK"
}
~~~

Not every log entry will have a trace ID: a request may arrive before tracing is initialized, a trace may be sampled out, or a background job may have a correlation ID without an active span. When trace context exists, retrieve `trace_id`/`span_id` from the current OpenTelemetry `Context` instead of manually parsing headers in every service.

Request ID should also never be a metric label. Metrics use `service`/`method`/`status` with finite cardinality; request ID belongs in logs and traces. Search logs by `request_id` and then open the linked trace to inspect the timeline.

## 15. Security and Trust Boundaries

A caller-supplied request ID can be forged or crafted with malicious content. Principles:

- Validate length and character set before placing into MDC/logs.
- Disallow newlines, tabs, control characters, or arbitrary JSON fragments.
- Do not embed email addresses, usernames, access tokens, account numbers, or personal data.
- At public ingress, consider generating a new internal request ID rather than trusting external headers.
- If storing an external request ID is required, log it in a separate field after validation and length capping.
- Never use request ID as an authorization input, idempotency key, or secret.
- Do not forward arbitrary metadata across trust boundaries.

A request ID is not a secret; avoid using it as a capability token or a URL to access private resources.

## 16. Testing Request ID and Method Name

Integration tests should verify metadata, context, and log fields on both client and server:

1. Send a request with a valid `x-request-id`; verify the server reads the exact ID and logs the full method name.
2. Send a request without an ID; verify the server generates a new valid ID and uses it consistently in start/completed logs.
3. Send an oversized ID or one containing newlines; verify it is replaced with a new ID and raw input never appears in logs.
4. Invoke a downstream gRPC call from the server handler; verify the client interceptor propagates the same request ID.
5. Invoke two downstream services within the same operation; verify they share the same correlation ID.
6. Run two concurrent requests; verify MDC does not bleed across requests.
7. Offload a task to an executor; verify the request ID remains in worker logs when context is wrapped.
8. Invoke a multi-message streaming RPC; verify lifecycle logs contain one start and one terminal event, without `INFO` logs per message.
9. Invoke two services with colliding short method names; verify logs use the full method name to distinguish them.

Use an in-process gRPC server/channel for interceptor and metadata tests. Use a test logger appender or JSON log encoder to verify actual output fields; checking MDC alone on the test thread does not prove JSON output contains the `request_id` field. Add TCP/TLS tests when verifying metadata across real proxies or trust boundaries.

## 17. Common Pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Every service logs a different request ID | Generating a new ID at each hop. | Preserve valid IDs across metadata and Context. |
| Multiple requests share the same ID | Using static/global IDs or reusing the wrong scope. | Generate IDs per logical operation and attach per request context. |
| Logged method is only a short name | Extracting method name without service/package. | Use fullMethodName from the descriptor. |
| Previous request's ID appears in the next request | MDC not restored on thread pool. | Restore/remove in finally for every scope. |
| Downstream logs miss request ID | Context lost across executor or callback switch. | Capture/wrap gRPC Context and attach MDC. |
| Client retries produce multiple request IDs | Generating ID per attempt instead of per logical call. | Create ID before the retry layer and keep it stable for the call. |
| Log lines injected or malformed | Trusting raw caller-supplied request IDs. | Validate allowlist, length, and characters. |
| Metrics backend has too many series | Using request ID as a label. | Keep request ID in logs/traces, never as a metric tag. |
| Logs leak sensitive data | Logging all metadata or payloads. | Enforce field allowlists and redaction policies. |

## 18. Hands-On Exercises

1. Create the `x-request-id` metadata key and a validation rule with a maximum length.
2. Write a `ServerInterceptor` that reads or generates a request ID, extracts the full method name, and logs start/completed events.
3. Put the request ID into `io.grpc.Context` and MDC; ensure context is restored in `finally`.
4. Write a `ClientInterceptor` that propagates the request ID to downstream gRPC services.
5. Call two services sequentially and two services in parallel; verify logs link to the same logical request.
6. Run a downstream call on an executor using `Context.wrap`; verify the request ID remains in logs.
7. Test malformed request IDs, concurrent requests, retries, and streaming lifecycles.
8. Configure structured JSON logging to search by `request_id` and `grpc_method`; cross-reference `trace_id` when tracing is enabled.

After this lesson, you should know how to generate/validate request IDs, propagate them through gRPC metadata, retrieve exact method names from descriptors, and preserve request context across listener callbacks and executors. Logging `request_id` alongside `grpc_method`, status, duration, and appropriate trace context enables operations teams to search logs across services faster while keeping sensitive data and log volume under control.
