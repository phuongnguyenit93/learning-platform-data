# Concurrent Streams

## Learning Objectives

After this lesson, you can:

- Explain concurrent streams and distinguish them from connections, in-flight messages, and total RPC count.
- Distinguish per-connection HTTP/2 limits from admission limits at the server, service, and tenant levels.
- Design limits on active streaming RPCs in Spring gRPC.
- Hold a slot throughout the entire stream lifecycle and release it accurately on completion, error, or cancellation.
- Combine concurrency limits with deadlines, idle timeouts, flow control, and backpressure.
- Choose limits based on memory, CPU, downstream capacity, and tenant fairness.
- Handle overload with appropriate statuses and retries with backoff.
- Test limits, cleanup, and isolation across concurrent streams.

## 1. What are concurrent streams?

In **SPRING_GRPC**, streaming RPCs keep a call open while the client and server exchange multiple messages. The three streaming types are server-streaming, client-streaming, and bidirectional streaming. Each open call holds resources for its entire lifetime: handler state, buffers, subscriptions, callbacks, timers, principal references, and potentially database or broker connections.

**Concurrent streams** are the number of streaming RPCs active at the same time within a defined scope. That scope can be a connection, a server instance, a service, a tenant, or the entire system.

This is a critical limit because a stream can live much longer than a unary RPC. A client opening thousands of idle streams or sending data slowly can hold resources without producing useful throughput. Without limits, one group of callers can exhaust workers, memory, subscriptions, and connection pools, preventing other tenants from opening new streams.

Distinguish between:

- **Concurrent connections:** number of open TCP/TLS connections.
- **Concurrent HTTP/2 streams:** number of active HTTP/2 streams on a single connection.
- **Concurrent gRPC calls:** number of active RPCs; both unary and streaming are RPCs.
- **Concurrent application streams:** number of streaming RPCs the application allows to run.
- **In-flight messages:** number of messages currently being sent, received, or processed.
- **Total messages/bytes:** total volume of data exchanged within a stream.

One HTTP/2 connection can multiplex many streams. Therefore, a low connection count does not mean a low active RPC count; conversely, a single stream can carry very many messages while still being just one RPC.

## 2. Layers of concurrency limits

No single number protects every layer. Place limits at scopes that have distinct meanings:

| Scope | What is limited | Purpose |
| --- | --- | --- |
| HTTP/2 connection | Concurrent streams/calls per connection | Prevent one connection from consuming too many slots |
| Server instance | Active streaming RPCs on an instance | Protect memory, CPU, and local resources |
| Service/method | Streams for a specific API group | Isolate heavy or sensitive workloads |
| Tenant/principal | Streams of one customer or caller | Fairness and preventing noisy neighbors |
| Cluster | Total streams across instances | Protect shared downstreams and system-wide quotas |

A per-connection limit does not replace a server-wide limit. If each connection can open up to 100 calls and the server has 200 connections, the theoretical total call count can still be huge. Similarly, a global limit does not guarantee fairness: one tenant can consume all slots before others.

Good designs typically combine transport caps, global admission, per-tenant quotas, and separate limits for resource-intensive methods.

## 3. HTTP/2 limits and grpc-java transport

HTTP/2 allows multiple streams to run concurrently on one connection. A peer can advertise its concurrent stream limit via SETTINGS_MAX_CONCURRENT_STREAMS. This is an HTTP/2-layer limit scoped per connection.

With grpc-java's Netty transport, the server builder provides an API to limit concurrent calls per connection:

~~~java
import io.grpc.Server;
import io.grpc.netty.shaded.io.grpc.netty.NettyServerBuilder;

Server server = NettyServerBuilder.forPort(9090)
        .maxConcurrentCallsPerConnection(64)
        .build();
~~~

The value 64 is just an example. This API is a per-connection limit and can affect both unary and streaming calls. It is not a total quota across all connections, does not distinguish tenants, and does not replace application-layer admission.

Other transports and grpc-java versions may provide different APIs. Check the actual builder your application uses. In Spring gRPC, the server is usually managed by a starter; configure via the builder customizer/configurer or extension point supported by your starter version. Do not assume all starters share the same property name. Verify configuration with an integration test that starts the application's server.

