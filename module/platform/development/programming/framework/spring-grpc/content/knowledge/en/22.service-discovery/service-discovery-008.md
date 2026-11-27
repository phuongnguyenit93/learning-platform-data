# Resolver and Load Balancer

In Spring gRPC, service discovery and RPC distribution are two sequential steps with distinct responsibilities. **The name resolver finds the available addresses of a service; the load balancer uses that list to manage connections and pick an endpoint for each RPC.** Separating the two makes it easier to diagnose DNS/registry errors, connection errors, and load-distribution errors accurately.

For example, a client calls the logical target `dns:///orders.default.svc.cluster.local:8443`. The resolver resolves this name into one or more endpoints. The load balancer receives the result, creates or updates subchannels to the endpoints, and selects an appropriate subchannel when a stub executes an RPC. The application keeps using one stable `ManagedChannel` and stub while the endpoint list changes.

## 1. Two Responsibilities in One Flow

```text
Client target URI
      |
      v
NameResolverRegistry -> NameResolver
      |
      | ResolutionResult: endpoint list + attributes/service config
      v
ManagedChannel
      |
      v
LoadBalancer
      |
      +---- create/update/remove Subchannels
      |
      v
Picker selects Subchannel for each RPC
      |
      v
HTTP/2 transport -> gRPC server instance
```

| Component | Question It Answers | Responsibility |
| --- | --- | --- |
| Target URI | Which logical service does the client want to call? | Selects scheme and service name |
| Name resolver | Which addresses does the service currently have? | Queries DNS/registry and emits resolution results |
| Load balancer | Which connection does the next RPC use? | Manages subchannels, connectivity state, and the picker |
| Subchannel | How is a connection to an address group maintained? | Establishes/reconnects transport to endpoints |
| Picker | Should the current call be sent, queued, or failed? | Picks a ready subchannel or returns the corresponding decision |

The resolver does not round-robin RPCs itself. The load balancer does not know all instances in the registry unless the resolver supplies their addresses. Each component builds on the contract of the previous one.

## 2. Name Resolver: From Target to Endpoint List

When a channel is created with `ManagedChannelBuilder.forTarget(...)`, gRPC parses the target URI and chooses a `NameResolverProvider` by scheme. The provider creates a `NameResolver`, which then queries the discovery source.

Example targets:

```text
dns:///orders.default.svc.cluster.local:8443
catalog:///orders
```

`dns` is the standard DNS scheme; `catalog` is an example custom scheme and only works when its provider is registered. The resolver does not need to know whether the client uses `pick_first` or `round_robin`; it only publishes valid endpoints.

A resolution result typically includes:

- A list of `EquivalentAddressGroup` objects, each containing one or more equivalent addresses.
- `Attributes` attached to groups or the result, such as zone/region if needed by policy.
- Service config if the resolver has a configuration source and the channel permits it.

Example emitting a result:

```java
List<EquivalentAddressGroup> groups = new ArrayList<>();
for (InetSocketAddress address : resolvedAddresses) {
    groups.add(new EquivalentAddressGroup(address));
}

NameResolver.ResolutionResult result =
    NameResolver.ResolutionResult.newBuilder()
        .setAddresses(groups)
        .build();

listener.onResult(result);
```

This is the core of a simple resolver. A real resolver must also validate addresses, manage refresh/watch, handle errors, and emit new snapshots on `SynchronizationContext`. Each `onResult(...)` should carry the complete list of currently valid endpoints so the channel can update state consistently.

If DNS/registry cannot resolve the target, the resolver reports an error via the listener. Do not fabricate a fallback address or embed RPC retry algorithms inside the resolver; lookup retries and RPC retries are two different policies.

## 3. Load Balancer: From Endpoint List to RPC Pick

The load balancer receives addresses from the resolver via internal gRPC APIs, creates or updates `Subchannel` objects, and tracks connectivity state. It then supplies a picker that the channel consults for each new RPC.

Core duties:

1. Receive new `ResolvedAddresses`.
2. Compare current endpoints against the new snapshot.
3. Create subchannels for new endpoints and start connecting.
4. Keep valid subchannels; remove or shut down subchannels no longer in the snapshot per policy.
5. Track the connectivity state of each subchannel.
6. Update the picker to select an appropriate subchannel for new RPCs.

Common connectivity states:

| State | Meaning to the Load Balancer |
| --- | --- |
| `IDLE` | Subchannel has no active connection attempt |
| `CONNECTING` | Establishing connection |
| `READY` | Transport is ready to accept RPCs |
| `TRANSIENT_FAILURE` | Connection temporarily failed; may attempt reconnect |
| `SHUTDOWN` | Subchannel has closed |

