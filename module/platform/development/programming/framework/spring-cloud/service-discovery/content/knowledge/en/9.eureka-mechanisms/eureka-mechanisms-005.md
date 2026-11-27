# Server-Side Cache, Client-Side Cache, and Change Propagation Path

## 1. Why Does the Registry Need Multiple Cache Layers?

In Spring Cloud Service Discovery, Eureka stores information about applications and instances so clients can look up services by name. The registry changes continuously as instances start up, send heartbeats, change status, or shut down. If every registry read request had to rebuild the entire dataset from scratch, Eureka Server and its clients would bear unnecessary load.

Eureka therefore uses caching in multiple places. When investigating a newly registered instance that has not yet appeared in a client, you need to know which layer holds the data and which steps a change must pass through.

In a Eureka-based application, three layers can be distinguished:

1. **Server response cache:** Eureka Server builds and caches registry response payloads to serve REST API requests.
2. **Eureka Client registry cache:** Eureka Client downloads the registry and keeps a local copy for lookups.
3. **LoadBalancer cache:** if the application uses Spring Cloud LoadBalancer with caching enabled, the load balancer may keep an additional cached list of instances obtained from DiscoveryClient.

These three layers serve different purposes. The registry inside Eureka Server is the registration data managed by the server; the response cache speeds up read queries; the client registry cache allows the application to perform local lookups; and the LoadBalancer cache optimizes retrieving the instance list for choosing a call target.

## 2. High-Level Overview of a Change's Path

Suppose a new instance of `payment-service` registers with Eureka A. The change is recorded in A's registry, replicated to peers if clustered, and then placed into the response cache used by the REST API. Eureka Client periodically calls the API to fetch deltas or the full registry. DiscoveryClient reads from Eureka Client's local registry; LoadBalancer may cache the instance list in one more layer.

~~~mermaid
flowchart LR
    APP[Instance registers] --> REG[Eureka Server Registry]
    REG --> PEER[Replicate to peers]
    REG --> RWC[Server Read-Write Cache]
    RWC --> ROC[Server Read-Only Cache]
    ROC --> API[Eureka REST API]
    API --> FETCH[Eureka Client Fetch]
    FETCH --> CRC[Client Registry Cache]
    CRC --> DISC[DiscoveryClient]
    DISC --> LBC[LoadBalancer Cache if enabled]
    LBC --> CALL[Select instance for request]
~~~

This is a conceptual model. Specifics of cache updates and replication may vary by Eureka version, configuration, and provider. Not every change passes through every cache layer on every request, but the diagram helps pinpoint where observable latency can arise.

## 3. Eureka Server-Side Cache

### 3.1. Registry and Response Cache Are Two Different Things

Eureka Server manages the registry containing instance information. When a client requests the application list via the REST API, the server must construct a response from registry data. To reduce processing and serialization overhead, Eureka maintains a response cache.

The response cache is not an independent source of registration data. It is a cached representation used to serve read queries. When an instance is registered, renewed, deregistered, or changes status, the registry is updated accordingly; the response cache must be refreshed or invalidated so subsequent responses reflect the new data.

Therefore, if the registry has received a change yet the REST API still returns old data, inspect the response cache mechanism and when the cache is refreshed.

### 3.2. Read-Write Cache and Read-Only Cache

In common Eureka Server implementations, the response cache has two layers typically referred to as:

- **Read-write cache:** stores generated responses and can be invalidated when the registry changes or the cache expires.
- **Read-only cache:** holds response payloads for fast read queries. A periodic background task updates data from the read-write cache; configuration can allow disabling this read-only layer.

High-level read flow:

1. A REST request needs registry data for a cache key, such as all applications or a specific application.
2. The server checks the read-only cache if this mechanism is enabled.
3. If no suitable data exists in the read-only cache, the server can retrieve or generate the response via the read-write cache.
4. The result is returned to the client and cached according to the corresponding mechanism.

