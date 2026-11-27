# Global and Per-Destination Pool Limits

When **Spring Cloud LoadBalancer** selects a `ServiceInstance` for a request, the HTTP client still must lease or open a network connection to call that instance. If many requests arrive concurrently, a **connection pool** helps reuse sockets and control the number of open connections. However, not all pool limits have the same scope: some apply to the **entire connection manager**, while others only limit connections to **a single HTTP route or a single destination address**.

This is a key point in the **Connections and Performance** chapter. For example, setting `maxConnTotal = 30` and `maxConnPerRoute = 5` does not mean each service gets up to 30 connections. If LoadBalancer selects one physical instance, requests to that instance are still capped at 5/route, even if the overall pool has plenty of room left.

This lesson focuses on three topics: **understanding limit scopes accurately**, **configuring RestClient, WebClient, and OpenFeign**, and **measuring to distinguish pool contention from LoadBalancer errors or a slow backend**.

## 1. A Service ID Is Not an HTTP Route

Suppose `order-service` calls:

~~~http
GET http://catalog-service/products/42
~~~

Discovery provides three `ServiceInstance`s for the `catalog-service` service ID:

| Instance ID | Physical URI | Typical HTTP route |
|---|---|---|
| `catalog-1` | `http://10.0.1.11:8081` | HTTP to `10.0.1.11:8081` |
| `catalog-2` | `http://10.0.1.12:8081` | HTTP to `10.0.1.12:8081` |
| `catalog-3` | `http://10.0.1.13:8081` | HTTP to `10.0.1.13:8081` |

Spring Cloud LoadBalancer receives the logical URL, retrieves the instance list, and selects **one** instance. The HTTP transport works with the selected endpoint; the connection pool does not query the registry or apply round-robin on its own.

~~~mermaid
flowchart TD
    A["order-service calls<br/>http://catalog-service"]
    B["Spring Cloud LoadBalancer<br/>selects ServiceInstance"]
    C["catalog-1<br/>10.0.1.11:8081"]
    D["catalog-2<br/>10.0.1.12:8081"]
    E["catalog-3<br/>10.0.1.13:8081"]
    P["HTTP connection manager<br/>total limit T"]
    R1["Route 1<br/>limit P"]
    R2["Route 2<br/>limit P"]
    R3["Route 3<br/>limit P"]
    A --> B
    B --> C
    B --> D
    B --> E
    C --> P
    D --> P
    E --> P
    P --> R1
    P --> R2
    P --> R3
~~~

The diagram illustrates separation of responsibilities, not that every request passes through all three routes. A request only uses the route corresponding to the selected instance.

With **Apache HttpClient 5**, an `HttpRoute` typically includes scheme, target host/port, and proxy/tunnel information if any. Therefore, a "route" is not simply the service ID name and does not always equal a single instance: proxies, shared endpoints, schemes, or network configuration can change how routes are grouped.

## 2. Two Main Limits in Apache HttpClient 5

Apache HttpClient 5 provides `PoolingHttpClientConnectionManager` with two prominent parameters:

- **`maxConnTotal`:** the maximum number of connections that **one connection manager** is allowed to manage across all routes of that manager.
- **`maxConnPerRoute`:** the maximum number of connections allocated to **each HTTP route** of that manager, unless a specific route is configured with a custom limit.

The builder configuration APIs:

~~~java
PoolingHttpClientConnectionManager manager =
        PoolingHttpClientConnectionManagerBuilder.create()
                .setMaxConnTotal(30)
                .setMaxConnPerRoute(5)
                .build();
~~~

When using HTTP/1.1 where one in-flight request occupies one connection, the number of concurrent requests using connections at the same time is typically constrained by both conditions:

~~~text
Total connections across all routes <= maxConnTotal
Connections for any single route    <= maxConnPerRoute
~~~

This is a simplified model for capacity estimation. HTTP/2 supports multiplexing, so **concurrent requests do not necessarily equal TCP connections**. Pooling policies, proxies, and specific implementations can also affect allocation.

### Numerical Example with Total Pool 6, Per-Route 4

