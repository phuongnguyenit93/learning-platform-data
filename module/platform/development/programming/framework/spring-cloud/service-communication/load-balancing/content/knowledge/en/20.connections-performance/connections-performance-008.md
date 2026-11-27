# Cold Starts, Client Initialization, and Connection Warm-Up

When a new Spring Boot service starts up, the very first request to a downstream is sometimes slower than subsequent requests. For instance, Order Service calling **http://inventory-service/api/stock/BOOK-01** might take 800 ms on the first call, while subsequent calls take only 30–50 ms. Looking solely at Round Robin makes it tempting to misdiagnose **Spring Cloud LoadBalancer as slow at choosing**. In reality, the first request may be paying for work that has not happened yet: bean and child-context initialization, loading the `ServiceInstance` list, allocating HTTP client resources, DNS lookup, opening a TCP connection, TLS handshake, and classloading/JIT compilation.

In this lesson, **cold start** refers to the cost incurred when a process, service ID, HTTP client, or connection is used for the first time after an inactive period. **Warm-up** means proactively executing parts of initialization *before critical traffic arrives*, whereas **connection reuse** means reusing an already established connection. These three concepts are related, not synonymous.

The goal is to pinpoint where latency originates, configure intentional warm-up for **RestClient, RestTemplate, WebClient, and OpenFeign**, coordinate with **ServiceInstanceListSupplier**, discovery, health checks, timeouts, and retries, and verify with real measurements. This lesson does not assume a single warm-up command guarantees every subsequent request will be fast.

## 1. Multiple Forms of "Cold" Can Occur in One Request

| Layer | What can happen for the first time? | Can it stay cold or re-occur later? |
| --- | --- | --- |
| **JVM / Spring Boot** | Classloading, bean creation, auto-configuration, mapper/converter setup, JIT | Can keep warming gradually over many requests |
| **Spring Cloud LoadBalancer** | Creating the child `ApplicationContext` for a service ID; creating suppliers and chooser | Context is usually reused within the process |
| **Discovery / supplier** | Calling the registry, fetching the initial snapshot, building cache/health publishers | Can recur when TTL expires or registry changes |
| **HTTP client resources** | Creating event loops, resolvers, threads, native transport/SSL libraries | Usually reused if keeping the same client/resources |
| **DNS** | Resolving the selected `ServiceInstance` hostname | Can recur due to DNS TTL, new instances, or new resolvers |
| **TCP / TLS** | Opening a new connection, TLS handshake, HTTP/2 setup | Recurs when the pool is empty, connections expire, or new origins appear |
| **Application protocol** | Initializing serializers/deserializers, authentication, loading schemas, app caches | Depends on client, endpoint, and libraries |
| **Runtime pressure** | GC, CPU contention, pool acquisition, autoscaling, cold backend | Can cause slowness even in a "warm" process |

A single warm-up technique targets only **one or a few layers** in this table. For example, eagerly initializing a LoadBalancer context does not open TCP connections; warming up Reactor Netty does not call an Inventory API; calling one Inventory endpoint does not guarantee every replica in the registry has been pre-initialized.

### 1.1. Illustrative Timeline

~~~mermaid
sequenceDiagram
    autonumber
    participant O as Order Service
    participant LB as Spring Cloud LoadBalancer
    participant D as Discovery/Supplier
    participant H as HTTP Client
    participant I as Inventory Instance B
    O->>LB: GET http://inventory-service/...
    Note over LB: Child context may be created for the first time
    LB->>D: Fetch ServiceInstance list
    D-->>LB: [A, B]
    LB-->>O: Select B
    O->>H: Request to B's host:port
    Note over H: Pool/Resolver/Native resources
    H->>H: DNS + TCP + TLS if needed
    H->>I: HTTP request
    I-->>H: HTTP response
    H-->>O: DTO / response
~~~

These steps are a **logical model**: LoadBalancer typically runs inside an HTTP client interceptor/filter rather than returning control to the business layer in a separate step. With an existing connection, DNS/TCP/TLS can be skipped. With caching, discovery need not hit the network.

## 2. Distinguishing Startup Latency, First-Call Latency, and Steady-State Latency

Three distinct metrics must be recorded separately:

1. **Process startup:** from JVM launch until the app is considered ready to accept traffic.
2. **First-call latency:** from the start of the first request until full results arrive, including deferred lazy work.
3. **Steady-state latency:** latency of subsequent requests once primary config/resources are active, under a defined load.

Illustrative example:

| Event | Time |
| --- | ---: |
| Spring Boot starts | T=0 ms |
| `ApplicationReadyEvent` | T=2,500 ms |
| First request to inventory-service | T=2,600 ms |
| First Inventory call completes | T=3,350 ms |
| Later Inventory call completes | 45 ms after start |

A **750 ms vs. 45 ms** gap does not prove LoadBalancer took 705 ms. You must separate context initialization, discovery, pool, DNS, TCP/TLS, and backend time. Nor should you extrapolate warm localhost timings into cross-zone production latency.

### 2.1. Warm-Up Shifts Cost; It Does Not Erase Cost

If you shift 500 ms of initialization out of the first request into startup, the first user sees a faster response. However:

- Startup/readiness can take longer.
- Some downstreams may not be ready yet when the caller starts warming up.
- Rolling out many pods at once can send warm-up traffic spikes downstream.
- Pre-initializing resources can increase memory/threads and idle connections.

Therefore, evaluate **time to readiness**, **first-call P95/P99**, **startup error rates**, and **downstream load**—not just a single post-warm-up latency number.

## 3. Spring Cloud LoadBalancer Creates Child Contexts per Service ID

Spring Cloud LoadBalancer documentation notes that each **service ID** has its own **Spring child `ApplicationContext`**. By default, this context is created **lazily** when the first request for that service ID passes through LoadBalancer.

Suppose the Order app calls three services:

~~~text
inventory-service  -> Inventory LB context
payment-service    -> Payment LB context
catalog-service    -> Catalog LB context
~~~

If the first request only calls `inventory-service`, the contexts for `payment-service` and `catalog-service` may not yet exist. **Creating `RestClient`/`WebClient` beans at startup does not mean all service-ID child contexts are initialized.**

### 3.1. Eager-Load Specific Critical Service IDs

Spring Cloud supports:

~~~yaml
spring:
  cloud:
    loadbalancer:
      eager-load:
        clients:
          - inventory-service
          - payment-service
~~~

Meaning: eagerly initialize the **LoadBalancer client contexts** for the two listed service IDs instead of waiting for the first request.

You do not need to list every service if only a few downstreams have critical first-request latency. **Names must match the exact service IDs used in calls**, not class names, physical URLs, pod names, or RestClient bean names.

### 3.2. Eager Contexts Are Not Preconnect

| Effect of eager-load | Achievable? |
| --- | --- |
| Eagerly create child `ApplicationContext` per service ID | **Yes** |
| Create supplier/LoadBalancer beans inside the child context | **Yes**, per configuration |
| Guarantee the registry already returned the latest list | **No** |
| Guarantee the cache holds all instances | **No** |
| Open TCP/TLS to all instances | **No** |
| Guarantee backends are ready for requests | **No** |
| Guarantee all HTTP clients initialized their resources | **No** |

Eager-loading removes part of **lazy initialization cost**; it does not replace health checks, discovery synchronization, or connection warm-up.

