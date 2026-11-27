# Latency Histogram for Unary and Streaming

Counting RPCs tells you how many calls a service receives, but not how long callers have to wait. A method may keep a steady request rate while p99 latency spikes sharply due to a slow database, long queues, or a few degraded instances. Latency histograms help observe the RPC duration distribution, compare across methods, and uncover slow tail behavior that averages usually hide.

**Latency histogram for unary and streaming** is the practice of measuring RPC duration and its distribution by service/method, status, and RPC type. This lesson belongs to the **Observability** chapter of the **SPRING_GRPC** module: developing gRPC services in the Spring ecosystem using Protocol Buffers contracts, generating Java code, and implementing client/server for unary or streaming RPCs; learners work with metadata, deadlines, statuses, interceptors, TLS, integration testing, and monitoring performance and reliability. The focus is on defining the exact interval being measured, configuring a Micrometer `Timer` histogram, and reading p95/p99 per method.

## 1. Where Is the Latency of an RPC Measured From and To?

For an RPC, duration is typically measured from when the call starts at the instrumentation boundary until the call enters a terminal state:

- Client-side duration: from when the client starts the call until it receives `onClose`.
- Server-side duration: from when the server interceptor receives the call until the server closes the call or receives cancellation.
- Unary RPC: duration covers processing the request and producing the response.
- Streaming RPC: duration of the entire call from when the stream opens until the stream completes, errors, or is cancelled.

Client and server measurements do not necessarily match. Client-side duration can include transport, network, queueing, and waiting for the response; server-side duration reflects how long the call stayed on the server relative to the interceptor position. When comparing both sides, treat them as two distinct perspectives rather than subtracting directly to infer network latency without synchronized clocks and well-defined measurement boundaries.

For streaming RPCs, total stream duration is not the same as per-message latency. A server-streaming call that stays open for 20 minutes and sends 10,000 messages has an RPC duration of 20 minutes; this number does not tell you how long it took for the first message to reach the client or the interval between messages. If you need answers to those questions, you must create separate metrics.

## 2. Distinguishing RPC Duration, Time-to-First-Message, and Message Latency

Define metrics based on the operational questions you need to answer:

| Metric | Start | End | Used to Answer |
| --- | --- | --- | --- |
| RPC duration | Call starts | Call terminal | How long does an RPC live? |
| Time to first response | Call starts | First response message | How long does the client wait to see the first data? |
| Inter-message gap | Previous message sent/received | Next message sent/received | Does the stream have abnormal pauses in emitting data? |
| Message processing duration | Processing a message starts | Processing the message finishes | How long does each message take to process? |
| Stream lifetime | Stream opens | Stream closes/cancels | How long does a subscription or streaming session last? |

Unary RPCs typically use RPC duration as the primary latency metric. For streaming, RPC duration is still useful to measure call lifetime and detect hung or abnormally long-lived streams, but it does not replace time-to-first-message or message processing duration.

Do not put unary duration and stream lifetime into a single shared histogram and interpret p99 as the same kind of experience. Streams are often longer by many orders of magnitude. You can use separate metric names, or an `rpc_type` label with a finite set of values such as `unary`, `client_streaming`, `server_streaming`, `bidi_streaming`. Dashboards should filter to the right type before comparing.

## 3. Why Use a Histogram Instead of Only an Average?

Average is total duration divided by call count. A small number of very slow requests can be hidden by a large volume of fast requests. A histogram distributes observations into time-threshold buckets, thereby revealing the latency tail.

For example, out of 1,000 RPCs, 990 calls finish in 40 ms and 10 calls take 3 seconds. The average may still look acceptable, but p99 reflects the slow group of callers. A histogram retains observation counts in each interval so the backend can compute approximate quantiles over a time window.

