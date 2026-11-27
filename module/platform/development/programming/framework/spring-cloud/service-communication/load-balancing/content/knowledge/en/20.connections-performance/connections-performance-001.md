# Reusing HTTP Clients and Avoiding Per-Request Connection Creation

In a microservices system, `order-service` might call `catalog-service` hundreds or thousands of times per second. If every call builds a new HTTP client with its own transport resources, or closes the connection immediately after each request, the application easily pays more than necessary for **TCP/TLS handshakes, socket allocation, thread/memory management, and connection pool waiting**. Increasing load can also exhaust file descriptors, produce many sockets in the `TIME_WAIT` state, or increase tail latency.

This lesson belongs to the **Connections and Performance** chapter of the **SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING** module. The focus is on **reusing HTTP clients and connection pools** when calling by service ID through **Spring Cloud LoadBalancer**, while understanding the role of discovery, health checks, routing policies, timeouts/retries, and error observability. The examples cover synchronous `RestClient`, reactive `WebClient`, and declarative `OpenFeign`.

> **Principle:** create and configure the client at the application level or in a sufficiently long-lived scope; reuse the client across multiple requests. However, *reusing a client object* and *reusing a TCP connection* are not the same concept: a connection can only be reused if the HTTP transport, server, proxy, and pool policy allow it.

## 1. Four Distinct Components: Service ID, Client, Pool, and Socket

When calling `http://catalog-service/api/items/42`, there are at least four levels to distinguish:

1. **Service ID:** `catalog-service` is the logical name that Spring Cloud LoadBalancer uses to look up the list of `ServiceInstance`s.
2. **HTTP client:** the `RestClient`, `WebClient`, or Feign proxy object that holds request configuration and uses an HTTP transport.
3. **Connection manager/pool:** the layer that manages physical connections or logical HTTP streams that can be reused, depending on the client and protocol.
4. **TCP/TLS connection:** the actual communication channel to a specific endpoint, which may be kept open for subsequent requests or closed.

~~~mermaid
flowchart TD
    A["order-service"] --> R["RestClient / WebClient / Feign proxy (reuse)"]
    R --> LB["Spring Cloud LoadBalancer"]
    DISC["Discovery + supplier + health/filter"] --> LB
    LB --> X{"Select ServiceInstance"}
    X --> B["catalog-a :18081"]
    X --> C["catalog-b :18082"]
    R --> P["HTTP transport + connection pool"]
    P -. "Existing connection to A" .-> B
    P -. "Existing connection to B" .-> C
~~~

**LoadBalancer selects the destination for an HTTP request; the connection pool manages connections to the selected destination.** A pool does not replace discovery, and a cached instance list does not mean sockets to each instance are already open.

### Lifecycle Example

~~~text
Request #1: service ID -> choose A -> no socket yet -> TCP/TLS connect -> HTTP GET
Request #2: service ID -> choose B -> no socket B yet -> TCP/TLS connect -> HTTP GET
Request #3: service ID -> choose A -> usable socket A exists -> reuse
Request #4: service ID -> choose B -> socket B was closed by server -> open new socket
~~~

This example illustrates a possible scenario; it does not guarantee that Round Robin always produces the exact order above. Socket reuse depends on the actual transport and connection state at the time of the request.

## 2. Why Creating a New Client and Connection per Request Is Expensive

A new HTTP connection may have to perform:

- Destination address resolution at the transport layer according to configuration, network routing, and selecting an appropriate address.
- A TCP three-way handshake; if using HTTPS, performing the appropriate TLS handshake.
- Initializing or allocating sockets, buffers, and connection management structures.
- Establishing connection state, verifying certificates, and exchanging HTTP headers.
- Closing the socket and incurring cleanup overhead; in some cases many `TIME_WAIT` connections appear.

These costs increase **latency per request**, network/crypto CPU usage, concurrent connection counts, and resource pressure. Creating a new HTTP client may also create a new request factory, connection manager, or event-loop resources depending on how it is configured.

However, avoid claiming that "every `new RestClient` definitely creates a TCP connection." **Creating a client object and opening a socket are two different operations**; some implementations may share a default transport or open connections lazily. The problem is that creating unnecessary clients/transports/pools forfeits controlled reuse and makes resource lifecycles difficult to manage.

### Recognizing the Anti-Pattern

~~~java
// Do not create a new client every time a business operation needs to make an HTTP call.
ItemDto findItem(String id) {
    RestClient client = RestClient.create();

    return client.get()
        .uri("http://catalog-service/api/items/{id}", id)
        .retrieve()
        .body(ItemDto.class);
}
~~~

Beyond the client creation overhead, this example has a separate bug: `RestClient.create()` does not automatically receive Spring's `@LoadBalanced` configuration, so the host `catalog-service` may be sent through regular DNS instead of Spring Cloud LoadBalancer discovery.

With WebClient, calling `WebClient.create(...)` in every handler likewise makes client and connector policies inconsistent. With Feign, building a Feign proxy per request instead of injecting a Spring-managed bean is a similar anti-pattern.