Transport limits protect the connection layer; the application still needs to limit how many streams can hold subscriptions, buffers, or business resources.

## 4. Global admission control for streaming RPCs

A simple way to limit streaming RPCs on a server instance is to use a Semaphore. When a stream starts, an interceptor tries to acquire a permit. If no permit remains, the server rejects before invoking the handler. The permit is held until the RPC finishes or is canceled.

~~~java
import io.grpc.ForwardingServerCallListener;
import io.grpc.MethodDescriptor;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;
import java.util.concurrent.Semaphore;
import java.util.concurrent.atomic.AtomicBoolean;

public final class StreamingAdmissionInterceptor
        implements ServerInterceptor {

    private final Semaphore permits;

    public StreamingAdmissionInterceptor(int maxConcurrentStreams) {
        if (maxConcurrentStreams <= 0) {
            throw new IllegalArgumentException(
                    "maxConcurrentStreams must be positive");
        }
        this.permits = new Semaphore(maxConcurrentStreams);
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        MethodDescriptor.MethodType type =
                call.getMethodDescriptor().getType();

        boolean streaming =
                type != MethodDescriptor.MethodType.UNARY;

        if (!streaming) {
            return next.startCall(call, headers);
        }

        if (!permits.tryAcquire()) {
            call.close(
                    Status.RESOURCE_EXHAUSTED
                            .withDescription("Concurrent stream limit reached"),
                    new Metadata());
            return new ServerCall.Listener<ReqT>() {};
        }

        AtomicBoolean released = new AtomicBoolean();

        Runnable releasePermit = () -> {
            if (released.compareAndSet(false, true)) {
                permits.release();
            }
        };

        try {
            ServerCall.Listener<ReqT> delegate =
                    next.startCall(call, headers);

            return new ForwardingServerCallListener
                    .SimpleForwardingServerCallListener<ReqT>(delegate) {

                @Override
                public void onComplete() {
                    try {
                        super.onComplete();
                    } finally {
                        releasePermit.run();
                    }
                }

                @Override
                public void onCancel() {
                    try {
                        super.onCancel();
                    } finally {
                        releasePermit.run();
                    }
                }
            };
        } catch (RuntimeException | Error failure) {
            releasePermit.run();
            throw failure;
        }
    }
}
~~~

This example counts only the three streaming RPC types and skips unary. The permit is held for the entire call lifecycle, not only while the interceptor executes. AtomicBoolean ensures release happens only once if terminal callbacks arrive via multiple paths or if an error occurs while initializing the handler.

Place the admission interceptor after authentication and method authorization so unauthenticated or unauthorized callers do not consume stream slots. Exact interceptor ordering depends on how they are registered in grpc-java/Spring starter; verify with an integration test. If you also need to limit unary calls, use a separate admission policy instead of skipping UNARY.

This example is for a single instance. Each replica has its own Semaphore, so total cluster capacity is roughly the sum of permits across replicas. If a cluster-wide quota is needed, you need a shared quota coordinator or explicit budget allocation per instance.

## 5. Per-tenant and per-method limits

A global semaphore protects the instance but does not guarantee fairness. One tenant can open streams until it consumes all permits. For multi-tenant systems, also apply:

- **Per-tenant cap:** limits active streams for a single tenant.
- **Per-principal cap:** prevents one user/service identity from opening too many streams.
- **Per-method cap:** separate limits for methods consuming significant memory or downstream connections.
- **Global cap:** protects total instance resources.

An admission controller can accept the principal and full method name and return a lease:

~~~java
public interface StreamAdmissionController {

    StreamLease tryAcquire(
            String tenantId,
            String subject,
            String fullMethodName);
}

public interface StreamLease extends AutoCloseable {
    @Override
    void close();
}
~~~

A lease represents a granted slot. When the RPC completes, is canceled, or handler initialization fails, close the lease to return the quota. This pattern enables enforcing global and per-tenant limits together without the interceptor needing to know the details of the quota structure.

