# Connection Limits

gRPC runs over HTTP/2, so a single TCP connection can carry multiple concurrent RPCs as HTTP/2 streams. This makes connection limits and active RPC limits two distinct problems. A server may have few connections yet still handle thousands of streams; conversely, many clients opening many idle connections can exhaust file descriptors, memory, TLS state, and transport resources.

**Connection limits** control the number of concurrent network connections accepted or maintained at a specific boundary, while setting appropriate limits on the number of RPCs/streams running per connection. This lesson belongs to the **Resource limits** chapter of the **SPRING_GRPC** module: developing gRPC services in the Spring ecosystem with Protocol Buffers contracts, Java code generation, and client/server implementations for unary or streaming RPCs; learners work with metadata, deadlines, statuses, interceptors, TLS, integration testing, and performance/reliability monitoring. The focus is distinguishing TCP connections from HTTP/2 streams, choosing the right enforcement layer, reusing client channels, and sizing capacity to avoid file descriptor exhaustion or server overload.

## 1. Connections and RPC streams are not the same unit

A gRPC channel is the client-side abstraction for calling a service. The channel manages connections and can use load balancing to create multiple subchannels/transports. Over each HTTP/2 connection, client and server can multiplex multiple RPC streams.

| Concept | Meaning | What does the limit control? |
| --- | --- | --- |
| TCP connection | Network connection between client/proxy and server. | Sockets, file descriptors, TLS state, buffers, and transports. |
| HTTP/2 stream | A logical stream within a connection, usually corresponding to one RPC. | Concurrent RPCs on one connection. |
| Logical RPC | A single application invocation of a gRPC method. | Business load and method concurrency. |
| ManagedChannel | Client abstraction managing calls and transports. | Lifecycle, resolver, load balancing, and client-side connections. |

One TCP connection can serve many RPCs simultaneously. Therefore, limiting connection count does not automatically limit total RPCs; limiting streams per connection does not automatically limit total connections either.

For example: 100 client connections, each allowed 50 concurrent streams, can generate up to 5,000 active RPCs at that boundary. To limit total load, you need an additional global concurrency limit or application-layer capacity control.

## 2. Identifying the boundary to limit

Before choosing configuration, identify which connections are being counted:

- Client to load balancer: number of TCP connections accepted at the edge from clients.
- Load balancer to gRPC server: number of upstream connections opened by the proxy to backends.
- Direct connections to the server: number of transports maintained by the gRPC server.
- Outbound from service A to service B: number of connections created by A's client channels/subchannels.

These numbers are not necessarily equal. A proxy might accept thousands of downstream connections while opening only a small upstream connection pool to each backend. If a dashboard only shows server connections, it does not reflect all sockets on the client or edge.

Name metrics by boundary, such as downstream_active_connections, upstream_active_connections, or grpc_server_active_transports. Avoid a generic metric named connections when it is unclear where sockets are counted.

## 3. Choosing where to enforce a hard connection cap

A hard cap on TCP connections is usually best placed at the layer accepting connections:

| Layer | How it controls | Appropriate when |
| --- | --- | --- |
| L4 load balancer / network proxy | Sets concurrent connection limits per listener, cluster, or connection source. | Need to block sockets before they consume deep application resources. |
| API gateway / L7 proxy | Limits downstream connections and upstream connection pools; can return appropriate HTTP/gRPC errors. | Need policies per route, identity, or authenticated tenant. |
| Network policy / firewall | Limits sources, subnets, or connection counts supported by infrastructure. | Need network perimeter protection and throttling unwanted sources. |
| gRPC server | Monitors transports, limits RPC concurrency per connection, and bounds work inside the application. | Need resource control inside the process. |
| Client application | Reuses channels and manages channel/subchannel counts. | Need to avoid creating too many outbound connections. |

If the requirement is "do not allow the server to have more than N concurrent TCP connections," you need a real admission control mechanism at the listener/proxy or a transport implementation that supports rejecting connections. A ServerInterceptor running at the RPC level is too late to act as a hard TCP connection cap because it is only invoked when an RPC stream begins.

Do not confuse TCP listen backlog with open connections. Backlog limits how many connections are waiting to be accepted/finish handshaking per OS behavior; it is not a cap on total established sockets.

## 4. HTTP/2 multiplexing and concurrent call limits

gRPC Java supports limiting concurrent calls on a connection via ServerBuilder/NettyServerBuilder in supported versions:

~~~java
NettyServerBuilder serverBuilder =
        NettyServerBuilder.forPort(9090)
                .maxConcurrentCallsPerConnection(64);
~~~

The value 64 is an example, not a universal default suitable for every service. This setting caps concurrent RPCs per connection. When the threshold is reached, the HTTP/2/gRPC transport throttles or stops accepting new streams according to the implementation's mechanism.

