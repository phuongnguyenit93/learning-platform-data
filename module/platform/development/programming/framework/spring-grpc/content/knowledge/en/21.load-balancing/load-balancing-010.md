# Balancing across regions or zones

A gRPC service can run across multiple zones within a single region or across multiple geographic regions. How requests are distributed across these locations directly impacts latency, fault tolerance, data transfer costs, and data consistency. A policy that blindly splits requests evenly across all endpoints can send requests to a distant region even when a nearby zone still has capacity.

**Balancing across regions or zones** means choosing where to process RPCs based on locality (deployment location), endpoint status, capacity, and availability goals. This lesson belongs to the **Load balancing** chapter of the **SPRING_GRPC** module: developing gRPC services in the Spring ecosystem with Protocol Buffers contracts, generating Java code, and implementing clients/servers for unary or streaming RPCs; learners handle metadata, deadlines, statuses, interceptors, TLS, integration testing, and performance and reliability monitoring. The focus here is designing locality-aware routing across zones and regions for gRPC clients.

## 1. Region, zone, and locality

- **Region** is a geographic area with dedicated infrastructure, typically having higher network latency to other regions compared to intra-region communication. Example: Southeast Asia or East Asia.
- **Zone** is an isolated deployment domain within a region, typically corresponding to a cloud provider's availability zone. Zones within the same region usually have low-latency connectivity, yet can still fail independently.
- **Locality** is the location label used by the load balancing system to group endpoints. A locality is commonly described by region, zone, and optionally a sub-zone.

For example, an Inventory service has endpoints in three zones of region A and two zones of region B:

~~~text
Region A
  zone-a: inventory-a1, inventory-a2
  zone-b: inventory-b1, inventory-b2
  zone-c: inventory-c1

Region B
  zone-a: inventory-rb-a1, inventory-rb-a2
  zone-b: inventory-rb-b1
~~~

A client in region A/zone-a should generally prefer nearby endpoints to reduce latency and cross-zone traffic. If that locality loses capacity or becomes overloaded, the client can shift to another zone in the same region. Another region acts as the next fallback layer, depending on RTO, RPO, and cost targets.

Do not equate locality with hostname or IP. Endpoints can change during autoscaling, rolling deployments, or failover; locality is an infrastructure attribute provided by service discovery or the control plane.

## 2. Why plain round-robin is not enough

gRPC client-side load balancing picks a subchannel/endpoint for each RPC. With the round-robin policy, endpoints in the `READY` state are selected in rotation. This works well when all endpoints have equivalent cost and location.

However, round-robin over a flat endpoint list does not inherently know which endpoints sit in the same zone or region as the client. If a resolver returns endpoints from multiple regions, the client can distribute requests to a distant region even while nearby endpoints remain healthy.

| Selection method | Behavior | Limitations |
| --- | --- | --- |
| pick-first | Selects the first usable endpoint in the resolver list. | Does not distribute load evenly; outcome depends on ordering and connectivity. |
| round-robin | Rotates across `READY` endpoints. | Does not inherently prefer nearby zones or recognize cross-region cost. |
| Locality-aware | Selects locality by priority/weight, then picks an endpoint within that locality. | Requires discovery/control plane to supply locality metadata and compatible policy. |
| Proxy/service mesh routing | Proxy or mesh applies locality, health, and failover policies. | Requires configuring, operating, and observing an additional infrastructure tier. |

In gRPC, HTTP/2 multiplexes many RPCs over a single channel. Using only one TCP connection through an L4 load balancer can pin many RPCs to one backend due to connection affinity. Client-side load balancing or an L7 proxy that understands gRPC RPC-level routing distributes calls at the proper granularity. A streaming RPC stays pinned to the backend that accepted the stream until the stream ends; the load balancer does not route individual messages of the same stream to different backends.

## 3. Locality-aware routing model

A locality-aware policy typically performs two steps:

1. Select a locality by priority or weight, based on the client's location, locality health, and capacity.
2. Select an endpoint within the chosen locality using an appropriate policy such as round-robin.

Example three-tier policy:

| Priority | Locality | Purpose |
| --- | --- | --- |
| Primary | Current zone | Minimize latency and cross-zone traffic. |
| Secondary | Other zones in the same region | Continue serving when the current zone fails or lacks capacity. |
| Tertiary | Backup region | Maintain availability when the primary region experiences an outage or insufficient capacity. |

This ordering is an architectural choice, not a universal rule for every system. If the current zone is overloaded, the policy may spill part of the traffic to another zone before endpoints are marked unhealthy. If data resides in only one region, preferring a zone near the client might increase synchronization lag or cause business errors. Locality decisions must match where data is read/written and consistency requirements.