If storing per-tenant limiters in a ConcurrentHashMap, manage entry lifecycles. Do not create a map that grows unboundedly by tenant ID and never cleans up. You can use a quota service with TTL, a size-bounded cache, or a registry with safe reference counting/eviction. With distributed quotas, handle timeouts, partitions, and lease release when a process crashes.

Do not take a tenant ID from metadata or messages and trust it directly. Tenant scope must be verified from the principal/policy; if a stream allows selecting a tenant, verify membership before requesting that tenant's quota.

## 6. Choosing limits from the resource budget

Do not pick concurrency by choosing an arbitrary number or relying solely on connection counts. Estimate per-stream resources and the remaining instance budget.

Components that typically consume resources:

- Principal, handler state, and objects.
- Inbound/outbound buffers and queued messages.
- Subscriptions to brokers, database change streams, or event sources.
- Downstream connections or cursors.
- Scheduled tasks, heartbeats, and timers.
- Executor tasks and callbacks.
- Response queues, compression buffers, and telemetry state.

A simple estimation model:

\[
N_{\text{memory}} =
\left\lfloor
\frac{M_{\text{budget}}}
{M_{\text{per-stream, peak}}}
\right\rfloor
\]

Where M_budget is the memory genuinely available for streaming after subtracting baseline heap, caches, unary workload, and headroom; M_per-stream,peak is the peak memory measured for one stream under realistic workload.

Final capacity should be the smallest limit across budgets:

\[
N_{\text{safe}} =
\min(N_{\text{memory}}, N_{\text{CPU}},
N_{\text{downstream}}, N_{\text{transport}}, N_{\text{operational}})
\]

This is a planning model, not a formula that replaces load testing. Idle streams and streams processing large payloads can consume vastly different resources. If there are multiple method groups, use separate capacities or weighted admission so heavy streams do not share the exact same budget as lightweight streams.

Measure p95/p99 memory, CPU, queue depth, downstream connection usage, and latency as stream count scales up. Reserve headroom for traffic bursts, reconnects, and administrative operations.

## 7. Long-lived streams need deadlines, idle timeouts, and maximum lifetimes

Limiting concurrent streams is not enough if a stream can live indefinitely. Idle streams can hold permits and subscriptions even when no messages are being exchanged.

Combine:

- **RPC deadline:** limits total call duration per contract.
- **Idle timeout:** terminates streams with no activity within a defined period.
- **Maximum stream lifetime:** forces clients to reopen streams periodically to refresh credentials/policies and rebalance load.
- **Heartbeat:** use only when needed to detect whether the connection/peer is still alive; heartbeats do not replace deadlines.
- **Cancellation:** release work immediately when the client cancels or the server decides to stop.

Do not set overly short deadlines on streams intentionally designed to be long-lived. You can use a controlled maximum lifetime and a cursor/sequence resume mechanism so clients reconnect without data loss.

When a stream has a bounded lifetime, API documentation must specify that clients must reconnect, how to resume, and how to handle the last committed message. Do not silently cut streams without a cursor or retry semantics.

## 8. Flow control differs from stream count limits

Flow control throttles the volume of messages in flight or awaiting processing within a single stream. It does not limit the number of open RPCs.

For example, a client can open 500 streams, each sending only one small message per minute. Flow control does not stop those 500 streams from holding 500 sets of state and subscriptions. Conversely, a single stream can send messages too fast and fill queues if the application does not apply backpressure.

Combine:

| Mechanism | Protects |
| --- | --- |
| Concurrent stream cap | Number of open streaming RPCs |
| Inbound/outbound flow control | Number of messages currently in transit/being received |
| Bounded queue | Number of messages waiting for application processing |
| Message-size limit | Size of each individual message |
| Total bytes/messages quota | Total data of the stream |
| Rate limit | Rate of messages/bytes |
| Deadline/idle timeout | Duration resources are held |

For outbound streaming, ServerCallStreamObserver can provide isReady and an on-ready handler so the producer only emits when the transport is ready. For inbound streaming, manual flow control allows requesting the next messages in a controlled way. Regardless of mechanism, queues must be bounded and cancellation must stop the producer.

## 9. Rejecting when slots are exhausted and client retries

