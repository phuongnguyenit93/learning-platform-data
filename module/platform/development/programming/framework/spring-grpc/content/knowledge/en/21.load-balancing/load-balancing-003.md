# Round robin and other policies

## 1. Load balancing policy determines how backends are selected

In **SPRING_GRPC**, a `ManagedChannel` uses a name resolver to find endpoints of a gRPC service. When the resolver returns multiple addresses, the channel needs a **load balancing policy** to decide which subchannel receives a new RPC. The policy directly affects backend utilization, continuity when an endpoint fails, and load distribution across instances.

Two fundamental policies commonly encountered in gRPC Java are:

- **`pick_first`:** prefers one connectable endpoint and keeps using it; tries another address when the currently selected endpoint cannot connect.
- **`round_robin`:** distributes new RPCs in turn across subchannels that are currently ready.

Suppose the resolver provides three backends A, B, and C:

~~~text
Name resolver: [A, B, C]

pick_first:
  RPC 1 -> A
  RPC 2 -> A
  RPC 3 -> A
  ...

round_robin:
  RPC 1 -> A
  RPC 2 -> B
  RPC 3 -> C
  RPC 4 -> A
  ...
~~~

This is conceptual behavior when all backends are `READY`. Actual ordering depends on connection states, the resolver list, and the active picker. A policy cannot distribute to an endpoint that the resolver does not provide.

## 2. Where does the policy fit in the RPC lifecycle?

The components cooperate in this flow:

1. **Target** identifies the service to call, for example `dns:///orders.internal:9090`.
2. **Name resolver** resolves the target into one or more `EquivalentAddressGroup` entries.
3. **Load balancing policy** receives the addresses and subchannel states, then produces a picker.
4. **Picker** selects a subchannel for a new RPC.
5. **Subchannel** manages the connection to the selected backend.

~~~mermaid
flowchart TD
    A["Generated stub"] --> B["ManagedChannel"]
    B --> C["Name resolver"]
    C --> D["Endpoint list"]
    D --> E["Load balancing policy"]
    E --> F["Picker"]
    F --> G["Subchannel A"]
    F --> H["Subchannel B"]
    F --> I["Subchannel C"]
    G --> J["Backend A"]
    H --> K["Backend B"]
    I --> L["Backend C"]
~~~

The resolver answers **what addresses exist**; the policy answers **which address a new RPC goes to**. Therefore, changing the policy cannot fix a resolver that returns only a single virtual IP. Similarly, a resolver updating its list does not mean all new endpoints are already connected and ready immediately.

## 3. pick_first: preferring one active connection

`pick_first` fits when you want a single primary backend at a time. When given multiple addresses, the policy attempts connections down the list and picks a subchannel that reaches `READY`. Subsequent new RPCs typically continue using that chosen subchannel.

If the current endpoint loses connectivity, the policy can try the remaining addresses. This is the ability to switch to another endpoint when the connection is not ready; it is not a mechanism for splitting load evenly across all backends.

**Consider `pick_first` when:**

- The downstream service already has a network-layer or proxy load balancer.
- You want a stable connection and do not need the client to spread requests across every instance.
- The address list mainly serves as fallback endpoints to try.
- Load from a single client does not need to utilize multiple backends concurrently.

Do not interpret `pick_first` as "always pick the first address regardless of state." The endpoint must be connectable; when that endpoint fails, the policy can switch to another address according to state and implementation behavior.

## 4. round_robin: distributing new RPCs across ready backends

`round_robin` creates and maintains subchannels for the addresses provided by the resolver and distributes new RPCs across subchannels that are `READY`. With three ready backends, the selection sequence may be A, B, C, A, B, C.

This policy is useful when:

- The client directly sees multiple instances.
- Instances serve the same API and can handle requests independently.
- You want one client to leverage multiple backend connections concurrently.
- There is no requirement that every RPC from a given caller must hit the same instance.

Round robin **does not balance CPU or processing time precisely**. It distributes RPCs in turn across ready subchannels, while one RPC may take 2 ms and another 2 minutes. One backend may also experience higher actual load if the requests routed to it are heavier.

If only B is `READY`, new RPCs go through B even though the resolver still returns A, B, and C. When A or C returns to `READY`, they can participate in subsequent selections.

## 5. Comparing policies and choosing by architecture