### Locality preference and locality weight

- **Preference/priority** determines which locality is tried first and which localities serve as failover tiers.
- **Weight** determines the relative traffic share among localities currently eligible to receive requests.
- **Endpoint weight** can distribute load among endpoints within the same locality if supported by the control plane.

Illustrative example: within the same region, locality zone-a receives 70%, zone-b receives 20%, and zone-c receives 10% of traffic. These are relative shares among eligible localities, not a guarantee that every single second receives exact proportions. At low request volumes, short-term observations can deviate from target ratios.

Do not configure weights based solely on endpoint counts. A zone with fewer machines might still have higher capacity; conversely, a locality with many endpoints constrained by CPU, database connections, or quotas should probably not receive a high share.

## 4. Choosing an implementation mechanism in the gRPC ecosystem

There are three common places to implement load balancing:

**Client-side gRPC load balancing.** The name resolver returns an endpoint list to the gRPC channel; the load-balancing policy selects a subchannel for each RPC. This is a good fit when a Java application needs channel-level control and has reliable discovery metadata.

**xDS control plane.** xDS provides cluster, endpoint, and locality configuration to clients or proxies. With xDS-enabled gRPC Java, clients can receive locality-grouped endpoints and apply policies distributed by the control plane. This fits organizations already running a control plane across multiple services, regions, and zones. Check the `grpc-java` version, xDS resolver/load-balancer support, and supported policies in the deployed version.

**Proxy or service mesh.** The client connects to a sidecar/gateway; the proxy handles routing, health handling, and locality policies. This centralizes policy in infrastructure, while adding a network hop and requiring observability across both application and proxy.

In Spring applications, channels are usually created and managed as beans or via a gRPC client integration library. Whichever mechanism you choose, manage the channel along the application lifecycle, reuse channels across RPCs, and close them when the application stops. Do not create a new channel per request just to switch localities.

## 5. Configuring round-robin when endpoints are already scoped by the resolver

If the goal is solely to distribute across multiple endpoints already scoped to the same locality, gRPC Java can use round-robin. The example below illustrates a default service config for a DNS target:

~~~java
Map<String, ?> serviceConfig = Map.of(
        "loadBalancingConfig",
        List.of(Map.of("round_robin", Map.of()))
);

ManagedChannel channel = ManagedChannelBuilder
        .forTarget("dns:///inventory.internal:8443")
        .defaultServiceConfig(serviceConfig)
        .build();
~~~

This snippet assumes the resolver returns multiple backend addresses belonging to the same locality and that the round-robin policy is registered in the runtime. It **does not create locality awareness on its own**: the DNS resolver must return the appropriate endpoint subset, or another discovery layer must filter/group endpoints before the policy chooses. Standard DNS does not guarantee supplying enough region/zone metadata for gRPC to make locality decisions.

In Spring, place the channel in a bean with a clear lifecycle and inject stubs or the channel into client adapters. Example:

~~~java
@Configuration
class InventoryGrpcClientConfiguration {

    @Bean(destroyMethod = "shutdown")
    ManagedChannel inventoryChannel() {
        Map<String, ?> serviceConfig = Map.of(
                "loadBalancingConfig",
                List.of(Map.of("round_robin", Map.of()))
        );

        return ManagedChannelBuilder
                .forTarget("dns:///inventory.internal:8443")
                .defaultServiceConfig(serviceConfig)
                .build();
    }
}
~~~

This is only a plain gRPC Java channel example. TLS, authority, resolver, retry, and integration property configuration depend on how the Spring project builds channels; avoid manually creating an extra channel if a starter already manages the channel for that same client.

## 6. Locality-aware balancing with xDS

When routing across zones or regions is required, endpoint discovery must supply locality metadata. With xDS, the control plane can group endpoints by locality and assign weights/priorities. The gRPC Java client uses the xDS resolver and corresponding load balancer to apply the received configuration.

The logical data model can be pictured as:

~~~yaml
service: inventory
localities:
  - region: region-a
    zone: zone-a
    priority: 0
    weight: 70
    endpoints:
      - address: inventory-a1:8443
      - address: inventory-a2:8443
  - region: region-a
    zone: zone-b
    priority: 0
    weight: 30
    endpoints:
      - address: inventory-b1:8443
  - region: region-b
    zone: zone-a
    priority: 1
    weight: 100
    endpoints:
      - address: inventory-rb-a1:8443
~~~