| Statistic | Meaning | Limitation |
| --- | --- | --- |
| Count | Number of recorded measurements. | Does not indicate whether times were fast or slow. |
| Sum | Total duration of all observations. | Does not describe the distribution. |
| Average | Sum / Count. | Hides tail latency. |
| p50 | Median; half of observations do not exceed this threshold. | Does not reflect the slowest group. |
| p95 / p99 | Threshold that 95% / 99% of observations do not exceed. | Estimated from histogram buckets; accuracy depends on bucket boundaries. |

Micrometer `Timer` is suitable for recording duration. When percentile histograms or service-level objectives are enabled, the Prometheus exporter can publish bucket series so the backend can compute quantiles. Histogram buckets are aggregatable data across multiple instances; percentiles computed from histogram buckets are much better suited for service-wide aggregation than averaging per-instance p99 values.

## 4. Choosing Buckets and SLOs

Bucket boundaries should reflect the response times the service aims to achieve. For internal unary RPCs with SLOs under a few hundred milliseconds, buckets should be dense in the lower range and include higher thresholds to observe incidents:

```text
10 ms, 25 ms, 50 ms, 100 ms, 200 ms,
300 ms, 500 ms, 1 s, 2 s, 5 s
```

This is only an example; do not use the same bucket set for every method. Cache-reading RPCs, database-querying RPCs, and RPCs calling multiple downstream services have different characteristics. Choose buckets around SLO thresholds, alert thresholds, and the actual latency range.

For streaming, stream duration buckets may need to span from seconds to hours. If the goal is time-to-first-message, create a separate `Timer` with buckets suited to first-message delay. Do not stretch unary buckets just to hold stream lifetimes; doing so makes the unary histogram less useful.

Micrometer allows configuring `serviceLevelObjectives(...)` to generate buckets corresponding to SLO thresholds, and `publishPercentileHistogram()` to export histograms compatible with supported backends. More buckets increase the number of time series proportionally with label combinations. Only choose thresholds that serve operational questions.

## 5. Recording RPC Duration on the Server with ServerInterceptor

`ServerInterceptor` can extract service/method names from `MethodDescriptor`, start a timer when receiving the call, and record the duration when the call closes or is cancelled. Example using Micrometer:

```java
import io.grpc.ForwardingServerCall;
import io.grpc.ForwardingServerCallListener;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicBoolean;

public final class RpcLatencyServerInterceptor
        implements ServerInterceptor {

    private final MeterRegistry registry;

    public RpcLatencyServerInterceptor(MeterRegistry registry) {
        this.registry = registry;
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String fullMethod =
                call.getMethodDescriptor().getFullMethodName();
        int separator = fullMethod.lastIndexOf('/');
        String service = separator < 0
                ? "unknown"
                : fullMethod.substring(0, separator);
        String method = separator < 0
                ? fullMethod
                : fullMethod.substring(separator + 1);

        Timer.Sample sample = Timer.start(registry);
        AtomicBoolean recorded = new AtomicBoolean();

        java.util.function.Consumer<Status> record =
                status -> {
                    if (recorded.compareAndSet(false, true)) {
                        Timer timer = Timer.builder(
                                        "grpc.server.call.duration")
                                .description("Duration of handling a gRPC server call")
                                .publishPercentileHistogram()
                                .serviceLevelObjectives(
                                        Duration.ofMillis(10),
                                        Duration.ofMillis(25),
                                        Duration.ofMillis(50),
                                        Duration.ofMillis(100),
                                        Duration.ofMillis(200),
                                        Duration.ofMillis(500),
                                        Duration.ofSeconds(1),
                                        Duration.ofSeconds(2))
                                .tags(
                                        "service", service,
                                        "method", method,
                                        "status", status.getCode().name())
                                .register(registry);
                        sample.stop(timer);
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

        ServerCall.Listener<ReqT> listener =
                next.startCall(monitoredCall, headers);

        return new ForwardingServerCallListener
                .SimpleForwardingServerCallListener<>(listener) {
            @Override
            public void onCancel() {
                record.accept(Status.CANCELLED);
                super.onCancel();
            }
        };
    }
}
```