## 3. HTTP/1.1 Keep-Alive and HTTP/2 Multiplexing

**HTTP/1.1:** when persistent connections are supported, multiple sequential requests can travel over the same TCP connection. An HTTP/1.1 connection generally cannot execute multiple responses concurrently in the multiplexed manner of HTTP/2; to handle many concurrent requests, the transport may need multiple connections in the pool.

**HTTP/2:** multiple HTTP streams can coexist over a single TCP/TLS connection when the client, server, and intermediary infrastructure have negotiated HTTP/2. This reduces the need to open new TCP connections in many cases, though there are still concurrent stream limits, flow control, and server resource limits.

| Aspect | HTTP/1.1 persistent | HTTP/2 |
|---|---|---|
| TCP reuse | Yes, when keeping the connection open | Yes |
| Concurrent requests on the same connection | Usually not multiplexed like HTTP/2 | Multiple logical streams can be multiplexed |
| How concurrency is limited | Connection count and pool queue | Connection count, streams, and flow control |
| Always used? | Depends on transport/server | Must actually be supported and negotiated |
| Eliminates the need for pool management? | No | No |

Even if the client is a singleton, the server/proxy can close an idle connection after a timeout or send `Connection: close` in HTTP/1.1. The client may have to open another connection on a subsequent request. **Do not aim for "never open a new connection"; the goal is sensible reuse and proper connection lifecycle cleanup.**

## 4. LoadBalancer Still Selects an Instance on Every HTTP Request

Spring Cloud LoadBalancer can choose `catalog-a` for the first request and `catalog-b` for the second request. When the transport has an open socket to A, it can only reuse that socket for a request that matches the **physical destination, scheme, security, and the transport's connection partitioning rules**.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Caller
    participant LB as Spring Cloud LoadBalancer
    participant Pool as HTTP connection pool
    participant A as catalog-a
    participant B as catalog-b

    C->>LB: Request 1 to catalog-service
    LB-->>C: Select A
    C->>Pool: Request connection to A
    Pool->>A: Open TCP/TLS if not present
    A-->>C: Response 200
    Note over Pool: Keep connection A if reusable

    C->>LB: Request 2 to catalog-service
    LB-->>C: Select B
    C->>Pool: Request connection to B
    Pool->>B: Open TCP/TLS if not present
    B-->>C: Response 200

    C->>LB: Request 3 to catalog-service
    LB-->>C: Select A
    C->>Pool: Request connection to A
    Pool-->>C: Reuse connection A if still valid
    C->>A: GET over connection A
    A-->>C: Response 200
~~~

**A shared client does not force all requests to go to the same instance.** Conversely, a connection pool is not a sticky-session policy: it only reuses a connection if the newly selected instance has an endpoint matching an existing connection.

This is also why changing the instance selection algorithm, filtering by zone, or updating health checks still takes effect when the client is reused. Those changes typically affect **new requests**, without forcibly redirecting an in-flight request or stream.

## 5. Designing the HTTP Client Lifecycle in Spring

In Spring, the standard approach is to **declare the client or proxy as a bean** and inject it into business services:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
class CatalogClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder catalogLoadBalancedBuilder() {
        return RestClient.builder();
    }

    @Bean
    RestClient catalogRestClient(
            @Qualifier("catalogLoadBalancedBuilder")
            RestClient.Builder builder) {

        return builder
            .baseUrl("http://catalog-service")
            .build();
    }
}
~~~

Then reuse it:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

record ItemDto(String id, String name, int stock) {}

@Service
class CatalogGateway {

    private final RestClient catalogRestClient;

    CatalogGateway(RestClient catalogRestClient) {
        this.catalogRestClient = catalogRestClient;
    }

    ItemDto getItem(String id) {
        return catalogRestClient.get()
            .uri("/api/items/{id}", id)
            .retrieve()
            .body(ItemDto.class);
    }
}
~~~

With a Spring singleton bean like the above, multiple calls to `getItem` use **the same configured RestClient instance**. The request specs created from the client are per-call objects; do not store a mutable request spec to share across threads.

### Distinguishing Between Client and Builder

- **A built RestClient/WebClient** is generally safe to use across multiple threads when its configuration is not modified, and is designed for reuse.
- **A Builder** is a mutable configuration object. Do not let multiple threads mutate the same builder and build a client per request.
- If you need multiple clients for different downstreams, you can create separate client beans from cloned builders or separately configured builders.
- Do not retain request/response body streams after the request lifecycle ends; close/consume them according to the HTTP stack's contract.

In Spring MVC applications or background tasks, inject `CatalogGateway` or `RestClient` as a long-lived dependency. In WebFlux, inject a pre-configured `WebClient` instead of creating a client inside each `flatMap` chain.

## 6. Reusing RestClient Is Not Enough Without an Appropriately Pooled Transport

