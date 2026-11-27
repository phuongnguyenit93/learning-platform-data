# Measuring Metrics by RPC Method

When monitoring a Spring gRPC service, total request counts or application-wide CPU usage are not enough to tell which method is slow, where errors are spiking, or which RPC pattern consumes the most time. You need measurements **per RPC method**, recording status and duration at a consistent point in the call lifecycle. A server interceptor is the right place because it sees the full method name and when the call ends, even when the service returns an error.

This lesson focuses on per-method metrics with Micrometer: choosing bounded-cardinality tags, measuring elapsed time with a monotonic clock, recording exactly once when a call finishes, and distinguishing unary from streaming calls. Client-side metrics have a different meaning from server-side metrics; do not merge the two measurements into one metric.

## 1. Choosing the metric and RPC identifier

Every RPC has a full method name of the form:

```text
shop.catalog.v1.CatalogService/GetProduct
```

Retrieve this name from the descriptor:

```java
String method = call.getMethodDescriptor().getFullMethodName();
```

The full method name includes the protobuf package, service, and method. It distinguishes methods that share the same short name across different services or API versions. Do not derive names from implementation class names or manually concatenate Java packages, because those are not the RPC's wire identifier.

A useful server metric typically needs the following dimensions:

| Label | Example value | Why it is useful |
| --- | --- | --- |
| method | shop.catalog.v1.CatalogService/GetProduct | Compare load and latency across RPCs |
| rpc_type | unary, server_streaming, client_streaming, bidi_streaming | Distinguish call duration by exchange pattern |
| status | OK, NOT_FOUND, UNAVAILABLE | Track errors and success rates |

These labels have finite value sets defined by the schema/service. Do not add request_id, user_id, product_id, tokens, arbitrary IP addresses, or exception messages as tags. Every new value can create a new time series; across millions of requests, unbounded cardinality drives up memory usage and monitoring costs.

## 2. Which measurements to collect on the server?

A server interceptor can measure the interval from when the server receives the call until the call finishes on the server side:

- **Call count:** number of completed RPCs. A Micrometer Timer already maintains a count, so you generally do not need a separate Counter for the same purpose.
- **Call duration:** time from when the interceptor starts until the server ends the call.
- **Status distribution:** call counts grouped by gRPC status such as OK, INVALID_ARGUMENT, UNAUTHENTICATED, or INTERNAL.
- **RPC type:** unary and streaming types should be grouped separately because their duration semantics differ.

Measure duration with System.nanoTime():

```java
long startedAt = System.nanoTime();
// When the call finishes:
long elapsedNanos = System.nanoTime() - startedAt;
```

nanoTime() is a monotonic clock suitable for computing elapsed intervals. currentTimeMillis() represents wall-clock time, which can jump or be adjusted, making it unsuitable for latency measurement.

Server call duration is not purely business method execution time. It can include handler initialization, processing, waiting for client messages, and the entire time a stream remains open. Metric names and dashboards must reflect this actual measurement scope.

## 3. Recording a Timer by full method name

A Micrometer Timer records count, total duration, and distribution statistics when histograms/percentiles are configured. A helper method can accept the method name, RPC type, status, and elapsed nanoseconds:

```java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.util.concurrent.TimeUnit;

final class RpcMethodMetrics {
    private final MeterRegistry registry;

    RpcMethodMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    void record(
            String method,
            String rpcType,
            String status,
            long elapsedNanos) {

        Timer.builder("grpc.server.call")
                .description("Duration of a server-side gRPC call")
                .tag("method", method)
                .tag("rpc_type", rpcType)
                .tag("status", status)
                .register(registry)
                .record(elapsedNanos, TimeUnit.NANOSECONDS);
    }
}
```

The registry returns the already-registered meter for the same name and tag set, so subsequent calls continue updating the same Timer. Timer.count() gives the recorded call count; Timer.totalTime(...) gives total elapsed time. To view p50/p95/p99, enable histograms or percentiles supported by your metrics backend; do not assume every registry exports percentiles by default.

You can enable histograms via Micrometer configuration or publishPercentileHistogram() on the Timer if your backend and time-series budget allow it. Histograms enable percentile aggregation in systems like Prometheus; review bucket counts and tag combinations before enabling them broadly.

## 4. Server interceptor recording metrics exactly once

An RPC may end via ServerCall.close, be cancelled by the client via onCancel, or fail immediately when starting the handler. Use an AtomicBoolean to ensure a call is recorded only once even if multiple completion callbacks fire:

```java
package com.myshop.grpc.metrics;

import io.grpc.ForwardingServerCall;
import io.grpc.ForwardingServerCallListener;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.util.Locale;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.function.Consumer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class RpcMethodMetricsInterceptor implements ServerInterceptor {
    private static final Logger log =
            LoggerFactory.getLogger(RpcMethodMetricsInterceptor.class);

    private final MeterRegistry registry;

    public RpcMethodMetricsInterceptor(MeterRegistry registry) {
        this.registry = registry;
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String method = call.getMethodDescriptor().getFullMethodName();
        String rpcType = call.getMethodDescriptor()
                .getType().name().toLowerCase(Locale.ROOT);
        long startedAt = System.nanoTime();
        AtomicBoolean recorded = new AtomicBoolean();

        Consumer<Status> finish = status -> {
            if (!recorded.compareAndSet(false, true)) {
                return;
            }
            long elapsedNanos = Math.max(0L, System.nanoTime() - startedAt);
            try {
                Timer.builder("grpc.server.call")
                        .description("Duration of a server-side gRPC call")
                        .tag("method", method)
                        .tag("rpc_type", rpcType)
                        .tag("status", status.getCode().name())
                        .register(registry)
                        .record(elapsedNanos, TimeUnit.NANOSECONDS);
            } catch (RuntimeException metricsFailure) {
                // Metrics must not alter the RPC outcome.
                log.warn("Unable to record gRPC metric for method={}",
                        method, metricsFailure);
            }
        };

        ServerCall<ReqT, RespT> monitoredCall =
                new ForwardingServerCall.SimpleForwardingServerCall<>(call) {
                    @Override
                    public void close(Status status, Metadata trailers) {
                        finish.accept(status);
                        super.close(status, trailers);
                    }
                };

        final ServerCall.Listener<ReqT> listener;
        try {
            listener = next.startCall(monitoredCall, headers);
        } catch (RuntimeException ex) {
            finish.accept(Status.fromThrowable(ex));
            throw ex;
        }

        return new ForwardingServerCallListener
                .SimpleForwardingServerCallListener<>(listener) {
            @Override
            public void onCancel() {
                try {
                    super.onCancel();
                } finally {
                    finish.accept(Status.CANCELLED);
                }
            }
        };
    }
}
```

This code illustrates the key design choices:

- Extract getFullMethodName() and the RPC type from MethodDescriptor.
- Start timing when the server interceptor receives the call.
- Record the Timer in close to capture the final server-side status.
- Record CANCELLED if the listener receives cancellation without another completion path.
- Use AtomicBoolean to prevent double counting when both close and onCancel occur.
- Catch metrics recording failures so a registry problem never breaks an in-flight RPC.

If next.startCall throws an exception synchronously, the interceptor records a status derived from the exception and rethrows it so gRPC's error handling continues working. For errors occurring after the handler returns a listener, the status should be recorded when the server closes the call.

## 5. Placing the interceptor at the right position in the chain

If an authentication interceptor rejects a call before the metrics interceptor sees it, rejected requests will not appear in this metric. To measure both successful calls and rejected calls, the metrics interceptor needs to wrap interceptors that can short-circuit the call.

Actual chain order depends on registration style and framework version. Verify with integration tests rather than guessing from configuration line order alone. If you want separate counts, you can maintain a dedicated metric for requests blocked at the gateway/authentication layer.

In Spring gRPC, the server is usually auto-configured. Register the interceptor via the extension point supported by your project's Spring gRPC version; declaring a class as a bean does not guarantee it is attached to the server. Test with real RPCs and verify that the Timer is updated.

## 6. Reading metrics and analyzing latency

With the grpc.server.call metric, dashboards typically need:

| Indicator | Operational question |
| --- | --- |
| Count by method/status | Which method has high load or rising errors? |
| Error rate by method | Which method has a rising non-OK status ratio? |
| p50 | Typical call latency |
| p95/p99 | Slow tail calls in the distribution |
| Total duration and call rate | Which methods are consuming backend processing time? |

When using a Prometheus registry and histograms, a p95 query can look like:

```promql
histogram_quantile(
  0.95,
  sum by (le, method) (
    rate(grpc_server_call_seconds_bucket[5m])
  )
)
```

Exact Prometheus metric names depend on the registry's naming conventions and application configuration; inspect the actual scrape endpoint before using queries. Do not compare p95 values across methods with different semantics without considering RPC type and traffic distribution.

## 7. Analyzing unary and streaming separately

