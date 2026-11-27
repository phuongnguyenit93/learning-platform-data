# Distinguishing Discovery Cache, Load Balancer Cache, and HTTP Connections

When a consumer calls a service by a logical name such as `inventory-service`, Spring Cloud must locate instances, pick an endpoint, and then send the request through an HTTP client. Along that path, three mechanisms that retain data or resources may appear: **the discovery cache**, **the LoadBalancer cache**, and **the HTTP connection pool**.

These three mechanisms are often lumped together as "caches," yet they store completely different things. The discovery cache holds a view of the registry; the LoadBalancer cache holds the `ServiceInstance` list used for selection; the HTTP connection pool holds open network connections for reuse. Each mechanism has its own lifecycle, expiration, and failure handling.

Understanding all three layers answers important operational questions: Why does the consumer still call an instance after the registry deleted it? Why does increasing cache duration fail to reduce TCP handshakes? Why does closing the connection pool fail to refresh the instance list? This article traces a request across all three layers and guides configuration, observability, and handling stale data.

## 1. The three layers sit at different positions

Suppose `order-service` needs to call `inventory-service`, which currently has two instances:

| Instance | Endpoint |
|---|---|
| inventory-a | `10.0.1.11:8081` |
| inventory-b | `10.0.1.12:8081` |

The consumer calls the logical URL:

~~~text
http://inventory-service/api/items
~~~

Before sending the request, the system must know which instances are advertised and pick one. Once chosen, the HTTP client needs a connection to that host and port.

~~~mermaid
flowchart TD
    REG[("Service Registry")] --> DC["DiscoveryClient"]
    DC -->|"Registry snapshot / discovery cache"| SUP["ServiceInstanceListSupplier"]
    SUP -->|"LoadBalancer cache (if enabled)"| LB["Spring Cloud LoadBalancer"]
    REQ["Request to inventory-service"] --> LB
    LB -->|"Select host:port"| HTTP["HTTP client"]
    HTTP -->|"Acquire or open connection"| POOL[("HTTP connection pool")]
    POOL --> NET["TCP / TLS connection"]
    NET --> PROVIDER["inventory-service instance"]
~~~

| Layer | What does it store? | Common key or scope | Purpose |
|---|---|---|---|
| Discovery cache | Registry data or snapshot of service instances | Depends on registry implementation | Reduce registry queries and provide a local view |
| LoadBalancer cache | `ServiceInstance` list supplied by the supplier | Service ID / client | Reduce repeated retrieval of instance lists during target selection |
| HTTP connection pool | Open, reusable TCP/TLS connections | Remote host, port, or HTTP route | Reduce the cost of establishing new connections |

Some systems have all three layers; some have only two. `DiscoveryClient` is an abstraction and does not force every implementation to use the same caching model. Similarly, an HTTP client may use a pool or create connections differently depending on the library and configuration.

## 2. Discovery cache: local view of the registry

The discovery cache retains service and instance information received by the discovery client from the registry. It answers the question: **Which instances does the consumer currently see?**

For example, with Eureka, the Eureka Client downloads the registry from Eureka Server and stores it locally. The client periodically updates its snapshot via deltas and can re-fetch the full registry when resynchronization is needed. The `eureka.client.registry-fetch-interval-seconds` property controls the fetch interval; current Spring Cloud Netflix documentation lists the default as 30 seconds.

Illustrative configuration:

~~~yaml
eureka:
  client:
    fetch-registry: true
    registry-fetch-interval-seconds: 30
    filter-only-up-instances: true
~~~

Meaning:

- `fetch-registry`: whether the client fetches the registry to discover services.
- `registry-fetch-interval-seconds`: interval at which the client refreshes registry data.
- `filter-only-up-instances`: filters results to keep only instances with status UP when fetching the application list.

Setting a smaller fetch interval helps the client pick up changes sooner, at the cost of more exchanges with Eureka Server. Setting it too large widens the window during which consumers can see stale data after providers change status or deregister.

### 2.1. Not every DiscoveryClient caches like Eureka