### 3.3. Do Not Eager-Load Every Service "Just in Case"

Creating hundreds of contexts at startup can:

- Increase startup duration and bean/object counts.
- Increase memory footprint and configuration work.
- Initialize services that are never called in this process.
- Obscure the real bottleneck: the true cost may lie in TLS or DNS rather than context setup.

Before adding many service IDs, measure how much **lazy child-context creation** actually contributes to first-call latency.

## 4. Discovery, Caches, and Health Checks Also Have Initial States

**ServiceInstanceListSupplier** supplies the replica list to the chooser. Depending on config, it reads from `DiscoveryClient`/`ReactiveDiscoveryClient`, `CachingServiceInstanceListSupplier`, or `HealthCheckServiceInstanceListSupplier`.

~~~text
Discovery source -> Cache or HealthCheck -> Zone/Hint filters -> LB
~~~

### 4.1. First Discovery Query

If the discovery client has no snapshot yet, the first instance lookup may:

- Query the registry or read the registry cache.
- Deserialize metadata and construct `ServiceInstance`s.
- Wait for registry sync after a provider recently registered.

Eager-loading the context does not guarantee a network discovery query has completed. A warm-up call by service ID can force a real **lookup + choose**, though you should never trigger uncontrolled lookups inside a bean constructor.

### 4.2. A Warm Cache May Still Hold Unhealthy Instances

Spring Cloud LoadBalancer caches per service ID; current docs note caching is enabled by default with a default TTL of **35 seconds** in common setups. Once the TTL expires, the next read may refresh from discovery.

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: true
        ttl: 35s
~~~

This illustrates that caching cuts instance-list fetch overhead—**it is not a mechanism for keeping connections open**. If the discovery implementation (e.g., Eureka) already caches, two-tier caching can add lag before seeing new or removed instances.

A warmed cache can be faster yet **stale**. Never trade away instance-selection accuracy just to shave a few milliseconds off the first request.

### 4.3. Health-Check Warm-Up Has Its Own Delay

`HealthCheckServiceInstanceListSupplier` probes instances on a schedule and emits the latest list. After startup, it can take time for the first probe cycle to complete before health data is populated. If the health publisher uses replay/snapshots, the initial result also depends on the fallback policy when no healthy instances are found.

Never treat a single successful HTTP warm-up call as proof all instances are healthy; LoadBalancer may have hit just one instance. When health checks run on their own schedule, monitor **when the snapshot updates**, not just the HTTP status of the warm-up probe.

## 5. Initializing RestTemplate and RestClient with the Right Lifecycle

**RestTemplate** and **RestClient** are synchronous HTTP clients. Typically you create the configuration and client **once** and reuse them across requests rather than rebuilding them on every business call.

Configuration example for `RestClient`:

~~~java
@Configuration(proxyBeanMethods = false)
class InventoryRestClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }

    @Bean
    RestClient inventoryRestClient(
            @LoadBalanced RestClient.Builder builder) {
        return builder
                .baseUrl("http://inventory-service")
                .build();
    }
}
~~~

Example for `RestTemplate` in legacy systems:

~~~java
@Bean
@LoadBalanced
RestTemplate inventoryRestTemplate() {
    return new RestTemplate();
}
~~~

These snippets illustrate lifecycle and LoadBalancer integration only—**they omit timeouts, HTTP engines, pools, and observability**. Production setups should configure explicit transport timeouts and use Spring Boot-managed customizers/beans where appropriate.

### 5.1. Creating a Client Object Does Not Open Connections

Many HTTP clients use **lazy I/O**:

~~~text
Create RestClient bean
       |
       | Inventory not called yet
       v
Build first request
       |
       | LoadBalancer selects instance
       | HTTP transport finds/opens connection
       v
Receive response
~~~

Never conclude a client is "warm" merely because the Spring Context contains the `RestClient` bean. Even when a request factory or underlying HTTP client is instantiated early, **DNS/TCP/TLS may still run only on the first request**.

### 5.2. Never Create a New Pool per Request

An anti-pattern:

~~~java
StockResponse loadStock(String sku) {
    // Do not repeatedly rebuild the HTTP client and underlying transport.
    RestClient client = RestClient.builder()
            .baseUrl("https://inventory.internal")
            .build();

    return client.get()
            .uri("/api/stock/{sku}", sku)
            .retrieve()
            .body(StockResponse.class);
}
~~~

This snippet drops timeouts, auth, tracing, and request factories configured on the main bean. If code also builds a **new Apache HttpClient/connection manager** on every call, pools cannot be reused and resources risk leaking.

**Do not claim every `RestClient.builder()` call opens a new pool/socket**: that depends on the HTTP engine and resource sharing. Still, repeatedly constructing clients/factories makes lifecycles hard to govern and is never a sound warm-up strategy.

### 5.3. Treat Configured Clients as Long-Lived Objects

`RestClient`/`RestTemplate` are typically used as singletons or long-lived reusable components, fully configured before handling traffic. Do not mutate interceptors, message converters, or request factories concurrently with live requests. Set timeouts, pool sizes, auth, TLS, and observability when constructing the client.

In stable existing `RestTemplate` systems, there is no immediate need to rewrite to `WebClient` just for first-call latency; first verify **bean reuse, connection pooling, and lookup timing**.

## 6. OpenFeign: Creating a Feign Proxy Differs from Opening Connections

**Spring Cloud OpenFeign** generates a Java proxy from an interface:

~~~java
@FeignClient(name = "inventory-service")
interface InventoryFeignClient {
    @GetMapping("/api/stock/{sku}")
    StockResponse stock(@PathVariable("sku") String sku);
}
~~~

OpenFeign also maintains per-named-client contexts/configs with encoders, decoders, contracts, interceptors, and an HTTP Client implementation. Since Spring Cloud OpenFeign 4.x, **`@FeignClient` attributes are resolved eagerly by default** to support AOT. The property:

~~~yaml
spring:
  cloud:
    openfeign:
      lazy-attributes-resolution: false
~~~

governs **when annotation attributes are resolved**. It is **not a TCP preconnect toggle, is not equivalent to `spring.cloud.loadbalancer.eager-load.clients`**, and does not ensure Feign has sent any HTTP requests.

### 6.1. Do Not Call Feign in Constructors or Bean Initialization

Spring Cloud OpenFeign documentation warns that invoking a Feign client early in the application lifecycle while beans/contexts are still initializing is **unsupported** and can cause initialization failures.

Avoid:

~~~java
@Component
class BadStartup {

    BadStartup(InventoryFeignClient feign) {
        feign.stock("BOOK-01");  // Wrong place: I/O inside constructor.
    }
}
~~~

If a real test call is necessary, run it in a startup hook **after contexts and proxies are ready**, with timeouts, bounds, and a clear policy on whether downstream failures block readiness.

### 6.2. Configure Feign Transport Based on the Actual Implementation

Feign may use Apache HttpClient 5, OkHttp, or another HTTP client. First-call TCP/TLS duration, pool acquisition, and connection reuse depend on the **underlying transport**, not the `@FeignClient` interface alone. Feign's `connectTimeout`/`readTimeout` parameters do not cover every phase or the overall deadline.

"Creating Feign proxies early" only removes proxy/config initialization cost; warming connections requires making a real safe request or using transport-specific preconnect APIs if supported and justified.