`RestClient` is a facade for synchronous HTTP operations; pooling capability depends on the `ClientHttpRequestFactory` and HTTP transport. If you want explicit pool control in an application using Apache HttpComponents 5, you can provide an `HttpComponentsClientHttpRequestFactory`.

**Dependencies (Gradle, with a compatible Spring Boot/Spring Cloud BOM):**

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.cloud:spring-cloud-starter-loadbalancer'
    implementation 'org.apache.httpcomponents.client5:httpclient5'
}
~~~

**Example Apache HttpClient 5 pool configuration:**

~~~java
import org.apache.hc.client5.http.config.RequestConfig;
import org.apache.hc.client5.http.impl.classic.CloseableHttpClient;
import org.apache.hc.client5.http.impl.classic.HttpClients;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManagerBuilder;
import org.apache.hc.core5.util.TimeValue;
import org.apache.hc.core5.util.Timeout;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.HttpComponentsClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
class PooledCatalogRestClientConfiguration {

    @Bean(destroyMethod = "close")
    CloseableHttpClient pooledApacheHttpClient() {

        var manager = PoolingHttpClientConnectionManagerBuilder.create()
            .setMaxConnTotal(200)
            .setMaxConnPerRoute(50)
            .build();

        RequestConfig requestConfig = RequestConfig.custom()
            .setResponseTimeout(Timeout.ofSeconds(3))
            .build();

        return HttpClients.custom()
            .setConnectionManager(manager)
            .setDefaultRequestConfig(requestConfig)
            .evictExpiredConnections()
            .evictIdleConnections(TimeValue.ofSeconds(30))
            .build();
    }

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder(
            CloseableHttpClient pooledApacheHttpClient) {

        var factory = new HttpComponentsClientHttpRequestFactory(
            pooledApacheHttpClient);

        factory.setConnectTimeout(2000);
        factory.setConnectionRequestTimeout(1000);

        return RestClient.builder().requestFactory(factory);
    }

    @Bean
    RestClient catalogRestClient(
        @Qualifier("loadBalancedRestClientBuilder") RestClient.Builder builder
    ) {
        return builder.baseUrl("http://catalog-service").build();
    }
}
~~~

The bean definitions in sections 5 and 6 are **two alternative configuration approaches**; do not register both under the same name if the Spring context only needs one `catalogRestClient`.

Configuration meaning:

| Component | Example Value | Purpose |
|---|---:|---|
| `maxConnTotal` | 200 | Caps total connections managed by the Apache connection manager |
| `maxConnPerRoute` | 50 | Caps connections per corresponding physical route |
| `connectionRequestTimeout` | 1 second | Caps wait time to acquire a connection from the pool |
| `connectTimeout` | 2 seconds | Caps connection establishment according to transport/factory |
| `responseTimeout` | 3 seconds | Caps waiting for a response according to the Apache transport |
| `evictIdleConnections` | 30 seconds | Evicts idle connections according to policy |
| `destroyMethod="close"` | When Spring context closes | Releases transport and connections |

**These numbers are experimental configuration values, not default production recommendations.** Timeout APIs or Apache HC5 policies may differ across minor versions of Spring Framework/HttpComponents; check the dependencies you use before applying the code verbatim.

### Why Limit Both Total and Per-Route?

Spring Cloud LoadBalancer can choose among multiple instances, each representing a physical destination. With Apache HttpClient, `maxConnTotal` limits total connections managed by the manager; `maxConnPerRoute` limits connections per route. If there are 10 instances and each could receive 50 connections, you cannot assume the system is allowed 500 total connections when `maxConnTotal` is only 200.

Conversely, a single overloaded instance can exhaust its per-route limit while the overall pool is not yet full. The two metrics must be interpreted differently.

## 7. Reusing WebClient and the Reactor Netty Connection Pool

`WebClient` provides a reactive API and can use Reactor Netty as its HTTP connector. In a Spring WebFlux application, a configured `WebClient` should be **reused**—do not create a new WebClient/HttpClient/ConnectionProvider for each event.

**Dependencies (Gradle):**

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.cloud:spring-cloud-starter-loadbalancer'
}
~~~

Example of **customizing a ConnectionProvider** to manage pooled connections:

~~~java
import java.time.Duration;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;

@Configuration(proxyBeanMethods = false)
class PooledCatalogWebClientConfiguration {

    @Bean(destroyMethod = "dispose")
    ConnectionProvider catalogConnectionProvider() {
        return ConnectionProvider.builder("catalog-pool")
            .maxConnections(100)
            .pendingAcquireMaxCount(200)
            .pendingAcquireTimeout(Duration.ofSeconds(1))
            .maxIdleTime(Duration.ofSeconds(30))
            .maxLifeTime(Duration.ofMinutes(5))
            .evictInBackground(Duration.ofSeconds(30))
            .build();
    }

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder(
            ConnectionProvider catalogConnectionProvider) {

        HttpClient client = HttpClient.create(catalogConnectionProvider)
            .responseTimeout(Duration.ofSeconds(3));

        return WebClient.builder()
            .clientConnector(new ReactorClientHttpConnector(client));
    }