The picker may return a ready subchannel, tell the channel to wait when no connection is ready yet, or return an error based on state/policy. Thus, "the resolver returned three addresses" does not mean all three are `READY` or that requests are immediately split evenly.

## 4. Common Policies

The resolver provides endpoints; the policy decides how to use them. Two common policies:

| Policy | Selection Behavior | Best Suited When |
| --- | --- | --- |
| `pick_first` | Tries addresses and uses the first ready subchannel in resolver order; switches if needed | You want one stable active connection, discovery usually returns one endpoint, or there is a proxy/service VIP |
| `round_robin` | Distributes RPCs across `READY` subchannels | You want client-side load distribution when the resolver returns multiple independent endpoints |

For example, suppose the resolver returns three Pod IPs. With `pick_first`, the channel typically uses one ready subchannel and does not alternate each call across all three. With `round_robin`, the picker can distribute new RPCs across the `READY` subchannels.

Not every policy is available in every runtime. The policy must be registered/present in the active grpc-java version and selected via service config or channel configuration. An unsupported policy may cause the channel to fall back or fail depending on version/configuration; observe the actual active policy rather than relying solely on declared JSON.

Illustrative service config for round robin:

```json
{
  "loadBalancingConfig": [
    {
      "round_robin": {}
    }
  ]
}
```

This is service config content; supply it to the channel via your project's grpc-java/starter mechanism and confirm that the resolver/channel accepts service config. Do not assume that placing JSON in an arbitrary file causes the channel to read it automatically.

## 5. Integrating with Spring gRPC

In a Spring application, channels should be long-lived and reused across stubs. The target determines the resolver; service config or channel configuration determines the load balancing policy.

Example creating a channel with a DNS target:

```java
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrdersClientConfiguration {

    @Bean(destroyMethod = "shutdown")
    ManagedChannel ordersChannel() {
        return ManagedChannelBuilder
            .forTarget("dns:///orders.default.svc.cluster.local:8443")
            .useTransportSecurity()
            .build();
    }

    @Bean
    OrdersGrpc.OrdersBlockingStub ordersStub(
            ManagedChannel ordersChannel) {
        return OrdersGrpc.newBlockingStub(ordersChannel);
    }
}
```

`OrdersGrpc` is an illustrative name for a generated stub. If a Spring gRPC starter manages channels/clients, configure the target and load balancing/service config through the extension point for your exact starter version; do not manually create extra channels per RPC.

Checklist:

- Does the target have the right scheme for the resolver provider?
- Does the resolver return multiple endpoints as expected?
- Is the load balancing policy registered and actually selected?
- Are TLS authority/certificates valid for the service name?
- Is the channel closed when the Spring context shuts down?

Do not put fixed IPs in channel configuration when dynamic discovery is the goal. Likewise, do not create a new channel every time the endpoint list changes; the resolver and load balancer are designed to update on a live channel.

## 6. How Endpoint Updates Affect the Load Balancer

Suppose the resolver emits a new snapshot:

```text
Old snapshot: A, B
New snapshot: B, C

A -> removed from membership
B -> remains present
C -> new endpoint, needs a subchannel
```

The load balancer processes the change:

- Creates a subchannel for C and connects to the new endpoint.
- Retains subchannel B if address/identity still matches.
- Stops selecting A for new RPCs and shuts down its subchannel as policy/lifecycle allows.
- Updates the picker according to the `READY` state of B and C.

If C is still `CONNECTING`, the picker can continue choosing B instead of sending RPCs onto an unready connection. If no `READY` subchannel remains, the channel can wait, reconnect, or fail according to policy and call deadlines.

Removing an endpoint from a snapshot does not necessarily cancel in-flight RPCs on A. In-flight RPCs and connection draining must be handled separately; do not rely on the resolver emitting a new snapshot to assume existing calls automatically migrate to B or C.

## 7. Health Checking vs. Connectivity and Load Balancing

A `READY` subchannel only indicates the transport is connected. It does not prove the business service is healthy. A server might keep an HTTP/2 connection open even though its database pool is exhausted.

Signals to distinguish:

- **Resolver membership:** is the endpoint still published by the discovery source?
- **Connectivity:** does the subchannel have a ready transport connection?
- **gRPC health:** does the service report `SERVING` or `NOT_SERVING`?
- **Readiness:** is the instance willing and able to receive new traffic?

If client-side gRPC health checking is enabled and supported by the policy, `NOT_SERVING` can prevent the picker from selecting that backend for new RPCs even while transport remains `READY`. Without health checking enabled, merely registering a health service on the server does not automatically change client selection.

