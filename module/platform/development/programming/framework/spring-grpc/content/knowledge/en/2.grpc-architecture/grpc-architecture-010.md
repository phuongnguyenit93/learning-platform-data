# Channel lifecycle and connection reuse

## Learning objectives

After this lesson, you can:

- Explain the roles of **Channel** and **ManagedChannel** in a gRPC client.
- Describe how a Channel manages name resolution, load balancing, Subchannels, and HTTP/2 connections.
- Explain why Channels and stubs should be reused rather than created per RPC.
- Manage a Channel as a Spring bean resource, including initialization, graceful shutdown, and forced shutdown.
- Distinguish connection state from service readiness and business health.
- Recognize the impact of idle timeout, keepalive, reconnect/backoff, and HTTP/2 limits.
- Choose an appropriate number of Channels, test reuse, and diagnose connection leaks.

## 1. Channel is the client's connection boundary

In **SPRING_GRPC**, generated stubs provide Java methods matching the RPC methods in the Protocol Buffers contract. Stubs need a **Channel** to deliver calls to the server. In grpc-java, **ManagedChannel** is the client lifecycle-managed implementation: it coordinates name resolution, load balancing, Subchannels, transports, and active RPCs.

~~~mermaid
flowchart LR
    A["Spring service"] --> B["Generated stub"]
    B --> C["ManagedChannel"]
    C --> D["NameResolver"]
    D --> E["LoadBalancer / picker"]
    E --> F["Subchannel"]
    F --> G["HTTP/2 transport"]
    G --> H["gRPC server"]
~~~

A Channel is a logical abstraction; it does not necessarily correspond to a single TCP connection. Depending on the resolver, policy, and topology, one ManagedChannel can manage multiple Subchannels and multiple connections to different backends. For a simple single endpoint, it typically maintains one active connection path.

Distinguish clearly:

| Component | Role |
| --- | --- |
| **Channel** | Abstract API for creating RPCs |
| **ManagedChannel** | Channel with lifecycle, resolver, load balancer, and shutdown |
| **Subchannel** | Logical connection path to a backend address group |
| **Connection** | Actual transport connection, usually TCP/TLS |
| **HTTP/2 stream** | A specific RPC running over a connection |
| **Stub** | Generated Java API to invoke methods on a Channel |

**A Channel outlives an individual RPC.** One Spring service can make thousands of RPCs over the same Channel; each call opens its own HTTP/2 stream. This enables connection reuse and reduces transport setup overhead.

## 2. HTTP/2 multiplexing: why one Channel serves many RPCs

gRPC typically uses HTTP/2. One HTTP/2 connection can carry many concurrent streams, each representing one RPC. Frames from multiple streams are multiplexed onto the same connection:

~~~text
ManagedChannel
   |
   +-- HTTP/2 connection
         |-- stream 1: GetOrder
         |-- stream 3: UpdateOrder
         |-- stream 5: WatchOrder
         |-- stream 7: GetCustomer
         +-- stream 9: SearchOrders
~~~

Therefore, there is no need to open a new TCP/TLS connection per method call. The Channel reuses established connections, while the runtime still keeps each RPC's metadata, deadline, request/response messages, and status separate.

Key benefits:

- Fewer TCP connects and TLS handshakes.
- Fewer sockets and file descriptors to manage.
- Leverages HTTP/2 multiplexing for concurrent RPCs.
- Keeps resolvers and load balancers running continuously to track backend updates.
- Centralizes TLS, credentials, interceptors, and service config on a single Channel.

Multiplexing does not mean concurrent RPC capacity is unlimited. An HTTP/2 peer may limit **MAX_CONCURRENT_STREAMS**; transports or servers may queue, open extra connections depending on implementation, or reject under overload. Measure in-flight RPCs and latency rather than assuming one Channel handles arbitrary load.

### 2.1. A Channel is not a traditional connection pool

Some HTTP applications create large connection pools because each connection handles only one or a few concurrent requests. gRPC over HTTP/2 multiplexes many RPCs on one connection, so the usual approach differs:

- Use one shared ManagedChannel per target and security configuration.
- Let gRPC manage Subchannels and connections according to its resolver and load-balancing policy.
- Create multiple Channels only for concrete architectural reasons such as load isolation, distinct security identities, separate targets, or independent configurations.

Creating a new Channel per RPC is not connection pooling. It typically increases handshakes, DNS lookups, threads/timers, and connection churn, while undermining load balancing and reconnection.

## 3. Lifecycle of a ManagedChannel

A Channel typically moves through the following states:

~~~mermaid
stateDiagram-v2
    [*] --> Created
    Created --> Connecting: First RPC / connection triggered
    Connecting --> Ready: transport ready
    Connecting --> TransientFailure: connection failed
    TransientFailure --> Connecting: backoff and retry
    Ready --> TransientFailure: connection lost
    Ready --> Idle: idle per policy
    Idle --> Connecting: new RPC arrives
    Created --> Shutdown: shutdown()
    Connecting --> Shutdown: shutdown()
    Ready --> Shutdown: shutdown()
    TransientFailure --> Shutdown: shutdown()
    Idle --> Shutdown: shutdown()
    Shutdown --> Terminated: resources released
    Terminated --> [*]
~~~

Connectivity states are typically represented by **ConnectivityState**:

| State | Practical meaning |
| --- | --- |
| **IDLE** | Channel has no activity requiring a connection or is resting |
| **CONNECTING** | Resolving addresses or establishing transport |
| **READY** | A connection path is ready for RPCs |
| **TRANSIENT_FAILURE** | Connection temporarily failed; runtime may retry with backoff |
| **SHUTDOWN** | Channel has been asked to shut down and accepts no new RPCs |

A Channel usually does not open a socket immediately when the bean is created. Connections can be established when the first RPC needs one or when the runtime is explicitly asked to connect. Do not treat ManagedChannel creation as proof that the backend is ready.

When a connection drops, the Channel can reconnect automatically per policy/backoff. New RPCs may wait or fail depending on state, deadlines, and configuration. An RPC already in flight on a lost connection usually fails; the runtime cannot automatically move a mid-flight streaming RPC with partial messages to another backend.

## 4. Reusing Channels and stubs

### 4.1. Channels and generated stubs can be shared

grpc-java Channels are designed for concurrent use. Generated stubs are immutable configuration objects; methods like **withDeadlineAfter(...)** and **withCallCredentials(...)** return a new stub with the corresponding call options.

Usage pattern:

~~~java
OrderServiceGrpc.OrderServiceBlockingStub baseStub =
        OrderServiceGrpc.newBlockingStub(managedChannel);

// Each RPC can create its own variant without mutating baseStub.
GetOrderResponse response = baseStub
        .withDeadlineAfter(800, TimeUnit.MILLISECONDS)
        .getOrder(request);
~~~

Keep **baseStub** as a shared bean; configure deadlines, credentials, or call options per use case. There is no need to recreate `ManagedChannel` when changing the deadline for an RPC.

For async stubs, the same principle applies. However, each streaming call has its own observer and lifecycle; never reuse a finished observer for a new RPC.

### 4.2. Anti-pattern: creating a Channel inside every method

Avoid writing:

~~~java
public GetOrderResponse getOrder(GetOrderRequest request) {
    ManagedChannel channel = ManagedChannelBuilder
            .forAddress("orders.internal", 8443)
            .build();

    try {
        return OrderServiceGrpc.newBlockingStub(channel)
                .getOrder(request);
    } finally {
        channel.shutdownNow();
    }
}
~~~

Every call has to create and tear down its own transport. Common consequences:

- Higher TCP/TLS handshake count and cold-start latency.
- More connections, threads, timers, and pressure on the server.
- DNS/service discovery queried far more often.
- Load balancing struggles to maintain stable Subchannel state.
- In-flight work interrupted when the Channel closes in `finally`.

Create a Channel once for a logical configuration scope and reuse it across many calls.

### 4.3. When are multiple Channels needed?

One shared Channel is usually a good default, yet multiple Channels can make sense when:

- Connecting to **different targets** or environments.
- Requiring independent **identities/credentials/TLS trust** across backend groups.
- Isolating a specific workload so it does not affect critical RPCs.
- Applying separate policies, resolvers, or resource limits that one Channel cannot cleanly express.
- Measured connection/stream bottlenecks prove controlled multi-channel scaling is necessary.

Do not create a Channel per user, order ID, or request without a genuine isolation requirement. When using multiple Channels, bound their count and manage shutdown for all of them.

## 5. Managing Channels in Spring

The Spring container is well suited to own Channels because a Channel's lifecycle usually matches or closely follows the application's lifecycle. Declare the Channel as a singleton bean, build stubs from that bean, and inject stubs into business services.

Basic grpc-java example:

~~~java
package dev.example.orders.client;

import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class OrderGrpcClientConfig {

    @Bean(destroyMethod = "shutdown")
    ManagedChannel orderChannel() {
        return ManagedChannelBuilder
                .forAddress("orders.internal", 8443)
                .build();
    }

    @Bean
    OrderServiceGrpc.OrderServiceBlockingStub orderStub(
            ManagedChannel orderChannel) {
        return OrderServiceGrpc.newBlockingStub(orderChannel);
    }
}
~~~