| Concurrent Demand | Total Limit = 6 | Per-Route Limit = 4 | Achievable Outcome |
|---|---|---|---|
| A needs 6, B needs 0 | Total not full at 4 | A max 4 | 4 requests on A; 2 requests must wait even though 2 total slots remain |
| A needs 4, B needs 4 | Only 6 total | A and B each ≤4 | At most 6 in use; at least 2 waiting |
| A needs 2, B needs 2 | Enough total | Neither route hits cap | 4 in use |
| A needs 0, B needs 7 | Total has spare room | B max 4 | 4 in use; 3 waiting |
| A needs 4, B needs 0, C needs 2 | Enough total | A max 4; C max 4 | 6 in use |

The table assumes requests do not finish during the observation window, the pool already has or can open connections, and all requests belong to two/three distinct physical routes. Once busy connections are returned, queued requests can proceed; the table does **not** cap total requests completed per second.

An easily overlooked consequence: **increasing `maxConnTotal` does not relieve contention on a route that has hit `maxConnPerRoute`**. Conversely, only increasing `maxConnPerRoute` does not resolve contention when the entire manager has reached `maxConnTotal`.

## 3. Pool Limits Are Not System-Wide Load Limits

The limits above apply only within the scope of **a single `PoolingHttpClientConnectionManager` that is actually shared**.

For example, suppose an application has three different clients, and each client creates its own connection manager with `maxConnTotal=30`. You cannot conclude the whole process is limited to 30 connections; total connections can climb higher because there are **three independent pools**.

Also distinguish:

| Concept | Scope | Cannot be inferred as |
|---|---|---|
| Apache `maxConnTotal` | All routes within **one manager** | Whole-JVM or cluster-wide limit |
| Apache `maxConnPerRoute` | **One route** within a manager | Per-service-ID limit |
| Application thread pool | Number of blocking tasks that can run | Physical connection count |
| Rate limiter | Rate at which requests are allowed to start | Live connection count |
| Bulkhead/semaphore | Concurrent calls across a business boundary | HTTP socket count |
| HTTP/2 max concurrent streams | Concurrent streams on one HTTP/2 connection | TCP connection count |
| LoadBalancer cache | List of `ServiceInstance`s | HTTP connection reuse |

If the requirement is "no more than 100 concurrent calls to payment-service across the whole application," setting `maxConnTotal=100` alone is usually **not enough**. You need concurrency/bulkhead controls at the application or HTTP client layer, and if you want a cluster-wide limit you may need a distributed mechanism.

## 4. Relationship Between LoadBalancer and Route Count

One service ID can map to multiple physical routes. When autoscaling increases the number of instances, the number of routes used can also increase, even if total request rate stays flat.

Suppose:

~~~text
maxConnTotal    = 24
maxConnPerRoute = 8

catalog-service:
  catalog-1 -> 10.0.1.11:8081
  catalog-2 -> 10.0.1.12:8081
  catalog-3 -> 10.0.1.13:8081
~~~

When all three instances are selected repeatedly, the combined limit for all three routes is still **24**, not `3 × 24`. Each route cannot exceed 8 connections in this example. If the application also uses the same manager to call `payment-service`, the payment routes compete for that same **total of 24**.

### Setting Per-Route Too Low

If a group of requests is constrained by a zone/hint policy to call only `catalog-1`, all load concentrates on a single route. Even if the manager has `maxConnTotal=100`, with `maxConnPerRoute=4`, most requests may wait to lease a connection.

### Setting Total Too Low

Suppose three catalog instances and two payment instances are all serving traffic. Each route still has individual headroom, yet many requests on other routes can consume all of `maxConnTotal`. Requests to a fresh route may have to wait due to the **total limit**, even though that route never reached `maxConnPerRoute`.

### A Route Stops Receiving Traffic

When an instance deregisters, LoadBalancer can stop selecting it once discovery/cache data refreshes, but the connection pool may still keep a few **idle connections** to the old endpoint until their TTL/idle time expires or they are evicted. These are two different lifecycles: **the instance list** and **physical connections**.

## 5. Configuring RestClient with Total and Per-Route Pool Limits

The following example applies to Spring Framework with `RestClient` (since 6.1), Spring Cloud LoadBalancer, and a compatible Apache HttpClient 5.

Illustrative dependencies with Gradle Kotlin DSL, assuming a compatible Spring Boot BOM/release train is already configured:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.cloud:spring-cloud-starter-loadbalancer")
    implementation("org.apache.httpcomponents.client5:httpclient5")
}
~~~

