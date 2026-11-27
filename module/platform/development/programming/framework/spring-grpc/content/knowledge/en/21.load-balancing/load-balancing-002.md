# Name resolution returning multiple addresses

## 1. The resolver supplies endpoints; the policy decides how to use them

In **SPRING_GRPC**, the client calls a gRPC service through a `ManagedChannel` and stubs generated from Protocol Buffers contracts. When a service has multiple instances, the client needs to resolve the service name into connectable addresses. **Name resolution returning multiple addresses** means the resolver provides the channel with a set of endpoints instead of a single address.

For example, the `inventory.internal:9090` service has three backends:

~~~text
inventory.internal
  ├── 10.30.1.21:9090
  ├── 10.30.1.22:9090
  └── 10.30.1.23:9090
~~~

The resolver discovers those addresses and notifies the gRPC channel. A **load balancing policy** receives the list along with connection states, then picks a subchannel for a new RPC.

Two responsibilities must be distinguished:

- **Name resolver:** "What endpoints exist for this service?"
- **Load balancing policy:** "Among the available endpoints, where should the next RPC go?"

DNS returning three addresses does not automatically mean those three addresses will receive an equal number of requests. If the policy only uses one endpoint at a time, the remaining addresses may only be used when the current endpoint is unavailable. To distribute new RPCs across multiple backends, the client needs an appropriate policy such as `round_robin`.

## 2. Target and DNS resolution mechanism in gRPC Java

A gRPC target is a URI specifying the resolution mechanism and service address. With the built-in DNS resolver, the common form is:

~~~text
dns:///inventory.internal:9090
~~~

In this URI:

- `dns` is the scheme selecting the DNS name resolver.
- The authority part is empty; hence the URI has three slashes after the colon.
- `inventory.internal:9090` is the hostname and port to resolve.

The resolver looks up the hostname and may receive multiple IP addresses, such as IPv4 (A) and IPv6 (AAAA) records. The actual result depends on DNS, the network environment, address ordering, and the runtime's resolver.

~~~text
DNS answer:
  inventory.internal.  A     10.30.1.21
  inventory.internal.  A     10.30.1.22
  inventory.internal.  A     10.30.1.23

Name resolver result:
  10.30.1.21:9090
  10.30.1.22:9090
  10.30.1.23:9090
~~~

Do not assume DNS always returns multiple addresses. If DNS returns only one address, the client only has one endpoint to choose from. Also do not assume every DNS record represents a separate backend: an address may be a virtual IP, proxy, or infrastructure load balancer.

## 3. The resolver returns an address list to the gRPC channel

In gRPC Java, resolution results are represented via `ResolutionResult` and a list of `EquivalentAddressGroup`. Each group contains one or more addresses considered equivalent for connection purposes. In a simple example, each backend has one group:

~~~java
import io.grpc.EquivalentAddressGroup;
import io.grpc.NameResolver;

import java.net.InetSocketAddress;
import java.util.List;

List<EquivalentAddressGroup> endpoints = List.of(
        new EquivalentAddressGroup(
                new InetSocketAddress("10.30.1.21", 9090)),
        new EquivalentAddressGroup(
                new InetSocketAddress("10.30.1.22", 9090)),
        new EquivalentAddressGroup(
                new InetSocketAddress("10.30.1.23", 9090))
);

NameResolver.ResolutionResult result =
        NameResolver.ResolutionResult.newBuilder()
                .setAddresses(endpoints)
                .setAttributes(io.grpc.Attributes.EMPTY)
                .build();

// In a custom NameResolver, deliver the result to the listener:
listener.onResult(result);
~~~

This illustrates how a result is constructed; `listener` belongs to the lifecycle of a custom `NameResolver`. When using the built-in DNS resolver, the application does not build these groups manually. The resolver sends the list to the channel, and the policy uses it to create or update subchannels.

`EquivalentAddressGroup` is not a protobuf request or response. It is an address unit at the transport layer. One group can contain multiple equivalent socket addresses; the number of groups and how the policy interprets them affect how subchannels are created.

The resolver can emit new results when addresses change. The channel does not need to be recreated just because DNS records change; the policy receives the update and adjusts subchannels according to the new result.

## 4. Multiple addresses do not mean round robin

Suppose the resolver returns three endpoints A, B, and C. The distribution result depends on the policy:

~~~text
Resolver:
  [A, B, C]

pick_first:
  RPC 1 -> A
  RPC 2 -> A
  RPC 3 -> A
  ...
  If A cannot connect, the policy tries another endpoint based on state.

round_robin:
  RPC 1 -> A
  RPC 2 -> B
  RPC 3 -> C
  RPC 4 -> A
  ...
~~~

This is a conceptual diagram when all backends are ready. The actual ordering also depends on subchannel states, resolver updates, and the active picker.