## 7. Reactor Netty Provides a warmup() API for Client Resources

**WebClient** typically uses **Reactor Netty** as its HTTP connector in Spring WebFlux. Per Reactor Netty documentation, the following resources may be lazily initialized on the **first request** by default:

- Event loop group.
- Hostname resolver.
- Native transport libraries (when used on the platform).
- Native security libraries, such as OpenSSL (when configured).

Reactor Netty provides:

~~~java
HttpClient httpClient = HttpClient.create();

// Proactively initialize Netty resources.
httpClient.warmup().block(Duration.ofSeconds(3));
~~~

**`HttpClient.warmup()` returns `Mono<Void>`**. Calling `warmup()` without subscribing means the reactive work **has not executed yet**. In the snippet above, `block(Duration)` runs on a **startup thread or blocking-safe worker**, never on a Netty event loop and never on a WebFlux request path.

### 7.1. What warmup() Does and Does Not Do

| Task | `HttpClient.warmup()` |
| --- | --- |
| Initialize configured event loops/resources | Yes |
| Initialize hostname resolver | Yes |
| Load required native transport/security libraries | Yes |
| Pre-resolve DNS for `inventory-a.internal` | **Not guaranteed** |
| Perform TCP connect to `inventory-service` | **No** |
| Perform TLS handshakes with every instance | **No** |
| Run through Spring Cloud LoadBalancer to select a `ServiceInstance` | **No** |
| Warm up endpoint-specific decoders/mappers | **Not guaranteed** |

Per Reactor Netty documentation, the **first** HTTP call still resolves the hostname and opens the connection; subsequent requests can reuse pooled connections. Thus `warmup()` removes only **part of client-side startup cost**, not full network preconnect.

### 7.2. Make Sure You Warm the Same HttpClient Used by WebClient

Unified bean configuration example:

~~~java
import java.time.Duration;
import io.netty.channel.ChannelOption;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.boot.ApplicationRunner;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;

@Configuration(proxyBeanMethods = false)
class InventoryWebClientConfiguration {

    @Bean
    HttpClient inventoryNettyHttpClient() {
        return HttpClient.create()
                .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 500)
                .responseTimeout(Duration.ofSeconds(2));
    }

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder(
            HttpClient inventoryNettyHttpClient) {
        return WebClient.builder().clientConnector(
                new ReactorClientHttpConnector(inventoryNettyHttpClient));
    }

    @Bean
    ApplicationRunner warmupHttpResources(
            HttpClient inventoryNettyHttpClient) {
        return args -> inventoryNettyHttpClient.warmup()
                .block(Duration.ofSeconds(3));
    }
}
~~~

The key is that the **exact same `HttpClient` bean** is:

1. Passed into `WebClient`'s `ReactorClientHttpConnector`.
2. Invoked with `warmup()` inside `ApplicationRunner`.

If you warm an `HttpClient` A while `WebClient` uses an `HttpClient` B with separate resources, warm-up results may not apply to live traffic. In practice `HttpClient`s can share global resources, yet **never rely on implicit sharing** to claim warm-up covered the right connector.

**Spring Boot note:** manually calling `WebClient.builder()` may skip **`WebClientCustomizer`, observation, codec, auth, or connector customizations** provided by Boot. For production, preserve existing customizations or integrate via Boot's managed builder appropriately. The example above focuses purely on Netty warm-up mechanics.

### 7.3. Never Call block() on the WebFlux Event Loop

Putting a blocking warm-up inside a handler:

~~~java
@GetMapping("/stock")
Mono<StockResponse> readStock() {
    // Wrong: blocking warmup on a reactive request path.
    httpClient.warmup().block();
    return inventoryClient.getStock("BOOK-01");
}
~~~

This is an anti-pattern: requests running on the event loop can block, cutting concurrency and triggering non-blocking-thread exceptions. If startup must wait for Netty resources, do it in `ApplicationRunner` (startup thread) with a **bounded timeout**, or run async warm-up with an explicit readiness gate.

## 8. Connection Pools, TCP Keep-Alive, and TLS Reuse

After selecting a `ServiceInstance`, the HTTP client connects to the **actual origin** (scheme, host, port). The connection pool can retain connections so later requests skip repeating TCP/TLS setup from scratch.

~~~text
Request 1 -> inventory-a:8443
  pool has no matching connection
  DNS / TCP / TLS -> HTTP request -> keep connection idle

Request 2 -> inventory-a:8443
  pool has valid connection
  reuse -> HTTP request

Request 3 -> inventory-b:8443
  different origin
  may need fresh DNS / TCP / TLS
~~~

### 8.1. Load Balancing and Connection Reuse Do Not Conflict

Round Robin can alternate between A and B while the transport maintains **separate connections to each origin**, as permitted by the pool and servers. You do not need to pin all traffic to a single instance just to achieve connection reuse.

However, when instance count jumps suddenly, each new origin may require fresh connections. That is why post-scale-out latency can briefly rise even though both caller and Spring Cloud LoadBalancer contexts already exist.

### 8.2. HTTP/2 Changes "One Request = One Connection"

When HTTP/2 is negotiated, one connection can carry multiple concurrent streams. Therefore:

- **HTTP request count** does not equal **TCP connect count**.
- Connection pool limits do not map one-to-one to request concurrency limits.
- Connections can still be closed by servers/proxies via idle timeouts, max age, or `GOAWAY`.

Never use **response count** stats to claim the client reused connections. Inspect connection-level metrics/traces from the HTTP transport and verify the actual negotiated HTTP version.

### 8.3. Reasons Connections Fail to Be Reused

- Server, ingress, infrastructure load balancer, or proxy sends `Connection: close` / closes idle connections.
- Client pool has `maxIdleTime` or `maxLifeTime` set too short.
- Connection encountered a reset, timeout, or was flagged unhealthy.
- Request routed to another instance (different origin).
- HTTP engine repeatedly recreated without a shared pool.
- TLS/proxy configuration changed.
- Pool hit its cap, evicting or closing connections to conserve resources.

Do not set enormous idle timeouts just to keep connections alive forever: sockets can die silently in the middle without the client knowing, and idle resources still carry cost.

### 8.4. A Warm DNS Cache Does Not Mean Stable IPs

DNS TTLs can cause hostnames to re-resolve. With registries storing hostnames, IP changes after deployments are normal. Hardcoding or pinning DNS caches overly long to optimize cold lookups can send traffic to dead addresses.

**Never disable TLS validation, hostname verification, or certificate checks just to cut handshake time.** TLS session resumption can lower cost depending on transport and server, though it does not guarantee every new connection resumes successfully.

## 9. Application Startup and Readiness: Where Does Warm-Up Belong?

Per Spring Boot documentation, the late lifecycle sequence runs roughly as:

~~~text
ApplicationContext refreshed
    |
ApplicationStartedEvent
    |
ApplicationRunner / CommandLineRunner
    |
ApplicationReadyEvent
    |
AvailabilityChangeEvent: ReadinessState.ACCEPTING_TRAFFIC
~~~

Hence, **`ApplicationRunner`** is an appropriate place for bounded warm-up **after the context is ready**, before readiness signals `ACCEPTING_TRAFFIC` in Spring Boot's standard lifecycle.

### 9.1. Choosing by Criticality