`Timer.Sample` records the start time; `sample.stop(timer)` records the duration into the `Timer` when the call ends. `AtomicBoolean` guarantees only one terminal path records a sample, even when `onCancel()` and `close()` happen close together.

Server-side `onCancel()` only indicates the call was cancelled; it does not necessarily identify whether the caller explicitly cancelled or the deadline expired. Therefore, the server status label may be `CANCELLED` while the client observes `DEADLINE_EXCEEDED`. If you need to distinguish the cause, cross-reference client metrics, deadline context, and traces instead of assuming statuses on both sides are always identical.

The example builds a `Timer` with the same bucket configuration per meter ID. In a real application, centralize the `Timer` configuration into a shared factory/helper to avoid bucket mismatches across calls or services. Also verify terminal callback behavior with the `grpc-java` version in use.

## 6. Recording Duration on the Client with ClientInterceptor

Client-side duration measures from when the client starts the call until the listener receives `onClose`. It encompasses the time observed by the client, making it useful for measuring caller experience:

```java
import io.grpc.CallOptions;
import io.grpc.Channel;
import io.grpc.ClientCall;
import io.grpc.ClientInterceptor;
import io.grpc.ForwardingClientCall;
import io.grpc.ForwardingClientCallListener;
import io.grpc.Metadata;
import io.grpc.MethodDescriptor;
import io.grpc.Status;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

import java.time.Duration;

public final class RpcLatencyClientInterceptor
        implements ClientInterceptor {

    private final MeterRegistry registry;

    public RpcLatencyClientInterceptor(MeterRegistry registry) {
        this.registry = registry;
    }

    @Override
    public <ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
            MethodDescriptor<ReqT, RespT> method,
            CallOptions callOptions,
            Channel next) {

        String fullMethod = method.getFullMethodName();
        int separator = fullMethod.lastIndexOf('/');
        String service = separator < 0
                ? "unknown"
                : fullMethod.substring(0, separator);
        String methodName = separator < 0
                ? fullMethod
                : fullMethod.substring(separator + 1);

        return new ForwardingClientCall
                .SimpleForwardingClientCall<>(
                        next.newCall(method, callOptions)) {
            @Override
            public void start(
                    Listener<RespT> responseListener,
                    Metadata headers) {

                Timer.Sample sample = Timer.start(registry);
                Listener<RespT> monitored =
                        new ForwardingClientCallListener
                                .SimpleForwardingClientCallListener<>(
                                        responseListener) {
                            @Override
                            public void onClose(
                                    Status status,
                                    Metadata trailers) {
                                Timer timer = Timer.builder(
                                                "grpc.client.call.duration")
                                        .publishPercentileHistogram()
                                        .serviceLevelObjectives(
                                                Duration.ofMillis(10),
                                                Duration.ofMillis(50),
                                                Duration.ofMillis(100),
                                                Duration.ofMillis(250),
                                                Duration.ofMillis(500),
                                                Duration.ofSeconds(1),
                                                Duration.ofSeconds(2))
                                        .tags(
                                                "service", service,
                                                "method", methodName,
                                                "status", status.getCode().name())
                                        .register(registry);
                                sample.stop(timer);
                                super.onClose(status, trailers);
                            }
                        };

                super.start(monitored, headers);
            }
        };
    }
}
```

The client interceptor must be attached to the channel via `ManagedChannelBuilder.intercept(...)` or the corresponding extension point of the Spring gRPC starter. A client call may be retried internally. Where the interceptor sits in the interceptor chain and retry machinery determines whether the timer observes the logical call or an individual attempt. If you need attempt-level duration, verify the instrumentation/version semantics with tests or use instrumentation that supports attempt metrics.

Do not add client duration and server duration together into a total. They are two measurements covering different boundaries and can overlap.

