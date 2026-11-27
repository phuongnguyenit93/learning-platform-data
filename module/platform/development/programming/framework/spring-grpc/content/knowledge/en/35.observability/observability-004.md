# Active Streams and Stream Duration

With a unary RPC, a call usually finishes quickly after one request and one response. With server-streaming, client-streaming, or bidirectional streaming, a call can hold connections and resources for minutes or hours. Measuring only the request rate and latency of completed calls misses open, stuck, or resource-heavy streams.

**Active streams and stream duration** provide two complementary views: active streams tell you how many streams currently exist; stream duration measures the time from when a stream starts until it ends. This lesson belongs to the **Observability** chapter of the **SPRING_GRPC** module: developing gRPC services in the Spring ecosystem using Protocol Buffers contracts, generating Java code, and implementing client/server for unary or streaming RPCs; learners work with metadata, deadlines, statuses, interceptors, TLS, integration testing, and monitoring performance and reliability. The focus is on properly tracking streaming call lifecycles, updating gauges exactly once, and interpreting duration without confusing it with per-message latency.

## 1. Distinguishing Active Streams and Stream Duration

- **Active streams** is the number of streaming RPCs that have started but not yet entered a terminal state at the time of observation.
- **Stream duration** is the time from when the call starts at the instrumentation boundary until it completes, errors, or is cancelled.
- **Message latency** is the time to send/receive or process a single message; it is not synonymous with stream duration.
- **Time to first message** is the time from opening the stream to the first message; this is also a separate metric.

For example, a subscription that stays open for 30 minutes and receives 2,000 messages:

- Active streams increments by 1 when the subscription starts and decrements by 1 when the call ends.
- Stream duration records one observation of roughly 30 minutes when the call ends.
- Message count increments per message, without incrementing active streams.
- Time to first message records one observation when the first message is sent/received.

An open stream does not yet have a duration sample in a regular `Timer`, because a `Timer` records when the sample is stopped. Therefore, an active stream gauge is needed to see calls that still exist. If you want to observe the age of open streams, you can add a `LongTaskTimer` or a separate age metric.

## 2. Identifying Which RPC Types to Track

gRPC defines four method types in Protobuf:

| RPC Type | Message Direction | Is It a Stream? | Lifecycle |
| --- | --- | --- | --- |
| Unary (MethodType.UNARY) | One request, one response | No | Usually short; exclude from active stream gauge. |
| Client streaming (MethodType.CLIENT_STREAMING) | Multiple requests, one response | Yes | Client sends multiple messages then half-closes; server may still process before returning the final response. |
| Server streaming (MethodType.SERVER_STREAMING) | One request, multiple responses | Yes | Server sends multiple messages then closes the response stream. |
| Bidirectional streaming (MethodType.BIDI_STREAMING) | Multiple messages in both directions | Yes | Both sides exchange independently until the call terminates. |

The active stream metric should count only the three streaming types. If counting all RPCs, name it clearly as `active calls` instead of `active streams`. Metric names and dashboards must remain consistent with this definition.

Obtain the method type from the Protobuf `MethodDescriptor` rather than inferring it from the method name or observed message count:

~~~java
MethodDescriptor.MethodType type = call.getMethodDescriptor().getType();
boolean streaming = type != MethodDescriptor.MethodType.UNARY;
~~~

## 3. Lifecycle of a Server-Side Stream

On the server, the interceptor receives the call before the service handles it. The call terminates normally when the server closes `ServerCall` with a terminal status. If the peer cancels or loses connection, the listener may receive `onCancel`. Both paths can happen close together, so decrementing the active count and recording duration must be idempotent.

~~~mermaid
flowchart TD
    A[Server receives streaming RPC] --> B[active streams +1]
    B --> C[Timer sample starts]
    C --> D{Call terminal?}
    D -->|Server close| E[Record status and duration]
    D -->|Peer cancel/disconnect| E
    E --> F[active streams -1]
    F --> G[Cleanup completes exactly once]
~~~

Do not decrement active streams in `ServerCall.Listener.onHalfClose`. With client-streaming and bidirectional streaming, `onHalfClose` only indicates that the client has finished sending request messages; the server may still be processing or continuing to send responses. Active streams must only decrement when the entire RPC terminates.

## 4. Choosing Appropriate Metrics

A basic metric set can include:

| Metric | Type | Tags | Meaning |
| --- | --- | --- | --- |
| grpc.server.active.streams | Gauge | service, method, rpc_type | Number of currently active streams on the server. |
| grpc.server.stream.duration | Timer histogram | service, method, rpc_type, status | Lifetime of finished streams. |
| grpc.client.active.streams | Gauge | service, method, rpc_type | Number of streams held open by the client. |
| grpc.client.stream.duration | Timer histogram | service, method, rpc_type, status | Duration observed by the client from start to onClose. |
| grpc.server.stream.messages.received | Counter | service, method | Total request messages received by the server. |
| grpc.server.stream.messages.sent | Counter | service, method | Total response messages sent by the server. |