This is not a hard cap on TCP connections. Clients can open additional connections and start more streams on new connections. Therefore:

- Use maxConcurrentCallsPerConnection to cap stream concurrency per transport.
- Use a global application concurrency limit to cap total in-flight RPCs.
- Use an edge connection cap to bound accepted sockets.

These layers complement one another; they do not replace one another.

## 5. Tracking active transports on the server

gRPC Java provides ServerTransportFilter to observe transport lifecycles. With a Netty HTTP/2 server, each transport typically corresponds to one connection; the filter can increment a counter when the transport is ready and decrement when it terminates.

~~~java
import io.grpc.Attributes;
import io.grpc.ServerTransportFilter;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;

import java.util.concurrent.atomic.AtomicLong;

public final class ActiveTransportFilter
        extends ServerTransportFilter {

    private final AtomicLong activeTransports = new AtomicLong();

    public ActiveTransportFilter(MeterRegistry registry) {
        Gauge.builder(
                        "grpc.server.active.transports",
                        activeTransports,
                        AtomicLong::get)
                .description("Number of active gRPC server transports")
                .register(registry);
    }

    @Override
    public Attributes transportReady(Attributes transportAttrs) {
        activeTransports.incrementAndGet();
        return transportAttrs;
    }

    @Override
    public void transportTerminated(Attributes transportAttrs) {
        activeTransports.updateAndGet(value -> Math.max(0, value - 1));
    }
}
~~~

Register the filter on the server builder:

~~~java
NettyServerBuilder serverBuilder = NettyServerBuilder.forPort(9090)
        .addTransportFilter(new ActiveTransportFilter(meterRegistry));
~~~

In a Spring application, attach the filter to the server builder managed by the Spring gRPC starter via your version's extension point. Do not start a standalone server just to attach the filter.

ServerTransportFilter is a lifecycle observation hook, not a transport-rejection API. The snippet above only creates a gauge; it does not limit connection count. If a hard cap is required, enforce it at a proxy/listener with admission control or use a transport implementation with explicit support.

## 6. Server-wide RPC concurrency limits

Per-connection limits are insufficient if multiple connections open streams simultaneously. You can apply admission control at the RPC layer to cap total running handlers. One approach is using a semaphore in a ServerInterceptor; when permits run out, return RESOURCE_EXHAUSTED and skip invoking the service handler:

~~~java
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;

import java.util.concurrent.Semaphore;
import java.util.concurrent.atomic.AtomicBoolean;

public final class RpcAdmissionInterceptor
        implements ServerInterceptor {

    private final Semaphore permits = new Semaphore(500);

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        if (!permits.tryAcquire()) {
            call.close(
                    Status.RESOURCE_EXHAUSTED
                            .withDescription("Server RPC capacity reached"),
                    new Metadata());
            return new ServerCall.Listener<>() {};
        }

        AtomicBoolean released = new AtomicBoolean();
        Runnable release = () -> {
            if (released.compareAndSet(false, true)) {
                permits.release();
            }
        };

        ServerCall<ReqT, RespT> monitored =
                new io.grpc.ForwardingServerCall
                        .SimpleForwardingServerCall<>(call) {
                    @Override
                    public void close(Status status, Metadata trailers) {
                        try {
                            super.close(status, trailers);
                        } finally {
                            release.run();
                        }
                    }
                };

        ServerCall.Listener<ReqT> listener;
        try {
            listener = next.startCall(monitored, headers);
        } catch (RuntimeException failure) {
            release.run();
            throw failure;
        }

        return new io.grpc.ForwardingServerCallListener
                .SimpleForwardingServerCallListener<>(listener) {
            @Override
            public void onComplete() {
                try {
                    super.onComplete();
                } finally {
                    release.run();
                }
            }

            @Override
            public void onCancel() {
                try {
                    super.onCancel();
                } finally {
                    release.run();
                }
            }
        };
    }
}
~~~

This example limits the number of RPCs admitted into handlers, not TCP connections. Check every terminal path and exception when calling next.startCall so permits never leak; in production, wrap synchronous errors during listener initialization as well and use a unified lifecycle guard. For streaming RPCs, the permit is held for the entire duration of the stream, because the stream continues holding resources until closed/canceled.

Global limits should also be partitioned by method or workload group if a long-lived streaming method could exhaust permits needed by critical unary RPCs. You can use separate semaphores per service/method, weighted admission, or bounded queues.

## 7. Managing client-side connections with ManagedChannel

A common mistake is creating a new ManagedChannel per request. Each channel has its own lifecycle, resolver, load-balancing state, and transport; creating too many channels increases TCP connections, TLS handshakes, threads, and file descriptors.

Reuse channels by target and connection configuration:

~~~java
ManagedChannel channel = ManagedChannelBuilder
        .forTarget("dns:///inventory.internal:8443")
        .useTransportSecurity()
        .build();

InventoryGrpc.InventoryBlockingStub stub =
        InventoryGrpc.newBlockingStub(channel);

// Reuse channel/stub across many RPCs over the bean/service lifecycle.

// On application shutdown:
channel.shutdown();
if (!channel.awaitTermination(5, TimeUnit.SECONDS)) {
    channel.shutdownNow();
}
~~~

In Spring Boot, manage channels as beans with clear lifecycles and shut them down when the application context stops. Never create channels inside individual controller methods or message callbacks.

One ManagedChannel does not always correspond to one TCP connection: load balancing can open multiple subchannels to multiple backends, and resolvers/policies govern transports. gRPC Java has no universal maxConnections property across every ManagedChannelBuilder. If strict outbound socket limits are needed, manage channel/target counts intentionally and consider an egress proxy with connection pool caps.

## 8. Connection lifecycle: idle, age, and keepalive

Connection lifecycle policies reclaim or refresh long-idle connections, yet they are not hard concurrent connection caps:

- maxConnectionIdle: allows the server to close connections with no active RPCs for a period of time.
- maxConnectionAge: bounds connection lifetime to gradually rotate transports.
- maxConnectionAgeGrace: grace period allowing in-flight RPCs to finish before the connection closes.
- Keepalive: checks whether the transport is still alive; pinging too often creates unnecessary load.
- Client idle/shutdown policies: help release unused channels.

Server options may be provided by ServerBuilder/NettyServerBuilder depending on the grpc-java version. Configuration examples must be verified against the version in use:

~~~java
NettyServerBuilder.forPort(9090)
        .maxConnectionIdle(5, TimeUnit.MINUTES)
        .maxConnectionAge(30, TimeUnit.MINUTES)
        .maxConnectionAgeGrace(2, TimeUnit.MINUTES)
        .permitKeepAliveTime(1, TimeUnit.MINUTES)
        .permitKeepAliveWithoutCalls(false);
~~~

Idle/age policies can trigger client reconnects and new connections. During rollouts or when setting age too low, connection churn rises, along with TLS handshakes and load-balancer activity. Monitor connection creation rate and reconnect rate alongside active connection count.

## 9. Placing connection caps at the edge proxy

When a hard limit is required, configure it at the L4/L7 proxy or load balancer accepting connections. Policies must define:

| Property | Question to answer |
| --- | --- |
| Scope | Limit by listener, backend cluster, source IP, or identity? |
| Concurrent cap | What is the maximum number of established connections? |
| Pending cap | Is there a limit on connections waiting for accept/handshake? |
| Overflow behavior | Reject/reset new connections, bounded queue, or return L7 error? |
| Fairness | Can one client consume all slots from other clients? |
| Recovery | How are slots freed on close, timeout, or health failure? |

With Envoy or similar proxies, use connection limit/network filters or upstream connection pool limits appropriate to the version and listener type. L4 proxies typically close/reset TCP connections; L7 gateways can return an appropriate status if requests are parsed. Do not assume every connection limit filter shares identical semantics.

If limiting by source IP, remember many users may share a NAT IP. If limiting by authenticated identity, the proxy must authenticate identity before applying quotas. Never use x-request-id or caller-declared metadata as a trusted identity.

## 10. Backlogs and file descriptors do not replace admission control

Operating system limits remain important:

- Listen backlog regulates connections waiting to be accepted; it does not cap total established connections.
- File descriptor limits cap how many sockets/handles a process can open; hitting the ceiling typically causes accept/connect failures.
- Ephemeral ports and conntrack tables can constrain outbound/network state.
- Memory/socket buffers and TLS session state scale with connection count.

Do not rely on file descriptor exhaustion to protect the server. That is a last-resort failure mode, not controlled rejection. Set caps at the edge, bound RPC concurrency inside the application, and size OS limits generously for expected load plus headroom.

## 11. Estimating capacity

Connection counts must be grounded in measurements of real workloads. A simple model:

\[
\text{Total connection budget} =
\text{steady-state connections}
+ \text{rollout/reconnect headroom}
+ \text{failure headroom}
\]

Capacity planning must account for:

- Number of client instances and targets/backends each client calls.
- Number of subchannels/connections the load-balancing policy can open.
- Number of connections from proxies to each backend.
- Concurrent streams per connection.
- Memory, file descriptors, TLS handshake rate, and socket buffers.
- Connection churn during deploys, autoscaling, DNS changes, or failovers.
- Headroom for retry storms and simultaneous reconnects.

Do not simply multiply client count by an assumed single connection. Measure active transports on the server and connection pools on the proxy during load tests. Few connections with high stream concurrency can still overload CPUs/worker pools; many idle connections still consume resources.