### Creating a Shared Connection Manager

To inspect `PoolStats`, the manager is declared as a separate bean. Spring is responsible for closing the manager when the application context shuts down; `CloseableHttpClient` is configured with a **shared connection manager** so it does not close the manager ahead of other beans.

~~~java
import org.apache.hc.client5.http.config.ConnectionConfig;
import org.apache.hc.client5.http.config.RequestConfig;
import org.apache.hc.client5.http.impl.classic.CloseableHttpClient;
import org.apache.hc.client5.http.impl.classic.HttpClients;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManager;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManagerBuilder;
import org.apache.hc.core5.util.Timeout;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.HttpComponentsClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
class PooledRestClientConfiguration {

    @Bean(value = "sharedConnectionManager", destroyMethod = "close")
    PoolingHttpClientConnectionManager sharedConnectionManager() {
        ConnectionConfig connection = ConnectionConfig.custom()
                .setConnectTimeout(Timeout.ofSeconds(2))
                .setSocketTimeout(Timeout.ofSeconds(8))
                .build();

        return PoolingHttpClientConnectionManagerBuilder.create()
                .setMaxConnTotal(6)
                .setMaxConnPerRoute(4)
                .setDefaultConnectionConfig(connection)
                .build();
    }

    @Bean(destroyMethod = "close")
    CloseableHttpClient pooledHttpClient(
            @Qualifier("sharedConnectionManager")
            PoolingHttpClientConnectionManager manager) {

        RequestConfig requestConfig = RequestConfig.custom()
                .setConnectionRequestTimeout(
                        Timeout.ofMilliseconds(500))
                .setResponseTimeout(Timeout.ofSeconds(6))
                .build();

        return HttpClients.custom()
                .setConnectionManager(manager)
                .setConnectionManagerShared(true)
                .setDefaultRequestConfig(requestConfig)
                .disableAutomaticRetries() // Only to keep lab measurements clear.
                .build();
    }

    @Bean("catalogRestClientBuilder")
    @LoadBalanced
    RestClient.Builder catalogRestClientBuilder(
            CloseableHttpClient pooledHttpClient) {
        return RestClient.builder()
                .requestFactory(
                        new HttpComponentsClientHttpRequestFactory(
                                pooledHttpClient));
    }

    @Bean
    RestClient catalogRestClient(
            @Qualifier("catalogRestClientBuilder")
            RestClient.Builder builder) {
        return builder.baseUrl("http://catalog-service").build();
    }

    // Bean for calling physical URLs: also shares the exact HTTP pool above.
    @Bean("directLabRestClient")
    RestClient directLabRestClient(
            CloseableHttpClient pooledHttpClient) {
        return RestClient.builder()
                .requestFactory(
                        new HttpComponentsClientHttpRequestFactory(
                                pooledHttpClient))
                .build();
    }
}
~~~

The parameters in the example are **lab values**, not production recommendations:

| Parameter | Value | Meaning |
|---|---|---|
| `maxConnTotal` | 6 | All routes in the manager share at most 6 connections |
| `maxConnPerRoute` | 4 | One physical route has at most 4 connections |
| `connectionRequestTimeout` | 500 ms | Wait at most 500 ms to lease a connection from the pool |
| `connectTimeout` | 2 s | Time to establish a new connection |
| `responseTimeout` | 6 s | Wait for response per Apache HttpClient 5 semantics |
| `socketTimeout` | 8 s | Default I/O timeout on the socket |
| `disableAutomaticRetries` | Enabled | Prevents automatic HTTP transport retries during the experiment |

`connectionRequestTimeout` is especially important when studying **pool exhaustion**. When a route or manager hits its cap, a request can wait to lease a connection and time out **before the server ever receives that request**.

With `setConnectionManagerShared(true)`, you must explicitly manage the manager's lifecycle; do not assume background eviction managed by `CloseableHttpClient` will run the same way as when the client owns the manager. When idle connection cleanup is needed, configure TTL/idle eviction/scheduler appropriately for your pool ownership model and version.

### Two RestClient Beans, One Pool

Both `catalogRestClient` and `directLabRestClient` use the **same `pooledHttpClient`/connection manager**. Therefore, requests from both beans compete for `maxConnTotal=6` if their routes are held in that manager.