When global or tenant admission runs out of slots, the server can reject new calls with **RESOURCE_EXHAUSTED**. This indicates a quota/resource limit has been reached; do not use PERMISSION_DENIED because the caller does not necessarily lack permissions.

Clients should:

- Retry with bounds using exponential backoff and jitter if the RPC can be safely reopened.
- Respect RetryInfo or retry-after if provided by the API.
- Avoid retrying continuously in a tight loop, which worsens overload.
- Use cursor/sequence to resume streams after reconnecting.
- Use idempotency keys for commands with side effects.
- Distinguish resource exhaustion from UNAVAILABLE, authentication failures, and permission denials.

Not every streaming RPC can be retried from the start. If a client-streaming call has already sent part of the data, opening a new stream can create duplicate records or drop messages. The contract must define checkpoints, sequences, deduplication, and commit semantics.

Admission control can also apply a short wait policy if appropriate, but avoid holding large numbers of pending requests in memory. Rejecting early and letting clients back off is usually easier to manage than unbounded queues.

## 10. Cleanup and releasing permits exactly once

Permits are only useful if returned along every terminal path. Terminal paths to account for:

- Client finishes requests and server finishes responses.
- Client cancels the stream.
- Deadline expires or transport closes the connection.
- Application encounters an error.
- Authorization is revoked.
- Downstream subscription fails.
- Handler fails to initialize after acquiring the permit.

Use a lease with an idempotent close or an AtomicBoolean to prevent double release. Place cleanup in finally or the appropriate terminal callback. When handler setup fails after acquiring, release immediately; otherwise, permits leak and the server gradually rejects all new streams even when no active streams remain.

Do not release the permit merely because the server sent the first response. With streaming, the call stays open until completion/cancellation. Also do not hold the permit past the terminal event while performing slow cleanup work; release the admission slot before or after cleanup according to the definition of the bounded resource, but stay consistent and never let cleanup run indefinitely.

## 11. Observing concurrent streams

Monitor metrics per instance, service/method, and tenant at appropriate cardinality:

- Current active streaming RPCs.
- Stream admission successes/rejections.
- Remaining permits and admission wait time, if any.
- Active stream duration p50/p95/p99.
- Streams ending by status: OK, CANCELLED, DEADLINE_EXCEEDED, RESOURCE_EXHAUSTED.
- Streams by method type: server, client, or bidi.
- Streams by tenant tier/quota group.
- Buffer/queue depth, memory, CPU, and downstream pool utilization.
- Streams closed due to idle timeout, max lifetime, or revocation.

The active stream metric must increment when a permit is granted and decrement exactly once when the lease is released. If the metric climbs steadily despite stable traffic, a listener terminal path may have been missed or cleanup is not running.

Do not put raw user IDs, arbitrary tenant IDs, or stream IDs into metric labels if doing so creates uncontrolled cardinality. Use redacted logs/traces to investigate individual calls; metrics should use method, status, and quota tier.

## 12. Testing concurrency limits

Tests must verify that limits are enforced over the entire stream lifecycle, not just at the moment the interceptor is called.

Suppose the server allows at most two streaming RPCs:

| Scenario | Expected result |
| --- | --- |
| Open first stream | Slot granted |
| Open second stream | Slot granted |
| Open third stream while two are still open | Rejected with RESOURCE_EXHAUSTED |
| Complete one stream | Slot returned |
| Open new stream after slot returned | Accepted |
| Client cancels a stream | Slot returned exactly once |
| Handler setup throws exception after acquire | Slot returned |
| Unary RPC when policy only limits streaming | Does not consume streaming permit |
| Tenant A hits its own quota | Tenant B can still open streams if global capacity remains |
| Two streams finish close together | No double release or negative permits |

Use latches/barriers in in-process gRPC integration tests to intentionally hold streams open. Open enough streams to exhaust all permits, attempt to open one more stream, and assert the status. Then complete/cancel a stream and retry.

Additional tests:

1. Global cap holds across multiple connections, not just one channel.
2. Per-tenant cap prevents one tenant from exhausting all capacity.
3. Both listener onComplete and onCancel release idempotently.
4. Canceled streams release subscriptions and buffers.
5. Deadline/idle timeout/max lifetime closes streams and returns slots.
6. Spring application context actually registers the admission interceptor.
7. Active stream metrics increment/decrement accurately across the lifecycle.

