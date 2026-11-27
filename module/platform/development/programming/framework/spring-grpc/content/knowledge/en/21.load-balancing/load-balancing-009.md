# Coordinating load balancing with service discovery

## 1. Discovery finds instances; the load balancer chooses an instance

In **SPRING_GRPC**, clients call services using gRPC Java and stubs generated from Protocol Buffers contracts. When a service runs on multiple instances, the client needs to know which instances exist and which ones can accept traffic. **Service discovery** supplies the instance list; **load balancing** picks one instance from that list for each new RPC.

These two responsibilities follow sequentially:

- **Service discovery:** finds and updates addresses of instances belonging to a logical service.
- **Name resolver:** translates discovery results into endpoints understood by the gRPC channel.
- **Load balancing policy:** uses endpoints and subchannel states to pick a backend for an RPC.
- **Subchannel/transport:** establishes and maintains the connection to the selected backend.

For example, the `orders` service has three replicas:

~~~text
Service registry / control plane
  orders -> [A, B, C]
              |
              v
        gRPC NameResolver
              |
              v
      ManagedChannel + policy
         /       |       \
    subchannel A B       C
        |       |        |
      server A server B server C
~~~

The registry does not decide whether the next RPC goes to A or B. It provides the instance list. The resolver passes the list to the channel; the load balancer's picker selects the subchannel.

## 2. Flow from instance registration to RPC

A typical lifecycle includes these steps:

1. An instance starts up and creates its gRPC server.
2. The instance finishes initializing mandatory dependencies and transitions to ready.
3. The instance registers its service name, host, port, and required metadata with the registry.
4. The client resolver receives the endpoint list from the registry or DNS.
5. The resolver delivers the new list to `ManagedChannel`.
6. The load balancing policy creates/updates subchannels and picks a backend for new RPCs.
7. When the instance stops or ceases to be ready, the registry/resolver updates the list so the policy stops picking it.

~~~mermaid
sequenceDiagram
    participant S as Server instance
    participant R as Service registry
    participant N as NameResolver
    participant C as ManagedChannel
    participant P as Load balancer
    S->>S: Initialize service and dependencies
    S->>R: Register once ready
    N->>R: Watch/query service endpoints
    R-->>N: Instance list
    N-->>C: ResolutionResult
    C->>P: Update endpoints/subchannels
    Note over P: Picker selects backend for new RPCs
    S->>R: Deregister on drain/shutdown
    R-->>N: Updated endpoint list
    N-->>C: Updated ResolutionResult
    C->>P: Exclude endpoint from new selections
~~~

Registering too early can send RPCs to an instance that opened its port before loading config or connecting to its database. Deregistering too late can leave clients picking an instance that is shutting down. Registration and deregistration timing must align with readiness and graceful shutdown.

## 3. Common types of service discovery

| Mechanism | Endpoint source | How the client receives updates |
|---|---|---|
| DNS | A/AAAA records or service records | DNS resolver refreshes per runtime mechanism and caches |
| Registry such as Consul/Eureka | Registered instance list | Polling, watch, or registry adapter |
| Kubernetes Service | ClusterIP or pod IPs depending on Service type | DNS, API/control plane, or cluster proxy |
| xDS/control plane | Endpoints and routing config distributed by control plane | xDS protocol, typically via ADS/EDS and associated service config |
| Static resolver | Fixed configured list | Changes only when configuration/channel is updated |

Not every mechanism integrates into gRPC Java out of the box. The built-in DNS resolver handles DNS targets. For Consul, Eureka, or custom registries, applications typically need a custom `NameResolverProvider`, a compatible adapter, or xDS integration. Spring Cloud `DiscoveryClient` can supply instance lists to an adapter, but by itself does not turn an arbitrary `ManagedChannel` into a discovery-enabled gRPC client.

## 4. Connecting a registry to gRPC NameResolver

gRPC Java uses `NameResolver` to translate a target into transport addresses. With a custom registry, you can implement `NameResolverProvider` for a scheme such as `consul`, then build the target:

~~~java
ManagedChannel channel = ManagedChannelBuilder
        .forTarget("consul:///orders")
        .defaultLoadBalancingPolicy("round_robin")
        .useTransportSecurity()
        .build();
~~~