| Criterion | `pick_first` | `round_robin` |
|---|---|---|
| Goal | Use one active subchannel | Distribute new RPCs across multiple ready subchannels |
| Backend connections | Prefers one endpoint; tries another address when needed | Maintains subchannels for the endpoint list |
| Load distribution from one client | Focused on the chosen backend | Can utilize multiple backends |
| When an endpoint fails | Can switch to another endpoint | Excludes unready endpoints from current selection |
| Resolver dependency | Needs resolver to supply backup addresses | Needs resolver to supply multiple distinct endpoints |
| Typical scenario | Infrastructure already load-balances in front | Client directly sees multiple instances |

Examples:

- An application calls a Kubernetes ClusterIP virtual IP: Kubernetes infrastructure distributes to pods; `pick_first` may be sufficient because the client sees only one endpoint.
- An application calls a headless Service returning multiple pod IPs: `round_robin` can distribute RPCs directly among pods if the resolver receives those IPs and subchannels are ready.
- A system requires zone-based, weighted, or load-aware routing: basic policies may not be enough; a control plane or extended policy supporting those attributes is needed.

No policy is best in all cases. Choose based on **where load balancing sits**, how many endpoints the client actually sees, readiness behavior, and RPC characteristics.

## 6. Configuring a policy in gRPC Java

Example setting `round_robin` as the default policy for a channel:

~~~java
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;

ManagedChannel channel = ManagedChannelBuilder
        .forTarget("dns:///orders.internal:9090")
        .defaultLoadBalancingPolicy("round_robin")
        .useTransportSecurity()
        .build();
~~~

`defaultLoadBalancingPolicy(...)` is the fallback when the resolver does not provide a service config specifying a policy. The resolver can supply its own service config; in that case, the policy in the service config can determine what is used.

A service config can express a policy in JSON:

~~~json
{
  "loadBalancingConfig": [
    {
      "round_robin": {}
    }
  ]
}
~~~

This is an illustrative structure for the `loadBalancingConfig` field; how the service config is delivered depends on the resolver and channel configuration. The policy must have a provider loaded at runtime. If you specify a policy whose provider is missing in the application, the channel cannot initialize that policy as expected.

In gRPC Java, `pick_first` is a core policy; `round_robin` requires its corresponding provider to be present in the application's dependencies/runtime. Check the dependency graph and channel startup logs rather than assuming every policy is available in every dependency set.

## 7. Extended policies and service mesh

When requirements go beyond the two basic choices, the gRPC ecosystem can use policies supplied by extensions or an xDS control plane. Depending on runtime and version, extended capabilities may include:

- **Weighted:** distributes by weight, e.g., canary gets 5% and stable version gets 95%.
- **Priority/failover:** prefers one endpoint group and fails over to a backup group when the primary group is unavailable.
- **Locality-aware:** prefers endpoints in the zone or cluster closest to the client to reduce latency.
- **Ring hash:** consistent hashing by key, useful when routing-layer affinity is required.
- **Least request:** picks an endpoint based on active request count, if supported by the policy/control plane.

This is not a list of policies built into every gRPC Java client by default. Availability depends on xDS integration, providers, service config, and library versions. You cannot simply call `defaultLoadBalancingPolicy("least_request")` and expect the policy to appear if the runtime has no implementation.

For canary or locality routing, a control plane typically manages weights, endpoints, and policies. The client receives configuration via resolver/xDS and executes selection. Observe the actual applied configuration, not just what was intended in manifests.

## 8. Integrating a shared channel in Spring

In Spring, create a channel per target and reuse it throughout the application lifecycle. Each client service can create stubs from the channel:

~~~java
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrdersGrpcConfiguration {

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

Stub:

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

If there are multiple targets, declare separate channel beans and use clear qualifiers. Do not create a new channel per RPC: doing so increases DNS lookups, TCP connections, TLS handshakes, and thread/buffer overhead.

`useTransportSecurity()` requires a server certificate matching the target's authority/hostname. In production environments, keep certificate verification enabled and configure trust properly; `usePlaintext()` is only appropriate in controlled development environments.

## 9. Readiness, wait-for-ready, and deadlines

Policies pick from subchannels in an eligible state. Having an address in resolver output does not mean the connection is `READY`. A subchannel may be `IDLE`, `CONNECTING`, `TRANSIENT_FAILURE`, or `READY`.

If no backend is ready yet, the client can use `withWaitForReady()` to wait for a connection instead of failing immediately:

~~~java
GetOrderReply reply = orders
        .withWaitForReady()
        .withDeadlineAfter(3, java.util.concurrent.TimeUnit.SECONDS)
        .getOrder(request);
~~~

`waitForReady` does not create new endpoints and does not bypass the deadline. It only allows the RPC to wait within the remaining deadline budget so the channel has a chance to find a ready backend.

Transport readiness also does not replace business health checks. A process may open its gRPC port before finishing data loading or becoming ready to accept requests. Combine health checking, readiness probes, and service discovery that only advertises serviceable endpoints.

## 10. How does a policy select a backend for a server stream?

The load balancing policy selects a backend **when the RPC starts**. For unary RPCs, each new call can be routed to a different subchannel. For server streaming, the entire RPC typically stays pinned to the backend that accepted that call:

~~~text
WatchProgress RPC #1
    -> backend A
    <- event 1 from A
    <- event 2 from A
    <- event 3 from A
    <- stream ends

WatchProgress RPC #2 (new RPC)
    -> backend B may be selected by policy
~~~

`round_robin` does not route individual responses of a single stream to different backends. If backend A fails mid-stream, the current RPC may fail; the policy cannot transparently continue the remainder of the stream on B.

If business requirements need reconnect:

1. Server emits events with a stable sequence/cursor.
2. Client persists a checkpoint after durable processing.
3. When the stream fails, the client starts a new RPC and sends the cursor.
4. The new backend reads the missing portion from shared data storage.

Therefore, long-lived server streams need shared state or a replay/resume mechanism; state residing only in backend A's RAM does not automatically transfer to backend B.

## 11. Testing and observing policies

A test with one server cannot prove `round_robin` distributes across multiple backends. To test it, you need a resolver returning multiple addresses, multiple servers distinguishable by instance ID, and verification of which backend received each RPC.

| Scenario | What to verify |
|---|---|
| Resolver returns one endpoint | Both policies have only one backend to choose |
| Multiple endpoints all ready with `pick_first` | New RPCs focus on the chosen subchannel |
| Multiple endpoints ready with `round_robin` | New RPCs are distributed across subchannels |
| One endpoint transitions to error | Picker stops selecting the unready endpoint |
| Resolver adds or removes an endpoint | Policy updates subchannels according to the new list |
| No endpoint ready | Errors or wait-for-ready obey the deadline |
| Server stream running when backend stops | Current RPC may fail; client resumes with a new RPC if contract supports it |
| Policy provider missing from runtime | Channel cannot apply the configured policy |

Useful operational metrics:

- RPC count per backend and per policy.
- Subchannel count by state (`READY`, `CONNECTING`, `TRANSIENT_FAILURE`).
- Number of resolver address updates.
- Latency and error rate per backend.
- Active long-lived stream count and lifetime per instance.
- Reconnect/resume count after a backend is removed or stopped.

If `round_robin` does not distribute as expected, check in order: whether the resolver returns multiple distinct endpoints, whether a service config overrides the default policy, whether the provider is loaded, and how many subchannels are `READY`. Do not draw conclusions from channel configuration alone.

## 12. Common misconceptions

| Misconception | Accurate understanding |
|---|---|
| `round_robin` always balances CPU evenly | The policy distributes new RPCs in turn across ready subchannels, without measuring business cost |
| DNS returning multiple IPs automatically means round robin | DNS supplies addresses; the gRPC policy selects subchannels |
| `pick_first` cannot switch endpoints | It can try another address when the current endpoint cannot connect |
| Policy switches backends mid-stream | An active RPC usually stays pinned to the backend that accepted it |
| `waitForReady` is an infinite retry | The deadline still bounds waiting time |
| All policies are available in gRPC Java core | Extended policies require appropriate providers/runtime support |
| Creating a new channel helps the policy update faster | Long-lived channels have resolver and subchannel lifecycles to receive updates |

**Key takeaway:** `pick_first` prefers one connectable backend; `round_robin` distributes new RPCs across `READY` subchannels. Extended policies such as weighted, priority, locality-aware, ring hash, or least request depend on providers and a control plane rather than being present by default in every runtime. Choose a policy based on resolver architecture and where the load balancer resides, configure shared channels in Spring, set sensible deadlines/readiness, and remember that a server stream does not migrate backends mid-flight.