When the registry changes, Eureka typically invalidates related response cache keys; the next read request can regenerate the response from the updated registry. A periodic background task also refreshes the read-only cache from the read-write cache. Therefore, do not assume every change must wait out `response-cache-update-interval-ms` to become visible: invalidation can cause a key to be regenerated sooner, while the background interval is a supplementary refresh mechanism.

### 3.3. Configuring the Response Cache

Some Eureka Server properties commonly used to tune the response cache:

| Property | Common Default Value | Meaning |
|---|---:|---|
| eureka.server.use-read-only-response-cache | true | Enables the read-only response cache layer |
| eureka.server.response-cache-update-interval-ms | 30000 ms | Interval of the background task updating the read-only cache |

Example:

~~~yaml
eureka:
  server:
    use-read-only-response-cache: true
    response-cache-update-interval-ms: 30000
~~~

These are common Eureka Server defaults and may differ by version and configuration. Do not tune cache intervals solely out of a desire to see changes faster; measure REST API load, instance counts, and acceptable latency.

Disabling the read-only cache may cause responses to be served directly via the read-write cache in some situations, but the server must handle more read work. With large registries or high query rates, this can increase CPU usage and response-generation overhead. Load-test before changing it.

## 4. Eureka Client-Side Cache

### 4.1. Client Holds a Local Registry

Eureka Client does not send a new REST request to the server every time the application calls DiscoveryClient. Instead, the client downloads the registry and maintains a local copy. Components such as DiscoveryClient use this registry to look up service IDs and instance lists.

Benefits:

- Fast instance lookup without calling Eureka Server on every business request.
- Reduced read traffic to the server.
- The application can still look up the most recently fetched data if the server is temporarily unreachable.

The trade-off is that local data can lag behind the server registry. When an instance has just registered or been removed, the client must wait for the next fetch cycle or an appropriate sync before seeing the change.

### 4.2. Full Fetch and Delta Fetch

On initialization or when resynchronization is needed, Eureka Client can download the entire registry. On subsequent updates, the client typically uses delta fetches to retrieve only changes since the previous fetch, reducing network transfer volume.

Two corresponding common REST endpoints:

| Endpoint | Content |
|---|---|
| GET /eureka/apps | Full registry provided by the server |
| GET /eureka/apps/delta | Registry changes under the delta mechanism |

Deltas can contain new instances, removed instances, or status changes. The client applies those changes to its local registry copy.

If delta data cannot be applied consistently—for example, if the registry hash does not match the client's expected state—Eureka Client can request a full sync to recover. This mechanism lets the client repair its local copy when drift is detected.

### 4.3. Registry Fetch Interval

Properties commonly used to configure registry update intervals on Eureka Client:

| Property | Common Default Value | Meaning |
|---|---:|---|
| eureka.client.registry-fetch-interval-seconds | 30 seconds | Interval between registry fetches |
| eureka.client.disable-delta | false | Allows the client to use delta when false |

Example:

~~~yaml
eureka:
  client:
    registry-fetch-interval-seconds: 30
    disable-delta: false
~~~

Increasing the fetch interval makes the client send fewer requests, but it may hold stale registry data longer. Decreasing the interval updates the client more frequently, but increases REST API load, network traffic, and delta-processing work. Consider the number of clients and instances across the entire system.

## 5. Spring Cloud LoadBalancer Cache

Eureka Client's registry cache and the LoadBalancer cache are two separate layers. DiscoveryClient retrieves instance lists from Eureka Client's local registry. Spring Cloud LoadBalancer can cache the instance list supplied by `ServiceInstanceListSupplier` to avoid fetching and processing the list too frequently.

Lookup flow when using LoadBalancer:

1. The application sends a request to a service name, such as `payment-service`.
2. LoadBalancer retrieves the instance list from `ServiceInstanceListSupplier`.
3. The supplier may obtain data via DiscoveryClient.
4. If caching is enabled, LoadBalancer may return the list from its own cache.
5. LoadBalancer selects an instance and forwards the request to the chosen host/port.

