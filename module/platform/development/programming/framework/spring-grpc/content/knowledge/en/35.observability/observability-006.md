# Deadline Exceeded and Cancellation

Deadlines and cancellations can both terminate an RPC before the caller receives the expected result, but they describe two different signals. A deadline sets a time limit on the call; cancellation signals that the call no longer needs to continue. When a deadline expires, gRPC cancels the call and the client usually receives the `DEADLINE_EXCEEDED` status. When the caller explicitly cancels, the client usually receives `CANCELLED`. On the server, both cases can appear as a cancellation signal on the context or listener.

**Deadline exceeded and cancellation** in observability means tracking the count of calls that exceed their deadline, the count of cancelled calls, when the signal reaches the server, and how long work takes to actually stop and clean up. This lesson belongs to the **Observability** chapter of the **SPRING_GRPC** module: developing gRPC services in the Spring ecosystem using Protocol Buffers contracts, generating Java code, and implementing client/server for unary or streaming RPCs; learners work with metadata, deadlines, statuses, interceptors, TLS, integration testing, and monitoring performance and reliability. The focus is on not confusing client status with server cancellation signals, accurately measuring terminal events, and tracing deadlines through downstream chains.

## 1. Deadlines and Cancellations Differ in Purpose

- **Deadline** is the absolute point in time beyond which the RPC is no longer allowed to continue waiting for a result. The client sets a deadline or timeout; gRPC computes remaining time as the call runs.
- **Cancellation** is the signal to terminate a call early because the caller is no longer interested, a parent call was cancelled, a deadline expired, or transport became unavailable.
- **DEADLINE_EXCEEDED** is the status the client typically observes when the RPC's deadline expires before completion.
- **CANCELLED** is the status the client typically observes when the call is explicitly cancelled or a parent context is cancelled before the deadline ends.

A deadline can trigger cancellation. Thus, deadline expiry and cancellation have a causal relationship but are not synonymous. A call can be cancelled before its deadline; a call with a deadline that completes normally will not be cancelled.

For example:

| Scenario | Client Typically Sees | Server May Observe |
| --- | --- | --- |
| Client explicitly cancels before deadline | CANCELLED | Context cancelled, listener receives onCancel. |
| Deadline expires before server finishes | DEADLINE_EXCEEDED | Context cancelled, listener receives onCancel. |
| Parent RPC cancelled while child RPC is running | Parent and child usually end with CANCELLED on their respective clients | Child server receives cancellation signal. |
| Connection drops while call is running | Usually UNAVAILABLE or transport error depending on situation | Server may receive cancellation/disconnect if detected. |
| RPC completes before deadline | OK or business status | Server closes call normally. |

Do not infer the cause solely from a server-side `CANCELLED` metric. The server knows the call was cancelled, but does not always know whether the caller explicitly cancelled, the deadline just expired, or the transport disconnected.

## 2. Client Status and Server Signal Are Two Perspectives

On the client, the terminal callback `onClose` receives the final status observed by the caller. This is a reliable source for counting `DEADLINE_EXCEEDED` and `CANCELLED` according to the client's true status.

On the server, two points are commonly used to detect call cancellation:

- `ServerCall.Listener.onCancel()`: transport notifies that the peer cancelled or the call is no longer active.
- `Context.CancellationListener`: the RPC's context is cancelled; suitable for notifying running asynchronous work.

These two server callbacks are not two independent cancellations. Choose one boundary as the primary metric source per RPC; you can use the other listener to stop workers, but avoid counting the same call twice.

When `onCancel` occurs, you can inspect the `Context` deadline to see whether the deadline has already expired at the time of observation. This is only an analytical aid, not definitive proof of cause: an explicit cancel may arrive right as the deadline expires, and a transport disconnect may occur simultaneously. Use a label such as `deadline_expired_at_observation` rather than attaching a definitive cause label.

## 3. Why Track Both Count and Ratio?

A counter shows total calls ending with a status; rate shows how fast it occurs over a window; error ratio places errors alongside total calls. Three views answer different questions:

| Metric | Question |
| --- | --- |
| Deadline exceeded count | How many calls exceeded their deadline? |
| Deadline exceeded rate | Over the last few minutes, how fast is this error appearing? |
| Deadline exceeded ratio | What percentage of the method's calls exceeded their deadline? |
| Client cancelled count | How many calls were cancelled by callers? |
| Server cancellation observed | How many cancellation signals did the server receive? |
| Cancellation cleanup duration | After a cancel signal, how long does the server take to stop work and clean up? |

Do not merge `DEADLINE_EXCEEDED`, `CANCELLED`, and `UNAVAILABLE` into a generic `timeout` counter. `UNAVAILABLE` usually relates to availability/transport; `CANCELLED` relates to call lifecycle; `DEADLINE_EXCEEDED` indicates the time budget ran out.

## 4. Defining Metrics by Boundary

A metric set you can use:

~~~text
grpc.client.calls
  type: Counter
  tags: service, method, status

grpc.server.calls.cancel.observed
  type: Counter
  tags: service, method, deadline_expired_at_observation

grpc.server.cancel.cleanup.duration
  type: Timer
  tags: service, method

grpc.server.calls.inflight
  type: Gauge
  tags: service, method
~~~

The client counter counts terminal statuses received by the client. The server cancellation counter counts signals observed by the server; it is not an exact mirror of client `CANCELLED`/`DEADLINE_EXCEEDED`. The cleanup `Timer` measures from when the server receives cancellation until work belonging to the RPC has stopped and resources are released. The in-flight gauge helps spot calls still held after callers have left.

Labels should have a finite value set:

- `service`: full Protobuf service name.
- `method`: method name.
- `status`: one of the gRPC status codes.
- `deadline_expired_at_observation`: `true`/`false`/`unknown` if genuinely needed for analysis.

Do not put request ID, trace ID, user ID, deadline timestamp, exception message, or arbitrary metadata into labels. Such detailed data belongs in traces/logs.

## 5. Counting Terminal Status on the Client

`ClientInterceptor` can count statuses when the listener receives `onClose`. Example using a Micrometer `Counter`:

~~~java
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

public final class DeadlineStatusClientInterceptor
        implements ClientInterceptor {

    private final MeterRegistry registry;

    public DeadlineStatusClientInterceptor(MeterRegistry registry) {
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
                Listener<RespT> monitored =
                        new ForwardingClientCallListener
                                .SimpleForwardingClientCallListener<>(
                                        responseListener) {
                            @Override
                            public void onClose(
                                    Status status,
                                    Metadata trailers) {
                                registry.counter(
                                        "grpc.client.calls",
                                        "service", service,
                                        "method", methodName,
                                        "status", status.getCode().name()
                                ).increment();
                                super.onClose(status, trailers);
                            }
                        };
                super.start(monitored, headers);
            }
        };
    }
}
~~~

`onClose` is the terminal callback of `ClientCall`; the interceptor counts here so each logical call has one final status at this observation boundary. Depending on whether instrumentation sits inside or outside the retry layer, semantics may be a logical call or an attempt. Verify interceptor placement and retry implementation before calling this metric an attempt count.

Attach the interceptor to the channel via `ManagedChannelBuilder.intercept` or the extension point provided by the Spring gRPC starter. If the starter manages the channel, do not create a second channel just to attach metrics.

## 6. Observing Cancellation on the Server

`ServerInterceptor` can count the `onCancel` signal and check the context deadline at that moment:

~~~java
import io.grpc.Context;
import io.grpc.Deadline;
import io.grpc.ForwardingServerCallListener;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.micrometer.core.instrument.MeterRegistry;

import java.util.concurrent.TimeUnit;