| Goal | Mechanism | When downstream fails at startup |
| --- | --- | --- |
| Remove LB context creation cost | `eager-load.clients` | Usually needs no network probe |
| Initialize Reactor Netty resources | `HttpClient.warmup()` in runner | Log and optionally fail startup per policy if internal resources fail |
| Verify critical downstream actually responds | Time-bounded GET warm-up | Block readiness only if dependency is **truly mandatory** for all traffic |
| Warm optional caches | Async/periodic startup job | Keep serving traffic, emit degraded metric |
| Warm only once traffic arrives | Controlled post-ready probe | Does not delay startup, though first request may stay cold |

Never mechanically put **"every dependency must be UP"** into readiness. If A only powers a secondary feature, A being temporarily down should not knock all of Order Service out of Kubernetes load balancing. Conversely, for a dependency required by every request, blocking readiness can make sense—just guard against **circular startup dependencies**.

### 9.2. Never Warm Up via @PostConstruct When Using Feign/LoadBalancer

This pattern is risky:

~~~java
@PostConstruct
void init() {
    inventoryFeignClient.stock("BOOK-01");
}
~~~

Beans may still be initializing and Feign/LoadBalancer subcontexts may not be in a valid state yet. Performing I/O in constructors or `@PostConstruct` also makes startup failures harder to classify. Per Spring Cloud OpenFeign guidance, avoid calling Feign clients during bean initialization.

**No single lifecycle hook is safe for every warm-up strategy.** For async warm-up, merely using `@EventListener(ApplicationReadyEvent.class)` with fire-and-forget `subscribe()` does not guarantee completion before readiness. Implement explicit completion tracking and readiness gating if hard guarantees are required.

## 10. Warming Connections with a Safe HTTP Request

To ensure DNS/TCP/TLS/pools and LoadBalancer **are actually exercised**, you can run a safe GET/HEAD request downstream once the application context is ready:

~~~text
ApplicationRunner
  -> WebClient via @LoadBalanced
  -> LoadBalancer picks a ServiceInstance
  -> HTTP connector connects to real host/port
  -> GET /internal/warmup
  -> read/close response, letting the pool retain the valid connection
~~~

Do this only when there is an **explicitly safe, idempotent, low-cost endpoint**. Never invoke payment POSTs, order creation, reservations, or background job triggers as a "warm-up."

### 10.1. Example: Time-Bounded WebClient Warm-Up

Suppose Inventory exposes an authenticated, side-effect-free **GET /internal/warmup** endpoint:

~~~java
import java.time.Duration;
import org.springframework.boot.ApplicationRunner;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.http.ResponseEntity;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Bean
WebClient inventoryWebClient(
        @LoadBalanced WebClient.Builder builder) {
    return builder.baseUrl("http://inventory-service").build();
}

@Bean
ApplicationRunner inventoryWarmupProbe(
        WebClient inventoryWebClient) {
    return args -> {
        Mono<ResponseEntity<Void>> probe = inventoryWebClient.get()
                .uri("/internal/warmup")
                .retrieve()
                .toBodilessEntity()
                .timeout(Duration.ofSeconds(2));

        // Block only on startup thread; this acts as a hard-gate policy.
        probe.block(Duration.ofSeconds(3));
    };
}
~~~

This example **actively blocks startup if the probe fails**, because exceptions propagate out of `ApplicationRunner`. That fits only when Inventory is a mandatory dependency and rollouts account for temporary unavailability.

If warm-up is purely a performance optimization, **catch errors selectively, record a metric, and continue startup** rather than marking the entire replica unready because Inventory flickered. Never write an infinite retry loop inside `ApplicationRunner`.

**Distinguish the two timeouts in the example:**

- **`Mono.timeout(2s)`:** budget for the publisher, spanning instance selection, pooling, network, and decoding.
- **`block(Duration.ofSeconds(3))`:** limit on how long the startup thread waits for the result, not a transport connect/read timeout setter.

Configure transport timeouts separately (connect, response, pool acquire). Never treat a `block` timeout as a complete substitute for network/cleanup policies.

If you have both a runner calling **`HttpClient.warmup()`** and a runner making an HTTP probe, runner execution order is not guaranteed by default. When Netty resources must initialize before the probe, put them sequentially in **one `ApplicationRunner`** or specify explicit ordering with `@Order`.

### 10.2. One Request Does Not Warm Every Replica

If discovery returns `[A, B, C]`, the warm-up GET above may hit only **B**. Connections to A/C remain cold. Even sending three calls does not guarantee Round Robin or zone/hint policies hit each instance exactly once.

Truly warming every instance requires tracking lists, reachability, and per-origin calls, adding cost and complexity:

- Determine how many `inventory-service` replicas currently exist.
- Track instance ID, scheme, host, and port; the list can change right after taking a snapshot.
- Use **safe** requests, timeouts, and concurrency caps.
- Never bypass auth, mTLS, or tenant/zone policies.
- Avoid creating traffic storms against freshly deployed backends.
- Recognize connections still may not stay open past idle timeouts or scaling events.

In most cases, warming every instance is **unnecessary**. Warming local resources, eager-loading key service IDs, and letting normal traffic populate connection pools is simpler.

### 10.3. Health Endpoints Are Not Automatically Warm-Up Endpoints

`GET /actuator/health` is typically an application health signal, and does not necessarily:

- Exercise the expensive code paths of a specific business API.
- Run through the exact Jackson serializers/DTOs callers use.
- Share the same authentication/headers as business requests.
- Reflect the capacity to serve a business API.

If you build **`/internal/warmup`**, give it a strict contract, restrict access, avoid writes or expensive locks, and ensure it stays harmless when hundreds of callers invoke it simultaneously.

## 11. Warm-Up for RestClient/RestTemplate and OpenFeign

For blocking clients, there is no standard `warmup()` API on `RestClient` or `RestTemplate` equivalent to Reactor Netty's `HttpClient.warmup()`. You can:

1. Build a **reusable HTTP client/connection manager** during bean creation.
2. Eager-load Spring Cloud LoadBalancer child contexts.
3. Call a **safe endpoint** through the same LoadBalancer-wired `RestClient`/`RestTemplate`/Feign client.

Example with `RestClient`:

~~~java
@Bean
ApplicationRunner warmupInventoryBlocking(RestClient inventoryRestClient) {
    return args -> {
        inventoryRestClient.get()
                .uri("/internal/warmup")
                .retrieve()
                .toBodilessEntity();
    };
}
~~~

This assumes `inventoryRestClient` is properly configured as **`@LoadBalanced`** per Section 5, with baseUrl `inventory-service` and proper timeouts. **Never use a direct `RestClient` pointing to another URL** and claim the LoadBalancer-backed logical client is warm.

The snippet above **does not set an overall deadline**; it only shows the call site. In production, configure HTTP engine timeouts plus a total startup/probe budget, and decide whether exceptions fail startup or degrade gracefully.

With **Feign**, you can likewise call a side-effect-free GET method via the Feign proxy in `ApplicationRunner` when lifecycle and policies permit. However, Feign offers no preconnect guarantee across all instances; this executes **one real HTTP request** subject to underlying Feign/client exceptions and retries.

### 11.1. Never Use a Separate Warm-Up HTTP Client with a Different Pool