Spring Cloud Commons defines `DiscoveryClient` for querying services and instances. This abstraction does not impose a single shared caching mechanism across all registries.

For example:

- Eureka Client maintains a local registry and refreshes periodically.
- Another implementation may query an HTTP API when the supplier requests the list.
- Another integration may use its own cache, watch, or snapshot depending on the backend.

Therefore, before tuning caching, identify the concrete implementation. Do not apply Eureka properties to Consul or ZooKeeper simply because all three implement `DiscoveryClient`.

### 2.2. The discovery cache is not the instance list chosen by LoadBalancer

The discovery cache may hold the instances advertised by the registry. LoadBalancer can still filter by zone, health, metadata, hints, or other policies before picking an instance.

For example, the registry may have three instances while a zone policy keeps only two same-zone instances. The discovery cache may still hold all three; LoadBalancer's candidate input has only two.

Thus, the output of `DiscoveryClient.getInstances()` and the final list used by LoadBalancer are not necessarily identical.

## 3. LoadBalancer cache: the instance list used for target selection

Spring Cloud LoadBalancer uses `ServiceInstanceListSupplier` to obtain the instance list. The supplier typically reads data via `DiscoveryClient`; a cache layer can retain the returned list to avoid re-querying on every selection.

This cache answers the question: **Which candidate list does LoadBalancer currently hold to pick from for this service ID?**

Spring Cloud LoadBalancer provides `CachingServiceInstanceListSupplier` and default cache settings. According to current Spring Cloud Commons documentation:

| Property | Default value |
|---|---:|
| `spring.cloud.loadbalancer.cache.enabled` | `true` |
| `spring.cloud.loadbalancer.cache.ttl` | `35s` |
| `spring.cloud.loadbalancer.cache.capacity` | `256` |

If Caffeine is on the classpath, LoadBalancer uses a Caffeine-backed cache. Otherwise, the LoadBalancer starter provides a default cache. Verify actual defaults against your project's release train.

Example configuration:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: true
        ttl: 15s
        capacity: 256
~~~

TTL here is how long an instance list entry is kept after being written to the cache. It is neither the lifetime of a service instance nor the duration for which an HTTP connection is kept open.

### 3.1. Avoiding double caching with Eureka

Spring Cloud LoadBalancer documentation notes: if `DiscoveryClient` already caches data, such as `EurekaDiscoveryClient`, consider disabling LoadBalancer's cache to avoid double caching.

Example:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: false
~~~

This is not mandatory for every registry. If the discovery implementation does not cache instance lists, LoadBalancer caching can reduce query volume and is recommended in production per Spring Cloud documentation.

When two caches sit in series, a change may have to wait for the discovery client to update its snapshot and then wait for the LoadBalancer cache to expire or refresh. Actual lag depends on when the change happens, the fetch interval, how the cache is populated, and the refresh mechanism; do not mechanically add two TTLs together to assume a fixed bound.

### 3.2. Supplier and filter ordering

LoadBalancer can combine multiple suppliers:

- Supplier fetching the list from DiscoveryClient.
- Cache supplier storing the received list.
- Zone preference supplier filtering instances by zone.
- Health check supplier or other filters excluding unsuitable instances.
- Request-based supplier applying hints or request attributes.

When building a supplier chain manually, Spring Cloud documentation recommends placing `CachingServiceInstanceListSupplier` right after the supplier that fetches instances over the network, such as `DiscoveryClientServiceInstanceListSupplier`, and before other filtering suppliers. Placing the cache in the wrong position can cause already-filtered data to be cached and affect subsequent requests.

### 3.3. A cache is not a load-balancing algorithm

The cache only holds the candidate list. Algorithms such as round-robin or random are what decide which instance to pick.

A cached list does not mean every request goes to the same instance. Conversely, changing the LoadBalancer algorithm does not refresh the registry cache on its own.

## 4. HTTP connection pool: reusing network connections

After LoadBalancer picks `10.0.1.11:8081`, the HTTP client needs to connect to that endpoint. Creating a new connection typically involves DNS resolution (if using a hostname), a TCP handshake, and a TLS handshake if using HTTPS.