public final class ServerCancellationMetricsInterceptor
        implements ServerInterceptor {

    private final MeterRegistry registry;

    public ServerCancellationMetricsInterceptor(
            MeterRegistry registry) {
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

        Context rpcContext = Context.current();
        Deadline deadline = rpcContext.getDeadline();

        ServerCall.Listener<ReqT> listener =
                next.startCall(call, headers);

        return new ForwardingServerCallListener
                .SimpleForwardingServerCallListener<>(listener) {
            @Override
            public void onCancel() {
                boolean expired = deadline != null
                        && deadline.isExpired();
                registry.counter(
                        "grpc.server.calls.cancel.observed",
                        "service", service,
                        "method", method,
                        "deadline_expired_at_observation",
                        deadline == null ? "unknown"
                                : Boolean.toString(expired)
                ).increment();
                super.onCancel();
            }
        };
    }
}
~~~

This metric is named `cancel.observed` to accurately represent what the server knows. The `deadline_expired_at_observation` tag only describes the state of the `Deadline` at callback time; do not turn it into an absolute `source=deadline`. If you need more precise root-cause classification, cross-reference client status or traces.

The interceptor must be registered with the server managed by the Spring gRPC starter. If the application already has a centralized interceptor counting terminal statuses, integrate the cancellation callback into the same lifecycle recorder to avoid having two metrics both interpreted as a total cancellation count.

## 7. Stopping Asynchronous Work When an RPC Is Cancelled

Receiving a cancellation signal does not automatically stop all work created by the application. A database query, executor task, message subscription, or downstream RPC may continue running if the handler does not propagate the signal to it.

In the handler, register a `Context.CancellationListener` and clean up resources:

~~~java
Context rpcContext = Context.current();
AtomicBoolean stopped = new AtomicBoolean();

Context.CancellationListener cancellationListener = ignored -> {
    if (stopped.compareAndSet(false, true)) {
        worker.cancel(true);
        downstreamCall.cancel(
                "Parent RPC cancelled",
                null);
    }
};

rpcContext.addListener(cancellationListener, Runnable::run);

try {
    startWork();
} finally {
    rpcContext.removeListener(cancellationListener);
    cleanupResources();
}
~~~

This is an illustrative skeleton; `worker` and `downstreamCall` must be created, stored, and lifecycle-managed before the listener can use them. In real code, guard against the race where cancellation arrives before the handle is assigned: record a `cancelled` flag, then cancel the handle immediately once it appears. Cleanup must be idempotent because multiple terminal paths can race.

For blocking operations, interrupting only works if the API and code actually respond to interruption. JDBC drivers, native calls, or third-party libraries may not stop immediately. Use the resource's dedicated cancel/close API if available, set timeouts on dependencies, and verify the worker has exited before considering cleanup complete.

## 8. Propagating Remaining Deadline to Downstream RPCs

A request often traverses multiple services. If each service sets a new timeout equal to the full initial timeout, total chain duration can exceed the caller's budget. Downstream calls should use the remaining deadline:

~~~java
Deadline parentDeadline = Context.current().getDeadline();
if (parentDeadline == null) {
    return inventoryStub.getStock(request);
}

long remainingNanos =
        parentDeadline.timeRemaining(TimeUnit.NANOSECONDS);

if (remainingNanos <= 0) {
    throw Status.DEADLINE_EXCEEDED
            .withDescription("Parent RPC deadline exceeded")
            .asRuntimeException();
}

return inventoryStub
        .withDeadlineAfter(remainingNanos, TimeUnit.NANOSECONDS)
        .getStock(request);
~~~

gRPC Java has built-in `Context`/deadline propagation for compatible calls, but when spawning background tasks, switching executors, or explicitly constructing independent calls, verify that the current context is propagated and the deadline is preserved. Do not reset a full timeout at each hop. If you need to reserve time for final aggregation/response steps, subtract that buffer budget before calling downstream.

When the parent's deadline expires, running child RPCs must receive cancellation. Test both deadline propagation and child cleanup; checking only that the parent client receives `DEADLINE_EXCEEDED` does not prove downstream work stopped.

## 9. Prometheus: Deadline Exceeded and Cancellation Rates