This example uses grpc-java's default transport configuration; production requires checking TLS/trust, credentials, and resolvers per environment. If configuring TLS or custom load-balancing policies, configure them on the same Channel bean so all stubs share that policy.

The service holds only the stub:

~~~java
@Service
public class OrderClient {
    private final OrderServiceGrpc.OrderServiceBlockingStub stub;

    public OrderClient(
            OrderServiceGrpc.OrderServiceBlockingStub stub) {
        this.stub = stub;
    }

    public GetOrderResponse find(String orderId) {
        GetOrderRequest request = GetOrderRequest.newBuilder()
                .setOrderId(orderId)
                .build();

        return stub.withDeadlineAfter(800, TimeUnit.MILLISECONDS)
                .getOrder(request);
    }
}
~~~

This separates responsibilities cleanly: Channel configuration belongs to the Spring infrastructure layer; business services use stubs and set per-call options. Do not let individual business methods manage hosts, ports, and connection setup.

### 5.1. Closing the Channel when Spring stops

**destroyMethod = "shutdown"** instructs the Channel to stop accepting new RPCs and begin shutting down. **shutdown()** is a graceful request; in-flight RPCs get a chance to finish. The application can wait for a bounded duration before forcing closure:

~~~java
static void closeChannel(ManagedChannel channel) {
    channel.shutdown();

    try {
        if (!channel.awaitTermination(5, TimeUnit.SECONDS)) {
            channel.shutdownNow();
            channel.awaitTermination(2, TimeUnit.SECONDS);
        }
    } catch (InterruptedException ex) {
        channel.shutdownNow();
        Thread.currentThread().interrupt();
    }
}
~~~

This snippet illustrates a shutdown policy. In Spring, place this logic in an appropriate lifecycle bean (such as an **AutoCloseable** wrapper or application shutdown callback) and avoid having both the Channel bean and a wrapper close the same resource in an unclear order. Using only **destroyMethod = "shutdown"** tells Spring to request shutdown without guaranteeing it waited long enough for every RPC.

**shutdownNow()** requests cancelling remaining RPCs and releasing resources sooner. Use it after a bounded drain period or for emergency shutdown; never after every call.

## 6. Idle timeout, keepalive, and reconnect

### 6.1. Idle timeout

A Channel can transition to **IDLE** when there are no RPCs for a policy-defined duration. When a new call arrives, the runtime restarts resolution/connection. Idle timeout saves resources when a client rarely uses a service, though the first call after an idle period may incur extra connection latency.

Configure idle timeout only with clear resource-management needs. Setting it too short can cause connection churn and repeated cold starts; leaving defaults is usually fine without a specific reason to adjust.

### 6.2. Keepalive

HTTP/2 keepalive uses PING frames to check connection liveness per client/server configuration. It can detect unresponsive connections, but:

- Keepalive is not a business health check.
- Keepalive does not replace per-RPC deadlines.
- Servers/proxies may rate-limit PINGs; overly aggressive settings can be rejected or add load.
- Client and server policies should align to avoid unnecessary pings when traffic is absent.

Do not enable ultra-short keepalive as a fix for a slow backend. Distinguish dead connections from slow RPC processing.

### 6.3. Reconnect and backoff

When a connection fails, gRPC usually retries reconnection with backoff to avoid hammering a failing backend. A reused Channel retains its resolver, policy, and state needed for recovery.

Channel reconnection does not mean **sent RPCs are automatically re-executed safely**. A write operation may have already been executed by the server before the connection dropped. Retries must consider status, deadlines, retry policies, and method idempotency.

## 7. Connectivity state is not application health

**READY** indicates the transport can send RPCs; it does not assert the service is healthy at the business level. A server can accept HTTP/2 connections while its database, message broker, or critical dependency is broken.

Distinguish clearly:

| Signal | What it tells you |
| --- | --- |
| **Channel READY** | A transport is ready at the moment observed |
| **gRPC health SERVING** | The health service reports the service is serving |
| **Kubernetes readiness** | Pod/endpoint is allowed to receive traffic per deployment policy |
| **Business operation success** | A specific business operation completed |

Connectivity state can be observed via the Channel API, yet you should not poll it continuously or substitute it for RPC outcomes. For instance, **getState(...)** and **notifyWhenStateChanged(...)** suit deliberate monitoring/state-tracking logic; never treat READY as proof that every method will succeed.

For systems needing health checking, implement **grpc.health.v1.Health** and configure clients/policies accordingly. Infrastructure health checks and readiness probes should align so endpoints do not receive traffic before they are ready.

## 8. Common issues and remediation

