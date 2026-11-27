# Configuring Timeouts and Connection Reuse

When one microservice calls another using **Spring Framework `RestClient` combined with Spring Cloud LoadBalancer**, two operational concerns must be solved side by side: **selecting the right `ServiceInstance` replica** and **executing HTTP with appropriate time limits and connection resources**.

Spring Cloud LoadBalancer helps select a target by service ID such as `catalog-service`. It does not govern socket open time, response wait time, or connection pool sizing. Those behaviors belong to the **HTTP request factory and transport** used by `RestClient`, such as Apache HttpClient 5.

This lesson in the **RestClient** chapter focuses on configuring timeouts, reusing HTTP connections, interacting with client-side load balancing, and diagnosing incidents in inter-service communication.

## 1. Which layer do timeouts and connection pools live in?

Example business code calling:

~~~http
GET http://catalog-service/products/42
~~~

Suppose `ServiceInstanceListSupplier` for `catalog-service` returns two replicas:

| Instance | Host | Port |
|---|---|---|
| `catalog-1` | `10.0.1.11` | `8081` |
| `catalog-2` | `10.0.1.12` | `8081` |

Conceptual processing flow:

~~~mermaid
flowchart TD
    A["RestClient calls logical URL<br/>catalog-service/products/42"]
    B["Spring Cloud LoadBalancer<br/>selects ServiceInstance"]
    C["catalog-1: 10.0.1.11:8081"]
    D["Apache HttpClient 5<br/>connection pool"]
    E{"Suitable reusable<br/>connection available?"}
    F["Reuse existing socket"]
    G["Open new connection<br/>DNS/TCP/TLS if needed"]
    H["Send HTTP request and receive response"]
    A --> B --> C --> D --> E
    E -->|"Yes"| F --> H
    E -->|"No"| G --> H
~~~

Responsibility boundaries:

| Component | Primary responsibility |
|---|---|
| `ServiceInstanceListSupplier` | Supplies candidate list from discovery, caches, health checks, or filtering policies |
| LoadBalancer | Picks one `ServiceInstance` for the call |
| LoadBalancer interceptor/adapter | Translates the service-ID URL into the chosen physical target |
| `RestClient` and `ClientHttpRequestFactory` | Builds the request, hands it to HTTP transport, and receives the response |
| Apache HttpClient/connection manager | Manages sockets, connection pool, timeouts, keep-alive, TLS, and connection reuse |

**One instance selection does not equal opening one new connection.** When LoadBalancer selects the same endpoint again, the transport can lease an idle HTTP connection from the pool if that connection is still valid and reusable.

## 2. Distinguishing timeout types

Between the moment code calls `RestClient` and when reading the response finishes, several different wait timers exist. Never use the word “timeout” without specifying which phase.

| Limit type | Waiting for what? | Symptom when exceeded |
|---|---|---|
| **Connection request / pool lease timeout** | Borrowing a connection from the pool when route connections are busy | Request cannot acquire a connection to send |
| **Connect timeout** | Establishing a new TCP connection to the endpoint | Fails to connect before the deadline |
| **Response timeout** | Waiting for a server response per transport semantics | Backend/proxy did not respond in time |
| **Socket timeout** | Waiting for I/O activity on the socket | Data reading stalled too long |
| **End-to-end deadline** | Total duration for the entire business operation, potentially including retries | Requires a separate overall bounding mechanism; cannot be inferred from a single timeout |

In Apache HttpClient 5:

- `RequestConfig#setConnectionRequestTimeout(...)` sets the maximum wait to **borrow a connection from the connection manager**.
- `ConnectionConfig#setConnectTimeout(...)` sets the time to **establish a new connection**; this is the recommended API in newer HttpClient 5 versions instead of the deprecated `RequestConfig#setConnectTimeout(...)`.
- `RequestConfig#setResponseTimeout(...)` bounds waiting for a **response**; per Apache documentation, this is **not an absolute deadline** for the entire call.
- `ConnectionConfig#setSocketTimeout(...)` sets the default socket-layer timeout; response timeout may override this limit during HTTP execution depending on the transport.

These values must not be treated as simply additive to yield a “maximum duration” of one call. With redirects, retries, proxies, TLS handshakes, body processing, or multiple attempts, actual time can differ. Timeout mechanics and applicability also depend on HTTP client/version.

