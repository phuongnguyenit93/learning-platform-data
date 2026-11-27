# Monitoring cancelled RPCs

## 1. Why monitor cancellation?

In **Spring gRPC**, an RPC can terminate because the server returns a result, emits an error, the deadline expires, or the caller actively cancels. For short unary RPCs, cancellation may draw little attention. For server-streaming, client-streaming, or bidirectional streaming, cancellation is also the signal to stop queries, release subscriptions, stop emitting messages, and return resources to pools.

If you only log when an RPC completes, the system struggles to answer operational questions:

- How many RPCs were cancelled by callers?
- How many RPCs terminated due to deadlines?
- Did the server receive the cancellation and stop its work?
- After the client cancels, how long do database queries or broker subscriptions keep running?
- Did a spike in cancellations originate from clients, configured timeouts, or network errors?

Monitoring cancellation requires distinguishing three milestones:

1. **Cancel requested:** the client or reactive subscriber requests cancellation.
2. **Cancel observed:** the gRPC server/runtime observes that the call has been cancelled.
3. **Cleanup completed:** call-dependent work has stopped and resources have been released.

These three milestones can occur at different times. Recording them separately helps detect cases where the client has left while the server continues working.

## 2. How does cancellation differ from deadline and RPC errors?

Cancellation is a signal terminating a call before normal processing completes. A deadline is the time limit of a logical RPC; when the deadline expires, the runtime cancels the call and the caller typically receives status DEADLINE_EXCEEDED. A caller that actively cancels typically sees status CANCELLED.

| Situation | Caller typically observes | Server can observe | Interpretation |
| --- | --- | --- | --- |
| Caller actively cancels call | CANCELLED | Cancellation signal | Caller no longer needs the result |
| Reactor subscriber disposes/cancels | CANCELLED if bridge propagates signal properly | Cancellation signal | Pipeline has stopped caring |
| Deadline expires | DEADLINE_EXCEEDED | Call is cancelled | Time budget exhausted |
| Connection dropped | May be CANCELLED, UNAVAILABLE, or transport error depending on timing | Context/call may be cancelled | Not necessarily a user action |
| Server actively returns error CANCELLED | CANCELLED | Server knows it closed the call itself | Does not mean the client requested cancellation |
| Server returns another business error | Corresponding status | Server terminates normally with an error | Not caller-initiated cancellation |

Do not infer the cause from a status alone. A server-side cancellation handler indicates that the call was cancelled, but does not necessarily tell whether the user clicked cancel, the deadline expired, or the transport was lost. To classify the cause, combine data from the client, deadline, and gateway.

## 3. Monitoring cancellation on the server

In gRPC Java, two APIs are useful:

- **ServerCallStreamObserver.setOnCancelHandler():** registers a callback when the call is cancelled.
- **ServerCallStreamObserver.isCancelled():** checks call status before continuing to emit responses.

For work tied to gRPC Context, you can register a Context cancellation listener to propagate the stop signal to context-dependent tasks. The handler should be registered early, before starting resource-intensive work.

Example of a server-streaming service with a subscription to an event source:

~~~java
import io.grpc.Status;
import io.grpc.stub.ServerCallStreamObserver;
import io.grpc.stub.StreamObserver;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;
import org.springframework.stereotype.Service;
import reactor.core.Disposable;
import reactor.core.publisher.Flux;

