# Client-side load balancing

## 1. Client selects a backend per RPC

In **SPRING_GRPC**, the client and server communicate using gRPC, Protocol Buffers contracts, and generated Java code. When a service has multiple instances serving the same API, the client needs to know the instance addresses and decide where to send each RPC. **Client-side load balancing** is the model in which a gRPC client receives a list of endpoints from name resolution and then selects a backend for each call.

For example, the `orders` service has three instances:

~~~text
orders.internal
   |
   +--> 10.20.0.11:9090  (instance A)
   +--> 10.20.0.12:9090  (instance B)
   +--> 10.20.0.13:9090  (instance C)

Client creates a ManagedChannel
   |
   +--> resolver discovers endpoints
   +--> load balancing policy selects a subchannel
   +--> RPC is sent to a backend
~~~

A channel does not necessarily correspond to a single TCP connection. One `ManagedChannel` can manage multiple **subchannels**, where each subchannel represents a connection to an endpoint. The load balancer uses the state of the subchannels to choose where to send an RPC.

Goals of client-side load balancing:

- Distribute RPCs across multiple instances instead of sending every request to one backend.
- Detect new endpoints or removed endpoints through name resolution.
- Select a ready connection according to the policy.
- Continue operating when some backends are unavailable, within what the policy and connection states allow.

This is different from creating a new `ManagedChannel` for every request. The channel should be reused; the load balancer inside the channel is the component that selects the backend for RPCs.

## 2. Cooperating components

A client-side channel typically has four parts:

1. **Target:** the service name or destination address, for example `dns:///orders.internal:9090`.
2. **Name resolver:** resolves the target into a list of addresses. The resolver can use DNS or system-provided service discovery.
3. **Load balancing policy:** receives the address list and connection states, then selects a subchannel for the RPC.
4. **Subchannel/transport:** maintains the connection to the backend and transports gRPC messages.

~~~mermaid
flowchart TD
    A["Generated stub"] --> B["ManagedChannel"]
    B --> C["Name resolver"]
    C --> D["List of backend addresses"]
    D --> E["Load balancing policy"]
    E --> F["Subchannel A"]
    E --> G["Subchannel B"]
    E --> H["Subchannel C"]
    F --> I["Backend A"]
    G --> J["Backend B"]
    H --> K["Backend C"]
~~~

The resolver does not perform load balancing itself. It provides **addresses**. The policy decides how those addresses are used. Similarly, the policy cannot discover new instances on its own if the resolver does not update the endpoint list.

With DNS, the target has the form:

~~~text
dns:///orders.internal:9090
~~~

The three `/` characters after `dns:` indicate a target using the DNS resolver with an empty authority and the address part `orders.internal:9090`. In an environment with a custom resolver, the target scheme and configuration depend on the provider installed by the application.

## 3. pick_first and round_robin

Two common policies in gRPC Java:

| Policy | Selection behavior | Best suited when |
|---|---|---|
| `pick_first` | Picks one ready subchannel from the list and uses it for RPCs; can switch to another address when the connection is not ready according to state/policy | You want a single primary active connection, simplicity, and address failover on error |
| `round_robin` | Distributes new RPCs across ready subchannels in turn | You want to utilize multiple backends simultaneously |

For example, with three backends all ready, new RPCs can be distributed as:

~~~text
round_robin:
RPC 1 -> A
RPC 2 -> B
RPC 3 -> C
RPC 4 -> A
RPC 5 -> B
RPC 6 -> C
~~~

This is an illustrative model, not a guarantee that every RPC will always follow a fixed A-B-C sequence. When a subchannel is not ready, the resolver updates the list, or the policy updates state, the picker may choose another backend. If only one subchannel is ready, `round_robin` can only select that subchannel.

`pick_first` does not mean "never fail over." It prefers one subchannel from the list and can try another address when the current one is not working. Conversely, `round_robin` does not mean splitting request count or CPU usage evenly: RPCs have different durations and costs, and the policy generally distributes in turn across ready subchannels rather than measuring business load on each instance.

## 4. Configuring round_robin in gRPC Java

Example of a client creating a channel to a DNS target and selecting the `round_robin` policy:

~~~java
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;

ManagedChannel channel = ManagedChannelBuilder
        .forTarget("dns:///orders.internal:9090")
        .defaultLoadBalancingPolicy("round_robin")
        .useTransportSecurity()
        .build();
~~~

Then use the generated stub as usual:

~~~java
OrdersGrpc.OrdersBlockingStub orders =
        OrdersGrpc.newBlockingStub(channel);

GetOrderReply reply = orders
        .withDeadlineAfter(2, java.util.concurrent.TimeUnit.SECONDS)
        .getOrder(GetOrderRequest.newBuilder()
                .setOrderId("ORD-42")
                .build());
~~~

New RPCs using the same channel will have their backend selected by the policy. There is no need to read the IP list manually and pick randomly inside each service method.

`useTransportSecurity()` enables TLS for the connection. The server certificate must be valid for the hostname/authority used by the client. `usePlaintext()` should only be used in controlled development environments.