Thus, a new change in Eureka Server might already have been fetched by Eureka Client yet not immediately appear in the list cached by LoadBalancer.

Spring Cloud LoadBalancer can use caching depending on configuration and classpath implementations. Common cache properties include:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: true
        ttl: 35s
        capacity: 256
~~~

The TTL and capacity above are common configuration examples, not guaranteed defaults across all versions. Check the documentation for your active Spring Cloud release train and chosen cache provider. If the instance list is already cached at another layer, avoid enabling redundant caching that makes update latency unpredictable.

Not every Eureka application uses Spring Cloud LoadBalancer. If an application only calls DiscoveryClient directly, this LoadBalancer cache layer may not exist.

## 6. Change Propagation Path Across Components

### 6.1. New Instance Registration

When a new instance starts up:

1. Eureka Client sends a register operation to Eureka Server.
2. The server updates its local registry.
3. The server refreshes or invalidates related response caches.
4. If the server is part of a cluster, the change is replicated to peers per Eureka's mechanism.
5. Eureka Clients periodically fetch deltas or the full registry from the server they connect to.
6. The client updates its local registry cache.
7. DiscoveryClient returns the updated instance list to the caller.
8. If LoadBalancer caches the instance list, that cache must expire or refresh before selection reflects the change.

### 6.2. Instance Deregistration or Eviction

When an instance stops gracefully, the client can send a cancel. If an instance loses connection abruptly, the server can detect it via lease expiration and eviction. Once the registry changes, response caches and peers are updated according to their respective mechanisms; clients receive the change on the next fetch.

Even after the server deletes the instance, a client may still hold the old record in its registry cache. If LoadBalancer also caches that list, the stale window can extend further depending on the TTL and when the cache refreshes.

### 6.3. Instance Status Change

When an instance's status transitions from `UP` to `OUT_OF_SERVICE` or another status, the change must pass through the registry, response cache, and client fetch process. The instance-selection component only excludes or retains the instance based on the status it sees and the filtering policy in use.

Do not assume status changes propagate to every client instantaneously. If traffic needs to be drained urgently, combine appropriate traffic routing or gateway controls instead of relying solely on cache fetch cycles.

## 7. Where Does Update Latency Come From?

The time from when a change occurs until an application uses the updated data can span multiple intervals:

| Stage | Source of Latency | How to Observe |
|---|---|---|
| Registry receives change | Time to process register, renew, cancel, or eviction | Eureka Server logs and metrics |
| Server response cache | Invalidation or read-only cache refresh cycle | Compare registry with REST API responses |
| Peer replication | Network connectivity and replication queues between Eureka Servers | Peer logs and querying multiple nodes |
| Client registry fetch | Fetch interval and delta/full fetch processing time | Eureka Client logs, registry-fetch interval |
| LoadBalancer cache | TTL and instance list refresh mechanism | LoadBalancer config and supplier/cache logs |

There is no single fixed total number applicable to every system. Steps may run concurrently or along different paths. For example, a client might fetch from one peer that has already received the change while another peer is still awaiting replication.

Illustrative example: a client finishes fetching the registry, and immediately afterward a new instance registers. The client may have to wait nearly the entire next fetch interval before receiving the change. If the server response cache has not refreshed yet, the client's fetch on that cycle might still receive old content; if LoadBalancer just populated its cache, the list used to select instances may stay stale until that cache refreshes.

## 8. Configuration Example and Interpreting Latency

Suppose a test system has the following configuration:

~~~yaml
# Eureka Server
eureka:
  server:
    use-read-only-response-cache: true
    response-cache-update-interval-ms: 30000
~~~

~~~yaml
# Eureka Client
eureka:
  client:
    registry-fetch-interval-seconds: 30
    disable-delta: false
~~~

~~~yaml
# Spring Cloud LoadBalancer, if the application uses caching
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: true
        ttl: 35s
        capacity: 256
~~~