@Service
public class OrderWatchGrpcService
        extends OrderWatchGrpc.OrderWatchImplBase {

    private final OrderEventSource eventSource;
    private final CancellationMetrics metrics;

    public OrderWatchGrpcService(
            OrderEventSource eventSource,
            CancellationMetrics metrics) {
        this.eventSource = eventSource;
        this.metrics = metrics;
    }

    @Override
    public void watch(
            WatchRequest request,
            StreamObserver<OrderEvent> responseObserver) {

        ServerCallStreamObserver<OrderEvent> call =
                (ServerCallStreamObserver<OrderEvent>) responseObserver;
        AtomicBoolean terminated = new AtomicBoolean();
        AtomicReference<Disposable> subscriptionRef =
                new AtomicReference<>();
        AtomicBoolean cancelObserved = new AtomicBoolean();
        AtomicBoolean cleanupSignalSent = new AtomicBoolean();
        Object signalLock = new Object();

        Runnable disposeSubscription = () -> {
            Disposable subscription = subscriptionRef.get();
            if (subscription != null
                    && cleanupSignalSent.compareAndSet(false, true)) {
                subscription.dispose();
                metrics.recordCleanupRequested(
                        "orders.v1.OrderWatch/Watch");
            }
        };

        call.setOnCancelHandler(() -> {
            synchronized (signalLock) {
                if (!terminated.compareAndSet(false, true)) {
                    return;
                }
                cancelObserved.set(true);
                metrics.recordServerCancellation(
                        "orders.v1.OrderWatch/Watch");
            }
            disposeSubscription.run();
        });

        if (terminated.get() || call.isCancelled()) {
            return;
        }
        Flux<OrderEvent> events = Flux.defer(
                () -> eventSource.watch(request));
        Disposable subscription = events.subscribe(
                event -> {
                    synchronized (signalLock) {
                        if (terminated.get() || call.isCancelled()) {
                            return;
                        }
                        call.onNext(event);
                    }
                },
                error -> {
                    synchronized (signalLock) {
                        if (terminated.compareAndSet(false, true)) {
                            call.onError(Status.INTERNAL
                                    .withDescription("Event stream failed")
                                    .withCause(error)
                                    .asRuntimeException());
                        }
                    }
                },
                () -> {
                    synchronized (signalLock) {
                        if (terminated.compareAndSet(false, true)) {
                            call.onCompleted();
                        }
                    }
                });

        subscriptionRef.set(subscription);
        // Cancellation/completion may occur synchronously before subscribe returns.
        if (cancelObserved.get() || call.isCancelled()) {
            disposeSubscription.run();
        }
    }
}
~~~

The example illustrates important points:

- Register the cancel handler before subscribing to the event source.
- Use a terminal flag so cancellation, error, and completion do not terminate the call multiple times.
- Retain the subscription handle to dispose of it when the call is cancelled.
- Check cancellation before emitting messages.
- Handle the race when the stream terminates or is cancelled before subscribe returns the handle.
- Synchronize response writes because StreamObserver must not be called concurrently from multiple threads.

Types like OrderEventSource, CancellationMetrics, and generated services belong to the application. In production, ensure the event source emits callbacks sequentially or serialize them before calling the observer; disposing the subscription must be safe when called multiple times.

In the example, `dispose()` and the `cleanup requested` metric only confirm that the stop signal has been sent. If the broker/database needs to close resources asynchronously, record `cleanup completed` when receiving the actual acknowledgment or completion signal from the resource owner; do not measure the time of calling dispose as if resources were already guaranteed to be released.

## 4. Using gRPC Context for RPC-dependent work

gRPC Context carries information bound to the call lifecycle, including deadline and cancellation. When an RPC is cancelled, the associated Context can transition to the cancelled state. A Context-dependent task can register a listener:

~~~java
import io.grpc.Context;
import java.util.concurrent.Executor;

Context rpcContext = Context.current();
Context.CancellationListener listener =
        cancelledContext -> stopDependentWork();

Executor directExecutor = Runnable::run;
rpcContext.addListener(listener, directExecutor);
~~~

Register the listener while handling the RPC to obtain the right Context for the call. The listener may be invoked on the specified executor; therefore, the callback should be short and not perform lengthy blocking cleanup directly on the callback thread. It can signal the task owner or scheduler to stop the work.

If the task runs on a separate executor, pass the Context/cancellation token explicitly or use an executor with Context propagation. Do not assume every thread created by the application automatically carries the current Context.

If the task finishes normally before Context is cancelled, remove the listener with `rpcContext.removeListener(listener)` so unnecessary references are not retained. Even if the listener only lives for a short RPC, you should still manage registration lifecycle explicitly.

For downstream gRPC calls, keep the parent operation's deadline and cancellation within the appropriate scope. If creating a new call after the parent has been cancelled, check state and avoid starting futile work.

## 5. Monitoring cancellation on the client

The client is where you know best whether the caller actively cancelled. Record intent at the point where cancellation is invoked:

- User leaves the screen or cancels the action.
- Reactive subscriber calls dispose/cancel.
- A new request supersedes an old request.
- Application closes or stops a subscription.

Example with Reactor:

~~~java
Mono<GetOrderResponse> result = orderClient.getOrderReactive(request)
        .doOnCancel(() ->
                cancellationMetrics.recordClientCancelRequested(
                        "orders.v1.OrderService/GetOrder"));
~~~

The underlying bridge must wire Mono cancellation to the Future or gRPC ClientCall. If you only record a metric in doOnCancel while the bridge fails to cancel the real call, client metrics will report cancellation while the RPC keeps running.

With a future stub, record where the application calls future.cancel(...). With an async stub, record where the application calls ClientCallStreamObserver.cancel(...). Do not classify every CANCELLED terminal status as user cancellation: cancellation can originate from a deadline, parent call, or transport.

## 6. Distinguishing cancel requested, observed, and completed

A clear event model helps avoid double counting:

| Event | Where recorded | Meaning |
| --- | --- | --- |
| client.cancel.requested | Client application/bridge | Caller or pipeline requested stop |
| server.cancel.observed | Server cancellation handler/Context | Server observed the call was cancelled |
| server.cleanup.started | Service/resource owner | Started cleaning up resources |
| server.cleanup.completed | Service/resource owner | Subscription/task/resource stopped |
| rpc.closed | Client/server instrumentation | Call reached a terminal status |

Not every cancelled RPC will emit every event. The client may lose connectivity before telemetry is sent; the server process may be killed before cleanup; or the call may finish right before cancellation arrives.

When measuring cleanup duration, use a monotonic clock or telemetry Timer; do not subtract wall-clock timestamps, which are vulnerable to system clock synchronization adjustments.

## 7. Appropriate metrics and labels

An application metric set might include:

| Metric | Type | Purpose |
| --- | --- | --- |
| app.grpc.server.rpc.started | Counter | Server started processing RPC |
| app.grpc.server.rpc.completed | Counter | RPC finished, tagged with final status |
| app.grpc.server.rpc.cancel.observed | Counter | Server observed cancellation |
| app.grpc.server.rpc.cleanup.duration | Histogram | Time from receiving cancel until cleanup completed |
| app.grpc.client.rpc.cancel.requested | Counter | Client actively requested cancellation |
| app.grpc.client.rpc.completed | Counter | Client received terminal status |
| app.grpc.server.rpc.active | Gauge | Number of active RPCs |

These are application-defined metric names, not mandatory OpenTelemetry names. If gRPC/OpenTelemetry instrumentation already provides RPC started, duration, or status metrics, reuse the standard metrics and only add custom metrics for cancellation/cleanup that instrumentation does not yet measure.

Metric labels should have low cardinality:

- RPC service/method.
- gRPC status.
- Identified cancellation source: caller, deadline, or server policy.
- Type of resource cleaned up: subscription, task, or stream.

Do not use request ID, trace ID, user ID, tenant ID, or order ID as metric labels. Those values are better suited for controlled logs/traces.

## 8. Statuses and cancellation causes

When the client receives a terminal status, it can usually be categorized as:

| Final status | Common interpretation | Recording |
| --- | --- | --- |
| CANCELLED | Call was cancelled before completion | Cancellation outcome |
| DEADLINE_EXCEEDED | Call deadline expired | Timeout outcome; server may also receive cancellation |
| UNAVAILABLE | Transport or service unavailable | Availability failure; do not automatically treat as user cancel |
| OK | RPC completed successfully | Normal completion |
| INTERNAL/UNKNOWN | Execution error or unclassified failure | Error outcome |

Server cancellation handlers usually do not carry a cause parameter. If the server only knows the call was cancelled, record source as server_observed or unknown. Only tag source=deadline when there is evidence the deadline expired; only tag source=caller when the client sends reliable information from the call site.

Do not rely on client-self-reported metadata as security proof of the cause. Metadata can be helpful for correlation, but it does not replace the cancellation state observed by the runtime.

## 9. Logs and traces for investigation

Structured logs should contain:

~~~json
{
  "event": "grpc.server.cancel.observed",
  "rpc.method": "orders.v1.OrderWatch/Watch",
  "grpc.status": "CANCELLED",
  "cancel.source": "server_observed_unknown",
  "rpc.elapsed_ms": 840,
  "cleanup.duration_ms": 12,
  "trace_id": "trace-id",
  "rpc_id": "logical-call-id"
}
~~~