## 7. Configuring Micrometer Timer in Spring

Spring Boot typically manages `MeterRegistry` via Micrometer when the project includes the appropriate metrics dependency. You can create a helper to standardize `Timer` instances by service, method, and status:

```java
Timer timer = Timer.builder("grpc.server.call.duration")
        .description("gRPC server RPC duration")
        .publishPercentileHistogram()
        .serviceLevelObjectives(
                Duration.ofMillis(25),
                Duration.ofMillis(50),
                Duration.ofMillis(100),
                Duration.ofMillis(250),
                Duration.ofMillis(500),
                Duration.ofSeconds(1))
        .tags(
                "service", service,
                "method", method,
                "status", status)
        .register(meterRegistry);
```

Timers should use consistent names, consistent time units, and buckets suited to the RPC type. If using one `Timer` name for both unary and streaming, add an `rpc_type` label with a finite set of values or separate the metric names. Never create dynamic labels from requests.

Register the interceptor through the gRPC server/channel lifecycle managed by the starter. The bean example only illustrates how to construct the interceptor:

```java
@Configuration
class GrpcLatencyConfiguration {

    @Bean
    RpcLatencyServerInterceptor rpcLatencyServerInterceptor(
            MeterRegistry registry) {
        return new RpcLatencyServerInterceptor(registry);
    }
}
```

This bean still needs to be actually registered by the starter or server builder. Do not assume every starter automatically attaches every `ServerInterceptor` bean; verify with an integration test that invokes an RPC and checks that the meter appears. If the OpenTelemetry Java agent or a gRPC instrumentation library already collects duration, avoid adding an interceptor with the same metric semantics and counting twice.

## 8. Measuring Streaming Duration and Time-to-First-Message

The server interceptor above measures total stream duration: from when the server receives the call until the stream closes or cancels. That is a useful metric for detecting streams that stay open too long, but it does not indicate whether the first message arrived quickly or slowly.

To measure time-to-first-message in server-streaming, you can wrap `ServerCall.sendMessage(...)` and record only on the first call:

```java
AtomicBoolean firstMessageRecorded = new AtomicBoolean();
long startedNanos = System.nanoTime();

ServerCall<ReqT, RespT> monitored =
        new ForwardingServerCall.SimpleForwardingServerCall<>(call) {
            @Override
            public void sendMessage(RespT message) {
                if (firstMessageRecorded.compareAndSet(false, true)) {
                    Timer.builder("grpc.server.stream.time.to.first.message")
                            .publishPercentileHistogram()
                            .tags("service", service, "method", method)
                            .register(registry)
                            .record(
                                    System.nanoTime() - startedNanos,
                                    TimeUnit.NANOSECONDS);
                }
                super.sendMessage(message);
            }
        };
```

This is a conceptual example for server-streaming; in a complete interceptor, share the same call wrapper with the duration recorder and handle the case where a stream closes without sending any message. `System.nanoTime()` is suitable for measuring elapsed duration within a single process because it is unaffected by system clock adjustments.

For client-streaming or bidirectional streaming, clearly define what "first message" means: the first request message arriving at the server, the first response to the client, or the first message finished processing. Place the metric at the exact boundary you want to observe. For message processing duration, measure each message with a separate `Timer`, but do not add message ID as a label.

## 9. Streaming Histograms Need Separate Buckets

A stream can live for seconds, minutes, or hours. If you use unary buckets from 10 ms to 2 s, most streams will fall into the largest bucket and lose distribution information. If you extend unary buckets out to hours, unary quantiles lose granularity.

One way to organize them:

| Metric | Example Buckets | Purpose |
| --- | --- | --- |
| grpc.server.unary.duration | 10 ms to 2 s | Unary processing latency. |
| grpc.server.stream.lifetime | 1 s to 1 h | Server/client/bidi stream lifetime. |
| grpc.server.stream.time.to.first.message | 10 ms to 10 s | Wait time for the first message. |
| grpc.server.stream.message.processing | 1 ms to 1 s | Processing time per message. |