This is an illustrative model to explain locality/priority/weight, not a complete xDS resource file ready to load directly. Actual resource schemas depend on the xDS API and control plane version. In deployment, verify:

- The client receives accurate endpoint localities and the client's own locality comes from a trusted source.
- The policy exhibits the desired preference and failover behavior.
- Endpoint health is updated; endpoints that are not `READY` stop receiving new RPCs.
- Endpoint/weight changes take effect without disrupting active channels.
- TLS, authority, and identity policies remain valid when RPCs cross regions.

Do not infer locality from public IPs or hostnames unless infrastructure guarantees a stable mapping. Use metadata from the control plane, deployment platform, or a resolver with a clear contract.

## 7. Failover across zones and regions

Failover shifts traffic when the current locality cannot or should not accept more requests. Define both failover and failback conditions:

1. **Unhealthy endpoint:** remove the endpoint from the new-RPC pool.
2. **Degraded zone:** reduce weight or shift traffic to another zone in the same region.
3. **Degraded region:** activate backup locality/priority in another region.
4. **Recovery:** increase traffic back to the original locality only after health and capacity stabilize.

Avoid failing over based on a single failed RPC. One request can fail due to bad input, authorization, or a business error; those failures do not prove an entire zone is down. Use health checks, outlier detection, or aggregated signals across multiple endpoints to avoid premature traffic shifts.

Multi-region failover requires evaluating:

- **RTO:** time required to shift traffic and restore service.
- **RPO:** amount of data that could be lost during a region switch, especially with asynchronous writes.
- **Standby capacity:** whether the surviving region has enough capacity to absorb extra traffic.
- **Dependency locality:** whether databases, caches, brokers, and supporting services exist in the target region.
- **Cost:** cross-region traffic, replication, and operations are typically costlier than intra-region.

Shifting traffic to another region before its database is ready can turn a latency incident into data errors. Failover must be designed across both the application tier and the data tier.

## 8. Combining locality with health, retries, and deadlines

Locality-aware balancing does not replace health checking, deadlines, or retries:

| Mechanism | Role |
| --- | --- |
| Health checking | Determines whether an endpoint/service is eligible to accept new RPCs. |
| Locality policy | Picks the preferred zone/region within the eligible endpoint set. |
| Deadline | Bounds the total duration of the RPC, even when switching localities. |
| Retry | Retries the RPC when the error is retryable and the operation is safe. |
| Outlier detection | Detects endpoints with abnormal error/latency rates and temporarily ejects them per policy. |

Retries must not violate the overall deadline. If a request has already spent 700 ms out of a 1-second budget, an attempt in another region gets only the remaining budget. Never grant a fresh full timeout to each retry.

When the client retries, the new attempt may land in a different locality. For idempotent read RPCs, this is usually easier to accept. For write RPCs, you need an idempotency key and operation state; the endpoint in the other region must recognize the same business intent or forward to where the data is owned.

Do not retry all `UNAVAILABLE` errors indefinitely. Use jittered backoff, cap attempt counts, and set an overall deadline. Avoid simultaneous retries across client, proxy, and service layers, as that can amplify load while a region is degraded.

## 9. Impact of streams and affinity

Unary RPCs complete after one request/response, so each new call can be routed by the load balancer according to current policy. Server-streaming, client-streaming, and bidirectional-streaming RPCs live longer:

- An endpoint is chosen when the stream starts and typically holds that stream until it finishes.
- If a locality's weight is lowered after a stream is open, the active stream does not automatically move to another endpoint.
- When a stream drops, the client must open a new RPC; to continue data seamlessly, use a sequence number, cursor, or resume token.
- If business logic requires session affinity, define the key and policy explicitly; do not rely on coincidentally sharing an HTTP/2 connection.

For long-lived streams, setting maximum lifetimes or re-establish/resume mechanisms can aid rollouts and failover. However, periodic stream resets must fit application semantics and never drop unacknowledged messages.

## 10. Data and consistency when selecting regions

Picking the closest endpoint is not always right if data has its own locality. For example, an order written in region A while a client is routed to region B might read a replica that has not received the new record yet.

Common strategies:

- **Read local, write home:** read from a replica near the client; write to the region owning the data.
- **Regional ownership:** each tenant/account/order has a home region; requests route to the owning region.
- **Active-active:** multiple regions accept writes, requiring conflict resolution or clear data partitioning.
- **Controlled failover:** the standby region accepts writes only after ownership/fencing tokens are safely transferred.

Never trust client-supplied headers like region or tenant to grant data access. Locality used for routing must come from trusted sources; authorization must still be enforced independently on the service.