    @Bean
    WebClient catalogWebClient(
        @Qualifier("loadBalancedWebClientBuilder") WebClient.Builder builder
    ) {
        return builder.baseUrl("http://catalog-service").build();
    }
}
~~~

The values above illustrate how to configure the pool, not mandatory settings. Reactor Netty manages pools by remote endpoints/connection keys; `maxConnections` typically applies to a partitioned pool, **not automatically to the total TCP connections of the entire application**. You must monitor actual pool/target counts when there are many `ServiceInstance`s.

`pendingAcquireMaxCount` caps the queue waiting to acquire a connection; `pendingAcquireTimeout` caps how long to wait. `maxIdleTime` and `maxLifeTime` help avoid keeping sockets around for too long. Do not use these limits as a substitute for business timeouts or backpressure/concurrency control.

**Important regarding lifecycle:** because the ConnectionProvider is created specifically for this configuration, Spring needs to dispose of it when the context closes. In applications using global Reactor Netty resources or other Spring Boot auto-configurations, sharing and lifecycle management may differ; do not dispose of a shared provider serving other clients mid-operation.

### Example Using WebClient in a Reactive Service

~~~java
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

@Service
class ReactiveCatalogGateway {

    private final WebClient catalogWebClient;

    ReactiveCatalogGateway(WebClient catalogWebClient) {
        this.catalogWebClient = catalogWebClient;
    }

    Mono<ItemDto> getItem(String id) {
        return catalogWebClient.get()
            .uri("/api/items/{id}", id)
            .retrieve()
            .bodyToMono(ItemDto.class);
    }
}
~~~

Each subscription to `getItem` can trigger a new HTTP request, while sharing the **configured WebClient, connector, and pool**. Avoid calling `block()` on a WebFlux event-loop; if many requests must be processed concurrently, cap concurrency so everything is not dumped onto the pool at once.

## 8. OpenFeign: Reusing Proxies and the HTTP Transport

With Spring Cloud OpenFeign, the standard approach is to inject the `@FeignClient` bean created by Spring rather than creating a new Feign proxy in every method:

~~~java
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;

@FeignClient(name = "catalog-service")
interface CatalogFeignClient {

    @GetMapping("/api/items/{id}")
    ItemDto getItem(@PathVariable("id") String id);
}
~~~

Once `@EnableFeignClients` is enabled and compatible dependencies are configured:

~~~java
import org.springframework.stereotype.Service;

@Service
class CatalogUseCase {

    private final CatalogFeignClient catalog;

    CatalogUseCase(CatalogFeignClient catalog) {
        this.catalog = catalog;
    }

    ItemDto getItem(String id) {
        return catalog.getItem(id);
    }
}
~~~

The Feign proxy is managed by Spring, while **connection reuse capability** depends on the underlying HTTP client implementation used by Feign. With properly configured Apache HttpClient 5 or OkHttp, connection pooling is generally supported; however, you must not assume that simply adding `@FeignClient` guarantees a specific transport is in use.

Example configuration of common OpenFeign properties, which should be cross-checked against your release train:

~~~yaml
spring:
  cloud:
    openfeign:
      client:
        config:
          catalog-service:
            connectTimeout: 2000
            readTimeout: 3000
      httpclient:
        max-connections: 200
        max-connections-per-route: 50
~~~

This configuration targets the **client name** and HTTP client integration properties; it only tunes connections meaningfully when the corresponding implementation is loaded and active. To use HC5, ensure the Apache HC5 dependency is present and the transport-enabling configuration matches your version, and verify the actual beans/metrics. If you choose OkHttp, the properties and pool configuration also differ.

**Feign generally operates under a blocking model** in Spring Cloud OpenFeign. It does not automatically become a reactive client just because the backend supports HTTP/2 or connection pooling.

## 9. Do Not Confuse Three Different Kinds of Cache/Pool

The following components often appear together, yet serve different purposes:

| Component | What does it store? | What does it do? |
|---|---|---|
| `CachingServiceInstanceListSupplier` | Instance list per service ID | Reduces discovery queries, at the risk of a stale list |
| HTTP connection pool | Connections to a selected host/port/route | Reduces unnecessary TCP/TLS handshakes |
| Application response cache | DTOs/HTTP responses/business data | Reduces the number of HTTP requests actually sent |

Caching the instance list **does not hold sockets**; a connection pool **does not cache JSON responses**; a response cache **does not decide which instance LoadBalancer picks**. Tuning the TTL of one type does not automatically fix problems in the others.

### Numerical Example

Suppose 10,000 requests call `catalog-service` during a measurement window:

- The instance list cache can reduce the number of discovery lookups to a very small amount.
- The HTTP connection pool can reuse a set of connections to A/B instead of performing a TCP/TLS handshake for each request.
- The response cache (if allowed by contract) can reduce the number of requests that actually need to hit catalog.