This is an illustrative configuration to identify cache layers. Do not mechanically add 30 + 30 + 35 seconds and conclude that is the maximum stale time. When the change occurs relative to refresh schedules, cache invalidation, replication, retries, network errors, and how the supplier refreshes data all affect the outcome.

To measure in practice, record the timestamp when an instance registers, then query in sequence:

1. The REST API of the Eureka Server that accepted the registration.
2. The REST API of each peer in the cluster.
3. The registry cache used by the client application.
4. The instance list returned by the LoadBalancer supplier if LoadBalancer is used.

Comparing timestamps and instance IDs at each step helps pinpoint which layer is holding stale data.

## 9. Diagnosing When a Client Does Not See a Change

When a new instance has registered but a client does not see it yet, check in order:

1. Call `GET /eureka/apps/{APP_NAME}` directly on the Eureka Server that the client uses.
2. If the instance is missing there, check the server's registry, response cache, registration logs, and replication.
3. If this node lacks it while another peer has it, investigate peer connectivity and replication lag.
4. If the REST API has the instance yet the client does not see it, check `registry-fetch` interval, fetch logs, delta errors, and full fetch status.
5. If DiscoveryClient sees the instance yet requests via LoadBalancer do not select it, check LoadBalancer's cache, supplier, and filtering policies.
6. If all caches are updated yet requests still fail, check host, port, network policies, and business endpoint health.

| Symptom | Likely Layer Involved | Where to Check |
|---|---|---|
| REST API returns stale data right after register | Server response cache or unupdated registry | Check server logs, cache refresh, and registry |
| One Eureka Server has the instance, another peer does not | Peer replication | Check peer endpoints, network, and replication logs |
| REST API has the instance, but DiscoveryClient does not see it | Eureka Client registry cache | Check latest fetch, delta/full fetch, and interval config |
| DiscoveryClient sees the instance, but LoadBalancer does not select it | LoadBalancer cache or supplier/filter | Check TTL, cache provider, and instance selection policy |
| Instance cancelled, yet still receives calls | Stale client cache or LoadBalancer cache | Check fetch timing, TTL, and request logs |
| Client fetches fail repeatedly | Connectivity or API error | Check DNS, TLS, authentication, timeouts, and server health |

## 10. Principles for Tuning Caches

### 10.1. Do Not Shrink Every Interval at Once

Reducing the response-cache interval, client fetch interval, and LoadBalancer TTL simultaneously can spike load across multiple layers. Identify the exact layer causing latency, adjust one parameter at a time, and measure again.

### 10.2. Balance Freshness and System Load

Shorter intervals deliver fresh data faster, but increase requests, serialization, delta processing, and cache work. In systems with many clients, a small interval change can generate substantial periodic request volume.

### 10.3. Recognize That Stale Data Can Happen

Discovery provides information about instances at a recent point in time, not a guarantee that an instance is alive at the exact moment a request is sent. Applications still need timeouts, bounded retries, circuit breakers, and connection error handling.

### 10.4. Do Not Use Caches as a Substitute for Health Checks

Caches only determine which data is returned quickly and when it is refreshed. They do not prove an instance is healthy. Combine discovery state with health checks, readiness probes, and runtime monitoring.

### 10.5. Test Registration, Deregistration, and Recovery

When changing cache settings, test new instances, graceful shutdowns, disconnected instances, status changes, and inter-peer failures. Testing only new registrations is not enough to understand the full change propagation path.

## 11. Summary

Eureka Server uses a response cache to serve the REST API efficiently; in common deployments, the response cache has a read-write cache and a periodically refreshed read-only cache. Eureka Client keeps a local registry cache and updates it via full fetches or delta fetches. If the application uses Spring Cloud LoadBalancer, the instance list may be cached in one additional layer.

A change must pass through the registry, response cache, peer replication (if clustered), client fetch, and potentially the LoadBalancer cache before all components use the updated data. Therefore, discovery latency results from multiple intervals and update mechanisms. When diagnosing, inspect each layer in order, compare timestamps and instance IDs, and tune only the specific cache causing the delay.