If warm-up calls via `RestTemplate` A while business requests use `RestClient` B on a different Apache HC5 connection pool, connections opened by A **will not** be reused by B. Verify the exact same underlying pool/HTTP engine and TLS/proxy config if the goal is retaining connections.

Never maintain insecure dedicated credentials just to probe `/internal/warmup`. Warm-up must pass through the same authentication, tracing, and authorization policies required by the backend and environment.

## 12. Warming Connection Pools with Burst Requests: Risks and Limits

Some systems intentionally fire many parallel HTTP requests at startup to populate open connections:

~~~text
10 concurrent warm-up GETs -> expect 10 ready sockets
~~~

This assumption is unreliable without knowing the exact HTTP transport:

- The pool may reuse the same connection across sequential completions.
- HTTP/2 can multiplex multiple streams over a single TCP connection.
- Connection pools enforce max connections, pending acquires, or dynamic shrinking.
- LoadBalancer may route by zone/hint rather than spreading calls as imagined.
- Backends or proxies may close idle sockets shortly after warm-up.
- Concurrent startups can spike CPU/TLS handshakes, backfiring during rollouts.

**Sending hundreds of synthetic requests to force pools open is not recommended.** If controlled preconnect is truly needed, choose a transport/connection manager with explicit APIs and metrics, identify which origins matter, and bound traffic under a strict budget.

### 12.1. Cost-Appropriate Warm-Up Levels

| Strategy | Startup Cost | Main Benefit | Risk |
| --- | --- | --- | --- |
| No warm-up | Low | Fast startup | First call pays lazy overhead |
| Eager-load LB contexts | Low to medium | Eliminates per-service-ID lazy context init | Does not remove DNS/TCP cost |
| Reactor Netty `warmup()` | Low to medium | Prepares event loops/resolvers/native resources | No network preconnect |
| Single safe GET probe | Network I/O | Exercises LB + DNS/TCP/TLS + endpoint | Can fail startup/hit cold downstream/add load |
| Probe multiple services | Higher | Cuts cold starts across critical dependencies | Startup coupled to multiple backends |
| Probe every instance | High | Can warm multiple origins | Risk of connection storms, bypasses routing rules |

Start with the simplest option backed by measured impact instead of optimizing every layer at once.

## 13. Warm-Up Does Not Solve Retries, Timeouts, or Failure Recovery

Even after a successful warm-up:

~~~text
T0: caller successfully warms connection to A
T1: A terminates while registry is updating
T2: real request still picks A from stale cache
T3: connection refused / timeout
~~~

Warm-up **cannot guarantee an instance stays alive**. You still need:

- Suitable discovery and cache TTLs.
- Reliable health checks where needed.
- Connect/read/response timeouts to cap waiting.
- Retries only for safe errors/methods within an attempt budget.
- Circuit breakers/bulkheads for isolation and load shedding.
- Tracing/metrics to tell cold-connection errors apart from dependency outages.

Conversely, a failed warm-up should not automatically crash application startup. If Order can still serve endpoints that do not require Inventory, **decouple Order's readiness** from Inventory's status by contract instead of creating circular startup dependencies.

### 13.1. Avoid Retry Storms When Many Pods Boot Together

When 100 pods deploy simultaneously, each warming 3 services with 3 retry attempts, downstreams can get hit by 900 attempts in seconds. If the backend is also cold, probes pile pressure on right while it is booting.

Enforce:

- Few probes and strict concurrency limits.
- Short deadlines, few or zero retries during warm-up.
- Backoff and jitter where required.
- Controlled startup/rollout pacing.
- Explicit degraded-startup policy.
- Metrics to detect warm-up-induced load.

**Warm-up is an auxiliary performance optimization, not an excuse for unbounded retries when dependencies are unready.**

## 14. Infrastructure Events That Turn "Warm" Back into "Cold"

| Event | What can go cold again? | What to check |
| --- | --- | --- |
| Caller pod restarts | JVM/beans/LB contexts/HTTP resources | Startup/readiness and first call |
| Inventory pod scales out | Connections to new instances | First request to each new origin |
| DNS record changes | Resolver cache expires, connects to new IP | DNS TTL and pool |
| Long idle period | Pool evicted or proxy closed sockets | Keep-alive/idle timeouts |
| Backend rollout/TLS rotation | TLS handshake or session resumption | Certificates, SNI, truststores |
| LB cache TTL expires | Discovery refresh | Registry latency/cache metrics |
| Traffic shifts zone/hint | New filtered instance set | Supplier chain and metadata |
| JVM touches unused class | Classloading/JIT/serializer path | First-use code paths |
| Caller autoscales to zero | Whole process starts cold | Startup architecture |

Thus, measurements taken immediately after warm-up prove only **the state at that instant**. Systems can hit cold effects multiple times a day due to topology shifts, connection lifecycles, and traffic swings.

## 15. How to Measure Cold and Warm Latency

Before enabling warm-up, establish a baseline. Capture at minimum:

- **Startup duration** through readiness.
- **First HTTP call** to each critical service ID after startup.
- **Calls 2–N** to the same endpoint and payload, keeping the same client bean.
- **First call to a newly scaled-out instance**.
- **Request after an idle gap** longer than connection hold time.
- **P50/P95/P99** under production-representative load and topology.

Never compare a single cold request against a single warm request and declare an exact speedup. DNS caches, JIT, CPU scheduling, GC, backend load, and network jitter cause wide variance.

### 15.1. Use a Monotonic Clock for Elapsed Time

Minimal example timing a `RestClient` call:

~~~java
long begin = System.nanoTime();

try {
    StockResponse response = inventoryRestClient.get()
            .uri("/api/stock/{sku}", "BOOK-01")
            .retrieve()
            .body(StockResponse.class);
} finally {
    long elapsedNanos = System.nanoTime() - begin;
    System.out.println("Elapsed (ms) = " +
            Duration.ofNanos(elapsedNanos).toMillis());
}
~~~

**`System.nanoTime()`** is appropriate for elapsed time within a single process; never subtract wall-clock timestamps that can jump on clock sync. In production, use **Micrometer `Timer`/`Observation`** and histograms instead of `System.out` per request.

### 15.2. With WebClient, Start Timing Only on Subscription

`WebClient` executes I/O upon subscription. Measuring only **Mono construction** is wrong:

~~~java
long start = System.nanoTime();
Mono<StockResponse> mono = inventoryWebClient.get()
        .uri("/api/stock/BOOK-01")
        .retrieve()
        .bodyToMono(StockResponse.class);
// No HTTP request may have been sent yet here.
~~~

An approximate per-subscription timing pattern:

~~~java
Mono<StockResponse> timed = Mono.defer(() -> {
    long begin = System.nanoTime();
    return inventoryWebClient.get()
            .uri("/api/stock/BOOK-01")
            .retrieve()
            .bodyToMono(StockResponse.class)
            .doFinally(signal -> {
                long nanos = System.nanoTime() - begin;
                durationRecorder.record(
                        "inventory", signal.name(), nanos);
            });
});
~~~

In this example, **`durationRecorder`** is an application-provided metric helper, not a built-in Spring API. The `doFinally` hook fires for complete/error/cancel, so distinguish outcomes instead of treating every terminal signal as success.

When retries exist, distinguish whether a timer measures **each attempt** or the **logical call including retries/backoff**. Both are useful and neither replaces the other.