You can filter `NOT_SERVING` endpoints at the discovery/resolver source, or use health `Watch` on the client. Pick a clear rule and test propagation; avoid letting the registry, resolver, and health `Watch` hold conflicting states for extended periods.

## 8. Common Issues When Resolver and Load Balancer Interact

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| DNS resolves multiple IPs but traffic hits only one IP | Policy is `pick_first`, or only one subchannel is `READY` | Inspect service config, actual policy, and connectivity state |
| Resolver returns endpoints but RPCs fail `UNAVAILABLE` | Wrong address/port, TLS mismatch, or no subchannel is `READY` | Check endpoints, transport, TLS, and picker state |
| New endpoints are not used | Resolver did not refresh or LB did not receive new snapshot | Track revisions, `onResult` timestamps, and subchannel creation |
| Removed endpoint still receives calls | Old snapshot/cache, propagation delay, or in-flight RPCs | Inspect resolver snapshot, picker, and connection draining |
| Round robin does not work | Policy unsupported/not selected, resolver returns one address, or only one subchannel ready | Check provider, service config, and endpoint list |
| Channel fails to recover after transient error | Resolver does not refresh or subchannel reconnect affected by config | Observe resolver errors, connectivity states, and backoff |
| Healthy instance gets excluded | Wrong readiness/health signal or overly aggressive filter | Compare registry state, health `Watch`, and application readiness |

Diagnose along the chain: target → resolver provider → endpoint snapshot → load balancing policy → subchannel state → picker decision → transport/TLS → RPC status. This chain separates discovery issues from endpoint-usage issues.

## 9. Testing Resolver and Load Balancer

Test each responsibility separately and add integration tests through the channel:

| Test Case | What to Verify |
| --- | --- |
| Valid target | Correct resolver provider selected by scheme |
| Resolver returns one/many endpoints | `ResolutionResult` contains the exact address groups |
| Endpoint added/removed | Load balancer creates/removes subchannels per new snapshot |
| `pick_first` with multiple endpoints | Uses the first ready subchannel per policy |
| `round_robin` with multiple endpoints | New RPCs are distributed across `READY` subchannels |
| One endpoint in `TRANSIENT_FAILURE` | Failing endpoint is not picked while another `READY` endpoint exists |
| All endpoints not `READY` | Picker waits or fails according to state/deadline |
| Endpoint update during in-flight RPC | Current and new calls follow drain/update policy |
| Health `NOT_SERVING` | Backend is not chosen when client health checking is enabled |
| Resolver/channel shutdown | Watches, subchannels, and channel are released per lifecycle |

Use a fake resolver or mock registry to control snapshots and update ordering. Use test servers on dynamic ports to verify which backends actually receive RPCs. For `round_robin`, send enough calls after all subchannels reach `READY`, then verify distribution; do not assert exact equality on a tiny sample because connection timing and picker state can skew small counts.

In-process transport is useful for service/interceptor logic, but does not test DNS, TCP, TLS, or real subchannel connection behavior. Those require integration tests with real transport or a production-like environment.

## 10. Practice Exercise

`OrderService` runs three instances in Kubernetes. DNS returns three Pod IPs, but the client currently uses `pick_first`, concentrating most RPCs on a single instance. The team wants client-side load distribution and wants unhealthy backends removed from the pool.

**Requirements:**

1. Describe the data the resolver must emit to the channel and why the resolver does not pick backends per RPC itself.
2. Configure service config to use `round_robin` if the policy is supported.
3. Verify all three subchannels reach `READY` before evaluating distribution.
4. Add health checking or readiness filtering so `NOT_SERVING` endpoints are not picked.
5. When an endpoint is removed, verify subchannels update and in-flight RPCs drain properly.
6. Write an integration test comparing `pick_first` and `round_robin`, including one failing endpoint and one endpoint list update.

**Self-Check Questions:**

- How do the resolver and load balancer differ in inputs, outputs, and responsibilities?
- What data does `ResolutionResult` carry?
- Why do multiple endpoints in a resolver result not guarantee round-robin?
- Does a `READY` subchannel imply the service is `SERVING`?
- What does the picker decide when no subchannel is ready yet?
- When an endpoint is removed from the snapshot, do in-flight RPCs automatically fail over to another endpoint?
- When is `pick_first` more appropriate than `round_robin`?
- How do you verify which policy the channel is actually using?

**Key Takeaways:** The resolver turns a target into an endpoint snapshot; the load balancer turns that snapshot into subchannels and a picker for RPCs. The resolver owns discovery and membership updates; the load balancer owns connections, connectivity state, and endpoint selection. In Spring gRPC, keep channels long-lived, configure supported policies, distinguish connectivity from health, and test both endpoint updates and real RPCs.