The HTTP connection pool retains open persistent connections so later requests can reuse them. It answers the question: **Is there a suitable open connection to this endpoint to send the request immediately?**

A pool typically manages:

- Connections currently in use.
- Idle connections available for reuse.
- Maximum connections per route or host.
- Wait time to acquire a connection from the pool.
- Idle duration and maximum connection lifetime.
- Stale connections already closed by the server or an intermediary.

The pool does not store the service instance list. It does not know how many instances `inventory-service` has in the registry; it only manages connections to remote endpoints the HTTP client has used.

### 4.1. Connection pools have their own lifecycle

A connection can be reused across multiple requests to the same route when protocol and configuration allow. After a request completes, the connection can return to an idle state in the pool.

A connection is evicted when:

- It exceeds its TTL or max lifetime.
- It stays idle longer than allowed.
- The server or proxy closes the connection.
- The client detects that the connection is no longer valid.
- The application shuts down the HTTP client or connection manager.

With HTTP/1.1, connections are typically reused sequentially across requests; HTTP/2 can multiplex multiple streams over a single connection. Exact details depend on the protocol, server, and HTTP client.

### 4.2. Pool example with Reactor Netty

`WebClient` typically uses Reactor Netty in WebFlux applications. You can configure a dedicated `ConnectionProvider`:

~~~java
import java.time.Duration;

import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;

import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

ConnectionProvider provider =
        ConnectionProvider.builder("inventory-pool")
                .maxConnections(100)
                .maxIdleTime(Duration.ofSeconds(20))
                .maxLifeTime(Duration.ofMinutes(5))
                .pendingAcquireTimeout(Duration.ofSeconds(2))
                .build();

HttpClient httpClient = HttpClient.create(provider)
        .responseTimeout(Duration.ofSeconds(3));

WebClient webClient = WebClient.builder()
        .clientConnector(new ReactorClientHttpConnector(httpClient))
        .build();
~~~

The limits in this example are illustrative only; tune them based on concurrency, server-side timeouts, load, and provider capacity.

- `maxConnections`: maximum connections managed by the pool per pool/remote host scope depending on the implementation.
- `maxIdleTime`: duration a connection may remain idle.
- `maxLifeTime`: maximum lifetime of a connection.
- `pendingAcquireTimeout`: wait time to acquire a connection when none is immediately free.
- `responseTimeout`: wait time for a response per Reactor Netty configuration.

These are connection pool and HTTP transport parameters. They do not govern discovery refresh or the LoadBalancer cache.

### 4.3. Pool example with Apache HttpClient 5

For blocking HTTP clients, Apache HttpClient 5 provides `PoolingHttpClientConnectionManager`. The pool can cap total connections and connections per route:

~~~java
PoolingHttpClientConnectionManager connectionManager =
        PoolingHttpClientConnectionManagerBuilder.create()
                .setMaxConnTotal(200)
                .setMaxConnPerRoute(50)
                .build();
~~~

The connection manager also supports TTLs, idle timeouts, eviction, and connection validation after idle periods. When using `RestClient` or `RestTemplate`, pooling depends on the underlying request factory and HTTP client configured beneath them; neither abstraction defines a single universal pool across all implementations.

## 5. TTLs across the three layers do not share the same meaning

Both the LoadBalancer cache and the HTTP connection pool may have properties named TTL or lifetime, yet the objects they hold are completely different.

| Expiration setting | Subject | When expired |
|---|---|---|
| Registry fetch interval | Client-side registry snapshot | Discovery client performs the next fetch/refresh |
| LoadBalancer cache TTL | `ServiceInstance` list | Cache entry expires; supplier fetches a fresh list when needed |
| Connection max lifetime | TCP/TLS connection | Pool discards the connection and opens a new one when a request needs it |
| Connection max idle time | Idle connection | Pool closes connections idle for too long |
| Pool acquire timeout | Wait time to borrow a connection | Request fails if no connection is acquired in time |