### 15.3. An Illustrative Measurement Table

| Metric | Before tuning | After eager + warmup | Interpretation |
| --- | ---: | ---: | --- |
| Startup to ready | 2,400 ms | 2,750 ms | Startup increased by 350 ms |
| First-call Inventory | 750 ms | 180 ms | Cost shifted out of first request |
| Steady-state Inventory P50 | 45 ms | 44 ms | Essentially unchanged |
| Steady-state Inventory P99 | 190 ms | 188 ms | No meaningful improvement |
| First-call new instance | 600 ms | 590 ms | Still cold since new instance had no connection yet |

**Numbers are completely hypothetical** to demonstrate how to read the data. Reporting only that first-call latency fell 570 ms while omitting the 350 ms startup increase tells an incomplete story.

## 16. Breaking Down First-Call Latency by Layer

A single total duration hides root cause. Break it down:

| Layer to Observe | Signals / Measurement Source | Possible Optimization |
| --- | --- | --- |
| Spring beans/classloading | Startup instrumentation, profiler/JFR | Trim unnecessary beans/lazy paths |
| Child LB context | `LoadBalancerClientFactory`/context creation logs | Eager-load critical service IDs |
| Discovery query/cache | Registry metrics, supplier timing/cache hits | Tune caching thoughtfully, improve discovery |
| HTTP event loop | Reactor Netty init/CPU | `HttpClient.warmup()` |
| Pool acquire | Active/idle/pending connections | Pool sizing/concurrency, not just warm-up |
| DNS | Resolver timing/cache hits | Sensible DNS config/TTL |
| TCP connect | Connection establishment metrics | Connection reuse, network topology |
| TLS handshake | TLS handshake duration | Reuse/valid TLS config |
| Backend processing | Server tracing/endpoint latency | Backend warm-up, DB/query/cache tuning |
| Decode/serialization | JFR, profiler, conversion timing | Jackson/codec configuration |

**A slow first call may actually be a cold backend.** If the backend just booted and is loading caches, opening database connections, or JIT-compiling code for the first time, warming the **client** will not eliminate most of the latency. Trace both sides and separate server processing time.

### 16.1. JFR, Profiling, and Startup Steps

In Java applications, **Java Flight Recorder (JFR)** and profilers reveal CPU, classloading, lock contention, thread starts, GC, and network events. Spring Boot supports `ApplicationStartup` instrumentation to inspect application context startup steps. Combine with HTTP client metrics and distributed tracing so you do not blame LoadBalancer for everything.

Avoid leaving heavy profiling or wire logging enabled continuously in production without measuring overhead. When capturing short diagnostic windows, scope them tightly and scrub sensitive data.

### 16.2. Metrics to Separate

~~~text
app_startup_to_ready_seconds
outbound_first_call_seconds{service="inventory-service"}
outbound_http_duration_seconds{service="inventory-service"}
client_pool_pending_connections
client_pool_active_connections
client_connect_duration_seconds
client_tls_handshake_duration_seconds
loadbalancer_no_instance_total
outbound_retry_attempts_total
startup_warmup_failures_total
~~~

These are **suggested metric names**, not default built-ins across Spring Boot, Spring Cloud, or Reactor Netty. Exact names and availability depend on your instrumentation.

Avoid high-cardinality labels like request ID, SKU, user ID, connection ID, or ephemeral hostnames. Instance IDs help in traces and logs, but if used in metrics keep cardinality strictly bounded.

## 17. Testing Warm-Up with MockWebServer and Spring Cloud Context

A solid testing strategy has **two layers**:

1. **Unit tests:** verify the runner/subscription actually invokes the probe, timeout, or fallback policy.
2. **Integration tests:** verify requests with a **service ID** are resolved by LoadBalancer to a physical URI and hit the real `MockWebServer`.

### 17.1. Unit Test: WebClient Warm-Up Must Subscribe

Example using a fake `ExchangeFunction` to avoid network I/O:

~~~java
AtomicInteger requestCount = new AtomicInteger();

ExchangeFunction fake = request -> {
    requestCount.incrementAndGet();
    return Mono.just(ClientResponse.create(HttpStatus.NO_CONTENT).build());
};

WebClient client = WebClient.builder()
        .baseUrl("http://inventory-service")
        .exchangeFunction(fake)
        .build();

Mono<ResponseEntity<Void>> probe = client.get()
        .uri("/internal/warmup")
        .retrieve()
        .toBodilessEntity();

assertEquals(0, requestCount.get()); // Not subscribed yet.
probe.block(Duration.ofSeconds(1));
assertEquals(1, requestCount.get()); // Probe actually executed.
~~~

Corresponding classes: **`AtomicInteger`** in `java.util.concurrent.atomic`; **`ExchangeFunction`/`ClientResponse`** in Spring WebFlux; **`HttpStatus`** in Spring HTTP; **`Mono`** in Reactor.

**Limitation:** this test verifies only subscription and request building. A fake `ExchangeFunction` has **no** TCP/TLS, connection pool, or Spring Cloud LoadBalancer. Never cite it as proof connections are warm.

### 17.2. Integration Test: Observe a Real Server Receiving Requests

In `@SpringBootTest` with two `MockWebServer` instances on dynamic ports, configured via `SimpleDiscoveryClient`:

~~~java
@DynamicPropertySource
static void registerInstances(DynamicPropertyRegistry registry) {
    registry.add(
            "spring.cloud.discovery.client.simple.instances.inventory-service[0].uri",
            () -> serverA.url("/").toString());
    registry.add(
            "spring.cloud.discovery.client.simple.instances.inventory-service[1].uri",
            () -> serverB.url("/").toString());
}
~~~

Enqueue a `204` response for `GET /internal/warmup` on both servers. Then invoke the **exact `@LoadBalanced` `WebClient`/`RestClient`** used by the application. Verify:

- **`RecordedRequest`** appears on server A or B.
- Method is `GET`; path is `/internal/warmup`.
- It did not attempt DNS lookup for `inventory-service` as a physical hostname.
- No `POST` or side-effecting request occurred.
- A bounded timeout triggers when a server is slow or unresponsive.
- Probe/attempt counts match policy without unexpected automatic retries.

If you need to prove **every instance receives warm-up**, use deterministic selection or explicitly target each origin; default Round Robin alone does not guarantee it. Never assert that the first request always hits server A, as the initial counter offset can vary.

### 17.3. Do Not Verify Connection Reuse via Response Bodies

Two HTTP requests returning `200` **do not prove** they shared a TCP connection. Verifying reuse requires underlying transport metrics/event hooks or a server recording connection identifiers, TCP accepts, and TLS handshakes.

One server can serve 2 HTTP requests over 2 connections, or HTTP/2 can send many requests over one connection. Never infer reuse from response order or `RecordedRequest` count alone.

## 18. A/B Experiments: Avoiding Flawed Benchmarks

To evaluate benefits fairly:

1. Run **config A without warm-up** and **config B with warm-up** in equivalent environments.
2. Keep JDK, BOM, CPU/memory, HTTP engine, pool sizing, and traffic patterns identical.
3. Measure across multiple restarts **from fresh processes**, not inside one long-running JVM.
4. Separate first calls to **eager-loaded service IDs**, non-eager service IDs, and new instances.
5. Record startup time, first-call latency, steady-state P95/P99, and warm-up failures.
6. Compare connection counts and startup CPU/network usage.
7. Test cold cache, hot cache, and restarts after idle periods.
8. Keep backend load fixed or measure backend latency separately.

