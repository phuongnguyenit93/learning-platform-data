# Logging Method Name and Latency

When an RPC is slow or returns an error, an operator's first question is usually: **which method was called, what status did it finish with, and how long did it take?** Logging inside each service method is error-prone, inconsistent, and hard to cover calls rejected before reaching the handler. Interceptors let you measure timing at the gRPC boundary, where method names and call lifecycles can be observed consistently.

In **Spring gRPC**, you can use a server interceptor to measure server-side processing time and a client interceptor to measure the time the client application actually waits. Those two measurements answer different questions. This lesson focuses on retrieving the full method name, choosing the right start/end points, writing structured logs, and handling streaming RPCs separately.

## 1. Recording the full method name instead of just the Java method name

From `ServerCall` or `MethodDescriptor`, obtain:

```java
String methodName = call.getMethodDescriptor().getFullMethodName();
```

For the Catalog service, this value looks like:

```text
shop.catalog.v1.CatalogService/GetProduct
```

The full method name includes the protobuf package, service, and method. It is more useful than a Java method name such as `getProduct`, because multiple services may have a method named `GetProduct`. It is also the right identifier for grouping logs/metrics when an API has multiple package versions.

Do not construct names manually from Java classes or Spring bean names. If the protobuf package or service changes, the full method name on the wire changes; the interceptor will automatically record the exact identifier gRPC is handling.

## 2. Measuring latency with a monotonic clock

Latency is the elapsed time between two points. Use `System.nanoTime()` to measure duration:

```java
long startedAt = System.nanoTime();
// ... when the call ends
long elapsedNanos = System.nanoTime() - startedAt;
double latencyMs = elapsedNanos / 1_000_000.0;
```

`nanoTime()` is a monotonic clock suitable for measuring elapsed time because it is not affected by system wall-clock adjustments. `currentTimeMillis()` is suitable for calendar timestamps, but should not be used to compute elapsed time.

Before writing an interceptor, clearly define what latency is being measured:

| Scope | Start | End | Meaning |
| --- | --- | --- | --- |
| Server-side call duration | Server receives call in interceptor | Server closes call or receives cancellation | How long the call exists on the server, including processing and open stream time |
| Client-observed latency | Client starts call | Client receives `onClose` callback | How long the client waits for the entire RPC, including transport, server, and response |
| Handler execution time | Before invoking application/service method | After handler logic finishes | Execution time of a processing segment; does not cover the full transport lifecycle |

Do not label all of these measurements as "server processing time." Client-observed latency includes network and queueing; server-side call duration may include time spent waiting for the client to send messages or read a stream.

## 3. Server interceptor logging method, status, and latency

On the server, start measuring inside `interceptCall`. Completion is typically recorded when `ServerCall.close` is called; if the client cancels the call, the listener receives `onCancel`. Use an `AtomicBoolean` to guarantee that each RPC records only one entry even if multiple completion callbacks occur.

```java
package com.myshop.grpc.observability;

import io.grpc.ForwardingServerCall;
import io.grpc.ForwardingServerCallListener;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;
import java.util.concurrent.atomic.AtomicBoolean;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class RpcLoggingServerInterceptor implements ServerInterceptor {
    private static final Logger log =
            LoggerFactory.getLogger(RpcLoggingServerInterceptor.class);

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String method = call.getMethodDescriptor().getFullMethodName();
        long startedAt = System.nanoTime();
        AtomicBoolean recorded = new AtomicBoolean();

        java.util.function.Consumer<Status> record = status -> {
            if (recorded.compareAndSet(false, true)) {
                long elapsedNanos = System.nanoTime() - startedAt;
                double latencyMs = elapsedNanos / 1_000_000.0;
                log.info(
                        "grpc.server.call method={} status={} latency_ms={}",
                        method, status.getCode(), latencyMs);
            }
        };

        ServerCall<ReqT, RespT> monitoredCall =
                new ForwardingServerCall.SimpleForwardingServerCall<>(call) {
                    @Override
                    public void close(Status status, Metadata trailers) {
                        record.accept(status);
                        super.close(status, trailers);
                    }
                };

        final ServerCall.Listener<ReqT> listener;
        try {
            listener = next.startCall(monitoredCall, headers);
        } catch (RuntimeException ex) {
            record.accept(Status.fromThrowable(ex));
            throw ex;
        }

        return new ForwardingServerCallListener
                .SimpleForwardingServerCallListener<>(listener) {
            @Override
            public void onCancel() {
                try {
                    super.onCancel();
                } finally {
                    record.accept(Status.CANCELLED);
                }
            }
        };
    }
}
```

Points to note:

- `getFullMethodName()` provides the complete method name without manual string concatenation.
- Timing starts before `next.startCall`, so the measurement includes handler initialization.
- `close(Status, Metadata)` reports the status with which the server ends the call.
- `onCancel()` captures cases where the client cancels the call before the server sends a final response.
- `AtomicBoolean` prevents duplicate logging if both cancellation and close occur.
- `finally` ensures recording still runs even if delegating close or the completion callback throws an error.