The target `consul:///orders` only works when the application has registered a custom provider handling the `consul` scheme. It is not a built-in scheme in every gRPC Java runtime.

Inside the resolver, the instance list is converted into `EquivalentAddressGroup` entries. The core part of publishing results looks like:

~~~java
import io.grpc.Attributes;
import io.grpc.EquivalentAddressGroup;
import io.grpc.NameResolver;

import java.util.List;

void publishEndpoints(
        NameResolver.Listener2 listener,
        List<EquivalentAddressGroup> addresses) {

    NameResolver.ResolutionResult result =
            NameResolver.ResolutionResult.newBuilder()
                    .setAddresses(addresses)
                    .setAttributes(Attributes.EMPTY)
                    .build();

    listener.onResult(result);
}
~~~

This illustrates part of a custom resolver; constructing `InetSocketAddress`, mapping metadata, and managing listener lifecycles belong to the specific implementation. The resolver must emit updates when the registry changes, not merely read the registry once when creating the channel.

If the registry has no valid endpoints, the resolver must represent an empty state or report a resolution error per the implementation contract. Do not silently retain revoked endpoints indefinitely if doing so risks routing traffic to unsafe instances. If using last-known-good endpoints to tolerate registry outages, enforce a clear TTL, time cap, and metrics.

## 5. Integrating Spring DiscoveryClient

In applications using Spring Cloud, `DiscoveryClient` can return instances by service ID:

~~~java
List<ServiceInstance> instances =
        discoveryClient.getInstances("orders");
~~~

A custom adapter can:

1. Retrieve `ServiceInstance` entries from the discovery client.
2. Extract host/port and allowed metadata.
3. Check status or readiness attributes according to the discovery source.
4. Convert each instance into an `EquivalentAddressGroup`.
5. Deliver the `ResolutionResult` to gRPC's listener.

`getInstances("orders")` only queries the list at the moment of the call. For the channel to update when topology changes, the adapter needs a refresh mechanism: registry watches/events if available, or periodic polling with backoff. Never call `getInstances` per RPC; that puts unnecessary load on the registry and adds latency.

In Spring, custom resolvers/providers and `ManagedChannel` can be managed as beans. However, how providers are registered and how bean lifecycles are wired must match the project's specific Spring gRPC/Spring Cloud starter. There is no single universal property across all starters that automatically wires every registry into every gRPC channel.

## 6. How do the resolver and load balancing policy coordinate?

The resolver supplies the endpoint list. The policy decides how to use that list:

| Discovery returns | Policy | Outcome |
|---|---|---|
| One endpoint | `pick_first` | New RPCs use the single endpoint when ready |
| Multiple endpoints | `pick_first` | Prefers one active subchannel; tries others when needed |
| Multiple endpoints | `round_robin` | Distributes new RPCs across `READY` subchannels |
| Multiple endpoints with locality/weight attributes | Policy supporting those attributes | Can prefer zones or weights if supported by provider/control plane |
| Empty list | Any policy | No backend to pick; RPCs may wait or fail per deadline |

Example service config setting a policy:

~~~json
{
  "loadBalancingConfig": [
    {
      "round_robin": {}
    }
  ]
}
~~~

The service config can be delivered by the resolver alongside resolution results or set as the channel's default configuration. Configuration from the resolver can take precedence over default configuration. The policy provider must be present at runtime; merely writing `round_robin` in JSON does not install that provider.

A registry may return metadata such as zone, region, or weight. Such metadata only influences selection if the resolver maps it into attributes understood by the policy, or if a control plane translates it into policy configuration. Basic `round_robin` does not balance by CPU, latency, or arbitrary weights.

## 7. Client-side discovery and server-side load balancing

Not every system exposes individual replicas to gRPC clients:

| Model | Address the client sees | Where backends are selected |
|---|---|---|
| Client-side discovery | Multiple individual endpoints | gRPC resolver and load balancing policy |
| Server-side/network LB | One VIP or proxy hostname | Network load balancer |
| Sidecar/service mesh | Local proxy address or endpoints supplied by xDS | Sidecar/proxy or gRPC xDS client |
| Kubernetes ClusterIP | Typically one virtual IP | Kubernetes network/service proxy layer |
| Kubernetes headless Service | Can be multiple pod IPs | Client can pick individual pods if resolver receives the list |