It is not mandatory to implement all of them at the outset. Active gauge and duration histogram are usually the minimal pair for observing lifecycle. Message counters or time-to-first-message should only be added when addressing specific operational questions.

Keep client and server metrics separate. A client may have opened a call that the server has not yet received; the server may have closed a call before the client observes the terminal callback due to transport delay. Therefore, the two gauges do not necessarily match.

## 5. Measuring Active Streams on the Server with ServerInterceptor

The following example uses Micrometer. The interceptor skips unary RPCs, registers a gauge per `service`/`method`/`type`, and decrements the gauge and records the `Timer` only once when the call terminates:

~~~java
import io.grpc.ForwardingServerCall;
import io.grpc.ForwardingServerCallListener;
import io.grpc.Metadata;
import io.grpc.MethodDescriptor;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

import java.time.Duration;
import java.util.Locale;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public final class ActiveStreamServerInterceptor
        implements ServerInterceptor {

    private final MeterRegistry registry;
    private final ConcurrentMap<String, AtomicInteger> activeByMethod =
            new ConcurrentHashMap<>();

    public ActiveStreamServerInterceptor(MeterRegistry registry) {
        this.registry = registry;
    }

    private AtomicInteger activeCounter(
            String service, String method, String rpcType) {
        String key = service + "|" + method + "|" + rpcType;
        return activeByMethod.computeIfAbsent(key, ignored -> {
            AtomicInteger count = new AtomicInteger();
            Gauge.builder(
                            "grpc.server.active.streams",
                            count,
                            AtomicInteger::get)
                    .description("Active streaming RPCs on the server")
                    .tags(
                            "service", service,
                            "method", method,
                            "rpc_type", rpcType)
                    .register(registry);
            return count;
        });
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        MethodDescriptor<ReqT, RespT> descriptor =
                call.getMethodDescriptor();
        MethodDescriptor.MethodType type = descriptor.getType();
        if (type == MethodDescriptor.MethodType.UNARY) {
            return next.startCall(call, headers);
        }

        String fullMethod = descriptor.getFullMethodName();
        int separator = fullMethod.lastIndexOf('/');
        String service = separator < 0
                ? "unknown"
                : fullMethod.substring(0, separator);
        String method = separator < 0
                ? fullMethod
                : fullMethod.substring(separator + 1);
        String rpcType = type.name().toLowerCase(Locale.ROOT);

        AtomicInteger active = activeCounter(service, method, rpcType);
        active.incrementAndGet();

        Timer.Sample sample = Timer.start(registry);
        AtomicBoolean finished = new AtomicBoolean();

        java.util.function.Consumer<Status> finish = status -> {
            if (finished.compareAndSet(false, true)) {
                active.decrementAndGet();
                Timer timer = Timer.builder("grpc.server.stream.duration")
                        .description("Duration of a server-side streaming RPC")
                        .publishPercentileHistogram()
                        .serviceLevelObjectives(
                                Duration.ofSeconds(1),
                                Duration.ofSeconds(5),
                                Duration.ofSeconds(15),
                                Duration.ofSeconds(30),
                                Duration.ofMinutes(1),
                                Duration.ofMinutes(5),
                                Duration.ofMinutes(15),
                                Duration.ofHours(1))
                        .tags(
                                "service", service,
                                "method", method,
                                "rpc_type", rpcType,
                                "status", status.getCode().name())
                        .register(registry);
                sample.stop(timer);
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

        try {
            ServerCall.Listener<ReqT> listener =
                    next.startCall(monitoredCall, headers);
            return new ForwardingServerCallListener
                    .SimpleForwardingServerCallListener<>(listener) {
                @Override
                public void onCancel() {
                    finish.accept(Status.CANCELLED);
                    super.onCancel();
                }
            };
        } catch (RuntimeException failure) {
            finish.accept(Status.fromThrowable(failure));
            throw failure;
        }
    }
}
~~~

Key points:

- The `Gauge` is registered once per `service`/`method`/`rpc_type` combination; the map holds a strong reference to `AtomicInteger` so the gauge value stays alive.
- Each call increments `active` before passing to the service handler.
- `ServerCall.close` records status and duration when the server closes the call.
- `onCancel` records cancellation if the peer cancels before the server closes.
- `AtomicBoolean` prevents double decrementing and double `Timer` recording when the two terminal paths race.
- If initializing the listener throws a synchronous `RuntimeException`, the `catch` block still decrements `active` and records terminal duration.

This is a server-side instrumentation example; when using a Spring gRPC starter, register the interceptor via the starter's extension point or the server builder managed by the starter. Do not create a separate server just to attach metric interceptors.

## 6. Measuring Active Streams on the Client

A client-side stream begins at `ClientCall.start` and ends when the listener receives `onClose`. A `ClientInterceptor` can follow the same principles:

1. Extract full method name and `MethodType` from `MethodDescriptor`.
2. Skip unary methods if the metric is intended only for streams.
3. Increment the gauge before calling `start` on `ClientCall`.
4. Create a `Timer.Sample` for client-observed stream duration.
5. Wrap `ClientCall.Listener.onClose` to decrement the gauge and record duration/status.
6. Use `AtomicBoolean` to guarantee recording terminal state once if callbacks or synchronous errors race.

Client metrics measure from the caller's perspective, including transport time and waiting for responses. They can be longer than server duration or end with a different status than server-side metrics. Name them separately as `grpc.client.active.streams` and `grpc.client.stream.duration`; do not add them directly to server metrics.

With client streaming, the client may call `halfClose` after finishing sending request messages while still waiting for the response. Do not decrement the active gauge on `halfClose`; only decrement when `onClose` signals that the call has ended.

## 7. LongTaskTimer for the Age of Open Streams

A standard `Timer` histogram only receives duration when a stream ends. To observe the duration of streams that are still running, Micrometer provides `LongTaskTimer`:

~~~java
LongTaskTimer activeDuration = LongTaskTimer.builder(
                "grpc.server.stream.active.duration")
        .description("Elapsed time of active streaming RPCs")
        .tags(
                "service", service,
                "method", method,
                "rpc_type", rpcType)
        .register(registry);

LongTaskTimer.Sample activeSample = activeDuration.start();

// When stream terminates:
activeSample.stop();
~~~

`LongTaskTimer` tracks the number of running tasks and their duration while still active; when stopped, the task leaves the active set. You can use it instead of a manual gauge or combine it with a gauge if dashboards require distinct metric names/semantics. Avoid recording the same concept twice and then summing the series.

If you only need to alert on overly old streams, `LongTaskTimer` or an age-tracking mechanism can detect them earlier than a completed-duration `Timer`. You must distinguish whether a long stream is anomalous or designed as a long-lived subscription; do not alert simply because a valid stream stays open for many hours.

## 8. Do Not Confuse Active Streams with Message Flow

A stream can be active without any messages for a long period. This may be normal if the stream is waiting for events, or abnormal if a producer is hung. Active count cannot distinguish between these two scenarios.

To understand message flow, you can add:

- Message sent/received counters.
- Time-to-first-message timer.
- Inter-message gap or timestamp of the most recent message.
- Backpressure/ready state if the application needs to observe flow control.
- Stream age and idle time without messages.

Do not update the active gauge on every message. A stream sending 1,000 messages is still one active stream. For bidirectional streams, messages in each direction can be counted in two separate metrics.

## 9. Querying Active Streams and Stream Duration in Prometheus

The Micrometer Prometheus registry may normalize the gauge name to `grpc_server_active_streams` and the `Timer` histogram to `grpc_server_stream_duration_seconds_bucket`. Actual names depend on the registry/exporter; check the scrape endpoint before using them.

Total active streams by service/method:

~~~promql
sum by (service, method, rpc_type) (
  grpc_server_active_streams
)
~~~

Stream duration p95 over 15 minutes:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, service, method, rpc_type) (
    rate(grpc_server_stream_duration_seconds_bucket[15m])
  )
)
~~~