Suppose Micrometer Counter `grpc.client.calls` is exported as `grpc_client_calls_total`:

~~~promql
# Client deadline exceeded per second by service/method.
sum by (service, method) (
  rate(grpc_client_calls_total{status="DEADLINE_EXCEEDED"}[5m])
)
~~~

Client cancelled per second:

~~~promql
sum by (service, method) (
  rate(grpc_client_calls_total{status="CANCELLED"}[5m])
)
~~~

Ratio of deadline exceeded to total calls:

~~~promql
sum by (service, method) (
  rate(grpc_client_calls_total{status="DEADLINE_EXCEEDED"}[5m])
)
/
sum by (service, method) (
  rate(grpc_client_calls_total[5m])
)
~~~

Rate of cancellation signals observed by the server:

~~~promql
sum by (service, method) (
  rate(grpc_server_calls_cancel_observed_total[5m])
)
~~~

Final metric/label names depend on the registry and exporter; verify the scrape endpoint before using queries. Server cancellation observed should not be divided by client `CANCELLED` and treated as an exact reconciliation ratio, because server signals can include deadline expirations and transport disconnects.

When the denominator is 0, dashboards should display "no traffic". Alerts should combine ratio with a minimum call volume to avoid paging from a handful of requests.

## 10. Measuring Cleanup Duration After Cancellation

A server may receive cancellation immediately while a worker keeps running for several more seconds. This is a critical interval because the work no longer has value to the caller yet still consumes CPU, threads, connections, or downstream quota.

Measure cleanup duration from when cancellation is observed until:

1. The worker has stopped or confirmed it is no longer processing.
2. Downstream calls have been cancelled/terminated.
3. Subscriptions, cursors, statements, and call-owned resources have been released.
4. The in-flight gauge has decremented.

A `Timer` can record one sample per cancelled call. If you need to monitor ongoing cleanup tasks, use `LongTaskTimer`. Do not stop the timer immediately upon calling `worker.cancel(true)`; wait until the work actually terminates or cleanup meets its completion condition.

## 11. Reading Deadlines/Cancellations Alongside Latency and Status

Signals should be read together:

| Signal | Possibility | Investigation |
| --- | --- | --- |
| DEADLINE_EXCEEDED rises, p99 rises | Service or dependency is slower than the deadline budget. | Latency by method, downstream spans, queues. |
| DEADLINE_EXCEEDED rises, server duration is low | Client budget may have been spent before reaching the server, or client-side network/queue is slow. | Client span, remaining deadline when server starts. |
| CANCELLED rises, DEADLINE_EXCEEDED steady | Callers dropping calls, UI/request lifecycle changed, or parent cancelled. | Client cancellation source, parent traces, and disconnects. |
| Server cancel observed rises without matching client CANCELLED | Deadline expiry or transport disconnects may contribute to server signals. | Client status, deadline expiry at callback, and proxy logs. |
| High cleanup duration | Worker/dependency does not react quickly to cancellation. | Interrupt handling, driver cancel, executor queue, and child RPCs. |
| In-flight does not drop after cancel | Listener/worker/resource is retained or terminal cleanup is missing. | Thread dumps, active tasks, and cleanup paths. |

Do not increase deadlines just to make dashboards green. Deadlines must reflect caller SLOs and the end-to-end chain budget; raising them excessively causes requests to hold resources longer when the system is already degraded.

## 12. Traces and Logs for Root-Cause Analysis

Metrics reveal trends; traces help follow a specific call:

- Record the deadline/timeout configured on the client and remaining time when each service starts processing.
- Create child spans for downstream RPCs showing wait time per dependency.
- Record terminal status on each span, and mark cancellation observed on the server.
- Log when workers start cleanup and when cleanup completes.
- Include trace IDs in logs to link client, parent server, and child services.

Do not put tokens, authorization metadata, sensitive payloads, or full exception descriptions into metrics/logs. Trace sampling must sufficiently cover rare but severe errors; you can prioritize sampling calls with `DEADLINE_EXCEEDED` or cleanup durations exceeding a threshold.