Avoid accidentally stacking multiple load balancing layers without understanding the effects. For example, if the client only sees a ClusterIP, client-side `round_robin` cannot distribute directly across pods behind that IP. Conversely, if the client uses a headless Service and `round_robin`, each RPC can be sent directly to a pod.

With a service mesh, clarify whether the gRPC client connects to a sidecar or directly to endpoints. The proxy may already perform retries, outlier detection, locality routing, or traffic shaping; adding redundant configuration on the client can cause nested retries or unpredictable distribution.

## 8. Readiness, health, and registration state

A registry can contain starting instances or unserviceable instances if health signals update slowly. Agree on how an instance becomes eligible to be advertised:

- **Liveness:** process is alive; usually governs container restarts.
- **Readiness:** instance is ready to accept new traffic.
- **gRPC health:** whether a specific service is `SERVING` or `NOT_SERVING`.
- **Connectivity:** subchannel is connected and in `READY` state.

These signals do not replace one another. `READY` reflects only transport; having an endpoint in the registry does not prove the service is `SERVING`.

One coordination pattern:

1. Start the server and dependencies.
2. Register the instance only after readiness is reached.
3. Update health if a mandatory dependency loses serviceability.
4. On shutdown, set `NOT_SERVING` or readiness false before deregistering.
5. Wait for propagation and drain in-flight RPCs before closing the server.

If the client uses gRPC client-side health checking, the service must expose the health service and the client must be configured to watch the exact service name. If the registry already removes endpoints based on readiness, the client may no longer see the endpoint; avoid creating two conflicting sources of health truth.

## 9. Endpoint updates, caching, and stale discovery

Instance lists change continuously during scale-outs, scale-ins, rolling deployments, or network incidents. Resolvers must receive and apply updates appropriately:

~~~mermaid
sequenceDiagram
    participant D as Discovery registry
    participant N as NameResolver
    participant C as ManagedChannel
    participant L as Load balancer
    D-->>N: [A, B]
    N-->>C: ResolutionResult [A, B]
    C->>L: Create/update subchannels
    Note over D: Instance C is added
    D-->>N: [A, B, C]
    N-->>C: ResolutionResult [A, B, C]
    C->>L: Add subchannel C
    Note over D: Instance A begins draining
    D-->>N: [B, C]
    N-->>C: ResolutionResult [B, C]
    C->>L: Remove endpoint from new selections
~~~

Issues to control:

- **TTL/caching:** clients may keep seeing old endpoints after the registry changed.
- **Disconnected watches:** resolvers must reconnect with backoff without spawning duplicate watchers.
- **Rapid bursts of updates:** coalesce/debounce rapid changes to avoid churning subchannels.
- **Duplicate endpoints:** normalize host/port and deduplicate before publishing.
- **Empty results:** define clearly whether RPCs fail fast or wait-for-ready within the deadline.
- **Stale last-known-good:** if keeping old endpoints during registry failures, cap their age and enforce safety policies.

Do not recreate `ManagedChannel` on every registry change. The resolver sends a new `ResolutionResult` so the channel and policy adjust subchannels within the existing lifecycle.

## 10. TLS and service identity when addresses change

Discovery can return different IPs or hostnames per instance, yet the client must still verify TLS identity. For example, the target is:

~~~text
consul:///orders
~~~

The registry may return `10.60.0.11:9090`, but the backend certificate must be valid for the authority/hostname used by the client per gRPC configuration. Do not switch TLS authority to an IP just because the resolver received an IP address. If backends use different certificates or multiple SANs, trust and authority must be designed consistently across the entire endpoint set.

The registry is also a data source controlling where clients send traffic. Trust only authenticated registries/control planes, protect service registration write permissions, and restrict endpoint metadata. If an attacker can register a rogue endpoint, clients could be redirected to an untrusted server.

## 11. Retries, health, and discovery need a unified policy

When a backend fails, these mechanisms serve distinct roles:

| Mechanism | Responsibility |
|---|---|
| Discovery/resolver | Updates which endpoints remain advertised |
| Health/outlier detection | Evaluates whether a backend should accept new RPCs |
| Load balancing | Picks a subchannel among eligible endpoints |
| Retry | Creates a new attempt when status and commitment allow |
| Application resume | Starts a new RPC with cursor/checkpoint to continue a stream |