Peak active streams over 10 minutes:

~~~promql
max_over_time(grpc_server_active_streams[10m])
~~~

`LongTaskTimer` exports series with different names than standard `Gauge`/`Timer`; query using the actual names produced by the exporter. Do not assume all registries name them identically.

Duration histograms only contain streams that terminated within the observation window. A stream open for 2 hours that has not closed does not contribute a duration sample until it terminates. Therefore, do not use p95 duration alone to conclude there are no hung streams.

## 10. Alerting on Stream Age and Count

A high active stream count is not automatically an incident. A subscription service may be designed to hold thousands of streams. Establish baselines and capacity:

| Signal | Possible Indication | How to Evaluate |
| --- | --- | --- |
| Active streams spike rapidly | Client reconnect storm or many new subscribers. | Compare connect rate, disconnect rate, and deployment events. |
| Sustained high active streams | Heavy background load or streams not being cleaned up. | Compare against capacity, memory, workers, and hourly baselines. |
| Stream age p95 increases | Older streams lasting longer than expected. | Distinguish long-lived subscriptions from stuck calls. |
| Active drops suddenly | Server restart, network event, or mass client disconnect. | Cross-reference status, instance health, and rollouts. |
| Message gap increases while active stays steady | Producer/dependency stopped emitting messages. | Check upstream event rate and backpressure. |