However, only `catalogRestClient` is built from `@LoadBalanced RestClient.Builder`: it resolves service IDs via Spring Cloud LoadBalancer. `directLabRestClient` is used for physical URIs, allowing you to test per-route limits independently of the instance selection algorithm.

In Spring Boot applications, if you need default auto-customizers, metrics, and tracing, consider `RestClientBuilderConfigurer` and verify customizers after manually configuring the builder.

## 6. Observing States: Leased, Available, and Pending

Apache HttpClient 5 exposes `PoolStats`:

- `leased`: connections currently leased and serving requests.
- `available`: idle connections eligible for reuse, depending on validity state.
- `pending`: connection lease requests waiting to be fulfilled.
- `max`: the limit of the scope being observed.

You can capture total pool statistics:

~~~java
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManager;
import org.apache.hc.core5.pool.PoolStats;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Component;

@Component
class PoolInspector {

    private final PoolingHttpClientConnectionManager manager;

    PoolInspector(
            @Qualifier("sharedConnectionManager")
            PoolingHttpClientConnectionManager manager) {
        this.manager = manager;
    }

    void printTotal() {
        PoolStats stats = manager.getTotalStats();

        System.out.printf(
                "pool total: leased=%d available=%d pending=%d max=%d%n",
                stats.getLeased(),
                stats.getAvailable(),
                stats.getPending(),
                stats.getMax());
    }
}
~~~

To distinguish **total pool full** from **a single route full**, also inspect `manager.getStats(HttpRoute)` for the selected route. Constructing `HttpRoute` must reflect the actual request's target host, port, scheme, and proxy/tunnel; do not replace the route key with the logical service ID.

| Total Pool | Route A | Possible Interpretation |
|---|---|---|
| `leased=4, max=6` | `leased=4, max=4, pending>0` | Route A is full while the global pool still has room |
| `leased=6, max=6, pending>0` | `leased=2, max=4` | Total pool is full; A has per-route room left but no global connections remain |
| `leased=2, available=3, max=6` | `leased=2, max=4` | Several idle connections exist; do not conclude contention from `available` alone |
| `leased=6, pending high for long period` | Multiple routes pending | Risk of pool exhaustion or backend holding requests too long |

**`pending > 0` is a symptom**, not enough by itself to conclude you just need a bigger pool. Check service latency, connection hold time, unclosed/unconsumed response bodies, concurrent request count, and retry count.

## 7. Lab A — Limiting a Single Route

Create two `catalog-service` instances on the same lab machine with a slow endpoint:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
class SlowCatalogController {

    @GetMapping("/lab/slow")
    String slow(
            @RequestParam(defaultValue = "3000") long ms)
            throws InterruptedException {

        Thread.sleep(Math.max(0, Math.min(ms, 5000)));
        return "done";
    }
}
~~~

The server uses `Thread.sleep` solely to simulate holding requests in a test environment, not as a production design.

Initially run only one instance on `8081` so all requests take the same route. The client declares:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://127.0.0.1:8081
~~~

### Steps

1. Keep `maxConnTotal=6` and `maxConnPerRoute=4`.
2. Send **5 concurrent requests** to `/lab/slow?ms=3000` using the same HTTP client/connection manager.
3. Once 4 requests have leased connections, the 5th request must wait on the pool because the **route has reached its limit of 4**.
4. With `connectionRequestTimeout=500ms` and the backend holding requests for about 3 seconds, the waiting request may time out before ever being sent to the server.
5. Observe `getTotalStats()` and route stats; raising only `maxConnTotal` to 10 will not let route A exceed 4.
6. Re-run with `maxConnPerRoute=6` to compare; check the impact on backend response time/CPU.

Requests should be synchronized with a latch or a load-testing tool so they start close together and guarantee enough concurrent in-flight requests. Do not claim which thread-numbered "5th" request will wait; thread scheduling does not follow the order in your code.

### Expected Outcome

~~~text
Pool config: total=6, perRoute=4
Request group: 5 concurrent, one physical route

Expected while requests are still running:
  route leased <= 4
  total leased <= 6
  at least one acquisition waiting or timing out
  server sees at most 4 concurrent HTTP/1.1 requests from this pool
~~~