The example records `CANCELLED` when `onCancel` is received; if your system needs to distinguish deadline-induced cancellation from explicit client cancellation, include deadline/cause information from gRPC Context and test against your gRPC Java version. Do not guess the cause from this callback alone.

## 4. Client interceptor measuring actual client wait time

A client interceptor measures from when the call starts until `onClose` is received. This is useful for comparing the client's experience against server-side timing:

```java
package com.myshop.grpc.observability;

import io.grpc.CallOptions;
import io.grpc.Channel;
import io.grpc.ClientCall;
import io.grpc.ClientInterceptor;
import io.grpc.ForwardingClientCall;
import io.grpc.ForwardingClientCallListener;
import io.grpc.Metadata;
import io.grpc.MethodDescriptor;
import io.grpc.Status;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class RpcLoggingClientInterceptor implements ClientInterceptor {
    private static final Logger log =
            LoggerFactory.getLogger(RpcLoggingClientInterceptor.class);

    @Override
    public <ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
            MethodDescriptor<ReqT, RespT> method,
            CallOptions callOptions,
            Channel next) {

        String methodName = method.getFullMethodName();
        ClientCall<ReqT, RespT> delegate = next.newCall(method, callOptions);

        return new ForwardingClientCall.SimpleForwardingClientCall<>(delegate) {
            @Override
            public void start(Listener<RespT> listener, Metadata headers) {
                long startedAt = System.nanoTime();
                Listener<RespT> monitoredListener =
                        new ForwardingClientCallListener
                                .SimpleForwardingClientCallListener<>(listener) {
                            @Override
                            public void onClose(Status status, Metadata trailers) {
                                double latencyMs =
                                        (System.nanoTime() - startedAt) / 1_000_000.0;
                                try {
                                    super.onClose(status, trailers);
                                } finally {
                                    log.info(
                                            "grpc.client.call method={} status={} latency_ms={}",
                                            methodName, status.getCode(), latencyMs);
                                }
                            }
                        };
                super.start(monitoredListener, headers);
            }
        };
    }
}
```

The client measures up to `onClose`, so cancelled calls or expired deadlines still trigger a completion callback with their corresponding status. Do not start timing in `interceptCall` and stop as soon as `start` returns: `start` only initiates the RPC, not the arrival of the response.

Client and server may log the same full method name with different durations. That is normal:

- Client duration includes request/response transmission, network, and waiting on the server.
- Server duration starts when the server receives the call, excluding request travel time from client to server.
- The difference is not automatically exact network latency because both sides may experience queueing, buffering, and different measurement boundaries.

## 5. Unary and streaming have different latency semantics

For a unary RPC, a call typically has one request and one response. Measuring from start to `onClose` represents the end-to-end operation latency observed by the client.

For server streaming, the client may receive many messages over a long period. `onClose` only fires when the stream ends, so the duration is the **entire stream lifetime**, not time to the first message or per-message latency.

| RPC type | Measured at `onClose` | Additional metrics that may be needed |
| --- | --- | --- |
| Unary | End-to-end call latency | Server handler duration |
| Server streaming | Total open stream duration | Time to first message, message count, inter-message interval |
| Client streaming | Time from call open until final response finishes | Request stream receive duration, message count, client half-close time |
| Bidirectional streaming | Lifetime of the entire exchange session | Two-way message counts, first/last message timing, idle time |

Do not record a single `rpc_latency` metric that mixes unary calls with hours-long streams. Use descriptive metric names/labels, or separate metrics by RPC type. If you need per-message latency, wrap `ClientCall.Listener.onMessage` or `ServerCall.Listener.onMessage` and clearly define start/end points for each message.

## 6. Structured logging, status, and sensitive data

A useful log record typically includes:

| Field | Example | Notes |
| --- | --- | --- |
| `method` | `shop.catalog.v1.CatalogService/GetProduct` | Bounded label set defined by the API |
| `status` | `OK`, `NOT_FOUND`, `UNAVAILABLE` | Use gRPC status code, not just error strings |
| `latency_ms` | `18.42` | Duration calculated from `nanoTime()` |
| `side` | `server`, `client` | Distinguishes measurement point |
| `request_id` | Correlation ID if present | Can be included in controlled logs; do not use as a metric label |

Parameterized log example:

```text
grpc.server.call method=shop.catalog.v1.CatalogService/GetProduct status=OK latency_ms=18.42
```

Do not log full requests/responses, authorization headers, tokens, personal data, or arbitrary metadata. If correlation is needed, extract a validated request ID and apply the system's masking/retention policies. For failed calls, the status code is usually sufficient for grouping; descriptions can contain caller-supplied data, so do not log them indiscriminately.