| Symptom | Possible cause | Remediation |
| --- | --- | --- |
| High latency on initial RPCs | Cold connection, DNS/TLS handshake, or Channel exiting IDLE | Reuse Channel; measure connection time separately from processing time |
| Socket count grows with request count | Creating ManagedChannel inside each method | Use an application-lifecycle Channel bean |
| Closing one Channel breaks other RPCs | Shared Channel shut down in request-handling code | Shut down only when Spring/app stops |
| Channel READY yet RPC returns UNAVAILABLE | Backend/handler or proxy failed after connection became ready | Check status, server logs, and dependencies |
| Streaming RPC drops during backend restart | Stream is tied to the old connection and does not auto-migrate | Reconnect at application layer, resume via cursor/sequence |
| App shutdown drops in-flight results | Calling `shutdownNow` too early | Use graceful shutdown with bounded drain time |
| Keepalive rejected by server | PING frequency violates policy | Align client/server/proxy configs |
| Connection repeatedly opens and closes | Idle timeout too low or Channel recreated frequently | Adjust idle policy and inspect lifecycle |
| Multiple Channels created yet load remains skewed | Each Channel has separate resolver/LB state; uneven backends or RPC cost | Observe per-backend distribution; use appropriate policy |
| Threads/resources grow after redeploys | Old Channels not shut down | Close all Channels on context stop; check lifecycle beans |

## 9. Testing reuse and shutdown

Useful application checks:

1. Create the Channel once, make multiple unary RPCs, and confirm the Channel does not close between calls.
2. Issue concurrent RPCs through the same stub/Channel; verify responses never mix across calls.
3. Measure latency of the first call versus subsequent calls to separate connection cost from processing cost.
4. Stop the backend, observe connectivity state, reconnect/backoff, and statuses received by callers.
5. Stop the Spring context while RPCs are in flight; verify shutdown lets calls finish within the drain window before forcing closure.
6. Test long-lived streaming; when the connection drops, verify the client reconnects with a new RPC and resumes via cursor if supported.
7. Check Channel/connection counts across multiple context start/stop cycles to catch leaks.

**In-process transport** can test services and lifecycle APIs at the process level, yet cannot measure TCP/TLS handshakes, HTTP/2 keepalive, DNS, or proxies. Those aspects must be tested with a real transport and matching connection/metric observability.

## 10. Hands-on lab and self-check questions

### Hands-on lab

1. Create a shared **ManagedChannel** bean for **OrderService** and inject the generated blocking stub into a Spring service.
2. Call **GetOrder** multiple times through the same stub; observe Channel/connections and compare cold-call latency with subsequent calls.
3. Try creating a Channel per request in a test branch; compare connection counts, handshakes, and resource usage against reuse.
4. Add per-RPC deadlines using **withDeadlineAfter(...)** without creating a new Channel.
5. Test Channel shutdown with active RPCs: compare **shutdown()**, **awaitTermination(...)**, and **shutdownNow()**.
6. Simulate a backend restart; observe reconnect/backoff and verify streaming RPCs need application-level cursor/sequence resume.
7. Enable TLS in a test environment and verify the Channel reuses transport without bypassing hostname/certificate validation.

### Self-check questions

**1. Is a ManagedChannel a single TCP connection?**  
No. It is an abstraction managing resolvers, load balancers, Subchannels, and transports; depending on topology, it can manage multiple connections.

**2. Why reuse a Channel?**  
To leverage HTTP/2 multiplexing and reduce TCP/TLS handshakes, sockets, and discovery/reconnection overhead.

**3. Can a generated stub be shared across multiple threads?**  
Yes, grpc-java stubs are immutable configuration objects designed for reuse. Each call still has its own deadline/observer/lifecycle.

**4. How does shutdown() differ from shutdownNow()?**  
`shutdown()` initiates a graceful shutdown giving in-flight RPCs a chance to complete; `shutdownNow()` requests cancelling remaining calls and closes faster.

**5. Does Channel READY mean the business service is healthy?**  
No. READY only reflects transport state; health services and business outcomes are separate signals.

**6. Does reconnecting automatically re-run a write operation?**  
Never assume so. Retries depend on policy and idempotency; the server may have committed before the connection dropped.

**7. When should you create multiple Channels?**  
When you need independent targets, credentials/TLS identities, policies, or workload isolation; bound and manage the lifecycle of every Channel.

## Summary

**ManagedChannel** is the gRPC client's long-lived connection resource. It manages resolvers, load balancing, Subchannels, and transports; HTTP/2 lets many RPCs multiplex over reused connections. In Spring, own the Channel via a shared bean, derive stubs from the Channel, and apply call options per RPC. When shutting down the application, use graceful shutdown with a drain period before forcing closure. **READY**, keepalive, and reconnection reflect transport state rather than health checking or business guarantees, so test lifecycle, connection failures, and streaming resumption.
