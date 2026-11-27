# How Network Partitions Affect Registration and Queries

## 1. Network Partitions in Service Discovery

A network partition occurs when components are still running but cannot exchange data across part of the network. The outage may affect only one direction, one subnet, one availability zone, or connectivity between geographic regions. Therefore, "the server is alive" does not mean "every client can connect to the server."

In Spring Cloud Service Discovery, a network partition can affect multiple communication paths:

- **Instance → Registry:** the service cannot register anew or update its metadata/status.
- **Instance → Registry (heartbeat):** the instance is registered but cannot renew its lease or session.
- **Registry peer → Registry peer:** registry nodes cannot replicate changes.
- **Client → Registry:** the client cannot query or receive registry updates.
- **Client → Service instance:** the client finds the address in the registry but cannot connect to the instance.

These communication paths are relatively independent. For example, Eureka Server might be reachable from payment-service but unreachable from order-service; the registry still receives heartbeats from one group of instances while another group loses connectivity. A client may read an old registry cache yet fail to call the instance address due to a NetworkPolicy or broken route.

## 2. Separating the Control Plane and Data Plane

To diagnose accurately, separate the two planes:

- **Discovery control plane:** registration, heartbeats, health checks, replication, registry queries, and updating the instance list.
- **Request data plane:** the actual connection from client to instance host/port, across DNS, proxy, gateway, load balancer, and network policies.

Discovery helps find addresses; it does not create a network path to those addresses.

~~~mermaid
flowchart LR
    subgraph CP[Control plane]
        APP[Service instance] -->|register / heartbeat| REG[Registry]
        REG -->|replication / watch / fetch| PEER[Peer or client cache]
        PEER --> DISC[DiscoveryClient]
    end
    subgraph DP[Data plane]
        CALL[Caller] --> LB[LoadBalancer]
        LB -->|selected host:port| TARGET[Service instance]
    end
    DISC -.->|Address list| LB
~~~

If the control plane fails while the data plane remains intact, current requests can keep running using the already known instance list. Conversely, discovery may report an instance as UP while the data plane is severed and real requests fail.

## 3. Types of Partitions and Direct Effects

| Partition | Registration and updates | Queries and service calls |
|---|---|---|
| Instance cannot reach registry | Register/heartbeat fails or times out | Instance may not appear yet or stale data may remain |
| Client cannot reach registry | Registry can still accept registrations from other instances | Client keeps using cache or cannot refresh the list |
| Registry peers cannot communicate | Changes are not fully replicated | Nodes may return divergent views |
| Client cannot reach an instance | Registry may still record instance as UP | Lookup succeeds but request connections fail |
| Registry cluster loses quorum | Write operations may be rejected or stall | Reads may be restricted, stale, or still served from cache depending on provider |
| Asymmetric (one-way) partition | One side can send, but responses do not return | Timeouts and observed state differ between the two sides |

Do not infer solely from a single timeout. Identify the source-destination pair, connection direction, port, DNS, TLS, and intermediate components affected.

## 4. What Happens to Registration and Heartbeats?

When an instance starts up, it sends registration details to the registry. Afterward, the provider typically maintains presence via heartbeats, leases, health checks, or sessions. If the network path is split, several scenarios can occur:

1. **New registration does not reach the registry:** the process is running, but other clients cannot discover it yet.
2. **Heartbeats are lost:** the registry may consider the instance unreachable after a period.
3. **Health status does not update:** the registry retains the old status because it receives no new results.
4. **Deregistration cannot be sent:** the instance has stopped, but the registry has not received the deregister operation.
5. **Connectivity recovers:** the client retries registration or renewal; the registry needs time to update and clients need time to fetch/watch new data.

A timed-out register operation does not always mean the server failed to record the data. The request may have reached the server and been processed, while the response was lost on the return path. On retry, the application must rely on stable instance identifiers and the provider's idempotent semantics to avoid creating duplicate registrations or corrupting state.

## 5. Network Partitions with Eureka