`defaultLoadBalancingPolicy("round_robin")` is the fallback policy when the resolver does not provide a policy in the service config. A service config provided by the resolver can specify its own policy and may take precedence over the default value. The policy provider must also be present at runtime; if the policy is not registered, the channel cannot use it.

## 5. Integrating the channel into Spring

In a Spring application, `ManagedChannel` should be created and managed as a shared bean. Each request creates or uses a stub from the existing channel; do not create a new channel for every call:

~~~java
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class GrpcClientConfiguration {

    @Bean(destroyMethod = "shutdown")
    ManagedChannel ordersChannel() {
        return ManagedChannelBuilder
                .forTarget("dns:///orders.internal:9090")
                .defaultLoadBalancingPolicy("round_robin")
                .useTransportSecurity()
                .build();
    }
}
~~~

The client service receives the channel via constructor injection:

~~~java
import com.example.orders.rpc.OrdersGrpc;
import io.grpc.ManagedChannel;
import org.springframework.stereotype.Component;

@Component
public class OrdersClient {
    private final OrdersGrpc.OrdersBlockingStub stub;

    public OrdersClient(ManagedChannel ordersChannel) {
        this.stub = OrdersGrpc.newBlockingStub(ordersChannel);
    }
}
~~~

This is an illustrative configuration skeleton. If the application has multiple gRPC targets, declare a separate channel bean for each service and give it a clear qualifier name. Endpoint configuration, TLS credentials, resolver, and policy can be bound from properties according to the mechanism of the Spring gRPC starter in use; exact property names depend on the library and version.

A channel is a long-lived, thread-safe resource that can serve multiple stubs/RPCs. When the Spring context stops, `destroyMethod = "shutdown"` initiates an orderly channel shutdown. If a timed shutdown is needed, you can manage `shutdown()`, `awaitTermination(...)`, and then `shutdownNow()` according to the application lifecycle.

## 6. Name resolution determines which backends the client sees

Client-side load balancing only distributes across the endpoints provided by the resolver. If DNS only returns a single address, `round_robin` cannot know on its own how many instances sit behind that address.

For example, in Kubernetes:

- **ClusterIP Service:** DNS typically returns a single virtual IP. The client sees one endpoint; distribution to pods is handled by Kubernetes networking/service proxy. This is infrastructure-side load balancing, not the client directly selecting individual pods.
- **Headless Service:** DNS can return multiple pod IPs. The resolver can see individual endpoints; `round_robin` can distribute RPCs among those addresses.
- **Custom service discovery:** a custom resolver can fetch endpoints from a registry or control plane, updating addresses and attributes when instances change.

Do not assume that all DNS resolvers return pod lists in the same way. Verify the name resolution output in the deployment environment. If the resolver returns only one address, switching the policy from `pick_first` to `round_robin` will not create multiple backends to distribute across.

The resolver also needs to update when instances are added, removed, or change IP. The policy receives the new list and adjusts subchannels. When a backend is removed from the list, new RPCs should no longer be routed to that endpoint; in-flight RPCs may still need time to finish or fail depending on the transport and instance state.

## 7. Backend readiness and behavior when no endpoint is ready

Having an address in DNS does not mean the backend is ready to serve. A connection may be in `CONNECTING`, `TRANSIENT_FAILURE`, `IDLE`, or `READY`. The policy uses subchannel state to select an appropriate connection.

If no subchannel is ready:

- The RPC may fail with a connection error depending on state and configuration.
- The client can use `withWaitForReady()` to wait until the channel has a ready backend, instead of failing immediately when the picker has no connection.
- The deadline still applies while waiting; `waitForReady` does not make an RPC wait forever.

Example:

~~~java
GetOrderReply reply = orders
        .withWaitForReady()
        .withDeadlineAfter(3, java.util.concurrent.TimeUnit.SECONDS)
        .getOrder(request);
~~~

`waitForReady` is useful when backends are temporarily unready and the request is still meaningful after a short wait. It does not replace a retry policy, does not guarantee the request will be processed, and should not be used for every RPC if requests expire quickly or lose value when delayed.

Readiness at the gRPC layer primarily reflects connection/subchannel state. To avoid sending requests to an instance that has started but is not yet business-ready, combine this with health checking, deployment platform readiness probes, or service discovery that only publishes ready endpoints.

## 8. A server stream is pinned to one backend

Load balancing chooses a backend when an RPC starts. With unary RPCs, each new call can be routed to a different backend. With **server streaming**, the entire RPC typically stays pinned to the backend that accepted that call:

~~~text
WatchProgress RPC #1
    -> backend A
    <- event 1 from A
    <- event 2 from A
    <- event 3 from A
    <- stream ends

WatchProgress RPC #2 (new call)
    -> backend B may be selected
~~~

gRPC does not distribute individual responses of the same stream across different backends. If backend A stops mid-stream, that RPC may fail; the policy does not transparently migrate the remainder of the stream to backend B. The client must reconnect with a new RPC and use a cursor/sequence if the business logic requires resuming from where processing left off.