If the experiment runs over HTTP/2 or a multiplexing proxy, do not treat "4 requests" as a universal property of every protocol. This lab assumes Apache HttpClient 5 with standard HTTP/1.1 connections.

## 8. Lab B — Total Limit Across Two Routes

Continue running two backends:

~~~text
Route A: http://127.0.0.1:8081
Route B: http://127.0.0.1:8082
Pool: total=6, perRoute=4
~~~

To **clearly isolate the cause** in this experiment, use the `directLabRestClient` bean and physical URLs rather than relying on uncontrolled round-robin. Both URLs still share **one connection manager**.

Example requests:

~~~java
String a = directLabRestClient.get()
        .uri("http://127.0.0.1:8081/lab/slow?ms=3000")
        .retrieve()
        .body(String.class);

String b = directLabRestClient.get()
        .uri("http://127.0.0.1:8082/lab/slow?ms=3000")
        .retrieve()
        .body(String.class);
~~~

The snippet illustrates two distinct URIs, **not calling A then B sequentially** if you want to test contention; use an executor/load generator to send requests concurrently.

### Steps

1. Send 4 concurrent requests to route A.
2. Send 4 more concurrent requests to route B while group A has not yet finished.
3. Neither route exceeds `perRoute=4`, yet the **total is 8 requests**, which is higher than `maxConnTotal=6`.
4. While 6 connections are serving traffic, the remaining requests must wait to lease from the pool.
5. Verify `getTotalStats().getLeased() <= 6`, along with `pending` rising while the backends hold the requests.
6. Re-run after increasing only `maxConnTotal` to 8. If both backends have enough capacity, all 8 requests can proceed concurrently.

**Key takeaway:** both route A and route B can be "below their individual limit" at a given moment, yet requests still wait because the **total pool is full**.

When switching from physical URL tests to `@LoadBalanced RestClient`, instance selection can change distribution via round-robin, zone, hint, weight, cache, or health filter. Do not assume 50/50 without observing actual requests.

## 9. Choosing Limits Based on Load: More Than a Single Multiplication

An initial approximation for HTTP/1.1 is Little's Law:

~~~text
Concurrent requests ≈ request rate × request hold time
~~~

For example, with steady traffic of 100 requests/second and an average connection hold time of 200 ms:

~~~text
100 request/s × 0.2 s ≈ 20 concurrent requests
~~~

The result 20 is an **average estimate**, not a recommendation to set `maxConnTotal=20`. You must consider:

- Peak RPS and burst traffic, not just averages.
- p95/p99 latency; the backend can occasionally be several times slower than the mean.
- How many routes are actually active and the distribution across each route.
- Retries, hedged requests, or proxies that can multiply attempt counts.
- Whether the pool is shared across multiple service IDs.
- How long idle connections are kept according to timeout/TTL.
- CPU, heap, file descriptors, ephemeral ports, and backend connection limits.

If route A normally sees 60 requests/s and each request holds a connection for ~150 ms, the average is ~9 requests on A; however, a backend p99 spike to several seconds can cause the wait queue to grow rapidly. Therefore, choose limits through **load tests with observability enabled**, then verify the impact on SLOs and backend load.

### Overly Large Limits Also Cause Outages

Raising `maxConnTotal` into the thousands may eliminate some pool-wait errors, yet pushes excessive requests onto an overloaded backend, increasing connection setup, CPU, file descriptors, and TLS overhead. A pool is a **concurrency control mechanism**, not just a buffer where "bigger is always better."

It is better to balance the pool with timeouts, backpressure, rate limiting/bulkheads, and backend capacity.

## 10. WebClient/Reactor Netty: Limits Typically Apply per Remote Host

With `WebClient` using Reactor Netty, the corresponding component is `ConnectionProvider`. However, **do not map them one-to-one**:

~~~text
Apache maxConnTotal    == Reactor Netty maxConnections
Apache maxConnPerRoute == a single API with the exact same meaning
~~~

In Reactor Netty, connection pools are organized per remote host/destination address (and relevant pool/protocol details). `ConnectionProvider.Builder.maxConnections(n)` is the maximum number of connections **per connection pool**, typically corresponding to one remote address. It is **not** a simple global cap across all remote hosts using the provider.

### Reactive Example

~~~java
import java.time.Duration;
import io.netty.channel.ChannelOption;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;