Eureka is designed to support available discovery in distributed environments. Eureka Client maintains a local registry cache and usually continues serving previously fetched data when connectivity to Eureka Server has issues. Eureka Server nodes exchange changes with peers via replication; this is an asynchronous flow with latency, not a cluster-wide synchronous transaction.

### 5.1. Client Isolated from Eureka Server

If a client cannot reach Eureka Server:

- The client can continue looking up instances from its local registry cache.
- Newly registered instances on the server may not appear in that client's cache yet.
- Stopped instances may remain in the cache and be returned by lookups.
- Registry fetches may fail until connectivity recovers.

Therefore, DiscoveryClient.getInstances() returning a non-empty list does not prove the registry was just queried successfully. The data may come from the most recent cache.

### 5.2. Heartbeats and Self-Preservation

Eureka Server tracks instance renewals. When received heartbeats drop abnormally, the self-preservation mechanism can restrict eviction to avoid wiping out large numbers of instances simply due to a transient network outage.

This protects the registry against widespread heartbeat loss, at a trade-off: genuinely dead instances can also linger longer in the registry. Clients may then pick stale addresses and requests fail.

Do not disable self-preservation as a knee-jerk reaction when seeing stale instances. First inspect client-to-server networking, heartbeat rates, eviction logs, peer replication, and client cache behavior. Adjust thresholds or eviction mechanisms only after understanding the cluster-wide impact.

### 5.3. Peer Partitions and Divergent Registry Views

If Eureka Server peers cannot communicate, each node can temporarily hold a different registry view. An instance registered with node A might not appear on node B; clients reading from the two nodes may see different lists.

Once the network recovers, replication and subsequent fetch cycles help data converge. However, do not assume every node becomes identical the instant the network returns. Compare instance ID, host/port, status, metadata, and renewal timestamps across each node.

### 5.4. Configuration and Observation

Example of commonly inspected Eureka parameters:

~~~yaml
eureka:
  client:
    registry-fetch-interval-seconds: 30
  server:
    enable-self-preservation: true
    eviction-interval-timer-in-ms: 60000
~~~

This is an illustrative configuration; default values and configurability depend on the Spring Cloud Netflix/Eureka version. Client fetch intervals and server eviction intervals influence when changes become visible. Do not simply sum these intervals into a strict upper bound on staleness, because retries, cache invalidation, replication, and when the partition began all affect the outcome.

## 6. Network Partitions with Consul

Consul separates responsibilities between agent and server:

- Consul agent runs close to workloads, manages local services/checks, and communicates with Consul servers.
- Consul server maintains the catalog and uses Raft for consensus on committed changes.
- Gossip is used for membership and failure detection; RPC between agents and servers handles catalog operations and coordination.

### 6.1. Agent Loses Connectivity to Server

When an agent cannot reach Consul servers, local service/check state and server-side catalog updates can fall out of sync. The service may still be running on the host, while clients elsewhere may not see new registrations or health updates.

When connectivity returns, the agent and server must resynchronize state. Check agent logs, check statuses, the server catalog, and service registrations in the exact datacenter/namespace/partition in use.

### 6.2. Raft Quorum Loss

Consul servers need quorum to commit catalog changes and maintain consistent state. If the server cluster loses quorum, write operations requiring consensus cannot make progress. Reads depend on consistency mode and server state; some stale queries may return older data from followers, while queries requiring strong consistency need a leader/quorum.

Consul supports read modes with different consistency guarantees, such as consistent and stale. Choosing stale reads can increase availability during failures while accepting older data. For sensitive decisions like configuration changes or operations needing the latest state, use an appropriate read policy and handle errors when state cannot be confirmed.

### 6.3. A Passing Health Check Does Not Equal a Clear Call Path

Consul health checks are commonly executed from the agent or according to check configuration. A passing check indicates the check succeeded from the agent's vantage point. It does not guarantee that every caller in every subnet can connect to the instance.

For example, an agent on the same host can call localhost:8080/health, while a caller in another subnet is blocked on port 8080 by a firewall. Consul may still show the service as passing while requests from the caller fail.

## 7. Network Partitions with Kubernetes

In Kubernetes, Service Discovery can rely on Services, EndpointSlices, DNS, and the Kubernetes API. Multiple components participate in control-plane state:

- Kubelet reports node and Pod status to the API server.
- The EndpointSlice controller watches Pods/Services and updates endpoints.
- The API server persists state in etcd.
- Clients use list/watch or caches to track changes.
- kube-proxy or data planes like eBPF/mesh update traffic forwarding rules.

### 7.1. Workload Loses Connectivity to the API Server

Pods can keep running and serving active requests even if the application or node temporarily cannot reach the API server. However, clients using Spring Cloud Kubernetes to watch Services/EndpointSlices may stop receiving new updates; client-side caches can become stale.

If a node is partitioned from the control plane, kubelet cannot report new status. The control plane may continue showing old status for a period before marking the node or Pod not ready according to timeouts and controller policies.

### 7.2. EndpointSlices and the Data Plane

When Pod readiness changes, the EndpointSlice controller must observe the Pod change and update endpoint conditions. If the controller or API server cannot record the change, consumers may retain an outdated endpoint list.

Even after EndpointSlices are updated, the data plane on nodes or gateways still needs to receive the update. If a node loses control-plane connectivity while data-plane traffic still flows, old forwarding rules may remain active during that time.

This is why you must inspect both API objects and actual request paths. `kubectl get endpointslices` shows the state stored by the control plane; it does not prove every proxy or client has received the new version.

### 7.3. etcd Quorum Loss

The Kubernetes control plane depends on etcd to store cluster state. etcd uses quorum to commit changes. If quorum is lost, cluster state writes cannot proceed normally; the API server may return errors or timeouts for write operations.

Workloads already running on nodes can keep operating while the control plane cannot update Deployments, Pod conditions, or EndpointSlices. API-driven rollouts and recovery actions can be delayed until quorum is restored.

## 8. Network Partitions with ZooKeeper

Spring Cloud Zookeeper Discovery uses znodes and sessions to represent service registrations. Registrations are typically tied to an ephemeral znode belonging to the client's session.

When a client loses connectivity:

- The client may enter a suspended or disconnected state depending on the client library.
- If the session remains valid and connectivity recovers, the client can resume the session.
- If the session expires, the ephemeral znode is deleted from the ensemble.
- When a new session is created, the application must re-register the instance.

Do not assume a TCP disconnect immediately deletes the ephemeral znode. The znode is removed only once the ensemble determines the session has expired. Thus, during a network partition, other clients may still see the old registration.

If ZooKeeper servers lose quorum, the ensemble cannot commit new changes. Some nodes might still answer read operations from local state, but writes and quorum synchronization cannot make guaranteed progress. Upon recovery, verify leader/follower status, sessions, and registration znodes.

## 9. Client Caches and Stale Data

Many discovery providers or client libraries cache data locally to avoid calling the registry on every request. Spring Cloud LoadBalancer may also cache the instance list depending on the supplier and configuration.

During a network partition, a client may encounter these states:

| Client data | Meaning |
|---|---|
| Cache still holds UP instance | Instance was previously seen; not guaranteed to still be alive or reachable |
| Cache lacks new instance | Client has not received new registration or watch/fetch is disrupted |
| Cache has instance with old status | Health change or deregistration has not reached the client |
| Cache expired or refresh failed | Behavior depends on provider; client may retain stale data or return no results |
| DiscoveryClient throws error | Query or probe failed; must distinguish from a valid empty result |

Do not convert all query errors into an empty list. Doing so loses the ability to distinguish between:

- **No instances:** the registry responded successfully, and the service currently has zero instances.
- **Unable to query:** the provider, network, or access permissions are failing.
- **Cached data available:** the client returns the latest known data without confirming current live state.

### 9.1. Choosing a Policy When the Registry Is Unreachable

The right policy depends on the request type:

- If the service can continue processing with cached instances, allow using the most recent data for a bounded window while keeping request timeouts/retries in place.
- If the operation requires the latest state, reject or return a controlled error when the registry cannot be verified.
- If the service has no instances, return a clear error or apply a designed business fallback.
- If using a stale instance, handle connection failures and never retry indefinitely against the same address.