These are three distinct changes. When measuring performance, clarify your target: **instance lookup latency, new connection count, or request count to the backend**.

## 10. Sizing the Pool from Concurrency and Latency

A starting approximation is Little's Law in steady state:

~~~text
Average in-flight requests ≈ throughput (requests/second)
                           × average processing time (seconds)
~~~

For example, if a caller sends **200 requests/second** to a downstream with an average service time of **100 ms**:

~~~text
200 req/s × 0.1 s = 20 average concurrent requests
~~~

If one HTTP/1.1 request holds one active connection, an average of around 20 active connections is a reference point, **not the optimal `max=20` setting**. Burst traffic, p95/p99 tail latency, DB waits, retries, and parallel requests may require substantial headroom.

If latency rises to 500 ms while throughput stays at 200 requests/second:

~~~text
200 req/s × 0.5 s = 100 average concurrent requests
~~~

The connection pool may start blocking or pending counts may climb. In this scenario, simply increasing `maxConnections` can push even more concurrent requests onto the downstream and **worsen the overload**.

### A Service with Multiple Instances

If `catalog-service` has a fast instance A at 50 ms and a slow instance B at 500 ms, each receiving 100 requests/second:

| Instance | Assigned requests/second | Mean latency | Approximate average in-flight |
|---|---:|---:|---:|
| A | 50 | 50 ms | 2.5 |
| B | 50 | 500 ms | 25 |

Even though LoadBalancer distributes requests evenly, B consumes far more connection resources. If the pool has separate per-route limits, B may build up a larger pending acquire queue than A.

**Do not turn the connection pool into a band-aid that hides server slowness.** Investigate the root causes of latency, saturation, and retry architecture before blindly raising limits.

## 11. Pool Exhaustion: When Resources Are Held Too Long

A request may have to wait for a connection if the entire pool for a route is full or connections are busy serving other requests.

~~~mermaid
flowchart TD
    A["Request needs to be sent to catalog-b"] --> B{"Valid idle connection available?"}
    B -->|Yes| C["Lease/reuse connection"]
    B -->|No| D{"Can a new connection be created within limits?"}
    D -->|Yes| E["Open TCP/TLS connection"]
    D -->|No| F["Wait in pending-acquire queue"]
    F --> G{"Slot available before timeout?"}
    G -->|Yes| C
    G -->|No| H["Pool acquire timeout / wait rejected"]
    C --> I["Execute HTTP request"]
    E --> I
    I --> J["Consume/close response -> return resource to pool"]
~~~

When busy connections or the wait queue grow, check:

- Is the **application generating more concurrent requests** than expected?
- Is the **downstream processing slowly**, causing connections to be held for a long time?
- Are **response bodies consumed and closed properly**, or are streams leaking/hanging?
- Is the **response read timeout** too long, holding sockets open after the user has given up?
- Is a **retry storm** multiplying attempts?
- Are many **service instances/physical routes** fragmenting the pool?
- Is **long-lived streaming** sharing a pool with short requests?

Pool exhaustion and "server has no instances" are two different errors. With pool exhaustion, LoadBalancer may have already selected an instance; the HTTP transport simply failed to obtain a connection in time.

## 12. Managing the Response Body to Return Connections to the Pool

For an HTTP connection to have a chance at reuse, the HTTP transport needs to know that the response has been read to an appropriate point or properly closed/cancelled.

**With RestClient:**

~~~java
ItemDto item = catalogRestClient.get()
    .uri("/api/items/{id}", id)
    .retrieve()
    .body(ItemDto.class);
~~~

This is the common path: the converter consumes the body and RestClient/transport manages the response lifecycle. If you use `exchange(...)` for lower-level response access, do not carelessly retain the `ClientHttpResponse`/input stream outside the callback. Reading huge bodies into RAM with `readAllBytes()` also carries its own cost.

**With WebClient:**

~~~java
Mono<ItemDto> item = catalogWebClient.get()
    .uri("/api/items/{id}", id)
    .retrieve()
    .bodyToMono(ItemDto.class);
~~~

The publisher performs I/O upon subscription, and the lifecycle must be managed so the body is read or the subscription is cancelled when no longer needed. Do not create a `Mono` and call `subscribe()` yourself inside a service unless you manage the `Disposable` and cancellation.

**With SSE/long-lived streaming:** the response may continue indefinitely, so an HTTP connection or logical HTTP stream can be held for a long time. You cannot assume that "reading the first event" suffices to return the connection to the pool. You must have timeouts/heartbeats, cancellation, and dedicated quotas for streaming.

### Common Mistake

~~~java
// Do not do this inside a WebFlux pipeline:
catalogWebClient.get()
    .uri("/api/events")
    .retrieve()
    .bodyToFlux(String.class)
    .collectList()
    .block();
~~~

If `/api/events` is an unbounded stream, `collectList()` will wait forever and can accumulate unbounded data; `block()` also occupies a thread. This is not a "pool too small" error, but a response lifecycle and consumption issue.