You can alert when active streams exceed a threshold for a duration, or when stream age exceeds the method's policy. Use separate thresholds by `service`/`method`/`rpc_type`; a valid bidirectional session can last much longer than a server-streaming query.

## 11. Cardinality and Metrics Cost

Active gauges and duration histograms create series per label combination. Use finite values:

- `service`: full Protobuf service name.
- `method`: method name.
- `rpc_type`: `client_streaming`, `server_streaming`, or `bidi_streaming`.
- `status`: only on the post-terminal duration `Timer`.
- `instance`/`zone`: only when cardinality budget allows and locality investigation is needed.

Do not attach stream ID, user ID, account ID, tenant ID, request ID, or trace ID to metric labels. Every new stream ID can create a new series, causing cardinality to grow with session count. Use tracing/logging to follow individual streams; metrics only aggregate by method and controlled dimensions.

A `Gauge` must have a stable meter identity per label group; do not create a new `Gauge` for each stream. If you register a gauge with an object that only lives for the call scope, the registry may not keep a strong reference and the value can vanish. Use a map holding `AtomicInteger` instances per method, or use `LongTaskTimer` with per-task lifecycle samples.

## 12. Testing Active Count and Duration

Tests should control stream open and close timing using latches/barriers, avoiding `Thread.sleep` to guess lifecycle state:

1. Open a server-streaming RPC and wait for the server to confirm the handler started; the active gauge must increase by one.
2. Keep the stream unfinished; verify the active gauge remains one and the completed duration `Timer` has no sample yet.
3. Close the stream normally; verify the active gauge returns to zero and the duration `Timer` count increments by exactly one.
4. Cancel the stream from the client; verify active decrements by one and duration is recorded once with the appropriate server-side status.
5. Let a deadline expire; verify cleanup runs and active count is not leaked.
6. Send multiple messages in the same stream; verify active count does not change per message.
7. Open multiple streams on the same method; verify the gauge equals the number of active streams and returns to zero after all terminate.
8. Invoke a unary method; verify it does not increment the active stream gauge.
9. Create a long-lived unclosed stream; verify `LongTaskTimer`/active age observes the still-active task.

Use `SimpleMeterRegistry` to check gauges and `Timer` in unit/in-process tests. Integration tests over TCP/TLS additionally verify real disconnects and cleanup when transport is interrupted. All latches must have timeouts and be released in teardown so failed tests do not hang workers.

## 13. Common Pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Active streams drop on client half-close | Treating half-close as terminal for the entire RPC. | Decrement only when the server calls close or receives onCancel. |
| Gauge rises and never drops | Missing cancellation, exception, or terminal path. | Centralize cleanup in an idempotent function and test all terminal paths. |
| Active count goes negative or decrements twice | Both onCancel and close decrement. | Use an AtomicBoolean guard per call. |
| Long streams do not appear in duration histogram | Timer only records when sample stops. | Use an active gauge or LongTaskTimer to track open streams. |
| Dashboard treats long stream lifetime as bad latency | Mixing unary latency with stream lifetime. | Separate metrics and SLOs by rpc_type. |
| One multi-message stream inflates active count | Counting messages instead of calls. | Increment active once on start and decrement once on terminal. |
| Gauge disappears or is always zero | Gauge holds a weak reference to an object that was garbage-collected. | Keep strong references in a registry map or use LongTaskTimer. |
| Cardinality grows with subscribers | Attaching stream ID/user ID to labels. | Use only service, method, and rpc_type; put details in traces. |

## 14. Hands-On Exercises

1. Write a `ServerInterceptor` that tracks only the three streaming RPC types, excluding unary from the active stream gauge.
2. Register a `Gauge` by `service`/`method`/`rpc_type` and hold counter objects in a map with a clear lifecycle.
3. Record stream duration with a Micrometer `Timer` when `ServerCall` closes or the call is cancelled.
4. Use `AtomicBoolean` to guarantee active count decrements and `Timer` records once when `onCancel`/`close` race.
5. Add a `LongTaskTimer` to observe streams staying open longer than an expected threshold.
6. Write tests for complete, error, explicit cancel, deadline expiry, client half-close, and multiple messages.
7. Build a PromQL dashboard for active streams, stream duration p95, and peak active count over 10 minutes.
8. Audit label cardinality and verify stream ID/user ID do not appear in metrics.

After this lesson, you should be able to distinguish currently active streams from the duration of finished streams, count only the three streaming RPC types, and ensure each call increments/decrements the active count exactly once. Combining active gauges, `Timer` histograms, `LongTaskTimer`, and message-level metrics helps operations teams detect hung streams, abnormal reconnects, or long-held resources in a Spring gRPC system.