## 12. Metrics and alerting

Track connections and streams with separate metrics:

| Metric | Meaning |
| --- | --- |
| grpc.server.active.transports | Active transports/connections at the server. |
| edge.downstream.active_connections | Client-to-proxy connections. |
| edge.upstream.active_connections | Proxy-to-backend connections. |
| connection.accepted/rejected rate | Rate of accepted and rejected connections. |
| connection creation rate | Churn/reconnect level. |
| grpc.server.active.calls | Active RPCs/streams. |
| grpc.server.calls.rejected | RPCs rejected due to admission limits. |
| TLS handshake duration/errors | TLS setup cost and failures. |

Dashboards should compare active connections against configured caps while also displaying active streams, rejected connections, and connection creation rates. Alert when connection usage stays near the cap, rejection rates climb, or connection churn is abnormal; avoid alerting on brief spikes during planned rollouts.

Metric labels should stay bounded to controlled sets like listener, cluster, service, method, or zone. Never attach request IDs, local socket ports, ephemeral remote ports, or connection IDs as labels because they create high cardinality.

## 13. Testing connection limits

In-process gRPC transport is useful for testing interceptors/RPC logic, yet does not simulate real TCP sockets. Testing hard connection caps requires running the server over TCP and, if the policy lives at the edge, sending traffic through the actual proxy/load balancer:

1. Open fewer connections than the cap; verify all are accepted.
2. Open connections past the cap; verify overflow behavior matches policy (reject/reset/bounded queue).
3. Close one connection; verify the slot is freed and a new connection is accepted.
4. Hold one connection open and start many RPCs; verify maxConcurrentCallsPerConnection works as configured.
5. Open multiple connections simultaneously; verify the global RPC concurrency limit still holds.
6. Create multiple ManagedChannels in a client test; observe actual transport counts and verify channel reuse reduces connection churn.
7. Test connection age/idle policies; verify in-flight streams drain within the grace period.
8. Simulate rolling restarts/reconnects; verify headroom and connection caps do not lock out all clients.
9. Check the active transport gauge and edge connection metrics; verify increments/decrements follow socket lifecycles.

Use latches/barriers to synchronize tests and finite timeouts. Do not rely on sleep to guess when connections are accepted; observe metrics, health endpoints, or client channel states. With proxies, inspect proxy logs/metrics too because the server may never see connections rejected at the edge.

## 14. Common pitfalls

| Symptom | Cause | Fix |
| --- | --- | --- |
| Thinking maxConcurrentCallsPerConnection is max TCP connections | Confusing HTTP/2 streams with sockets. | Use edge connection caps for hard TCP limits. |
| Server has few connections yet is overloaded | Each connection multiplexes too many RPCs. | Bound stream/call concurrency and handler capacity. |
| Connection count scales with request rate | Creating ManagedChannel per RPC. | Reuse channels by target/lifecycle. |
| ServerTransportFilter does not block excess connections | Filter only observes transport lifecycle. | Enforce admission at a proxy/listener supporting rejection. |
| Treating backlog as a connection cap | Backlog only throttles the accept queue. | Use a separate concurrent connection limit. |
| File descriptors hit ceiling | Relying on OS limit as admission policy. | Set proactive caps and increase OS headroom appropriately. |
| Deploy causes reconnect storm | Connection age too short or simultaneous rollout. | Tune drain/grace, jittered reconnects, and headroom. |
| IP quota blocks many valid users | Multiple callers share NAT. | Apply quotas by authenticated identity at L7 when appropriate. |
| Dashboard connection counts do not match | Counting at different boundaries. | Name downstream/upstream/server transports clearly. |

## 15. Hands-on exercises

1. Diagram the connection path from clients through load balancers/proxies to the gRPC server and identify each counting point.
2. Configure maxConcurrentCallsPerConnection and test stream counts over a single connection.
3. Write a ServerTransportFilter using a Micrometer Gauge to track active transports.
4. Reuse ManagedChannel in a Spring bean and shut down the channel with the lifecycle.
5. Set a hard connection cap on a proxy/L4 listener; test behavior when exceeding the threshold.
6. Combine per-connection stream caps with a global RPC admission limit.
7. Measure connection churn, TLS handshakes, active streams, and file descriptors under load tests.
8. Build a dashboard distinguishing downstream connections, upstream connections, server transports, and active RPCs.

After this lesson, you should distinguish TCP connections from HTTP/2 streams, know how per-connection RPC limits differ from hard connection caps, and choose the right layer to enforce policies. Combining edge admission control, gRPC stream concurrency, channel reuse, and per-boundary metrics helps Spring gRPC systems protect sockets/file descriptors while maintaining stable service availability.