## 13. Choosing Layered Timeouts Without Confusing Them with Pool Size

Each limit governs a different phase:

| Limit | Applies to | When exceeded |
|---|---|---|
| Pool acquire timeout | Waiting to acquire a connection from the pool | HTTP request has not been sent to the backend yet |
| Connect timeout | Establishing the connection | No TCP connection established within deadline |
| TLS handshake timeout | Security negotiation | TLS handshake not completed |
| Response/read timeout | Waiting for/reading response in transport | The request may already have been processed by the target |
| End-to-end deadline | Overall business operation | Caller no longer wants to wait |
| Idle connection lifetime | Idle connections in the pool | Connections may be evicted |
| Maximum connection lifetime | Total age of a connection | Transport may replace it with a new connection |

**Increasing pool size does not fix read timeouts. Decreasing connect timeout does not resolve pending acquire queues.** You must measure wait time at each stage.

For calls with side effects such as a POST that creates an order, a response timeout does not mean the server definitely did not commit. If retrying, use an idempotency key that persists across attempts and query state when the outcome is uncertain.

## 14. Dead Instances, Stale Idle Connections, and Topology Changes

In autoscaling or rolling deployment environments, an instance with open connections in the pool can stop serving traffic:

~~~mermaid
sequenceDiagram
    participant D as Discovery
    participant LB as LoadBalancer
    participant P as Connection pool
    participant A as catalog-a
    participant B as catalog-b

    D-->>LB: [A, B]
    LB->>P: Request to B
    P->>B: Open connection to B
    B-->>P: Response
    Note over P: Connection B idle in pool
    Note over B: B stops or proxy closes idle socket
    D-->>LB: [A]
    LB->>P: New request to A
    P->>A: Reuse/open connection A
    Note over P: B may keep an idle entry until eviction/validation
~~~

When discovery/supplier updates and stops selecting B, **new requests** can avoid B. Old connections to B can be cleaned up by pool policy, but LoadBalancer does not automatically "delete sockets" solely because the service list changed.

Conversely, if discovery/health caches still consider B a candidate, LoadBalancer may pick B and the pool may try a socket already closed by the server; the request may encounter connection reset/refused/timeout. You must combine **timely discovery updates, health checks, pool TTL/eviction, timeouts, and safe retries**.

### Not Every Reuse Error Is a LoadBalancer Error

- `Connection reset by peer` may come from a backend/proxy closing an idle socket.
- `Pool acquire timeout` may result from caller concurrency saturation.
- `No servers available` / failure to select an instance usually relates to the discovery/supplier candidate set.
- `Read timeout` may happen because the request reached the server but took too long to process.
- HTTP `503` from a backend/gateway has a response, unlike a connection error before an HTTP response is received.

Proper error classification leads to the right fix: tuning the pool, tuning timeouts, fixing discovery, or shedding downstream load instead of merely adding retries.

## 15. HTTP Client Reuse and Long-Lived Connections

When calling SSE, gRPC streaming, or large HTTP responses, connection hold times differ completely from a short JSON GET. With HTTP/1.1, a single SSE response can keep a TCP connection busy for the entire stream. With HTTP/2, one TCP connection can carry multiple logical streams, yet concurrency and flow control still have limits.

An application with 500 SSE subscribers cannot be evaluated with the same "requests/second" metric as 500 short GETs. Consider:

- Dedicated pools/connectors and quotas for streaming if load is high.
- Limiting active subscribers and time without heartbeats.
- Cancellation when the client disconnects to release upstream resources.
- Not applying a short REST JSON response timeout to a stream that is intentionally quiet for long periods.
- Monitoring active connections, active streams, and memory buffers.

**Reuse does not mean keeping every connection alive indefinitely.** For long-lived streams, holding the connection is part of the data-transfer contract; for short requests, reusing idle connections helps reduce latency.

## 16. OpenFeign, RestClient, and WebClient: Choosing by Application Model

| Criterion | RestClient | WebClient | OpenFeign |
|---|---|---|---|
| API | Fluent, synchronous | Fluent, reactive | Declarative interface |
| Objects to reuse | `RestClient` and transport | `WebClient`, connector/provider | Feign proxy and HTTP transport |
| Pooling depends on | `ClientHttpRequestFactory` | Client connector (e.g., Reactor Netty) | Feign HTTP client (HC5/OkHttp...) |
| LoadBalancer by service ID | `@LoadBalanced` builder | `@LoadBalanced` builder | Feign integration with LoadBalancer |
| Request management | Thread blocking | Subscription, demand, cancellation | Usually blocking |
| Failure mode if created per-request | Loses configuration, hard to reuse pool | Creates redundant connectors/pools, hard to clean up | Creates redundant proxies/transports |
| What to monitor | leased/pending per-route, timeouts | active/pending connections, event-loop | HTTP transport metrics, Feign status |
| Best suited for | Spring MVC, request-response | WebFlux, streaming | Projects using many declarative clients |