### Distinguishing timeouts from no-instance errors

If the supplier cannot provide any replica for `catalog-service`, LoadBalancer can fail with “no servers available” **before the HTTP client ever opens a connection**. Increasing `connectTimeout` or `responseTimeout` will not make discovery find an instance. Conversely, when a selected instance has a valid URI yet cannot be reached, that is an HTTP transport failure.

## 3. Why reuse connections?

Opening a new connection for every request costs time and resources: socket allocation, TCP handshake, TLS if HTTPS, and client/server overhead.

With HTTP keep-alive, while a connection remains valid, the HTTP client can reuse it for subsequent requests to the same route. A shared pool provides these benefits:

- Reduces TCP/TLS handshakes when the same endpoint is called repeatedly.
- Caps concurrent connections to prevent unbounded socket growth.
- Retains idle connections to serve upcoming requests.
- Provides queuing and timeouts when demand exceeds pool capacity.

However, reuse **does not happen every time**: the server may send `Connection: close`, idle connections may be closed, routes may differ, or connections may have expired or be busy. Do not treat keep-alive as a guarantee that every call travels over the same socket.

### HTTP client pool differs from LoadBalancer cache

| Memory/resource | What does it store? | What problem does it solve? |
|---|---|---|
| `CachingServiceInstanceListSupplier` | List of `ServiceInstance` entries per service ID | Reduces discovery query overhead |
| Apache HTTP connection pool | Live network connections and leased slots | Reduces socket creation overhead, controls concurrency |
| DNS cache | Hostname-to-address resolution results | Reduces DNS lookup cost, runtime/resolver dependent |
| HTTP response cache (if present) | Response payloads | Avoids re-calling when cache policy allows |

Lowering the LoadBalancer cache TTL does not flush sockets in the HTTP pool; closing idle sockets does not refresh the discovery list sooner either.

## 4. Choosing an HTTP transport with connection pooling support

`RestClient` is Spring Framework's synchronous HTTP API. It uses `ClientHttpRequestFactory` to interact with the actual transport. Different request factories support timeouts and pooling to varying degrees.

For systems needing **explicit tuning of connection counts, pool lease wait time, keep-alive, and idle eviction**, Apache HttpClient 5 with `HttpComponentsClientHttpRequestFactory` is a popular choice.

Example Gradle Kotlin DSL dependencies in a project with a compatible Spring Boot/Spring Cloud BOM:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.cloud:spring-cloud-starter-loadbalancer")
    implementation("org.apache.httpcomponents.client5:httpclient5")
}
~~~

A `ServiceInstance` source such as Eureka, Consul, or `SimpleDiscoveryClient` is required to call by service ID. Subsequent examples assume a Spring Framework version with `RestClient` (Spring 6.1+) and an Apache HttpClient 5 version supporting the `ConnectionConfig` APIs used.

If an application uses another HTTP transport, **do not copy Apache configuration verbatim** to that transport: each request factory has its own API and timeout semantics.

## 5. Configuring a shared Apache HttpClient 5

Goals of the illustrative configuration:

- Wait at most **1 second** to borrow a connection from the pool.
- Allow at most **2 seconds** to establish a new TCP connection.
- **4-second** response timeout, **5-second** default socket timeout.
- Cap at **100 total connections**, with at most **20 connections per HTTP route**.
- Re-validate connections that have been idle long enough before leasing them again.
- Evict expired connections and connections idle longer than **30 seconds**.
- Use **one shared `CloseableHttpClient`** across the application context lifecycle.

Example configuration:

~~~java
import org.apache.hc.client5.http.config.ConnectionConfig;
import org.apache.hc.client5.http.config.RequestConfig;
import org.apache.hc.client5.http.impl.classic.CloseableHttpClient;
import org.apache.hc.client5.http.impl.classic.HttpClients;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManager;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManagerBuilder;
import org.apache.hc.core5.util.TimeValue;
import org.apache.hc.core5.util.Timeout;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.HttpComponentsClientHttpRequestFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
class CatalogRestClientConfiguration {