Thresholds are examples only; choose based on traffic, SLOs, and business type. A subscription stream designed to run all day should not trigger alerts simply for having a long duration. For this kind of stream, time-to-first-message, inter-message gap, reconnect count, and active stream count may be more useful than stream lifetime p99.

## 10. Querying p95/p99 in Prometheus

The Micrometer Prometheus registry typically exports `Timer` histograms as bucket, count, and sum series. For a metric named `grpc.server.call.duration`, the normalized name may be `grpc_server_call_duration_seconds_bucket`; actual names depend on the registry/export convention. Check the scrape endpoint to confirm.

Example calculating p95 by service and method:

```promql
histogram_quantile(
  0.95,
  sum by (le, service, method) (
    rate(grpc_server_call_duration_seconds_bucket[5m])
  )
)
```

p99:

```promql
histogram_quantile(
  0.99,
  sum by (le, service, method) (
    rate(grpc_server_call_duration_seconds_bucket[5m])
  )
)
```

Split by status to inspect errors versus successful calls:

```promql
histogram_quantile(
  0.95,
  sum by (le, service, method, status) (
    rate(grpc_server_call_duration_seconds_bucket[5m])
  )
)
```

The ratio of calls exceeding 500 ms can be calculated from the appropriate bucket if the histogram has that boundary:

```promql
1 -
(
  sum by (service, method) (
    rate(grpc_server_call_duration_seconds_bucket{le="0.5"}[5m])
  )
  /
  sum by (service, method) (
    rate(grpc_server_call_duration_seconds_count[5m])
  )
)
```

If the exporter uses different label or bucket names, adjust the query to match the actual series. `histogram_quantile` is an estimate from bucket boundaries; accuracy is limited by bucket width around the quantile. Do not average per-instance p99 values to produce a service-wide p99; sum the bucket counts first and then compute the quantile.

## 11. Interpreting Histograms Alongside Request Rate and Status

Latency should not be read in isolation from traffic and status:

| Signal | Initial Interpretation | Check Next |
| --- | --- | --- |
| p50 stable, p99 increases | A subset of requests is slow, possibly due to hot keys, pool exhaustion, or one failing instance. | Per-instance histograms, dependency latency, and queues. |
| Both p50 and p99 increase | The entire service may be overloaded or a primary dependency is slow. | CPU, thread pools, database, network, and request rate. |
| p99 increases alongside UNAVAILABLE | Connections or endpoints may be unstable; retries increase duration. | Subchannels, retry attempts, endpoint health. |
| p99 increases alongside DEADLINE_EXCEEDED | Requests hit time limits; callers may cancel before the server finishes. | Deadline budget, downstream spans, and server duration. |
| Stream lifetime increases | May be normal behavior for long-lived subscriptions or stuck streams. | Time-to-first-message, inter-message gap, stream age policy. |
| Low count but high duration | Few calls, but each call holds resources for a long time. | In-flight gauge and stream lifecycle. |

Duration histograms only record when a call ends. A stream that has been open for hours will not appear in the completed-duration histogram until it terminates. Therefore, combine them with an in-flight gauge or active stream gauge to see calls currently in existence.

## 12. Cardinality and Histogram Cost

Each label combination creates a meter/time series; each histogram has multiple buckets. If you use `service`, `method`, `status`, `rpc_type`, and `instance` dimensions, the number of series grows as the product of their value counts. Adding request ID, user ID, or stream ID will cause cardinality to explode.

Keep labels bounded:

- `service`: full Protobuf service name.
- `method`: method name.
- `status`: gRPC status code.
- `rpc_type`: only when needed, with the four fixed RPC type values.
- `instance`/`zone`: only when the backend and cardinality budget allow.