For a unary RPC, one call has one request and one response; server call duration is usually close to total server-side request processing time.

For streaming RPCs, duration at close reflects **the lifetime of the entire call/stream**:

| RPC type | Timer at close reflects | Additional metrics that may be needed |
| --- | --- | --- |
| Unary | Call processing time | Queue time or handler duration if breakdown is needed |
| Server streaming | Time stream stays open until completion/cancellation | Time to first message, message count, inter-message interval |
| Client streaming | Time receiving request stream and producing final response | Request message count, client half-close timing |
| Bidirectional streaming | Lifetime of the two-way exchange session | Two-way message counts, idle duration, message latency |

Do not lump minutes-long streams with unary requests on a single latency dashboard without categorization. If per-message metrics are needed, wrap the listener and measure onMessage/onNext under a separate definition; never label stream lifetime as message latency.

## 8. Server metrics and client metrics are not the same

Server metrics start when the server receives the call. Client metrics typically start when the client starts the call and end at the onClose callback. Client-observed latency includes request/response transmission, queueing, and server processing; server metrics exclude the request's travel time from client to server.

If you instrument both sides, use distinct metric names—such as grpc.server.call and grpc.client.call—while keeping the same method label for comparison. Do not subtract the two numbers and claim the difference is exact network latency; the two sides have different start/end boundaries and buffering.

## 9. Testing per-method metrics

Use SimpleMeterRegistry or a test registry to verify metrics are recorded properly. Core assertions:

```java
Timer timer = registry.find("grpc.server.call")
        .tag("method", "shop.catalog.v1.CatalogService/GetProduct")
        .tag("rpc_type", "unary")
        .tag("status", "OK")
        .timer();

assertNotNull(timer);
assertEquals(1L, timer.count());
assertTrue(timer.totalTime(TimeUnit.NANOSECONDS) >= 0L);
```

This assertion runs after a test performs a successful RPC. Also write tests for:

- Different methods producing distinct method tags.
- NOT_FOUND, INVALID_ARGUMENT, and UNAVAILABLE recorded with the right status.
- Client cancellation recorded only once.
- Unary and each streaming type producing the right rpc_type.
- Multiple concurrent RPCs not sharing start timestamps or recording state.
- Authentication rejections measured when the chain is configured so the metrics interceptor observes them.
- Metrics failures not altering the RPC response/status.

Unit tests for the interceptor can use an in-process server/channel. Spring integration tests should boot the actual server configuration to verify the framework registers the interceptor.

## 10. Implementation checklist

- [ ] Use the full method name from MethodDescriptor.
- [ ] Record method, RPC type, and gRPC status using bounded tags.
- [ ] Use a Timer for count and duration; enable histograms/percentiles as needed.
- [ ] Measure duration with System.nanoTime().
- [ ] Record exactly once on close, cancel, or initialization failure.
- [ ] Metrics failures never break an RPC.
- [ ] Chain order allows measuring calls rejected by authentication/policy if required.
- [ ] Never use request ID, user ID, resource ID, tokens, or exception messages as tags.
- [ ] Separate unary latency from streaming lifetime and message latency.
- [ ] Separate server-side duration from client-observed latency.
- [ ] Dashboards include request count, error rate, and p50/p95/p99 per method.
- [ ] Integration tests verify metrics are actually recorded in Spring gRPC.

**Self-check**

**Question 1.** Why should you use the full method name as the method tag?

*Answer:* It distinguishes service, package version, and method, avoiding collisions across RPCs with the same short name.

**Question 2.** What information does a Micrometer Timer already provide so you usually don't need a separate Counter?

*Answer:* A Timer tracks the recorded count and total duration, in addition to distribution statistics when configured.

**Question 3.** Why shouldn't request_id be added as a Timer tag?

*Answer:* Request IDs are nearly unique per call, causing unbounded cardinality and putting pressure on the metrics backend. Use IDs in controlled logs instead.

**Question 4.** What does a server streaming Timer recorded at close represent?

*Answer:* The lifetime of the entire stream from when the server receives the call until the stream finishes or is cancelled, not single-message latency.

**Question 5.** Why should server metrics be kept distinct from client metrics?

*Answer:* The client measures total application wait time including network and server processing; the server measures from call arrival to server completion. The two metrics have different scopes.

Measuring metrics per RPC method pinpoints exactly which methods drive high load, errors, and latency. Use full method names with bounded tags, record the Timer once when a call completes, and categorize streaming separately; combined with percentile dashboards and integration tests, your telemetry stays actionable without overloading the metrics backend.