    @Bean(destroyMethod = "close")
    CloseableHttpClient pooledCatalogHttpClient() {
        ConnectionConfig connectionConfig = ConnectionConfig.custom()
                .setConnectTimeout(Timeout.ofSeconds(2))
                .setSocketTimeout(Timeout.ofSeconds(5))
                .setValidateAfterInactivity(TimeValue.ofSeconds(3))
                .build();

        PoolingHttpClientConnectionManager manager =
                PoolingHttpClientConnectionManagerBuilder.create()
                        .setMaxConnTotal(100)
                        .setMaxConnPerRoute(20)
                        .setDefaultConnectionConfig(connectionConfig)
                        .build();

        RequestConfig requestConfig = RequestConfig.custom()
                .setConnectionRequestTimeout(Timeout.ofSeconds(1))
                .setResponseTimeout(Timeout.ofSeconds(4))
                .build();

        return HttpClients.custom()
                .setConnectionManager(manager)
                .setDefaultRequestConfig(requestConfig)
                .evictExpiredConnections()
                .evictIdleConnections(TimeValue.ofSeconds(30))
                .build();
    }

    @Bean("catalogRestClientBuilder")
    @LoadBalanced
    RestClient.Builder catalogRestClientBuilder(
            CloseableHttpClient pooledCatalogHttpClient) {
        return RestClient.builder()
                .requestFactory(new HttpComponentsClientHttpRequestFactory(
                        pooledCatalogHttpClient));
    }

    @Bean("catalogRestClient")
    RestClient catalogRestClient(
            @Qualifier("catalogRestClientBuilder") RestClient.Builder builder) {
        return builder.baseUrl("http://catalog-service").build();
    }
}
~~~

These are **illustrative values for learning the mechanics**, not a production parameter set for every system. Adjust according to SLOs, concurrent load, backend processing time, instance count, and network resource limits.

### Key points in the configuration

**`@LoadBalanced` goes on `RestClient.Builder`, not on `CloseableHttpClient`.** Spring Cloud integrates instance selection into the builder; Apache HttpClient receives the physical target and executes HTTP. Pooling still operates for LoadBalancer-selected requests.

**Do not create a new `CloseableHttpClient` per call.** A singleton bean lets requests share the same connection manager. When the application context shuts down, Spring calls `close()` on the bean to release the pool and eviction components.

**`setMaxConnPerRoute(20)` typically applies per physical HTTP route**, not strictly 20 connections across the entire `catalog-service` service ID. Routes also depend on proxy and scheme; multiple instances with different hosts/ports generally form distinct routes.

**Do not assume timeouts on the request factory and on Apache HttpClient add together.** Transport settings must be verified via real wait-time tests, especially when the application uses retries or network proxies.

### Integrating with Spring Boot auto-configuration

Creating raw `RestClient.builder()` above focuses on illustrating the Apache request factory. If your project relies on Spring Boot's automatic customizers (such as observability, codecs/message converters, or other interceptors), ensure they are still applied to the load-balanced builder. Spring Cloud documentation recommends using `RestClientBuilderConfigurer` when declaring a `@LoadBalanced RestClient.Builder` to inherit Spring Boot's defaults.

Do not replace a Boot-customized builder without checking the impact on metrics, tracing, authentication, or serialization.

## 6. Calling by service ID while reusing connections per endpoint

Using the `catalogRestClient` bean:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
class CatalogGateway {

    private final RestClient client;

    CatalogGateway(
            @Qualifier("catalogRestClient") RestClient client) {
        this.client = client;
    }

    Product getProduct(long id) {
        return client.get()
                .uri("/products/{id}", id)
                .retrieve()
                .body(Product.class);
    }
}

record Product(long id, String name) {}
~~~

On each call:

1. `RestClient` receives the logical URL from `baseUrl("http://catalog-service")`.
2. Spring Cloud LoadBalancer selects an available `catalog-service` instance.
3. The HTTP request is sent to the physical target via Apache HttpClient.
4. The connection manager looks for a valid idle connection for that route; if none exists, it opens a new one if under limits.
5. Once the response is properly processed, the connection can return to the pool for reuse.

For example, with round-robin, connections are maintained per route:

~~~text
Service ID: catalog-service

LoadBalancer selects catalog-1 (10.0.1.11:8081)
  -> Pool route 10.0.1.11:8081
     available: 2, leased: 1