There is no blanket conclusion that WebClient is always faster than RestClient or OpenFeign in every scenario. Actual performance also depends on transport, contention, serialization, server, CPU, connection pool, concurrency level, and how business code is written. Teams should measure against real SLOs and workloads.

## 17. Observability: Verifying That Clients Are Reusing Connections

Creating a singleton bean is a **design prerequisite**, but does not prove the transport is actually reusing sockets. To know for sure, you need metrics/logs at the HTTP transport and OS layers.

| Signal | Helps answer |
|---|---|
| Connections created/opened/closed | Is every request opening a new socket? |
| Active / idle / leased connections | Is the pool reusing sensibly or holding connections too long? |
| Pending acquire count/time | Are callers waiting because the pool is full? |
| Connection lifetime / idle age | Are sockets sitting idle too long, going stale, or churning? |
| Connect/TLS handshake latency | How much cost comes from opening new connections? |
| HTTP request rate and p50/p95/p99 | Did latency improve after pooling? |
| Error by cause | How do refused, reset, timeout, and HTTP 5xx differ? |
| Service ID and selected instance | What does actual traffic distribution look like? |
| Retry attempts | Is load spiking due to a retry storm? |
| Backend active connections | Is the client pool exceeding server capacity? |

With Reactor Netty, you can enable appropriate metrics for `ConnectionProvider` and the HTTP client as configured. With Apache HC5, use pool stats/JMX or compatible instrumentation. Do not assume Spring Cloud LoadBalancer emits all connection metrics on its own; it primarily sits on the **instance selection** side and does not control every transport socket.

### Do Not Rely Solely on TIME_WAIT

Many `TIME_WAIT` sockets can indicate connection churn, but can also appear normally under network traffic and the OS socket-closing policy. Cross-check new connections/second, actual load, port exhaustion, errors, and TLS handshakes. Do not fix it by arbitrarily changing sysctl settings or slashing `TIME_WAIT`.

If you need to log connection reuse in a test environment, use the chosen HTTP client's logging/debug features at an appropriate level. **Do not enable wire logging containing `Authorization`, `Cookie`, or sensitive payloads in production.**

## 18. Lab Exercise: Same Client, Two ServiceInstances, Multiple Requests

The lab goal is to demonstrate that:

1. Reusing the same HTTP client/proxy does not break per-service-ID instance selection.
2. The transport can reuse connections to each instance when responses are read and sockets remain valid.
3. When the pool is tight or a backend is slow, pending acquires and p99 latency rise; blindly enlarging the pool is not a guaranteed fix.

### A. Prepare Two Local Backends

The same Spring MVC application running on different ports and instance IDs:

~~~java
import java.util.Map;

import org.springframework.core.env.Environment;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CatalogController {

    private final String instanceId;

    CatalogController(Environment environment) {
        this.instanceId = environment.getProperty(
            "instance.id", "catalog-unknown");
    }

    @GetMapping("/api/items/{id}")
    Map<String, Object> item(@PathVariable String id) {
        return Map.of(
            "id", id,
            "name", "Notebook",
            "instanceId", instanceId
        );
    }
}
~~~

To run standalone, the backend application must have `@SpringBootApplication` and the Spring Web dependency; assuming it is built into `catalog-service.jar`:

~~~bash
java -jar catalog-service.jar --server.port=18081 --instance.id=catalog-a
java -jar catalog-service.jar --server.port=18082 --instance.id=catalog-b
~~~

### B. Static Discovery Configuration on the Caller

To avoid needing a separate registry in the lab, `SimpleDiscoveryClient` loads the instance list from the static configuration below:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://localhost:18081
              - uri: http://localhost:18082
~~~

Create a caller from **one of the RestClient bean configurations above**, then call it from a business service. With the demo body returning a `Map`, an example call is:

~~~java
import java.util.Map;

import org.springframework.web.client.RestClient;

class CatalogLoadTestGateway {

    private final RestClient client;

    CatalogLoadTestGateway(RestClient catalogRestClient) {
        this.client = catalogRestClient;
    }

    Map<?, ?> fetch(String id) {
        return client.get()
            .uri("/api/items/{id}", id)
            .retrieve()
            .body(Map.class);
    }
}
~~~

Run multiple calls **within the same caller process**. If writing a sequential test loop:

~~~java
for (int i = 0; i < 100; i++) {
    Map<?, ?> item = gateway.fetch(Integer.toString(i));
    System.out.println(item.get("instanceId"));
}
~~~

Expect to observe both `catalog-a` and `catalog-b` when using Round Robin with a stable instance list; the pool can reuse connections to both destinations when supported by the transport.

### C. Controlled Comparison

Run at least two configurations on the same workload:

| Scenario | Request distribution | New connections/s | Pool pending | p95/p99 | What to conclude |
|---|---|---|---|---|---|
| Singleton RestClient + pool | Record A/B | Measure | Measure | Measure | How well does reuse work? |
| Small pool, high concurrency | Record A/B | Measure | Increases? | Increases? | Where is the saturation point? |
| Slow backend B | Record A/B | Measure | High on B? | High on B? | Is the pool tight due to latency or max size? |
| Server closes idle sockets quickly | Record A/B | Increases? | Measure | Measure | Are there stale connections/reconnects? |
| Stop instance B | Selected per supplier | Reset/refused? | Measure | Measure | How do discovery/health and the pool interact? |

Use warm-up, and keep payloads and concurrency levels consistent. Do not measure performance from only the first few requests because JVM startup, JIT, TLS, DNS, and pool warm-up costs can skew results.

**Do not write a "create a new pool per request" benchmark in production**: it can cause leaks or overload infrastructure. If you need to verify the anti-pattern in a lab, properly create and close the transport per lifecycle, cap traffic, and use an isolated test environment.

### D. Increasing Concurrency in a Controlled Manner

If using WebClient in WebFlux, you can cap concurrent requests using `flatMap(..., concurrency)`:

~~~java
import java.util.Map;
import reactor.core.publisher.Flux;

Flux<Map> results = Flux.range(0, 100)
    .flatMap(
        i -> catalogWebClient.get()
            .uri("/api/items/{id}", i)
            .retrieve()
            .bodyToMono(Map.class),
        16
    );
~~~

This is an illustrative pipeline with a maximum concurrency of 16 on the `flatMap` operator; it does not directly dictate pool size. `results` must be subscribed to by the test/framework to actually send HTTP requests. Avoid `blockLast()` on the reactive event-loop, and do not unleash concurrency in the thousands if the backend/pool is not prepared.

## 19. Common Configuration Mistakes

1. **Creating RestClient/WebClient inside each handler:** misses configuration reuse and risks creating redundant transport resources.
2. **Using a non-`@LoadBalanced` client:** treats the service ID as regular DNS, even though discovery has instances.
3. **Only creating a singleton client without checking the HTTP transport:** assuming pooling is definitely configured properly without verifying.
4. **Raising `maxConnections` while backend p99 is already high:** can push additional concurrency into an overloaded server.
5. **Confusing per-route with total:** configuring a limit of 50/route does not mean the system-wide maximum is 50.
6. **Leaving the pending queue unbounded:** requests can queue far too long, exceeding business deadlines.
7. **Failing to consume/close responses properly:** connections do not return to the pool when needed.
8. **Sharing a mutable request builder across threads:** causes races on headers, URI, and body.
9. **Holding unbounded streaming responses without cancelling:** ties up connections/streams and memory.
10. **Using a pool lifetime that is too long when servers/proxies close idle sockets early:** increases the chance of using a stale connection, even if the transport validates before use.
11. **Using short timeouts with unlimited retries:** causes connection churn and retry storms.
12. **Equating the instance list cache with the connection pool:** changing discovery TTL to solve pool acquire timeouts.
13. **Forgetting to clean up custom pools on shutdown:** background resources can outlive the intended lifecycle.
14. **Mismatching Feign transport configuration with the classpath:** pool properties are declared, but the implementation does not use them.
15. **Measuring only request count:** ignoring connect/handshake, active connections, pool pending, and tail latency.
16. **Assuming HTTP/2 is always enabled:** depends on connector, TLS/ALPN, server, and proxy.

## 20. Operational Checklist and Conclusion

Before deploying, verify:

- HTTP clients/proxies are **injected and reused** appropriately for the application lifecycle, not rebuilt per request.
- `@LoadBalanced` and service IDs are configured properly for RestClient/WebClient; Feign has its corresponding integration.
- The exact **HTTP transport** beneath the client has been identified rather than assumed.
- The pool has appropriate total/per-route or remote-endpoint limits and idle/lifetime eviction policies.
- Connect, pool acquire, response/read timeouts, and business deadlines are clearly separated.
- Response bodies are properly consumed/cancelled; streaming has dedicated limits.
- Metrics exist for active/idle/pending connections, connection creations/closures, latency, and error causes.
- LoadBalancer/discovery/health can switch instances without being confused with socket management.
- Retries are bounded and do not cause duplicate side effects on response timeouts.
- Topology changes, a slow instance, server-closed idle sockets, and increased concurrency have been tested.
- Configuration is measured against actual SLOs rather than copying example max-connection or timeout numbers verbatim.

**Conclusion:** **reusing HTTP clients** is an architectural principle that keeps configuration and lifecycles consistent; **connection pooling/keep-alive** is the actual mechanism that lets multiple HTTP requests reuse physical connections when possible. In Spring Cloud LoadBalancer, the chooser can still select a `ServiceInstance` per request via discovery and health suppliers; the pool finds or opens a connection to the chosen endpoint. For reliable RestClient, WebClient, and OpenFeign communication, combine **client reuse, pool sizing, lifecycle cleanup, budgeted timeouts/retries, and actual connection observability**, rather than simply creating more clients or raising pool limits when high latency appears.