### 18.1. "Cold Start" Is Not a Typical JMH Microbenchmark

JMH excels for **Java microbenchmarks**, whereas an HTTP request traversing discovery, DNS, TCP/TLS, and a backend spans multiple systems and is unstable at nanosecond precision. Use an integration/performance harness tracking end-to-end latency and connection events.

A single run is easily skewed by:

- Warm state left over from an earlier test.
- Spring Test context caching reusing an `ApplicationContext`.
- Unreset DNS caches or global pools.
- Native transport/JIT already loaded in the JVM.
- A backend that just scaled or warmed its DB caches.

To measure a **true first run**, enforce explicit process/context isolation rather than merely instantiating a fresh `WebClient` inside the same JVM.

### 18.2. Never Assert Absolute Timings in Unit Tests

Tests like this are notoriously flaky:

~~~java
assertTrue(firstCallMillis > secondCallMillis);
~~~

Nothing guarantees the first call is always slower than the second on a shared CI runner. Instead:

- Unit tests verify **warm-up behavior is invoked** and retries/deadlines are bounded.
- Integration tests verify **requests traverse LoadBalancer and a real HTTP server**.
- Separate performance tests compare **statistical distributions** across multiple processes/requests.

## 19. Situations Where First-Call Is Slow Yet Warm-Up Is Not the Answer

| Symptom | Possible Cause | Appropriate Fix |
| --- | --- | --- |
| First call per service ID is slow | Lazy Spring Cloud LB child context | `eager-load.clients` for key services |
| First call per JVM is slow on WebClient | Reactor Netty event loop/resolver/native init | `HttpClient.warmup()` |
| First call per new host:port is slow | DNS/TCP/TLS not established yet | Connection reuse; optional bounded probe |
| Requests after long idle turn slow again | Idle connections closed | Tune pool idle policy; understand infra lifecycles |
| Slow only during traffic spikes | Pool acquire queue/CPU/backpressure | Pool/concurrency sizing, timeouts, profiling |
| Slow when many pods start together | Warm-up storm or unready registry/backends | Rollout pacing, jitter, probe limits |
| Immediate HTTP 503, no instances | Empty discovery/supplier | Check registry/health; do not raise timeouts |
| Slow responses despite pooled connections | Cold backend queries/DB/cache | Optimize backend; inspect server spans |
| Frequent and failing DNS lookups | Resolver/TTL/DNS network issues | Investigate DNS; do not pin caches overly long |
| RestClient fast but Feign first call slow | Different Feign proxy/config/HTTP engine | Separate proxy init, request factory, LB context |
| Warm-up fast yet real traffic slow | Probe misses real code path or backend instance | Measure against real endpoints/instances |
| P99 rises after deploying new instances | Cold new origins, TLS/connection setup | Monitor per-origin connects and rollouts |

If data shows **latency is mainly on the backend**, client eager-loading may polish startup traces while barely moving request latency. Optimize based on measured root cause, not mechanism names.

## 20. Designing Production Warm-Up: Prioritize by Impact

A safe rollout path:

1. **Confirm the cold effect:** demonstrate the first-call latency gap with the same client, instance, and endpoint.
2. **Break down the cause:** child LB context, discovery, Netty resources, DNS/TCP/TLS, backend, or codecs.
3. **Prioritize reuse:** build clients/HTTP engines/connection pools once and reuse them.
4. **Selectively eager-load:** only service IDs critical to first-request SLOs.
5. **Warm Netty resources if helpful:** share the exact same `HttpClient`/connector across WebClient and the startup runner.
6. **Add HTTP probes only with measurable gain:** safe GET endpoint, timeouts, auth, concurrency caps, and attempt bounds.
7. **Define readiness policy:** fail startup only for truly mandatory dependencies.
8. **Track trade-offs:** startup time, CPU, memory, connections, first-call P99, and downstream load.
9. **Pace rollouts:** avoid hundreds of pods warming up at once.
10. **Preserve resilience:** timeouts, retry budgets, health checks, caching, and observability must remain intact.

### 20.1. Deciding Between Fail-Fast and Best-Effort

| Condition | Viable Policy |
| --- | --- |
| Inventory is mandatory for **every** Order endpoint | May block readiness when Inventory is down, guarding against circular startup dependencies |
| Inventory is used only on some endpoints | Best-effort warm-up; other endpoints continue serving |
| Registry is booting with eventual consistency | Bounded low retries or allow degraded start; never retry endlessly |
| Probe needs special permissions | Never bypass auth; grant minimal dedicated scope |
| Large rollout | Cap rate, concurrency, jitter, and probed service count |
| Cold cost is only a few ms | Warm-up may be unnecessary; simpler setup wins |

Example application using a best-effort policy catching startup probe errors:

~~~java
@Bean
ApplicationRunner optionalInventoryWarmup(WebClient inventoryWebClient) {
    return args -> {
        try {
            inventoryWebClient.get()
                    .uri("/internal/warmup")
                    .retrieve()
                    .toBodilessEntity()
                    .timeout(Duration.ofSeconds(1))
                    .block(Duration.ofSeconds(2));
        } catch (RuntimeException ex) {
            // Record metric and structured log per application policy.
            // Do not treat probe failure as proof the entire app is broken.
            warmupMetrics.recordFailure("inventory-service", ex);
        }
    };
}
~~~

Here, **`warmupMetrics`** is an application-provided helper that must be injected; this illustrates a policy pattern rather than a built-in Spring class. If a hard gate is required, do not swallow exceptions; let the runner fail (or deliberately manage readiness state) and observe deployment behavior.

### 20.2. AOT/Native-Image Adds Service ID Declaration Requirements

Per Spring Cloud LoadBalancer documentation, when using **Spring AOT/native image**, service IDs must be declared explicitly via `@LoadBalancerClient` or **`spring.cloud.loadbalancer.eager-load.clients`** to aid configuration analysis. This is an **AOT metadata generation requirement**, not a guarantee all clients will automatically hold warm connections.

Never alter global lazy initialization, AOT configs, or all service ID lists solely to shave a few initial calls; verify whether your app targets JVM/JIT or native image and check exact compatibility requirements.

## 21. Exercises: Identifying the Right Warm-Up Type

### 21.1. Scenario A: First Call to inventory-service Is Slow

~~~text
Order app is already ready
Call #1 inventory-service: 640 ms
Call #2 inventory-service: 42 ms
Call #1 payment-service:   610 ms
Call #2 payment-service:    51 ms
~~~

**Question:** Which property helps reduce per-service-ID lazy context loading?

**Answer:** Declare `inventory-service` and `payment-service` in **`spring.cloud.loadbalancer.eager-load.clients`**. However, there is not enough data yet to claim the **entire** gap will disappear, because TCP/TLS and backend work may account for most of the latency.

### 21.2. Scenario B: WebClient Called HttpClient.warmup()

~~~text
Event loop/hostname resolver initialized
No HTTP request has been sent to inventory-a:8443 yet
~~~

**Question:** Are TCP and TLS connections to Inventory warm yet?