## 11. Testing locality and failover

Tests should verify endpoint selection, behavior during locality degradation, and effects on open RPCs:

1. Create a resolver/test control plane returning endpoints in two zones; verify traffic prefers the configured zone.
2. Adjust weights between zone-a and zone-b; send enough RPCs to verify statistical distribution rather than asserting a strict alternating sequence.
3. Mark an endpoint unhealthy; verify new RPCs stop choosing that endpoint.
4. Make the entire primary zone unhealthy; verify the client fails over to a backup zone within the deadline.
5. Make the primary region unavailable; verify region failover and check dependency/data readiness.
6. Open a streaming RPC across a locality weight change; verify the existing stream stays on the old endpoint while new RPCs follow the new policy.
7. Verify TLS/authority and identity when selected endpoints live in another region.

For client-side load balancing, use a fake `NameResolver` or test resolver to control the endpoint list. For xDS, use a control-plane test fixture or integration environment capable of updating endpoints/localities. Test over TCP/TLS to verify real transport and health behavior; policy unit tests alone do not prove DNS, xDS, or proxies are configured properly.

## 12. Observability and operations

Monitor by method and locality to see where traffic actually goes:

- RPC count, p50/p95/p99 latency, and error rate by region/zone.
- Share of local-zone, cross-zone, and cross-region requests.
- Failover counts, time to detect an unhealthy locality, and recovery time.
- `READY`/`UNREADY` endpoint counts and active subchannel counts.
- Retry counts, deadline exceeded counts, queueing, and connection churn.
- Cross-zone/cross-region egress cost and load on data dependencies.

Use bounded-cardinality region/zone labels. Avoid putting request IDs, user IDs, or ephemeral endpoints in metric labels. Logs/traces can record the chosen endpoint/locality to investigate specific requests, subject to security policies.

A locality receiving less traffic than expected is not automatically a bug: weights, health, client locality, RPC count, and long-lived streams all influence distribution. Compare metrics over a sufficiently long window and inspect resolver/control-plane state before tuning weights.

## 13. Common issues

| Symptom | Cause | How to handle |
| --- | --- | --- |
| Round-robin sends requests to a distant region | Policy sees only a flat endpoint list with no locality info. | Provide locality metadata and use a locality-aware policy. |
| DNS returns multiple IPs yet traffic hits one backend | Resolver/policy/channel did not create or pick multiple subchannels as expected. | Inspect resolver output, LB policy, and `READY` states. |
| L4 load balancer piles many RPCs onto one server | HTTP/2 multiplexes multiple RPCs over a single connection. | Use client-side gRPC LB or an RPC-aware L7 proxy. |
| Constant flapping between two zones | Noisy health signals or overly sensitive thresholds. | Use health windows, hysteresis, and recovery thresholds. |
| Backup region receives traffic yet requests fail on data | Replica lag or data ownership has not transferred. | Design data locality, consistency, and fencing. |
| Retries overload the remaining healthy region | Stacked retry layers or unbounded attempts. | Enforce overall deadline, jittered backoff, and retry budgets. |
| Streams do not move to the new zone after weight changes | Existing streams stay attached to the backend selected at open time. | Resume/reconnect with a cursor or token when migration is needed. |
| Increasing weight shows no matching traffic shift | Endpoints not `READY`, low RPC volume, or long-lived streams dominate load. | Check health, sample size, and stream lifetimes. |

## 14. Hands-on exercises

1. Create a gRPC client channel with round-robin and a resolver returning multiple endpoints in the same zone; verify distribution across endpoints.
2. Model endpoints by region/zone and explain why flat round-robin cannot automatically pick the locality closest to the client.
3. Use xDS or a resolver/control plane with locality metadata to prefer the current zone, then fail over to another zone.
4. Change weights between two zones and measure RPC share, latency, and cross-zone traffic.
5. Simulate primary region disconnection; verify failover, deadlines, and data state in the backup region.
6. Keep a server-streaming RPC open across a locality change; inspect current stream semantics and design resume for reconnection.
7. Build a per-region/zone dashboard for latency, error rate, failovers, retries, and `READY` endpoint counts.

After this lesson, you should be able to distinguish flat endpoint round-robin from locality-aware routing, choose between client-side, xDS, or proxy mechanisms, configure priorities and weights across zones/regions, and coordinate health, deadlines, retries, and data locality. Effective cross-region load balancing minimizes latency under normal conditions, shifts traffic safely during incidents, and preserves the data semantics of your Spring gRPC service.