Traces can mark the RPC span with a cancelled state or the corresponding status, while adding events:

- cancellation observed;
- cleanup started;
- cleanup completed;
- deadline remaining at the time the signal was received, if any.

Do not log payloads or sensitive data in cancellation events. Keep the same trace/correlation ID across client, gateway, and server to identify where cancellation started and when it reached the server.

With retries, distinguish a logical call from each server attempt. A logical call may spawn multiple attempts; cancellation of one attempt does not necessarily mean the entire user operation was cancelled. Name metrics and spans according to the exact scope being measured.

## 10. Testing cancellation

Use an in-process gRPC server/channel or a test server capable of controlling streams and verifying cleanup:

| Scenario | What to verify |
| --- | --- |
| Client calls cancel on async call | Server cancellation handler is invoked |
| Reactor subscriber disposes | Bridge cancels gRPC call, server observes cancellation |
| Deadline expires | Client receives DEADLINE_EXCEEDED; server stops call-dependent work |
| Client cancels before resource handle is created | When the handle appears, the resource is closed immediately |
| Cancel concurrent with onNext | No response emitted after terminal state |
| RPC completes normally | No spurious cancellation event recorded |
| Server cleanup invoked from multiple paths | Cleanup is idempotent, records completion only once |
| Network disconnect | Server stops task when runtime detects call is no longer active |
| Client cancels after DB commit | Do not assume the transaction rolled back |

Tests should use latch/await with a timeout to verify the subscription disposed or the task stopped. Avoid fixed sleeps because they create flaky tests. Separately measure the time from cancel observed to cleanup completed to detect resource leaks.

## 11. Common mistakes

1. **Looking only at status CANCELLED.** You cannot tell whether cancellation came from caller, deadline, or transport without telemetry at the source.
2. **Treating DEADLINE_EXCEEDED as unrelated to cancellation.** The server usually still needs to stop work when the deadline expires.
3. **Registering the onCancel handler too late.** Work may already be running and resources created before a cleanup hook exists.
4. **Non-idempotent cleanup.** Context listener and onCancel handler may both request resource cleanup.
5. **Assuming cancellation rolls back the database.** Committed transactions are not reversed automatically.
6. **Letting background tasks continue after the RPC ends.** Tasks must be bound to the call lifecycle or have a dedicated ownership mechanism.
7. **Calling blocking cleanup on the callback thread.** Can delay handling of other cancellations.
8. **Counting one cancellation multiple times.** Use a terminal guard to record once per server call.
9. **Putting unique IDs into metric labels.** Creates high cardinality and overloads the monitoring backend.

## 12. Hands-on exercises

With the server-streaming RPC Watch:

1. Register ServerCallStreamObserver.setOnCancelHandler before creating the subscription.
2. Use a terminal guard to handle cancellation, error, and completion exactly once.
3. Measure cancel requested on the client and cancel observed on the server.
4. Simulate Reactor dispose and deadline expiry; compare client status with the signal received by the server.
5. Measure cleanup duration from cancellation until the subscription actually closes.
6. Simulate a cancel race with onNext and verify no messages are emitted after terminal state.
7. Simulate cancellation after the server commits data; verify committed data is not mistaken for a rollback.

**Completion criteria:** learners can distinguish cancel requested, cancel observed, and cleanup completed; properly monitor status/deadlines; release server-side resources; design metrics, logs, and traces with sensible cardinality; and test cancellation races and cleanup.

### References

- [gRPC Cancellation](https://grpc.io/docs/guides/cancellation/): cancellation and how servers/clients react.
- [gRPC Deadlines](https://grpc.io/docs/guides/deadlines/): deadlines and cancelling RPCs on expiration.
- [gRPC Java ServerCallStreamObserver API](https://grpc.github.io/grpc-java/javadoc/io/grpc/stub/ServerCallStreamObserver.html): on-cancel handler and server-side call state.
- [gRPC Java Context API](https://grpc.github.io/grpc-java/javadoc/io/grpc/Context.html): cancellation context and listeners.
- [OpenTelemetry](https://opentelemetry.io/): metrics, traces, and logs for system observability.
- [Spring gRPC Reference](https://docs.spring.io/spring-grpc/reference/): integrating gRPC client/server in Spring.
