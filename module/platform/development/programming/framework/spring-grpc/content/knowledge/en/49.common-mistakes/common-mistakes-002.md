# Creating a New Channel for Every Request

## 1. Why is creating a channel per request wrong?

In **SPRING_GRPC**, a client calls a remote service via a gRPC channel and stub. A common mistake is creating a `ManagedChannel` right inside each request handler, making the RPC call, and discarding the channel without reusing or managing its lifecycle.

A `ManagedChannel` is not equivalent to a simple function call. It manages name resolution, load balancing, HTTP/2 connections, TLS, reconnection, backoff, and background resources. Repeatedly creating channels forces the application to repeat connection setup work, spawn many sockets/threads, increase handshakes, and make resource usage hard to control.

The standard design is to create a channel per endpoint and security configuration, keep it alive for the application lifecycle or a client component, and reuse it across many concurrent RPCs. Stubs can be created from that channel and reused; when per-call deadlines or call credentials are needed, derive a variant stub per call while still sharing the channel.

This article focuses on:

- Distinguishing Channel, ManagedChannel, and stub.
- The cost of creating a new channel for every request.
- Reusing a channel in a Spring singleton bean.
- Using one channel for multiple concurrent RPCs.
- Scoping channels by endpoint and TLS/identity configuration.
- Managing shutdown, drain, and reconnect.
- Testing to detect channel leaks and connection storms.

## 2. A channel is a long-lived managed client transport

In gRPC Java:

- Channel is the abstraction that a stub uses to send RPCs.
- ManagedChannel is the implementation with a lifecycle that manages connections and transport resources.
- Stubs are generated from the Protobuf service, such as a blocking stub or an async stub.
- Each RPC is a separate call running over the channel.

A channel does not necessarily correspond to a single fixed TCP socket. It can manage one or more connections/subchannels depending on the resolver, load balancer, endpoints, and network state. With HTTP/2, multiple RPCs can multiplex over the same connection; the channel also manages reconnection when a connection drops.

Therefore, reusing a channel does not mean all RPCs share one request or one processing flow. Each RPC still has its own metadata, deadline, request, and response.

## 3. What happens when creating a channel per request?

Anti-pattern example:

```java
public OrderReply getOrder(GetOrderRequest request) {
    ManagedChannel channel =
        ManagedChannelBuilder
            .forAddress("orders.internal", 8443)
            .useTransportSecurity()
            .build();

    OrderGrpc.OrderBlockingStub stub =
        OrderGrpc.newBlockingStub(channel);

    return stub.getOrder(request);
}
```

Every method invocation creates a new channel. If not shut down, the channel and background resources may continue to exist after the method returns. If shut down immediately after each call, the application has to re-establish the transport for the next request.

Under high load, this approach can cause:

- Increased socket and connection counts to the server.
- Repeated TLS handshakes and name resolution.
- Increased CPU, memory, threads, and context switching.
- Continuous connection churn, reconnects, and backoff.
- Higher p95/p99 latency because requests wait for connection setup.
- Traffic spikes against the server, proxy, DNS, or load balancer.
- Difficulty draining and observing client connection state.

Forgetting to shut down the channel is also a resource leak. Shutting it down immediately after each RPC loses most of the benefits of connection reuse and HTTP/2 multiplexing.

## 4. Create the channel once and reuse it

With Spring, you can register `ManagedChannel` as a singleton bean. Spring manages the bean in the application context and calls shutdown when the context closes:

```java
@Configuration
public class GrpcClientConfiguration {

    @Bean(destroyMethod = "shutdown")
    ManagedChannel ordersChannel() {
        return ManagedChannelBuilder
            .forAddress("orders.internal", 8443)
            .useTransportSecurity()
            .build();
    }

    @Bean
    OrderGrpc.OrderBlockingStub orderBlockingStub(
            ManagedChannel ordersChannel) {
        return OrderGrpc.newBlockingStub(ordersChannel);
    }
}
```

The service injects the stub via constructor:

```java
@Service
@RequiredArgsConstructor
public class OrderQueryService {
    private final OrderGrpc.OrderBlockingStub orderBlockingStub;

    public OrderReply getOrder(String orderId) {
        GetOrderRequest request =
            GetOrderRequest.newBuilder()
                .setOrderId(orderId)
                .build();

        return orderBlockingStub
            .withDeadlineAfter(400, TimeUnit.MILLISECONDS)
            .getOrder(request);
    }
}
```

Each request uses the same underlying stub/channel while having its own deadline. The `withDeadlineAfter` method returns a new stub carrying the call option; it does not create a new channel.

The Spring bean example illustrates configuration with gRPC Java. If the project uses a Spring gRPC starter with its own channel factory/auto-configuration, register named channels through the starter's mechanism and let Spring manage the lifecycle; avoid manually creating parallel channels for the same target.