LoadBalancer selects catalog-2 (10.0.1.12:8081)
  -> Pool route 10.0.1.12:8081
     available: 1, leased: 1
~~~

These numbers are illustrative, not framework-generated output. Notably, **LoadBalancer decides the instance**, while **the pool decides which socket to use** for the selected route.

### Why doesn't the pool “load-balance” instead of LoadBalancer?

The Apache connection manager does not know the full `ServiceInstance` list for `catalog-service` to apply round-robin, zone preference, or hints. It manages connections per resolved HTTP route. If LoadBalancer repeatedly selects one instance, the pool reuses sockets to that instance, but it will not switch to another instance on its own just because the current route is slow.

## 7. Pool sizing: total connections and connections per route

Suppose `catalog-service` has four instances and load spikes to 100 concurrent HTTP requests.

- `maxConnTotal=100`: caps total connections managed by the pool.
- `maxConnPerRoute=20`: caps connections per route; even if the pool has remaining total capacity, a single route can hit 20.
- `connectionRequestTimeout=1s`: a request waiting to lease a connection can fail if no slot becomes available before the timeout.

Because one service ID can map to multiple physical routes, a limit of 20/route **does not mean** 20 concurrent requests for the whole service. Conversely, if LoadBalancer steers many requests toward one instance, that route can bottleneck even while other routes have room.

| Symptom | Possible cause | Remediation |
|---|---|---|
| Waiting to lease a connection, timing out despite healthy server | Pool exhausted or per-route limit too small | Measure leased/pending/available counts and per-route concurrency |
| Increased pool size yet backend gets slower | Backend has no more capacity or is overloaded | Inspect CPU, DB pool, concurrency, and backend SLO |
| Many idle connections after scale-out | Traffic spreads across more routes | Cap idle/TTL and adjust pool sizing appropriately |
| Frequently opening new connections | Server disables keep-alive, idle eviction too aggressive, or client/pool recreated | Check server headers, bean lifecycle, and connection reuse |
| Only some instances hit the limit | Algorithm/supplier creates uneven distribution | Check zones, weights, hints, and per-route metrics |

Never increase pool sizes indefinitely. Each connection consumes file descriptors, memory, ephemeral ports, and backend capacity; nor can blocking requests finish fast if the application's thread pool is already saturated.

## 8. Keep-alive, idle eviction, and stale connections

A connection that just served a request can be reused if the HTTP protocol, server, and client allow it. However, in microservices environments, instances can be replaced, infrastructure load balancers can close idle connections, or the network can drop an existing connection.

Three commonly used mechanisms:

| Mechanism | Purpose |
|---|---|
| **Keep-alive** | Allows reusing eligible connections across requests |
| **Evict expired/idle connections** | Closes expired connections or connections idle for too long |
| **Validate after inactivity** | Checks reusability of a connection that has been inactive for a period |

In section 5's configuration, `evictIdleConnections(TimeValue.ofSeconds(30))` cleans up connections idle over 30 seconds, while `setValidateAfterInactivity(3s)` helps re-verify connections inactive long enough before leasing them out. These mitigate stale socket errors, yet **cannot eliminate every race condition**: a connection can be closed right after being validated.

### Difference between a stale instance and a stale socket

- **Stale instance:** LoadBalancer's supplier still returns a `ServiceInstance` that has shut down. Inspect discovery, caching, or health checks.
- **Stale socket:** the selected instance may still be alive, yet an idle pooled connection to it was closed by the server/proxy. Inspect connection manager, idle validation, and networking.
- **Combination of both:** the instance stopped and the pool still holds an old socket. Retries/timeouts and discovery refresh may both be needed, handled at separate layers.

A request hitting a stale socket may fail early and require a new connection; whether to retry depends on the transport and integration retry policy. For write operations, avoid uncontrolled retries since the request may have reached the server before the connection broke.

### Properly consume and release responses and bodies

A connection can only return to the pool once the response is processed and resources are released. Calls like `retrieve().body(Product.class)` normally consume the body and close resources via Spring's mechanics.

With streaming or callbacks handling the response directly, follow the API's response lifecycle so leased connections are not held indefinitely. Never retain references to closed body streams or bypass framework-provided closing mechanisms.