| Resolver returns | Policy | Expected behavior |
|---|---|---|
| One address A | `pick_first` | RPCs go to A |
| A, B, C | `pick_first` | Uses one connectable endpoint; can try other addresses when needed |
| A, B, C | `round_robin` | Distributes new RPCs across ready subchannels |
| A, B, C but only B is ready | `round_robin` | New RPCs are picked from B while B is the only ready endpoint |
| Empty list | Any policy | No backend to pick; RPC may wait or fail per readiness/deadline |

A common point of confusion is that **DNS round robin** and the **gRPC `round_robin` policy** are not the same mechanism. DNS may rotate order or return multiple records, but DNS caching and resolvers can keep the order unchanged between lookups. The gRPC policy is what selects a subchannel per RPC based on the resolved endpoints.

## 5. Configuring a client to use multiple addresses with round_robin

When the resolver returns multiple distinct endpoints, the client can configure the channel to use `round_robin`:

~~~java
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;

ManagedChannel channel = ManagedChannelBuilder
        .forTarget("dns:///inventory.internal:9090")
        .defaultLoadBalancingPolicy("round_robin")
        .useTransportSecurity()
        .build();
~~~

Stubs are created from the channel and used as usual:

~~~java
InventoryGrpc.InventoryBlockingStub inventory =
        InventoryGrpc.newBlockingStub(channel);

StockReply reply = inventory
        .withDeadlineAfter(2, java.util.concurrent.TimeUnit.SECONDS)
        .getStock(StockRequest.newBuilder()
                .setSku("SKU-42")
                .build());
~~~

`defaultLoadBalancingPolicy("round_robin")` is only the fallback policy when the resolver does not provide a service config with another policy. If the resolver returns a service config containing a load balancing policy, that configuration can determine the active policy. The `round_robin` provider must also be available at runtime; if the provider is missing, the channel cannot apply that policy.

Channels should be reused throughout the application lifecycle. Do not create a new channel for every request, as that increases connections, TLS handshakes, DNS resolution, and resource management overhead.

## 6. When DNS returns multiple addresses in Kubernetes

DNS results depend on the Service type and cluster configuration:

| Service type | What DNS typically provides | Who selects the pod/backend? |
|---|---|---|
| ClusterIP | A single Service virtual IP | Kubernetes network/service proxy |
| Headless Service | Can return pod IP addresses | Client can see individual endpoints if the resolver receives that list |

With ClusterIP, client-side `round_robin` may see only one address. Load distribution to pods happens in the Kubernetes networking layer. Switching the gRPC policy to `round_robin` does not make the client aware of the pods behind the virtual IP.

With a headless Service, DNS can return multiple pod IPs. When the gRPC resolver receives those IPs as multiple endpoints, a policy like `round_robin` can create subchannels and distribute new RPCs across ready backends.

Do not infer from Service YAML alone how many addresses the client will actually see. Check DNS answers from the exact namespace/network where the client runs, and inspect resolver results if suitable tracing tools are available. DNS records can be affected by TTL, JVM caching, node caching, or intermediate resolvers.

## 7. Resolver refresh and endpoint lifecycle

Endpoint lists are not static. Instances can be added, removed, change IPs, or temporarily lose connectivity. The name resolver can emit new results according to the provider's refresh mechanism. Upon receiving an update, the channel and policy adjust subchannels:

~~~mermaid
sequenceDiagram
    participant R as Name resolver
    participant C as ManagedChannel
    participant L as Load balancer
    participant B as Backend instances
    R-->>C: ResolutionResult [A, B]
    C->>L: Update addresses
    L->>B: Create/maintain subchannels A and B
    Note over B: Instance C is deployed
    R-->>C: ResolutionResult [A, B, C]
    C->>L: Update list
    L->>B: Create subchannel C
    Note over L: New RPCs can select C when ready
~~~

A few things to keep in mind:

- The resolver updating addresses does not mean the connection to a new endpoint is immediately `READY`.
- A new endpoint may require DNS lookup, TCP connect, TLS handshake, and health/readiness checks.
- Endpoints removed from the resolution result should not be selected by the picker for new RPCs after the update is applied; in-flight RPCs may still take time to complete or fail depending on the transport.
- If a DNS cache retains old results, the client may not see changes immediately. TTL is not a guarantee that every caching layer refreshes simultaneously.
- The resolver may return a resolution error; the channel must transition state appropriately and the client needs deadlines or bounded wait-for-ready.

Do not set a timer in business services to recreate channels every few seconds. Use the resolver and channel lifecycle properly; refreshing and updating subchannels belong in the name resolution/load balancing layer.

## 8. When there are no addresses or no ready backend

These two states are different:

- **No addresses:** the resolver has not found any endpoints, returned an empty list, or reported a resolution error.
- **Addresses exist but none are ready:** the resolver found endpoints, but subchannels have not connected yet or are in a failure state.

When no backend is ready, the client can fail immediately or wait if the RPC uses `withWaitForReady()`. Even when waiting, the deadline still bounds the total time:

~~~java
StockReply reply = inventory
        .withWaitForReady()
        .withDeadlineAfter(3, java.util.concurrent.TimeUnit.SECONDS)
        .getStock(request);
~~~