## 5. Channels and stubs can be used concurrently

`ManagedChannel` is designed for multiple threads to make concurrent RPC calls. Generated gRPC stubs are immutable: configuration methods like `withDeadlineAfter` or `withCallCredentials` return a new stub instead of mutating the original stub.

You can hold a base stub in a singleton service:

```java
@Service
@RequiredArgsConstructor
public class InventoryClient {
    private final InventoryGrpc.InventoryBlockingStub baseStub;

    public InventoryReply check(
            InventoryRequest request,
            long remainingMillis) {
        return baseStub
            .withDeadlineAfter(
                remainingMillis,
                TimeUnit.MILLISECONDS
            )
            .checkInventory(request);
    }
}
```

Do not store request-specific mutable data in fields of a singleton client. Per-call deadlines, metadata, tracing context, and credentials must be attached to the corresponding call/stub, not overwrite shared configuration.

With async stubs, multiple calls can be active concurrently on the same channel. Each call has its own observer and must respect its own lifecycle/cancellation.

## 6. Scope channels by endpoint and security identity

Reusing a channel does not mean there can only be one channel in the entire application. A reasonable scope is typically one channel per target and compatible transport/security configuration.

Separate channels may be needed when:

- Calling different targets/services.
- Using different authorities, resolvers, or load balancing policies.
- Using different client certificates/TLS identities.
- Needing workload isolation based on measured operational requirements.

Do not create a separate channel per user or per request solely because metadata differs. For bearer tokens or call credentials that vary per caller, it is usually better to attach `CallCredentials`/metadata per RPC while sharing the channel. If identity is a TLS client certificate at the transport layer, the channel is typically bound to that certificate and needs to be separated by identity/configuration.

If multiple tenants exist, distinguish per-call credentials from transport identity. Do not put sensitive tokens into channel names, logs, or metric labels.

## 7. Reusing a channel does not mean ignoring deadlines

A long-lived channel does not mean RPCs are allowed to wait indefinitely. Deadlines belong to individual calls, not the channel lifetime.

```java
OrderReply reply = orderBlockingStub
    .withDeadlineAfter(350, TimeUnit.MILLISECONDS)
    .getOrder(request);
```

Each RPC needs a deadline aligned with its SLO and remaining budget. When calling downstream from another RPC, propagate the parent deadline or remaining budget. Do not grant a fresh full timeout at each hop.

There is also no need to check channel connectivity before every request before calling. State can change immediately after checking; let gRPC handle reconnection and detect failures via status. Use health checking/monitoring for observability rather than turning it into a mandatory round trip before every RPC.

## 8. Channels manage reconnect and backoff

`ManagedChannel` maintains connections and can reconnect when the network or server is temporarily lost. The name resolver can update addresses; the load balancer selects an appropriate subchannel; the transport performs reconnection according to policy.

Do not create a new channel every time an RPC receives `UNAVAILABLE`. Doing so can trigger a connection storm right as the system is recovering.

Instead:

- Keep the channel and let gRPC manage reconnection.
- Set a finite deadline for each call.
- Retry commands only when status and contract allow.
- Use an idempotency key for side effects that may have already committed.
- Use backoff/jitter and attempt limits.
- Monitor connectivity, call failures, and reconnect behavior.

A channel does not by itself guarantee a healthy server or successful RPCs. It only manages client-side transport and endpoint selection per configuration.

## 9. Shutdown and graceful drain

Channels must be closed when the application context stops. `ManagedChannel.shutdown()` stops accepting new calls and gives in-flight calls a chance to complete; `shutdownNow()` more aggressively requests cancellation of active calls.

A lifecycle hook can wait for graceful termination before forcing shutdown:

```java
public final class ManagedChannelOwner
        implements DisposableBean {

    private final ManagedChannel channel;

    public ManagedChannelOwner(ManagedChannel channel) {
        this.channel = channel;
    }

    @Override
    public void destroy() throws Exception {
        channel.shutdown();

        if (!channel.awaitTermination(5, TimeUnit.SECONDS)) {
            channel.shutdownNow();
            channel.awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
```

The example above illustrates channel ownership. In a Spring application, choose a single place responsible for shutdown to avoid fragmented lifecycles. If using a bean `destroyMethod`, configure a corresponding owner to wait for termination before the process exits.

Application shutdown order also matters: stop accepting new RPCs, drain server requests, complete in-flight work, and then close client channels. Do not shut down channels while the service is still accepting requests that need to call downstream.

If a thread is interrupted while waiting, call `shutdownNow` when necessary, restore the interrupt flag, and finish cleanup in a controlled manner.

## 10. When are multiple channels or a channel pool needed?