## 9. Do not mistake timeouts for a total deadline

Suppose the configuration is:

~~~text
pool lease timeout : 1s
connect timeout    : 2s
response timeout   : 4s
socket timeout     : 5s
~~~

These are **per-phase limits**, not a promise that “every request finishes in 4 seconds” or “at most 1 + 2 + 4 seconds”.

Several reasons total request duration can exceed expectations:

1. The request waits in the pool queue before connecting or sending.
2. TLS, DNS, proxies, redirects, and reading the response body have transport-dependent timeout semantics.
3. Some HTTP clients retry automatically under configured conditions.
4. Spring Cloud LoadBalancer or the application layer may retry again with a newly selected instance.
5. The backend sends response headers promptly yet streams the body slowly.

**Apache HttpClient's response timeout is not a total deadline across all attempts.** If a business requirement has a strict time budget (e.g., 2 seconds to fetch pricing), design a higher-level time budget/deadline accounting for retries and queue waits, using cancellation/limits compatible with a synchronous client.

### Retries multiply wait durations

For example, if an initial request hits a 4-second response timeout and then retries twice more, total elapsed time can far exceed 4 seconds, excluding backoff, connection setup, or pool lease waits.

This becomes especially dangerous when the client has **multiple retry layers**: HTTP transport auto-retry, LoadBalancer retry, and Resilience4j or another retry loop in the application. Audit and cap total attempts, classify retryable exceptions, and verify endpoint idempotency.

An order-creating POST may have been processed by the server before the client timed out; resending without an idempotency key or deduplication can create two orders.

## 10. Diagnosing failures by phase

When `RestClient` times out, the effective order of investigation is confirming **whether an instance was selected**, then identifying whether it was waiting on **pool lease, connect, or response**.

| Observed signal | Suspected phase | Recommended action |
|---|---|---|
| No instance for service ID | Discovery/LoadBalancer | Check service ID, registry, supplier, health filtering |
| High pool pending and leased near limit | Connection lease | Check `maxConnPerRoute`, `maxConnTotal`, request concurrency, unclosed responses |
| Connect timeout to a specific instance | Connection setup | Check host/port, firewall, server listener, network reachability |
| `Connection refused` | Connection rejected | Check if instance stopped, port closed, or discovery stale |
| Response timeout despite fast connect | Slow backend/proxy response | Check server latency, thread/DB pools, downstream dependencies |
| Errors after long idle gaps | Pooled connection went stale | Check keep-alive, idle eviction, validate-after-inactivity |
| Timeouts increased after enabling retries | Multiple attempts and backoff | Measure retry counts and actual time budget |
| Selected instance changes yet pool stays slow | Multiple physical routes or hot route | Measure pool stats per route and load-balancing distribution |

Transport errors are normally wrapped by Spring in exceptions such as `ResourceAccessException`, while inner exception types vary by request factory. Never rely on a single exception class name to conclude whether it was a connect, lease, or response timeout.

An HTTP 503 is not always a timeout either: it can stem from LoadBalancer finding no instances or from the backend/proxy genuinely returning `503 Service Unavailable`.

## 11. Observing both systems: LoadBalancer and HTTP pool

A failed request may have had a valid instance selection yet hit connection congestion. Therefore, logs/traces should distinguish:

**Selection side:** service ID, instance ID, host/port, candidate count, and routing policy where observable.

**HTTP side:** physical route, pool lease wait time, connection open time, response receive time, HTTP status/exception, attempt count, and `leased/pending/available` connection counts if exposed by the HTTP client.

Example custom log format:

~~~text
traceId=abc123 serviceId=catalog-service selected=catalog-2
route=10.0.1.12:8081 poolPending=0 poolLeased=8
attempt=1 httpStatus=200 durationMs=53
~~~

This is a **suggested format**, not fields automatically emitted by Spring Cloud LoadBalancer/Apache HttpClient. When using Spring Boot observability, verify that appropriate customizers apply to `RestClient.Builder`; for detailed pool metrics, you may need to instrument the connection manager or enable a matching metrics library.

Never log tokens, cookies, credentials, or entire request bodies containing sensitive data just to measure timeouts.

## 12. Hands-on reproduction of timeouts and reuse checks