## 13. Testing Deadline Exceeded and Cancellation

Use an in-process gRPC server/channel and latches to control when handlers start, get cancelled, and finish:

1. **Explicit cancel:** client calls cancel while the handler is waiting; client receives `CANCELLED`, server receives the cancellation signal, and the worker stops.
2. **Deadline expiry:** client sets a deadline shorter than handler processing time; client receives `DEADLINE_EXCEEDED`, server receives the cancellation signal, and cleanup completes.
3. **Parent-child propagation:** parent RPC invokes child RPC; cancel or expire the parent's deadline and verify the child receives cancellation.
4. **Deadline budget:** verify downstream receives the remaining time rather than a freshly reissued initial timeout.
5. **Handle creation race:** cancellation arrives before the child call/worker handle is stored; once the handle appears, it must be cancelled immediately.
6. **Cleanup idempotency:** trigger `onCancel` and `close` close together; verify cleanup runs and metrics record only once.
7. **Blocking dependency:** simulate an API that does not respond to interrupts; verify dedicated timeout/cancel APIs and cleanup policy.
8. **Client/server metrics:** compare client `DEADLINE_EXCEEDED` with server `cancellation observed` without assuming they carry the same status label.

Use `CountDownLatch` or barriers instead of `Thread.sleep`. Every latch must have a timeout and be released in teardown so failing tests do not hang workers indefinitely. Add some TCP/TLS tests to verify peer disconnects; in-process transport does not fully simulate network partitions or proxy timeouts.

## 14. Common Pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Merging CANCELLED and DEADLINE_EXCEEDED | Treating all cancellations as timeouts. | Keep client terminal statuses separate; give server signals their own metric. |
| Server cancellation counter treated as explicit user cancel | onCancel does not uniquely identify the cause. | Name it cancel_observed and cross-reference client status/traces. |
| Downstream deadline longer than parent | Each hop grants a full timeout again. | Propagate remaining deadline and reserve budget for final steps. |
| Client timed out while worker keeps running | Application does not propagate cancellation to tasks/resources. | Context listener, cancel APIs, cooperative interruption, and cleanup. |
| Cleanup duration is always tiny | Timer stops right when sending cancel instead of when worker stops. | Record until cleanup actually completes. |
| CANCELLED is double-counted | Both onCancel and Context listener increment the same counter. | Pick one metric boundary or share a lifecycle guard. |
| Retries run past deadline | Retry policy is not bounded by total budget or app retries incorrectly. | Enforce total deadline, bound attempts, and use backoff. |
| Raising timeouts masks slow dependencies | Alerts rely solely on deadline status. | Read deadlines alongside latency histograms and downstream spans. |

## 15. Hands-On Exercises

1. Write a `ClientInterceptor` that counts terminal statuses `DEADLINE_EXCEEDED` and `CANCELLED` by service/method.
2. Write a `ServerInterceptor` that counts cancellation observed, with `deadline_expired_at_observation` valued as `true`/`false`/`unknown`.
3. Create an asynchronous handler; register a `Context.CancellationListener` to cancel the worker and downstream RPCs.
4. Propagate remaining deadline from parent to child RPC and verify the child does not exceed the parent's budget.
5. Measure cancellation cleanup duration from signal receipt until resources are released.
6. Write PromQL queries for deadline rate, cancellation rate, and deadline ratio by method.
7. Test explicit cancel, deadline expiry, parent-child cancellation, and the race when a handle has not yet been created.
8. Build a dashboard combining deadline status, server cancellation observed, p99 latency, in-flight calls, and cleanup duration.

After this lesson, you should be able to distinguish client deadline/cancel statuses from server cancellation signals, propagate remaining deadlines downstream, and verify that workers/resources actually stop. Combining status counters, cleanup duration, latency, and traces helps operations teams detect calls exhausting their time budget as well as work continuing to run after callers have cancelled in a Spring gRPC system.