This is especially important for servers that hold state in instance memory. If the second stream lands on another backend, local state from backend A will not automatically exist on B. Store job/session state in shared storage or provide a resume mechanism using identifiers and checkpoints.

## 9. Load balancing is not retry or failover in every scenario

The following mechanisms serve different roles:

| Mechanism | Responsibility |
|---|---|
| Client-side load balancing | Selects a subchannel/backend for a new RPC |
| Name resolution | Provides and updates the list of addresses |
| `waitForReady` | Waits for a ready backend/connection within the deadline budget |
| Retry policy | Retries RPCs based on conditions, status codes, and commitment rules |
| Application reconnect/resume | Opens a new RPC with a cursor/checkpoint to continue a stream |
| Server-side/network load balancing | Intermediary infrastructure selects the backend on behalf of the client |

When a unary RPC fails after the server may already have performed side effects, automatic retries can cause duplicate execution if the request is not idempotent. For server streaming that has already emitted responses, do not assume automatic retries will replay data. Design retry/resume behavior explicitly according to the contract.

## 10. Session affinity and application state

`round_robin` distributes RPCs across ready subchannels; it does not guarantee that the same user always reaches the same backend. If an API requires session affinity, an explicit design is needed:

- Store session/job state in shared storage.
- Use an identifier or routing key supported by the resolver/policy if the system truly requires affinity.
- Do not rely on round-robin ordering to assume a caller will always hit the same instance.
- Do not stuff secrets or raw tokens into metadata just to construct a routing key.

With gRPC, metadata can carry a correlation ID or routing information per infrastructure contract, but default policies do not automatically interpret an arbitrary header to pick a backend. Key-based routing requires a custom resolver/load balancer or an appropriate proxy mechanism.

## 11. Testing and observing client-side load balancing

A load balancing test must verify that **the resolver actually provides multiple addresses** and that the policy uses them. Simply creating a channel to a single in-process server does not test distribution across multiple backends.

Scenarios to test:

| Scenario | What to verify |
|---|---|
| Resolver returns one endpoint | All RPCs go to the single endpoint; no distribution expected |
| Resolver returns three ready endpoints with `round_robin` | Multiple new RPCs are distributed across the endpoints |
| One endpoint is not ready | New RPCs are selected from the remaining ready subchannels |
| Resolver adds an endpoint | The channel receives the update and the policy can use the new endpoint |
| Resolver removes an endpoint | New RPCs stop selecting the removed endpoint |
| No endpoint is ready | Error behavior or wait-for-ready respects the deadline |
| Server stream is open and backend stops | The current RPC may fail; the client reconnects using a cursor if needed |
| Multiple channels created per request | Detect wasted connections and resources |

For deterministic testing, you can use a custom `NameResolverProvider` returning a test address list and multiple servers that can identify each instance individually. Verify that the `round_robin` policy provider is loaded at runtime. In-process transport is suitable for gRPC logic; testing multi-endpoint resolver/policy behavior and TCP/TLS requires corresponding fixtures.

Useful metrics:

- RPC count per backend/target.
- Subchannel count by state (`READY`, `CONNECTING`, `TRANSIENT_FAILURE`).
- Number of resolver endpoint updates.
- Connection error rate, `UNAVAILABLE`, and deadline exceeded rate.
- Latency distribution per backend to spot a slow instance.
- Active long-lived stream count per backend and stream lifetime.

If one backend receives more requests, the policy is not necessarily wrong: RPC duration, number of ready subchannels, uneven resolver address lists, or requests sent before all backends became ready can all affect distribution. Observe both endpoints and business load.

## 12. Common configuration mistakes

| Mistake | Consequence | How to fix |
|---|---|---|
| Using `round_robin` when the resolver returns only one IP | No multiple backends to distribute across | Check the target and name resolution output |
| Creating a new channel per request | Increased connections, handshakes, and resource usage | Manage a shared channel per target |
| Confusing ClusterIP with a pod list | Client does not directly see individual instances | Decide whether load balancing lives at the client or infrastructure |
| Assuming streams automatically migrate when an instance dies | Current RPC may fail mid-stream | Reconnect with a new RPC and resume via cursor |
| Using `waitForReady` without a deadline | Requests may wait too long | Set an appropriate deadline for each RPC |
| Assuming round robin splits CPU evenly | Backends may receive disproportionate load | Monitor latency, duration, and actual load |
| Using local session state on each backend | New RPCs may hit another instance and lose state | Use a shared state store or explicit affinity |

**Key takeaway:** Client-side load balancing in gRPC Java combines a **name resolver**, a **load balancing policy**, and **subchannels** managed by `ManagedChannel`. The resolver supplies endpoints; `pick_first` prefers a single connection, while `round_robin` distributes new RPCs across ready subchannels. A server stream remains pinned to the backend that accepted that RPC; if the backend fails, continuing requires creating a new RPC and using an application-level resume mechanism. In Spring, reuse shared channels, configure TLS/readiness/deadlines, and observe load per backend.