Do not use message content, arbitrary metadata, exception messages, trace IDs, or client identity as histogram labels. Such detailed data belongs in traces/logs. Do not enable percentile histograms on every metric by default; select the methods that need tracking and the necessary buckets.

## 13. Testing Latency Instrumentation

Tests should verify that the timer starts and stops according to the lifecycle:

1. Invoke a successful unary RPC; verify count increments by one and duration is positive.
2. Invoke a method that returns an error; verify the corresponding status tag and that the timer still records.
3. Cancel an RPC; verify duration is recorded exactly once even though `onCancel` and `close` may race.
4. Invoke a multi-message server-streaming RPC; verify RPC duration records only one sample when the stream ends, not incrementing per message.
5. Record time-to-first-message separately; verify only one sample for the first message.
6. Keep a stream open; verify the active stream gauge increases even though the completed histogram has no sample yet.
7. Run multiple instances; verify Prometheus queries sum buckets before computing p95/p99.
8. Verify metric labels do not contain request ID, user ID, or message ID.

For unit tests, use `SimpleMeterRegistry` to check `Timer` count and total time. For integration tests, use an in-process gRPC server/channel to verify the interceptor is registered and terminal callbacks are observed. If you need to measure real network latency, add tests over TCP/TLS; in-process transport does not represent production network latency.

Do not use `Thread.sleep()` to assert an exact duration. For timing tests, introduce a controlled wait with a latch and assert invariants such as timer count, duration greater than 0, and no duplicate recording. Do not assert an exact millisecond number in CI because scheduling and machine load cause timing variability.

## 14. Common Pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Only average is visible, no tail latency | Histogram not enabled or buckets unsuitable. | Enable histogram and choose buckets around SLOs. |
| Huge stream lifetime p99 makes unary dashboard unreadable | Mixing stream duration with unary duration. | Separate metrics or filter by rpc_type. |
| Active streams do not appear in duration histogram | Timer only records when a call ends. | Add active stream gauge and age metric. |
| Cancelled calls have no duration | Only recording in close, missing onCancel. | Record on both terminal paths with an atomic guard. |
| Duration is recorded twice | Both onCancel and close record. | Use an idempotent recorder per call. |
| Per-instance p99 is low but service p99 is high | One instance has low traffic or histograms are aggregated incorrectly. | Sum bucket counts across the service then compute quantile. |
| Histogram has too many series | Many dynamic labels or too many buckets. | Limit labels and enable histograms only where needed. |
| Client and server durations do not match | The two metrics measure at different boundaries. | Keep direction separate and analyze alongside traces. |
| Retries increase client duration | Client timer includes attempt/backoff time depending on instrumentation placement. | Define logical call/attempt semantics and observe retries separately. |

## 15. Hands-On Exercises

1. Write a `ServerInterceptor` using Micrometer `Timer` to measure unary RPC duration by service, method, and status.
2. Enable percentile histograms and configure buckets around the SLO of a read method.
3. Write a `ClientInterceptor` to measure client-observed duration; compare with server duration while keeping the two metrics separate.
4. Create a server-streaming RPC; measure stream lifetime and time-to-first-message with two distinct metrics.
5. Write PromQL queries to compute p95/p99 by service/method and the ratio of RPCs exceeding 500 ms.
6. Test success, error, cancellation, and multi-message streams; verify one terminal sample per RPC.
7. Build a dashboard separating unary, streaming, status, and direction; combine histograms with an active stream gauge.
8. Audit cardinality and confirm labels contain only the selected bounded dimensions.

After this lesson, you should be able to distinguish RPC duration from time-to-first-message and message latency, use `Timer` histograms to observe unary/streaming distributions appropriately, record terminal duration exactly once, and compute p95/p99 by aggregating buckets. When reading histograms alongside request rate, status, and active stream count, operations teams can detect tail latency and anomalous streams in a Spring gRPC system.