@Configuration(proxyBeanMethods = false)
class PooledWebClientConfiguration {

    @Bean(destroyMethod = "dispose")
    ConnectionProvider webClientConnectionProvider() {
        return ConnectionProvider.builder("catalog-http")
                .maxConnections(4)
                .pendingAcquireMaxCount(32)
                .pendingAcquireTimeout(Duration.ofMillis(500))
                .maxIdleTime(Duration.ofSeconds(30))
                .metrics(true)
                .build();
    }

    @Bean
    @LoadBalanced
    WebClient.Builder catalogWebClientBuilder(
            ConnectionProvider webClientConnectionProvider) {

        HttpClient httpClient =
                HttpClient.create(webClientConnectionProvider)
                        .option(
                                ChannelOption.CONNECT_TIMEOUT_MILLIS,
                                2000)
                        .responseTimeout(Duration.ofSeconds(6));

        return WebClient.builder()
                .clientConnector(
                        new ReactorClientHttpConnector(httpClient));
    }
}
~~~

Suppose two instances have two different remote addresses, each pool capped at 4; then **one `ConnectionProvider` can manage more than 4 connections across all destinations**. If the requirement is "at most 6 in-flight requests across the whole application," limit concurrency at the application/resilience layer or with a dedicated limiter, rather than relying solely on `maxConnections(4)`.

Comparison table:

| Apache HttpClient 5 | Reactor Netty |
|---|---|
| `setMaxConnTotal(6)` — across the whole manager | No equivalent `maxConnections` option acting as a global cap across all hosts |
| `setMaxConnPerRoute(4)` — per `HttpRoute` | `ConnectionProvider.maxConnections(4)` — limit of each pool per remote address |
| `setConnectionRequestTimeout(500ms)` | `pendingAcquireTimeout(500ms)` |
| `PoolStats.getPending()` | ConnectionProvider pending/acquired/active metrics |
| Route may include proxy/tunnel | Pool keyed by remote address/protocol with Reactor Netty semantics |

Do not apply the numbers or limits above as if every HTTP/2 stream requires its own connection. Multiplexed protocols alter the request-to-connection relationship.

### Reactor Netty Metrics

When Micrometer is enabled for ConnectionProvider, commonly relevant metrics include:

- `reactor.netty.connection.provider.active.connections`
- `reactor.netty.connection.provider.idle.connections`
- `reactor.netty.connection.provider.pending.connections`
- `reactor.netty.connection.provider.max.connections`
- `reactor.netty.connection.provider.pending.connections.time`

Exact metric names/tags depend on the Reactor Netty version and metrics backend. Group by pool ID and remote address when supported, rather than only viewing total connections on a single dashboard.

## 11. OpenFeign: Pooling Depends on the HTTP Transport

Spring Cloud OpenFeign creates proxies from `@FeignClient` interfaces. When integrated with Spring Cloud LoadBalancer, `FeignBlockingLoadBalancerClient` selects a `ServiceInstance`, while the delegate HTTP client executes the connection.

Therefore:

- If the delegate uses **Apache HttpClient 5**, Apache's connection manager determines global and per-route limits.
- If the delegate uses another transport, you must use that transport's properties and semantics.
- `@FeignClient(name = "catalog-service")` does not automatically create a dedicated pool for that service ID.
- Feign clients may share or have separate pools depending on auto-configuration and bean scope.

Adding the `spring-cloud-starter-loadbalancer` dependency lets Feign select instances when eligible, but **is not a substitute configuration for an HTTP connection pool**.

In Spring Cloud OpenFeign there are HC5 properties to tune the pool for the auto-managed transport. Examples of property names described in current documentation:

~~~yaml
spring:
  cloud:
    openfeign:
      httpclient:
        max-connections: 200
        max-connections-per-route: 50
~~~

The values above are illustrative only and must be verified against your **actual Spring Cloud OpenFeign version and HC5 transport**. Do not apply them directly to `RestClient` or Reactor Netty.

If you define a custom `feign.Client` bean, verify whether the path through `FeignBlockingLoadBalancerClient` is still preserved; changing the HTTP transport must not accidentally bypass instance selection.

## 12. Distinguishing Pool Contention, Slow Backends, and Discovery Errors