`waitForReady` is useful when endpoints may appear or connections may recover within a short wait. It does not create new endpoints, does not fix DNS failures, and does not let requests wait indefinitely. When the deadline expires, the client still receives a deadline-exceeded outcome.

An address appearing in DNS also does not prove the application behind it is business-ready. To avoid sending RPCs to an instance that has just started and cannot serve yet, combine readiness probes/service health checking and only publish eligible endpoints.

## 9. Resolved addresses and TLS authority

Name resolution determines the socket address to connect to, but does not replace server authentication. The client must still verify TLS identity against an authority/hostname matching the certificate.

For example, a client connects to target `dns:///inventory.internal:9090`. DNS may return IP `10.30.1.21`, but the server certificate is usually issued for the service name `inventory.internal`. Resolving the name to an IP does not mean the client should switch its TLS identity to that IP.

~~~java
ManagedChannel channel = ManagedChannelBuilder
        .forTarget("dns:///inventory.internal:9090")
        .defaultLoadBalancingPolicy("round_robin")
        .useTransportSecurity()
        .build();
~~~

Only configure an authority override when the TLS/proxy architecture requires it and the corresponding certificate name has been verified. Do not disable certificate verification to "fix" errors caused by DNS returning multiple IPs. If endpoints have different TLS identities, an authority and trust design compatible with the entire backend set is required.

## 10. Testing a resolver returning multiple addresses

A test calling a single server cannot prove the resolver returns multiple endpoints or that the policy distributes across them. Separate tests for the resolver, policy, and DNS environment:

| Test | How to check | Expected result |
|---|---|---|
| Resolver returns one endpoint | Fake resolver returns A | Channel has one endpoint to select |
| Resolver returns multiple endpoints | Fake resolver returns A, B, C | Policy receives all three groups |
| `pick_first` with multiple endpoints | Observe which backend receives RPCs | One endpoint is preferred; others may be tried when needed |
| `round_robin` with multiple ready endpoints | Send multiple new unary RPCs and record instance IDs | RPCs are distributed across ready backends |
| One endpoint loses connectivity | Stop backend B | New RPCs continue through other ready endpoints per policy |
| Resolver adds/removes addresses | Emit new resolution results | Subchannels are updated |
| DNS caching | Change records in test environment | Measure actual lag before client sees new endpoints |
| No ready endpoint | Combine wait-for-ready and deadline | RPC waits within budget or ends with status |
| TLS across multiple IPs | Each backend presents a valid certificate for the authority | Secure connections succeed to working endpoints |

For custom resolvers, you can create a test `NameResolverProvider` and emit `ResolutionResult` containing multiple `EquivalentAddressGroup` entries. For real DNS, test in a production-like environment because DNS caching, network policies, headless/ClusterIP services, and TLS can all make behavior differ from an in-process test.

Metrics to observe:

- Number of addresses per resolution and resolver refresh count.
- Subchannel count by state (`IDLE`, `CONNECTING`, `READY`, `TRANSIENT_FAILURE`).
- Number of RPCs selected per backend.
- Rate of `UNAVAILABLE`, deadline, and TLS errors per endpoint.
- Time from endpoint appearance until its subchannel becomes ready.
- Latency distribution and active long-lived stream count per backend.

If three addresses are returned by the resolver but only one backend receives requests, check the active policy, service config, whether the provider is loaded, and how many subchannels are `READY`. Do not look only at the DNS answer and conclude load balancing is working.

## 11. Common mistakes

| Mistake | Consequence | How to fix |
|---|---|---|
| Assuming DNS returning multiple IPs means requests are split evenly | RPCs may still pile onto one endpoint depending on policy | Configure and verify the load balancing policy |
| Using `round_robin` when the resolver returns only one virtual IP | No multiple client-side endpoints to distribute across | Consider headless/service discovery or infrastructure load balancing |
| Confusing DNS round robin with gRPC `round_robin` | Wrong expectations about ordering and distribution | Distinguish DNS answers from the gRPC picker |
| Creating a new channel after every resolution | Unnecessary connections and handshakes | Keep a long-lived channel and let the resolver update it |
| Assuming a newly appeared endpoint is already `READY` | RPCs may still wait or fail | Observe subchannel state and health/readiness |
| Ignoring DNS caching | Client keeps using stale addresses | Check TTL and caches along the resolution path |
| Using an IP instead of hostname as TLS identity | Certificate may mismatch | Keep the authority aligned with server identity |
| Assuming a server stream migrates automatically when an endpoint fails | Current RPC may terminate mid-stream | Reconnect with a new RPC and resume via cursor if needed |

**Key takeaway:** Name resolution returning multiple addresses tells the gRPC channel the set of connectable backends; it does not decide request distribution by itself. The resolver provides `EquivalentAddressGroup` entries, while a load balancing policy such as `pick_first` or `round_robin` chooses subchannels based on addresses and readiness. Verify that DNS actually returns multiple endpoints, understand the difference between ClusterIP and headless Services, keep channels long-lived so the resolver can update them, and keep TLS authority aligned with server identity.