Do not use `spring.cloud.loadbalancer.cache.ttl` to fix stale connections. Do not lower `maxIdleTime` to force Eureka to update its instance list. Do not increase `registry-fetch-interval-seconds` to solve connection pool exhaustion.

## 6. Flow of a request across all three layers

When `order-service` calls `inventory-service`, the general sequence is:

1. The HTTP client receives a logical URL containing the service ID.
2. LoadBalancer requests the instance list from `ServiceInstanceListSupplier`.
3. The supplier reads data from DiscoveryClient; depending on configuration, the list may come from the discovery cache or the LoadBalancer cache.
4. LoadBalancer picks a `ServiceInstance`.
5. The HTTP client builds a route to the chosen host/port.
6. The HTTP client borrows an appropriate connection from the pool or creates a new connection.
7. The request is sent to the provider and the response is returned.
8. The connection may be returned to the pool for reuse if still valid.

~~~mermaid
sequenceDiagram
    participant O as order-service
    participant LB as LoadBalancer
    participant C as Discovery / LB cache
    participant D as DiscoveryClient
    participant P as HTTP connection pool
    participant I as inventory instance

    O->>LB: Call inventory-service
    LB->>C: Get ServiceInstance list
    alt Cache hit
        C-->>LB: Cached instances
    else Cache miss
        C->>D: Query service instances
        D-->>C: Registry view
        C-->>LB: Instance list
    end
    LB->>LB: Select instance A
    LB->>P: Acquire connection to A
    alt Reusable connection
        P-->>LB: Existing connection
    else No reusable connection
        P->>I: TCP/TLS connect
        I-->>P: Connection established
    end
    LB->>I: HTTP request
    I-->>O: HTTP response
    Note over P,I: Connection may return to pool
~~~

An HTTP request may open a new connection or reuse an existing one. One connection may serve many requests to the same route. Both happen independently of whether the instance list was freshly fetched from the registry.

## 7. When an instance is removed, how does each layer react?

Suppose `inventory-a` is deregistered from the registry.

| Layer | What happens? | What does not happen automatically? |
|---|---|---|
| Registry / Discovery cache | Discovery client sees the change on its next refresh or via backend mechanism | Not all consumers necessarily update at the exact same moment |
| LoadBalancer cache | Old list may still be used until refresh or TTL expiration | A registry update does not guarantee immediate cache entry eviction |
| HTTP connection pool | Connections to `inventory-a` may remain idle until expired/evicted | The pool does not automatically know the registration was removed |

Once discovery and LoadBalancer have updated their lists, new requests will no longer pick `inventory-a` from that list. Even so, an old connection may linger in the pool; it is merely an idle resource and does not mean new requests will keep using it.

If the LoadBalancer cache still contains `inventory-a`, new requests may still pick the stale endpoint. In that case, the HTTP client may try borrowing a live connection or encounter a stale connection already closed by the server.

### 7.1. When an instance is replaced at the same IP and port

A tricky scenario to diagnose is when the address `10.0.1.11:8081` is reused for a new process.

The pool may still hold an open TCP connection to the old process. When the old process shuts down, that connection may be closed or become stale. The first request after an idle period may hit an I/O error even though discovery returned an endpoint with the same host and port.

The fix belongs at the connection layer: idle timeout, max lifetime, post-idle validation, and controlled retries. Refreshing discovery alone does not guarantee old connections are closed immediately.

## 8. When the registry loses connectivity

If a consumer temporarily cannot reach the registry:

- The discovery cache may continue supplying a stale snapshot if the implementation stores data locally.
- The LoadBalancer cache may still retain a previously retrieved instance list.
- The HTTP pool can still send requests to providers using existing connections or create new ones if endpoints remain valid.

This can keep some requests working during registry outages. However, it also creates the risk of calling dead instances or missing newly added ones.

Do not assume caches are always retained when refresh fails. Behavior depends on the discovery implementation, supplier, cache, and the error raised. Inspect logs and metrics for your specific client.

## 9. When the HTTP connection pool is exhausted

A pool can run out of free connections even when both the registry and LoadBalancer are functioning normally.

For example:

- LoadBalancer properly picks `inventory-a`.
- The pool has reached `maxConnections`.
- All current connections are occupied by other in-flight requests.
- New requests must wait in the pending acquire queue.
- If waiting exceeds `pendingAcquireTimeout`, the request fails before connecting to the provider.

This is a transport resource error, not a discovery error. Increasing the LoadBalancer cache TTL will not give the pool more connections. Inspect concurrency, response times, leased connection count, idle connections, pending acquires, and provider-side limits.

Do not blindly raise `maxConnections` very high. Too many concurrent connections can overwhelm the provider, network load balancers, or operating system.

## 10. Overall configuration by registry type

### 10.1. Eureka

Eureka Client already maintains a local registry and refreshes periodically. In an illustrative setup, you can keep discovery caching and disable LoadBalancer caching to avoid double caching:

~~~yaml
eureka:
  client:
    fetch-registry: true
    registry-fetch-interval-seconds: 30

spring:
  cloud:
    loadbalancer:
      cache:
        enabled: false
~~~

The `registry-fetch-interval-seconds` property defaults to 30 seconds in current Spring Cloud Netflix configurations. Verify your actual version and change it only after measuring the trade-off between registry freshness and server load.

### 10.2. Registries that do not cache instance lists in DiscoveryClient

If the discovery implementation does not cache query results, LoadBalancer caching can reduce discovery call frequency:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: true
        ttl: 20s
        capacity: 256
~~~

A 20-second TTL is only an example value. Choose it based on how fast instances churn and how much stale data the application can tolerate.

### 10.3. HTTP pool

Pool configuration lives in the HTTP client, not in `spring.cloud.loadbalancer.cache`. With Reactor Netty, configure `ConnectionProvider`; with Apache HttpClient 5, configure the corresponding connection manager and request factory.

There is no single shared Spring Cloud property set controlling every HTTP client. Identify whether the application uses `WebClient`, `RestClient`, `RestTemplate`, or OpenFeign, and which transport implementation is underneath before tuning pools.

## 11. Rules for choosing timeouts and limits

Do not choose TTLs or pool sizes purely from defaults. Base them on operational requirements:

| Question | Parameters to examine |
|---|---|
| How soon must a new instance appear to consumers? | Registry fetch/refresh interval and backend event mechanisms |
| How long may a removed instance remain in the list? | Discovery cache and LoadBalancer cache TTL |
| How long can a request wait to acquire a connection? | Pool acquire timeout |
| How long may a new connection take to connect? | Connect timeout |
| How long before an idle connection is closed? | Max idle time |
| Maximum duration a connection may be reused? | Max lifetime / TTL |
| Maximum time a request waits for a response? | Response/read timeout |
| How many concurrent requests go to one provider? | Pool max connections, per-route limits, and concurrency |

Endpoint update lag can accumulate across multiple layers. When budgeting target time to drop a failing instance, measure the entire path from when the provider changes state until the consumer stops selecting the stale endpoint.

## 12. Observing each layer

### Discovery cache

Monitor:

- Timestamp of the latest successful registry fetch.
- Number of services and instances in the local registry.
- Delta/full fetch counts and synchronization errors.
- Time elapsed from registry change until DiscoveryClient observes it.

### LoadBalancer cache

Monitor:

- Cache hits/misses.
- TTL and entry counts.
- Instance list after filtering steps.
- Actual instance selected for each request.
- Supplier list-fetch latency and discovery errors.

### HTTP connection pool

Monitor:

- Leased, idle, and pending connections.
- New connection creation counts.
- Acquire timeouts, connect timeouts, and response timeouts.
- Connections closed due to idle/lifetime or stale validation.
- TCP/TLS handshake and request latencies.

Include service ID, instance ID, host/port, and trace ID in logs or metrics at appropriate levels. Do not log tokens or sensitive data.

## 13. Symptom-based diagnostic workflow