One channel is usually the right starting point because HTTP/2 multiplexes many RPCs. However, an HTTP/2 connection has a concurrent streams limit negotiated by the server/proxy; if that limit is exceeded, calls may have to wait.

Consider multiple channels only when a specific transport limit has been measured and it is verified that adding channels improves throughput/latency without overloading the server. Some cases:

- A single target has heavy workload and the concurrent streams limit becomes a bottleneck.
- Latency-sensitive traffic needs isolation from bulk workloads.
- Different transport identities or network paths are required.

If using a channel pool:

- Set a fixed, bounded number of channels.
- Distribute calls deliberately; avoid creating channels randomly per request.
- Monitor total connections across all replicas.
- Manage shutdown/drain for every channel.
- Test server connection limits, load balancers, and reconnection.
- Prove via load testing that a pool outperforms a single channel.

Do not use a channel pool to hide slow queries, server saturation, or connection leaks. Adding channels can increase connection counts and put pressure on downstream.

## 11. TLS and plaintext configuration

Channels should be created with transport security appropriate for the environment:

```java
ManagedChannel secureChannel =
    ManagedChannelBuilder
        .forAddress("orders.internal", 8443)
        .useTransportSecurity()
        .build();
```

In local test environments, plaintext can be used if the server is also configured for plaintext:

```java
ManagedChannel localChannel =
    ManagedChannelBuilder
        .forAddress("localhost", 9090)
        .usePlaintext()
        .build();
```

Do not use plaintext for production traffic over untrusted networks. If custom trust roots, client certificates, or authority overrides are needed, configure transport credentials according to environment policy and keep the channel reusable for that configuration set.

When certificates or trust configurations change, there is no need to create a new channel per call. Create a new channel in a controlled manner, shift traffic to the new channel, drain the old channel, and then shut it down. The rotation process must avoid periods with no available channel.

## 12. Observing channels and detecting excessive channel creation

Monitor these signals:

- Number of `ManagedChannel` instances created per target.
- Number of open connections/subchannels and sockets.
- TLS handshake/reconnect rate.
- RPC latency p50/p95/p99 and status distribution.
- Call queueing or wait time for stream capacity if corresponding metrics exist.
- Number of channels pending shutdown/termination.
- Thread count and memory related to transport.
- Connection churn after deployment or autoscaling.

Do not attach user ID or request ID as metric labels for channels; cardinality will grow unbounded. Use bounded labels such as target, client name, transport profile, and outcome.

If connection counts grow nearly linearly with request counts, inspect where `ManagedChannel` is instantiated. Channels should generally be created in configuration/client lifecycle, not inside RPC handler methods.

## 13. Testing channel lifecycle and reuse

Testing can be performed at multiple levels:

| Test | What to verify |
| --- | --- |
| Multiple RPCs through one client bean | Same channel serves multiple calls |
| Concurrent calls | Multiple threads use the channel safely |
| Different deadlines | Each call has its own deadline without affecting others |
| Server restart | Channel reconnects per policy; failed calls are handled clearly |
| Application context close | Channel shuts down and terminates within the timeout |
| TLS certificate rotation | New channel is brought into use, old channel drains |
| Load test | Channel reuse reduces connection churn and keeps latency stable |
| Leak test | Channel/socket/thread count does not grow with request count |

In integration tests, initialize the channel/client once in a fixture and close it after the test. If each test method creates its own channel, ensure cleanup in a `finally` block or lifecycle hook. Do not use fixed sleeps to wait for a channel to become ready; use health checks, latches, or bounded retries with deadlines.

## 14. Review checklist

- `ManagedChannel` is created in client/configuration lifecycle, not inside individual RPC methods.
- Channel is reused across multiple concurrent calls.
- Stub is kept as an immutable base stub; call options are derived per request.
- Deadlines and metadata are attached per call.
- Channel scope is tied to target and transport/security configuration.
- Per-request credentials are attached via call credentials when appropriate.
- A new channel is not created merely because a call receives `UNAVAILABLE`.
- Connectivity is not checked with a round trip before every RPC.
- Hikari/database work and network calls are not held together in long transactions.
- Each channel has a single owner responsible for shutdown.
- Shutdown stops new calls, drains in-flight calls, and forces shutdown after a grace period.
- Channel pools are only used after metrics prove they are necessary.
- TLS/plaintext is configured appropriately for the environment.
- Metrics track channel count, connection churn, reconnects, and RPC latency.
- Integration/load tests verify reuse, concurrency, reconnect, and cleanup.

In **SPRING_GRPC**, a `ManagedChannel` is a long-lived transport resource shared across many RPCs. Create channels per target and security configuration in the application lifecycle, inject them into services, set per-call deadlines/metadata, and close channels when the application stops. Creating a new channel for every request forfeits connection reuse, increases handshakes, and causes connection churn; use multiple channels only when metrics and load tests prove a specific transport limit.