**Answer:** **Cannot conclude they are warm.** Reactor Netty's `warmup()` API initializes client resources without sending requests to `inventory-a`. The first real HTTP call may still perform DNS resolution, TCP connect, and TLS handshake.

### 21.3. Scenario C: Three Instances, Only One Probe

~~~text
Discovery: [A, B, C]
LoadBalancer picks B for GET /internal/warmup
~~~

**Question:** Are connections to A and C warmed?

**Answer:** **No guarantee.** The probe only proves a request reached B and may keep a connection to B in the pool. When live traffic selects A or C, the transport may need to open new connections.

### 21.4. Scenario D: Calling Warm-Up Inside a Feign Client Constructor

**Question:** What is the risk?

**Answer:** Feign proxies, contexts, or dependencies may not be initialized yet, leading to lifecycle errors; Spring Cloud OpenFeign advises against calling clients during bean initialization. Move it to a post-context-refresh hook such as `ApplicationRunner` with proper timeouts and policies.

### 21.5. Scenario E: Warm-Up Increases Startup Time

Suppose before tuning, startup is **2,000 ms** and first call is **700 ms**. After tuning, startup is **2,400 ms** and first call is **180 ms**.

**Question:** Should this be deployed?

**Hint:** First call dropped by 520 ms while startup grew by 400 ms; this trade-off may be worthwhile if first-request SLOs are critical and rollouts fit within readiness budgets. Measure multiple times, check concurrency, and weigh overall UX/cost—there is no universal "always better" rule from two numbers alone.

## 22. Cold-Start and Warm-Up Verification Checklist

- [ ] Clarified whether measuring startup, first logical call, or first connection to an origin.
- [ ] Collected pre-warm-up baseline metrics, including P50/P95/P99 across multiple process restarts.
- [ ] Distinguished Spring Cloud LoadBalancer child contexts from HTTP client resources.
- [ ] Listed exact service IDs in `eager-load.clients` when early initialization is needed.
- [ ] Not treating eager-loaded contexts as TCP/TLS preconnect.
- [ ] `ServiceInstanceListSupplier` has appropriate caching/health checks without making data excessively stale.
- [ ] `RestClient`/`RestTemplate`/Feign HTTP engines and connection pools are intentionally reused.
- [ ] Not creating a new `HttpClient`/connection manager per HTTP request.
- [ ] With Reactor Netty, `warmup()` is subscribed to, executed on a startup thread, and targets the exact `HttpClient` used by `WebClient`.
- [ ] Never calling `block()` on the WebFlux event loop.
- [ ] If using HTTP probes, endpoints are safe/idempotent, authenticated, and strictly time-bounded.
- [ ] Warm-up never invokes order-creating POSTs, payments, writes, or side-effecting actions.
- [ ] Not assuming a single GET probe connected to every `ServiceInstance`.
- [ ] Readiness policy chosen deliberately, avoiding circular startup dependencies.
- [ ] Never calling Feign clients inside constructors or `@PostConstruct` before contexts are ready.
- [ ] Warm-up enforces concurrency/retry bounds and prevents rollout traffic storms.
- [ ] Measuring actual connection reuse/handshakes, not just HTTP request counts.
- [ ] Tests separate fake `ExchangeFunction` unit tests from real Spring Cloud LoadBalancer integration tests.
- [ ] Accounted for re-cooling on instance scale-out, DNS TTLs, and pool idle eviction.
- [ ] Never disabling TLS/hostname verification solely to cut latency.
- [ ] Timeouts, retry budgets, health checks, and circuit breakers remain in place post-warm-up.
- [ ] Metrics exist for warm-up failures, first-call latency, pool pending, no-instance errors, and downstream latency.
- [ ] Never logging tokens, cookies, or sensitive payloads in probes/traces.
- [ ] Evaluated post-deployment impact on startup duration, CPU, memory, and connection costs.

## 23. Conclusion

**Cold start is not a single point along the request path.** A Spring Cloud LoadBalancer call can incur costs across many layers: JVM/Spring context, per-service-ID child contexts, discovery/caching/health, HTTP client resources, DNS, TCP/TLS, and the backend. These layers initialize and reuse across **different** lifecycles.

Two key mechanisms to remember:

1. **`spring.cloud.loadbalancer.eager-load.clients`** eagerly initializes child contexts for critical service IDs; **it does not automatically connect** to replicas.
2. **Reactor Netty `HttpClient.warmup()`** prepares event loops, resolvers, and native resources; **it does not automatically preconnect DNS/TCP/TLS** to each origin.

When true connection warm-up is required, send a **safe** HTTP request through the exact client, LoadBalancer, and transport used in production, and observe network/connection metrics. This optimization has trade-offs: longer startup, extra backend traffic, and no guarantee connections stay open forever.

The best design is to **measure the true bottleneck, warm up only what is necessary, maintain long-lived clients/pools, keep sensible readiness policies, and test both first calls and steady state**. Warm-up improves first-request responsiveness, yet never replaces accurate discovery, timeouts, safe retries, or system resilience.

## 24. References

- [Spring Cloud LoadBalancer – Reference](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): per-service-ID child `ApplicationContext`, eager loading, `ServiceInstanceListSupplier`, and caching.
- [Spring Cloud Commons – Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html): `spring.cloud.loadbalancer.eager-load.clients` and cache TTL.
- [Spring Cloud Commons – Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): `@LoadBalanced` `RestTemplate`, `RestClient`, and `WebClient` builders.
- [Reactor Netty – HTTP Client Reference](https://projectreactor.io/docs/netty/release/reference/http-client.html): `HttpClient` eager initialization/warmup, DNS, pools, TCP, TLS, and timeouts.
- [Reactor Netty – HttpClient Javadoc](https://projectreactor.io/docs/netty/release/api/reactor/netty/http/client/HttpClient.html): `HttpClient.warmup()` and exact resources initialized.
- [Spring Boot – SpringApplication Events and Listeners](https://docs.spring.io/spring-boot/reference/features/spring-application.html): `ApplicationRunner`, `ApplicationReadyEvent`, and `ReadinessState.ACCEPTING_TRAFFIC`.
- [Spring Boot – Application Availability](https://docs.spring.io/spring-boot/reference/features/spring-application.html#features.spring-application.application-availability): readiness/liveness states and lifecycles.
- [Spring Boot – Calling REST Services](https://docs.spring.io/spring-boot/reference/io/rest-client.html): HTTP client builders and `RestClient`/`RestTemplate`/`WebClient` configuration.
- [Spring Framework – WebClient Configuration](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html): `ReactorClientHttpConnector` and client configuration.
- [Spring Framework – WebClient Testing](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-testing.html): mock HTTP servers for testing outbound `WebClient`.
- [Spring Cloud OpenFeign – Reference](https://docs.spring.io/spring-cloud-openfeign/reference/spring-cloud-openfeign.html): named client contexts, eager attribute resolution, and warning against calling Feign during bean initialization.
- [Spring Framework – REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): `RestClient`, `RestTemplate`, and `ClientHttpRequestFactory`.
- [Reactor – Testing](https://projectreactor.io/docs/core/release/reference/testing.html): `StepVerifier` and subscription in unit/integration tests.
- [Micrometer – Concepts](https://docs.micrometer.io/micrometer/reference/concepts.html): timers, counters, and controlled latency measurement.