No single stale/fail-fast choice fits all services. Assess the business impact of calling an outdated instance versus temporarily rejecting requests.

## 10. End-to-End Scenario Example

Suppose three inventory-service instances are running on three nodes. A network partition severs connectivity between instance A's node and the registry, while a client in zone-b also cannot reach instance A.

1. Instance A is still running, but heartbeats do not reach the registry.
2. The registry may not remove A immediately; lease, health check, or self-preservation rules determine when state changes.
3. The zone-b client may still hold A's address in its cache.
4. Lookup returns A, yet requests to A time out because the data-plane path is cut.
5. Instances B and C can still serve traffic if the registry and network paths to them remain healthy.
6. When connectivity recovers, A resumes heartbeats or re-registers depending on provider/session behavior.
7. Clients update their lists after replication, fetch/watch, and cache refresh.

~~~mermaid
sequenceDiagram
    participant A as inventory A
    participant R as Registry
    participant C as Client zone-b
    participant B as inventory B
    Note over A,R: Network partition
    A-xR: heartbeat / register
    C->>R: Query or read cache
    R-->>C: Instance list may still contain A
    C-xA: Request to A times out
    C->>B: Bounded retry / pick another instance
    Note over A,R: Network restored
    A->>R: Heartbeat or re-register
    R-->>C: Changes synchronized gradually
    C->>B: Subsequent requests follow updated list
~~~

Retrying to B is safe only if the request is retryable and business logic handles idempotency. For payment creation or data-mutating operations, an idempotency key or duplicate-processing guard is required.

## 11. Recovery After Network Restoration

When network connectivity returns, do not assume all state synchronizes instantly. Recover layer by layer:

1. **Restore connectivity:** verify DNS, routes, firewalls, TLS, and bidirectional connectivity between nodes.
2. **Restore quorum:** for Consul, ZooKeeper, or etcd, confirm a stable leader and quorum before heavy write operations.
3. **Restore replication:** verify peers/agents can synchronize data without communication errors.
4. **Restore registrations:** confirm running instances have heartbeated or re-registered; confirm stopped instances are deregistered/evicted.
5. **Refresh clients:** confirm fetch/watch works and client caches receive updated state.
6. **Refresh LoadBalancer:** inspect suppliers/caches and instance selection policies.
7. **Verify the data plane:** send live requests to valid instances and monitor latency/error rates.
8. **Reconcile state:** compare instance counts, instance IDs, host/port, statuses, and metadata in the registry against running workloads.

Do not manually bulk-delete instances just because the registry holds stale entries. Before intervening, determine whether the instance is still alive, whether it is reconnecting or rolling out, and what self-healing mechanisms the provider offers.

## 12. Symptom-Based Diagnostic Table

| Symptom | Layer to inspect first | Evidence to collect |
|---|---|---|
| Instance running but missing | Register path / permissions / network to registry | Register logs, DNS, TCP/TLS, catalog or registry API |
| Old instance lingers after stop | Heartbeat, lease, health check, session, or eviction | Last renewal, check status, session state, eviction logs |
| Two registry nodes return different lists | Peer replication or quorum | Peer status, leader, replication logs, update timestamps |
| DiscoveryClient returns stale list | Client cache, fetch/watch | Last successful fetch/watch timestamp, cache TTL, provider logs |
| Lookup returns instance but request times out | Data plane | Routes, NetworkPolicy, firewalls, ports, TLS, and packet flow |
| Consul does not accept catalog changes | Raft quorum or agent-server RPC | Leader/quorum, agent logs, RPC errors |
| Kubernetes EndpointSlice does not update | API server, etcd, or controller | Pod conditions, controller logs, API errors, etcd health |
| ZooKeeper registration disappears | Session expiration or quorum loss | Session state, ephemeral znodes, leader/follower |

## 13. Network Partition Investigation Runbook

When an abnormal discovery alert fires, follow this sequence:

1. Record the start time, service ID, instance ID, client source, and registry nodes involved.
2. Identify whether the partition affects registration, heartbeats, peer replication, client queries, or requests to instances.
3. Test connectivity from the exact workload/container; check both outbound and return paths.
4. Cross-check the registry across multiple nodes or datacenters if the provider uses such a topology.
5. Check heartbeats/leases/sessions and health statuses.
6. Compare the client cache against server data; note the timestamp of the last successful fetch/watch.
7. Call the instance's health endpoint and port directly from the caller's network.
8. Restore networking or quorum before forcing synchronization or deleting registry entries.
9. After recovery, confirm the registry has converged and clients/load balancers use the correct list.
10. Monitor error rates, timeouts, and retries to ensure the system is no longer hitting stale endpoints.

## 14. Designing to Withstand Network Partitions

### 14.1. Stable Instance Identifiers

Each instance needs an identifier suited to the provider so register, heartbeat, and deregister map to the same record. When retrying registration after a timeout, do not generate a new random identifier if doing so causes the registry to accumulate stale records.

### 14.2. Bounded Timeouts and Retries

Configure connect timeouts, request timeouts, and retry budgets for discovery operations. Use backoff and jitter so many clients do not retry in lockstep after the network recovers. Retrying does not make a request inherently safe; evaluate the idempotency of the business operation.

### 14.3. Explicit Cache Policies

Define how long stale discovery data is acceptable, how refresh failures are handled, and when to switch to fail-fast. Do not keep stale endpoints indefinitely without metrics or alerts.

### 14.4. Avoid Making Discovery a Single Point of Dependency

Where possible, use stable service DNS, bounded caches, or designed fallbacks to reduce the blast radius of registry failures. However, fallbacks help only if alternate addresses remain reachable and business data stays consistent.

### 14.5. Separate Readiness from Liveness

A temporarily unreachable registry does not necessarily mean a process should restart. Use readiness to stop receiving requests when genuinely unable to serve; use liveness to detect stuck processes that cannot self-recover. Avoid restarting all services en masse during a broad registry outage.

### 14.6. Monitor Per Communication Path

Track register errors, heartbeat failures, peer replication lag, client fetch/watch failures, cache age, lookup results, request connection errors, and health check failures separately. A single "registry UP" metric does not capture the health of the entire discovery pipeline.

## 15. Testing Network Partitions

Conduct controlled experiments in staging or chaos tests:

- Block connectivity from one instance to the registry for a period.
- Block clients from querying the registry while keeping data-plane connectivity intact.
- Block connectivity between registry peers.
- Induce quorum loss for Consul, ZooKeeper, or etcd in an appropriate test environment.
- Block a client from reaching one instance while keeping the registry healthy.
- Restore the network and measure convergence times for the registry, client caches, and LoadBalancer.

Results to record:

| Scenario | Questions to answer |
|---|---|
| Register loss | Is the instance considered ready prematurely? |
| Heartbeat loss | How long until the registry changes status or evicts the instance? |
| Client fetch loss | How long does the client use cache and how does it behave afterward? |
| Peer link loss | Do registry nodes return different results across nodes? |
| Data-plane path loss | Does the caller time out, retry, and pick another instance properly? |
| Network recovery | How long do nodes and clients take to converge? Are duplicate registrations created? |

Do not run network-blocking experiments in production without an approved isolation plan, blast-radius scope, and rollback procedure.

## 16. Summary

Network partitions can break individual Service Discovery communication paths independently: registration, heartbeats, peer replication, registry queries, or instance connections. As a result, an instance can still be running without being registered; the registry can retain stale records; and a client can succeed on a cached lookup while real requests time out.

Eureka typically continues serving clients via its registry cache and uses self-preservation to curb evictions when heartbeats drop abnormally. Consul and ZooKeeper require quorum for consistent cluster-wide mutations; Kubernetes relies on the API server, controllers, and etcd to update control-plane state. Each provider has distinct read, caching, and recovery semantics, so verify behavior against the specific implementation and version.

When troubleshooting, separate the control plane from the data plane, pinpoint the exact partitioned pair of components, compare server state against client caches, and test real request paths. After network restoration, confirm quorum, replication, registrations, client fetches, and LoadBalancer caches have converged before declaring the system stable.