You can practice without a separate service registry. Run two `catalog-service` instances on a test machine and declare them in `SimpleDiscoveryClient`:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://127.0.0.1:8081
              - uri: http://127.0.0.1:8082
~~~

Suppose each instance exposes these endpoints:

- `GET /whoami` returning the instance ID.
- `GET /slow?ms=5000` simulating a slow 5-second response.
- `GET /ping` returning a small fast body to measure connections.

These are **illustrative endpoints you implement in the test application**, not built-in Spring Cloud endpoints.

### Lab A — Verify instance selection and pooling

1. Initialize one `RestClient` bean from section 5's builder and **reuse the exact same bean** across many requests.
2. Call `/whoami` repeatedly to verify LoadBalancer selects instances provided by discovery.
3. Use Apache HttpClient logging or metrics to observe requests per route, connections opened, leased, and available.
4. Compare newly opened connections against total requests. When keep-alive and pooling work, connection opens are far fewer than requests.
5. Disable keep-alive on the test server or lower idle timeouts, then compare.

**Do not conclude connection reuse solely because the same instance answered.** To prove it, observe the connection manager, network traces, or socket/connection IDs.

### Lab B — Response timeout

1. Keep the 4-second response timeout in Apache HttpClient.
2. Call `/slow?ms=5000` and confirm the client reports a timeout per the actual transport and configuration.
3. Adjust the backend to reply faster and re-run.
4. If retries are enabled, record attempt counts and total elapsed time instead of reading only the response timeout.

Results also depend on whether the endpoint stalls while sending headers, body, or inside middleware/proxies.

### Lab C — Pool lease timeout

1. In a separate run, set `maxConnPerRoute=2` and `connectionRequestTimeout=1s`.
2. Send multiple concurrent blocking calls to the same route—for instance, temporarily use one instance so LoadBalancer does not spread traffic.
3. Have the backend hold requests for a few seconds so leased connections are not immediately returned.
4. Observe requests beyond two connections queuing on the pool and some timing out waiting for a lease.
5. Raise the per-route limit in another run to compare while watching backend impact.

Never run this load-forcing experiment in production.

### Lab D — Idle connections and replaced instances

1. Send requests so the pool holds idle connections.
2. Wait for the server to close idle connections or stop one instance.
3. Send the next request and observe failures or connection re-establishment.
4. Distinguish **stopped instance still picked by discovery** from **live instance whose idle pooled connection was closed**.
5. Tune idle eviction/validate-after-inactivity and compare, without assuming it fixes stale discovery.

## 13. Pre-production configuration checklist

- Is `@LoadBalanced RestClient.Builder` configured properly and does the logical URL use a valid service ID?
- Is a shared `CloseableHttpClient`/connection manager used rather than creating a new one per request?
- Have `connectionRequestTimeout`, `connectTimeout`, and `responseTimeout` been tested independently?
- Do `maxConnTotal` and `maxConnPerRoute` match instance counts, traffic distribution, and backend capacity?
- Are response bodies or streams consumed and released so connections return to the pool?
- Do idle eviction and validate-after-inactivity align with server/proxy connection keep-alive limits?
- During scale-down, are stale `ServiceInstance` caches separated from stale pooled sockets?
- Could retries multiply wait durations or duplicate write operations?
- Do Spring Boot tracing/metrics and HTTP pool metrics still work after declaring custom `RestClient.Builder` beans?
- Were timeouts tested with proxies, TLS, slow backends, and high concurrency on actual library versions?

**Conclusion:** Spring Cloud LoadBalancer determines **which replica is called**; `RestClient` along with the request factory/HTTP transport determines **how connections are opened, reused, and waited on**. Configuring timeouts per phase, managing a shared pool, and observing both layers reduces latency, controls resources, and accurately separates discovery failures from network failures.

**References:**

- [Spring Cloud Commons – RestClient as a LoadBalancer Client](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html#spring-restclient-as-a-loadbalancer-client)
- [Spring Framework – HttpComponentsClientHttpRequestFactory](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/client/HttpComponentsClientHttpRequestFactory.html)
- [Apache HttpClient 5 – RequestConfig.Builder](https://hc.apache.org/httpcomponents-client-5.6.x/current/httpclient5/apidocs/org/springframework/http/client/RequestConfig.Builder.html)