If the resolver keeps advertising backend A, no health checker excludes A, and `pick_first` keeps choosing A, retries may keep hitting A even though A returns `UNAVAILABLE` at the application layer. Decide which mechanism owns ejection and recovery timing.

Do not enable retries simultaneously in the gRPC client, service mesh, and application loop without accounting for total attempts. Nested retries can amplify load and blow past deadlines. Use idempotency keys for side effects and cursors for resuming committed server streams.

## 12. Testing discovery and load balancing coordination

A test creating a `ManagedChannel` and a single server does not verify dynamic discovery. Test the resolver, policy, and instance lifecycle:

| Scenario | What to verify |
|---|---|
| Registry returns A, B, C | Resolver publishes all endpoints |
| `round_robin`, all endpoints `READY` | New RPCs are distributed across multiple instances |
| Registry adds D | Resolver updates and policy can use D once subchannel is ready |
| Registry removes A | New RPCs stop choosing A after update applies |
| A is not ready | A is not advertised or is excluded by health policy |
| Watch/registry temporarily disconnects | Resolver reconnects with backoff; no duplicate watchers created |
| Registry returns duplicate endpoints | Resolver normalizes and avoids duplicate subchannels |
| Registry returns empty list | Fail-fast/wait-for-ready behavior respects deadline |
| TLS on new endpoint | Certificate and authority are still verified |
| Rolling shutdown | Deregister/drain does not cut off in-flight RPCs within grace period |
| Service config changes | Channel applies new policy as supported by runtime |
| Retries after endpoint failure | New attempts use updated backend set; retry limits respected |

You can use a fake registry and custom `NameResolverProvider` for deterministic testing. For DNS, Kubernetes, Consul/Eureka, or xDS, write integration tests in a realistic environment because TTLs, caches, watchers, proxies, and certificates are not fully simulated by in-process transport.

## 13. Metrics and diagnostics

Track both discovery and backend selection:

- Instance count returned by the registry per service.
- Endpoint count published by the resolver and update timestamps.
- Lag from register/deregister until client application.
- `READY`, `CONNECTING`, and `TRANSIENT_FAILURE` subchannel counts.
- RPC counts by backend, method, and status code.
- Count of stale, duplicate, or unready endpoints.
- Watcher reconnect duration and registry query failure count.
- Retry, deadline, and stream reconnect rates per backend.

When an instance receives no RPCs, check sequentially: whether the registry registered it, whether the resolver received the endpoint, whether the channel applied the result, whether the subchannel is `READY`, and whether the policy selects that endpoint. Checking only replica counts in Kubernetes or records in the registry is not enough.

## 14. Common integration mistakes

| Mistake | Consequence | How to fix |
|---|---|---|
| Assuming Spring `DiscoveryClient` automatically integrates with every gRPC channel | Channel still uses only the default resolver | Write an adapter/custom resolver or use appropriate xDS integration |
| Querying the registry on every RPC | Increases latency and control-plane load | Watch/poll inside the resolver over the channel lifecycle |
| Registering instances before readiness | Clients send requests to unready instances | Publish only after readiness |
| Deregistering after the server stops | Clients keep picking stale endpoints | Mark unready/deregister before graceful shutdown |
| Registry returns multiple IPs yet policy uses only one | Replicas are underutilized | Choose an appropriate policy and check subchannels |
| Client and proxy both retry without limits | Retry storms and missed deadlines | Pick one retry strategy with an overall attempt budget |
| Treating `READY` as `SERVING` | Backend with broken dependencies still receives RPCs | Combine with gRPC health/readiness |
| Trusting unauthenticated registry metadata | Risk of routing traffic to rogue endpoints | Secure the registry/control plane and verify TLS |

**Key takeaway:** Service discovery locates and updates endpoints; gRPC `NameResolver` converts endpoints into `EquivalentAddressGroup` entries; the load balancing policy picks a subchannel for each new RPC. With Spring Cloud registries, you need an adapter/custom resolver or compatible control plane because `DiscoveryClient` does not automatically wire into every `ManagedChannel`. Align registration, readiness, and deregistration, keep resolver updates controlled, choose the right policy, and maintain trustworthy TLS authority for stable discovery and load balancing coordination.