Do not use Thread.sleep to synchronize concurrency tests. Use CountDownLatch, barriers, or test observers to control when streams open/close.

## 13. Common implementation pitfalls

| Pitfall | Consequence | Fix |
| --- | --- | --- |
| Only limiting connection count | One connection multiplexes too many streams | Add per-connection and application stream caps |
| Only configuring per-connection cap | Multiple connections exceed total capacity | Add global admission |
| Using global cap without tenant quotas | One tenant consumes all slots | Add per-tenant/principal fairness |
| Acquiring permit without releasing on cancel | Permit leak, new streams wrongly rejected | Release in onComplete/onCancel and setup failures |
| Releasing right after first response | Stream stays open while slot is reissued | Hold permit until terminal event |
| Using flow control instead of concurrency cap | Many idle streams still consume resources | Limit open call count independently |
| Not bounding stream lifetime | Idle streams hold slots indefinitely | Deadlines, idle timeouts, and maximum lifetimes |
| Retrying immediately on RESOURCE_EXHAUSTED | Amplifies load while server is overloaded | Backoff, jitter, and resume |
| Counting with unsynchronized mutable fields | Races, negative counts, or cap exceedance | Semaphore/atomic lease and terminal guard |
| Testing only one connection | Misses global capacity across connections | Test multiple channels/connections against same server |

## 14. Hands-on exercises and self-check questions

### Hands-on exercises

1. Create one server-streaming method and one bidirectional streaming method in Spring gRPC.
2. Configure transport per-connection call caps if your grpc-java transport/version supports it.
3. Write an admission interceptor using Semaphore or StreamAdmissionController to limit streaming RPCs on one instance.
4. Register the interceptor after authentication and method authorization; verify ordering with an integration test.
5. Wrap ServerCall.Listener to release the lease on onComplete, onCancel, or handler setup failure.
6. Add per-tenant quotas and verify one tenant cannot exhaust global capacity.
7. Add maximum stream lifetime, cancellation cleanup, and flow control/bounded queues.
8. Write an in-process test for two slots, third stream rejected with RESOURCE_EXHAUSTED, slot returned after complete/cancel, and Spring wiring.

### Self-check questions

**1. What are concurrent streams?**  
The number of streaming RPCs active simultaneously within a scope such as a connection, instance, service, or tenant.

**2. Why is limiting connections not enough?**  
HTTP/2 multiplexes multiple streams over one connection; a single connection can hold many concurrent RPCs.

**3. Is maxConcurrentCallsPerConnection a global cap?**  
No. It is a per-connection limit of the Netty transport; multiple connections can still produce a large total call count.

**4. Why is application admission control needed?**  
To limit total streams per instance/service/tenant and protect subscriptions, memory, workers, and downstream resources.

**5. When should a stream permit be released?**  
When the RPC completes, is canceled, or setup fails; release must be idempotent and happen exactly once.

**6. Does flow control replace a concurrency cap?**  
No. Flow control limits messages in transit; a concurrency cap limits the number of open RPCs.

**7. Which status is appropriate when stream slots are exhausted?**  
RESOURCE_EXHAUSTED, because the server has reached its resource/quota limit.

**8. How do you prevent one tenant from consuming all stream slots?**  
Combine global caps with per-tenant/principal quotas and admission fairness.

## Summary

Concurrent streams must be controlled across multiple scopes. HTTP/2 and Netty can cap calls per connection, yet do not protect total server capacity or fairness across tenants. Spring gRPC requires application admission control to grant and reclaim slots over the entire lifecycle of streaming RPCs; release must be safe on completion, cancellation, and setup failure. Choose capacity from memory, CPU, and downstream budgets, while also applying tenant quotas, deadlines, idle timeouts, flow control, and bounded queues. When slots are exhausted, reject early with RESOURCE_EXHAUSTED and let clients retry with backoff/resume. Integration tests must hold streams open, exceed the threshold, close/cancel, and prove slots are returned accurately.