Logging every RPC at INFO level can generate high log volume. In production, consider:

- Recording all calls into a metrics histogram; logging only errors and calls exceeding a latency threshold.
- Sampling successful calls at a controlled rate.
- Setting slow-call thresholds per method group rather than one global threshold.
- Keeping logs structured and parameterized, avoiding string concatenation or payload serialization.

## 7. Combining logs with latency metrics

Logs help investigate individual calls; metrics reveal distributions and trends. With Micrometer, you can record duration into a `Timer` with low-cardinality tags:

```java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.util.concurrent.TimeUnit;

void recordLatency(
        MeterRegistry registry,
        String method,
        String status,
        long elapsedNanos) {
    Timer.builder("grpc.server.call")
            .description("Server-side gRPC call duration")
            .tag("method", method)
            .tag("status", status)
            .register(registry)
            .record(elapsedNanos, TimeUnit.NANOSECONDS);
}
```

A Timer can provide counts, total time, and histograms/percentiles depending on registry configuration. Do not create tags from request IDs, user IDs, product IDs, or exception messages: each new value creates a new time series, increasing memory usage and monitoring costs.

Track p50/p95/p99 alongside request counts and error rates. A low average does not mean the system is healthy if a small subset of calls has very high latency. For streaming, separate stream lifetime metrics from unary latency and consider dedicated message-level metrics.

## 8. Registering interceptors and testing

Core gRPC Java lets you attach interceptors on the server builder:

```java
Server server = ServerBuilder.forPort(9090)
        .intercept(new RpcLoggingServerInterceptor())
        .addService(new CatalogGrpcEndpoint(catalogService))
        .build();
```

On the client:

```java
ManagedChannel channel = ManagedChannelBuilder
        .forAddress("catalog.internal", 9090)
        .useTransportSecurity()
        .intercept(new RpcLoggingClientInterceptor())
        .build();
```

In Spring gRPC, servers/channels are usually configured by the framework. Register interceptors via the extension point supported by your exact Spring gRPC version; declaring a class as a bean alone does not prove it is attached to the server or channel. Verify with integration tests using real RPCs.

Key tests:

| Test case | What to verify |
| --- | --- |
| Unary returns `OK` | Logs exact full method name, status, and non-negative latency |
| Unary returns `NOT_FOUND`/`INVALID_ARGUMENT` | Status is recorded accurately, not lost by wrappers |
| Client cancellation or deadline | Client `onClose` and server `onCancel` are recorded; no duplicate logs |
| Multiple concurrent calls | Start times and statuses are not shared across calls |
| Server streaming | Duration is recorded only when the stream ends/cancels |
| Same method name in different packages | Logs distinguish full method names |
| Metadata contains tokens/PII | Logs do not print raw headers or payloads |

You can use an in-process server/channel for fast interceptor tests. For Spring tests, boot the application configuration to verify that the framework actually registers the interceptor.

## 9. Implementation checklist

- [ ] Use `getFullMethodName()` for method identity.
- [ ] Clearly define server duration, client-observed latency, or handler execution time.
- [ ] Use `System.nanoTime()` for duration measurement.
- [ ] Record the final status and ensure each call logs at most once.
- [ ] Cover cancellation, call initialization failures, and completion callbacks.
- [ ] Distinguish unary latency from stream lifetime and message latency.
- [ ] Keep logs structured; do not log payloads, tokens, or sensitive metadata.
- [ ] Do not use request/user/resource IDs as metric labels.
- [ ] Track percentiles and error rates, not just averages.
- [ ] Test wrapper ordering, concurrency, and Spring interceptor registration.

**Self-check**

**Question 1.** Why should you use `getFullMethodName()` instead of logging `getProduct`?

*Answer:* The full method name includes package, service, and method, distinguishing RPCs with the same method name across different services/versions.

**Question 2.** Why is `System.nanoTime()` better suited than `currentTimeMillis()` for measuring latency?

*Answer:* `nanoTime()` is a monotonic clock meant for measuring elapsed intervals; wall-clock time can be adjusted.

**Question 3.** What does measuring from client `start` to `onClose` reflect?

*Answer:* The total call time observed by the client, including data transmission, network, server processing, and waiting for the final response.

**Question 4.** For server streaming, is measuring until `onClose` the latency of the first message?

*Answer:* No. It is the lifetime of the entire stream. To measure time-to-first-message, you must additionally record when the first message arrives.

**Question 5.** Why shouldn't request ID be used as a Micrometer Timer tag?

*Answer:* Request IDs are nearly unique per call, creating very high cardinality and excessive memory/resource usage in monitoring. Only include them in controlled logs.

Logging method names and latency in interceptors enables consistent RPC observability without editing every service method. Choose the right completion points, record status once, distinguish client vs. server timing, and treat streaming calls by stream lifetime; your logs and metrics will then serve both error investigation and performance monitoring.