| Symptom | Primary Suspect | Data to Prove It |
|---|---|---|
| High `pending`, `leased` equals route max | Route-specific saturation | `getStats(route)` + request count to that route |
| High `pending`, `leased` equals total max | Total pool saturation | `getTotalStats()` + stats across multiple routes |
| `leased` stays high, response time rises | Slow backend or leaked/held connections | Backend latency, request traces, body consumption |
| High `available` yet new requests are slow | Another route is full, idle connections don't match the route, or different transport | Exact route stats, pool ID, DNS/TCP/TLS |
| HTTP client frequently opens new sockets | Connections not reused or wrong client lifecycle | New connection rate, keep-alive, idle eviction |
| LoadBalancer finds no instances | Empty discovery/supplier | Service ID, candidate list, health/filter config |
| Instance selected but `Connection refused` | Broken backend/port or stale instance data | Selected host/port, listener, network |
| HTTP 503 while pool is still idle | Backend/proxy or another component returned 503 | Target trace and response body |
| Raised `maxConnTotal` yet errors remain on one instance | `maxConnPerRoute` hit limit or weak backend | Route stats and server metrics |

**A pool-wait timeout is not a connect timeout.** While waiting on the pool, the request may not have been granted a connection to establish TCP yet. Therefore, raising `connectTimeout` does not help acquire a missing slot.

Inspect both **client-side metrics** and **backend throughput/latency**. Raising client limits alone without checking the backend can drive error rates up.

## 13. Idle Connections, Stale Connections, and Instance Transitions

A finished connection can return to the pool in an idle state. When a server/proxy closes an idle connection, the pooled connection can become stale before the next lease.

Related mechanisms:

| Mechanism | Role |
|---|---|
| Keep-alive | Allows keeping and reusing connections |
| Max idle time | Sets a threshold to close connections unused for too long |
| Max life time / TTL | Caps the total age of a connection |
| Validate after inactivity | Helps detect idle connections that are no longer valid before reuse |
| Evict expired/idle | Cleans up expired connections or those idle beyond threshold |
| Discovery/cache refresh | Removes the instance from the selection list; **does not directly close idle sockets** |

If an instance `catalog-2` stops:

1. Discovery and the LoadBalancer cache may take time to remove it from the list.
2. Idle connections to `catalog-2` may remain in the pool until closed/evicted.
3. Retries during that window may keep picking the dead instance, or pick another instance depending on policy.
4. Raising `maxConnPerRoute` cannot fix a stopped endpoint.

Even a properly configured pool can experience errors during scale-down. Combine graceful shutdown, discovery, health checks, timeouts, conditional retries, and idle connection management.

## 14. Impact of HTTP/2, Proxies, and Kubernetes Services

Connection limits should be understood in terms of the **actual transport**, not just the logical service architecture.

### HTTP/2

A single HTTP/2 connection can carry many concurrent streams. Thus, `maxConnections=4` does not necessarily mean at most 4 concurrent requests. The server may cap streams per connection; the transport has its own stream management. When measuring, distinguish **active TCP connections** from **active HTTP requests/streams**.

### Proxy

If outbound requests pass through an HTTP proxy, `HttpRoute` and connection grouping may include proxy/tunnel information. Two different backend hostnames going through the same proxy may still be managed under routes determined by the transport; do not use just `host:port` printed in business logs as the absolute route key.

### Kubernetes Service / Service Mesh

If calling a Kubernetes Service DNS or sidecar proxy directly via a **RestClient not using Spring Cloud LoadBalancer**, the connection pool may see a route to **ClusterIP/proxy**, not necessarily individual Pod IPs. When using Spring Cloud LoadBalancer and discovery to pick individual physical Pods/instances, the pool can have more routes.

Therefore, a goal such as "at most 10 connections per instance" must be verified against the destination addresses the HTTP client **actually connects to**, not merely from the Pod list or service ID.

## 15. Lab Practice: Measuring and Choosing Sensible Thresholds

Run in a test environment, changing **one parameter at a time**:

1. Run `/lab/slow` on one instance, set pool total 6 / per-route 4, and send 5 concurrent requests.
2. Measure `leased`, `pending` per route, and response statuses; record how many requests actually hit the server.
3. Increase only total from 6 to 10; verify why the route remains capped at 4.
4. Raise per-route to 6; re-run and also measure backend CPU and latency.
5. Run two instances, force 4 requests to each route using the **direct client sharing the pool**; observe total 6 becoming the bottleneck.
6. Raise total to 8 to observe the change, leaving per-route unchanged.
7. Switch to `@LoadBalanced RestClient` and compare when round-robin/zone/hint alters request distribution.
8. If using WebClient, run a separate test with `ConnectionProvider.maxConnections(4)` across two remote hosts and observe **two pools**, without misreporting it as a global 4.
9. Test a backend with higher latency and compare: does the pool saturate simply because requests hold connections longer?
10. Summarize p50/p95/p99 latency, successful request count, exceptions, and server resources before concluding which limit needs adjustment.

### Sample Result Table

| Run | Transport | Route count | Total cap | Per-route cap | Total leased | Total pending | p95 latency | Conclusion |
|---|---|---:|---:|---:|---:|---|---|---|
| A | Apache HC5 | 1 | 6 | 4 | Measure | Measure | Measure | Per-route bottleneck? |
| B | Apache HC5 | 1 | 10 | 4 | Measure | Measure | Measure | Does raising total alone help? |
| C | Apache HC5 | 1 | 6 | 6 | Measure | Measure | Measure | Can the backend handle the load? |
| D | Apache HC5 | 2 | 6 | 4 | Measure | Measure | Measure | Total bottleneck? |
| E | Apache HC5 | 2 | 8 | 4 | Measure | Measure | Measure | Compare with D |
| F | Reactor Netty | 2 | Not equivalent | 4/pool | Measure | Measure | Measure | Two remote-host pools? |

Do not record illustrative numbers as real measurements. Metrics must be gathered from pool instrumentation and load-testing tools compatible with your application.

## 16. Pre-Production Checklist

- How many physical routes does a service ID currently map to?
- Is the HTTP transport Apache HttpClient 5, Reactor Netty, or another implementation?
- Do clients actually share a single manager/provider, or does each bean create a new pool?
- Is the configured limit **manager total**, **per route**, or **per remote host pool**?
- Does the pool have enough capacity for peak load without exceeding backend/OS capacity?
- Are `connectionRequestTimeout`/`pendingAcquireTimeout` set so requests do not wait forever?
- Do response/read timeouts and total deadlines align with backend load?
- Are response bodies/streams properly released to return connections to the pool?
- Are `leased/available/pending/max` metrics available per pool/route, and can they be correlated with the selected instance?
- Are retries increasing attempt counts/concurrency and causing pool queues to spike?
- Are idle eviction, max lifetime, and graceful shutdown aligned with instance lifecycles?
- If HTTP/2 or a proxy/mesh is involved, are request counts being confused with TCP connection counts?
- Have you load-tested both a single hot route and multiple routes to catch both types of bottlenecks?

**Conclusion:** Apache HttpClient 5's `maxConnTotal` caps the **entire connection manager**, whereas `maxConnPerRoute` caps **each HTTP route**; both jointly govern allocation. With WebClient/Reactor Netty, `maxConnections` typically caps **each remote-host pool**, not an Apache-style global cap. Because Spring Cloud LoadBalancer can pick multiple physical `ServiceInstance`s from one service ID, measure pools by **actual target addresses**, size limits according to peak load and backend capacity, and clearly distinguish pool-wait errors from discovery, connect, or response errors.

**Official References:**

- [Apache HttpClient 5 – PoolingHttpClientConnectionManagerBuilder](https://hc.apache.org/httpcomponents-client-5.6.x/5.6/httpclient5/apidocs/org/apache/hc/client5/http/impl/io/PoolingHttpClientConnectionManagerBuilder.html)
- [Apache HttpClient 5 – PoolingHttpClientConnectionManager](https://hc.apache.org/httpcomponents-client-5.6.x/5.6/httpclient5/apidocs/org/apache/hc/client5/http/impl/io/PoolingHttpClientConnectionManager.html)
- [Reactor Netty – HTTP Client Connection Pool](https://projectreactor.io/docs/netty/release/reference/http-client.html#_connection_pool)
- [Spring Cloud Commons – Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html)
- [Spring Cloud OpenFeign – Spring Cloud OpenFeign](https://docs.spring.io/spring-cloud-openfeign/reference/spring-cloud-openfeign.html)