| Symptom | Layer to check first | How to verify |
|---|---|---|
| Registry removed instance, but consumer still picks it | Discovery cache and LoadBalancer cache | Check local registry, fetch interval, cache TTL, and supplier list |
| `DiscoveryClient` sees new instance, but LoadBalancer has not picked it | LoadBalancer cache/filter | Check cache entries, supplier chain, and zone/health filters |
| LoadBalancer picked the right instance, but connect times out | HTTP client / network | Check route, DNS, TCP connect, firewall, and connect timeout |
| Pool acquire timeout | HTTP connection pool | Check max connections, pending queue, request duration, and leased connections |
| First request after idle period gets reset | HTTP connection pool | Check server/proxy idle timeout, maxIdleTime, and stale validation |
| Closed pool, yet still calls stale endpoint | Discovery / LoadBalancer cache | Pool only opens new connections; the instance list can still be stale |
| Increased LoadBalancer TTL, yet TCP handshakes did not drop | HTTP connection pool | Check pool reuse and HTTP client scope |
| Requests still go to instance after deregister | Candidate list or in-flight requests | Check caches, endpoint selection timing, and in-flight requests |

Workflow for inspecting a failed request:

1. Record the service ID and endpoint selected by LoadBalancer.
2. Check what list `DiscoveryClient` currently returns.
3. Check whether the supplier and LoadBalancer cache hold a different list.
4. Check whether the HTTP client picked an existing connection or opened a new one.
5. Read the exact failure: acquire timeout, connect timeout, TLS error, response timeout, or HTTP status.
6. Compare timestamps to identify which layer held stale data.

## 14. Testing instance and connection changes

A useful test suite should cover all three layers:

| Scenario | Expected result to verify |
|---|---|
| Adding a new instance | Discovery client receives the instance; supplier/LoadBalancer sees it after refresh |
| Deregistering an instance | Instance disappears from candidate list after convergence time |
| Unhealthy instance | Health filter or status filter excludes the instance per policy |
| Temporary registry disconnection | Consumer handles stale snapshot and refresh failures as designed |
| Provider restarts on same IP/port | Stale connection is detected/discarded and a new connection is established |
| Pool reaches capacity | Requests wait or time out according to acquire policy |
| Server closes idle connection | Client evicts stale connection and establishes a new one |
| HTTP client shutdown | Pool releases resources with no leaked connections |

Do not just check instance counts in a dashboard. Verify which endpoint LoadBalancer actually picks and which connection the HTTP client actually uses.

## 15. Key takeaways

- The discovery cache stores the client-side registry view; its mechanism and refresh cycle depend on the DiscoveryClient implementation.
- Eureka Client maintains a local registry and provides `eureka.client.registry-fetch-interval-seconds` to control the fetch interval.
- The LoadBalancer cache stores the `ServiceInstance` list provided by the supplier; current defaults are a 35-second TTL and capacity of 256.
- If DiscoveryClient already caches, as with Eureka, consider disabling LoadBalancer caching to avoid double caching.
- The HTTP connection pool holds TCP/TLS connections to endpoints, not the instance list.
- `maxIdleTime`, `maxLifeTime`, `maxConnections`, acquire timeout, and response timeout govern different transport aspects.
- Registry updates do not automatically clear the LoadBalancer cache or connection pool; each layer has its own refresh/eviction mechanism.
- When debugging, record the service ID, selected instance, and transport error together to pinpoint which layer caused stale data or request failure.

All three layers participate in a single service call while solving three separate problems. Discovery finds instances, LoadBalancer picks a target, and the HTTP client manages connections to that target. Configuring and observing each layer independently lets the system balance discovery freshness, lookup cost, and connection reuse efficiency.

## References

- [Spring Cloud Commons — Service Discovery abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
- [Spring Cloud Commons — Spring Cloud LoadBalancer and caching](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html)
- [Spring Cloud Netflix — Configuration Properties](https://docs.spring.io/spring-cloud-netflix/reference/configprops.html)
- [Reactor Netty — HTTP Client connection pool and timeouts](https://projectreactor.io/docs/netty/release/reference/http-client.html)
- [Apache HttpComponents — Connection management](https://hc.apache.org/httpcomponents-client-5.6.x/connection-management.html)
