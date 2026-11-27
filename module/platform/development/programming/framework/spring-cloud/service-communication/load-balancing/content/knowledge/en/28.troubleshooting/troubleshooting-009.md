# Pool exhaustion, blocked event loops, and spiking latency

A system using **Spring Cloud LoadBalancer** can pick the exact right `ServiceInstance`, yet requests still take seconds, time out, or fail in bursts. Three distinct causes are frequently confused:

1. **HTTP connection pool exhaustion:** requests wait for a free connection before being sent.
2. **Blocked event loop:** one or more threads responsible for I/O and reactive callbacks are stalled by blocking or long CPU work, slowing down many unrelated requests.
3. **Genuine downstream latency spike:** backends, databases, DNS, TLS, network, or proxies slow down; connections are held longer and can **cause** pool saturation.

All three can occur together: a slow downstream holds connections longer; the pool begins queuing; retries multiply traffic and push latency up; and if blocking code also sits on the event loop, things deteriorate further. **Increasing `maxConnections` is not a universal cure.**

This lesson belongs to the **Troubleshooting** chapter of the Spring Cloud LoadBalancer module. You will learn how to pinpoint the slow stage along the call path from service ID to real instance; inspect `RestClient`/Apache HttpClient 5, `WebClient`/Reactor Netty, and OpenFeign; detect blocking in Spring WebFlux; and design load tests to prove the root cause before tuning configuration.

> Pool/timeout/RPS numbers in this lesson are **lab values for reproduction**, not default production configs. APIs can vary across Spring Boot, Spring Cloud, Apache HttpClient, and Reactor Netty versions; use a compatible release train/BOM.

## 1. Locate pools and event loops on the call path

~~~mermaid
flowchart TD
    A["Caller calls http://catalog-service"]
    B["Spring Cloud LoadBalancer<br/>picks ServiceInstance"]
    C["Physical address<br/>catalog-a:8081"]
    D{"Free connection<br/>or allowed to open new?"}
    E["Wait in pool acquisition"]
    F["DNS / TCP / TLS if needed"]
    G["Send request / wait for response"]
    H["Read body / decode"]
    I["Operation completes"]
    J["Pool pending timeout<br/>or pending queue full"]
    K["Connect / response timeout"]
    A --> B --> C --> D
    D -->|"No"| E
    E -->|"Timed out / full"| J
    E -->|"Slot granted"| F
    D -->|"Yes"| F
    F -->|"Error"| K
    F --> G
    G -->|"Timeout"| K
    G --> H --> I
~~~

**Spring Cloud LoadBalancer performs selection**; it does not own connection leasing or I/O execution. After picking an instance, the HTTP client must still:

- Lease a connection from the pool or open a new one.
- Connect to the instance's host/port.
- Send the request, wait for server processing, and read the response.
- Decode the body per the HTTP/JSON contract.
- Return the connection to the pool once the response lifecycle finishes properly.

In `WebClient` with Reactor Netty, much of the I/O and callback execution runs on **event-loop threads**. If a callback runs `Thread.sleep`, blocking JDBC, or heavy CPU work on the event loop, other connections and requests sharing that thread slow down even when the pool is **not** exhausted.

### Do not conflate three kinds of queues

| Queue / resource | Example | What to observe |
|---|---|---|
| Connection pool | Waiting to lease an HTTP connection | `leased`/`pending`, active/idle, acquire duration |
| Thread or event loop | Tasks waiting for thread execution | Thread dumps, event-loop pending tasks/latency, blocked stacks |
| Downstream/backend | Requests reached the server yet process slowly | Server latency, DB pool, queue depth, tracing |

All three can grow together, yet **their fixes differ**. An undersized pool queues before requests leave; a slow backend queues after requests arrive; a blocked event loop delays both reading responses and releasing connections.

## 2. Symptom matrix: which evidence to check first?

| Symptom | Primary suspect | Data to confirm |
|---|---|---|
| Pool `leased≈max`, `pending` rising | Pool saturated or connections held too long | Pool stats **per route** and total |
| Pending acquire timeout, backend shows zero requests | Requests timing out waiting to lease a connection | Acquire-time metrics, pending queue, leased |
| Pool `leased` low yet HTTP is slow | Not current pool saturation; suspect DNS, backend, or event loop | Latency breakdown, thread dumps, tracing |
| Many WebClient calls slow down; `reactor-http-nio-*` threads stuck in `sleep`/JDBC | Event loop blocked | Multiple timed thread dumps, BlockHound/tests |
| Error rate rises when retries are enabled | Retry amplification | Operations vs. attempts, backend RPS, timeouts |
| Only one instance slow, others normal | Backend hot spot or route-specific issue | Breakdown by `ServiceInstance`, server metrics |
| Cache/discovery returns a dead instance | Stale candidate list | Instance selection, health/cache/registry |
| `Connection refused` error | No process listening on selected host/port | Selected URI, port, container health |
| TLS/`UnknownHost` before HTTP response | Network/DNS/TLS failure | Transport cause, physical URI |
| JSON decode error on status 200 | Contract or codec, not pool | Content-Type, controlled schema/cause check |

**Do not rely solely on HTTP 500, p99 latency, or the word “timeout” in an exception.** Verify whether requests reached the backend, leased a connection, and which threads spent the time.

## 3. Understand “pool exhaustion” accurately

A connection pool holds two basic sets of objects:

- **Leased connections:** currently borrowed and not yet finished with their request/response lifecycle.
- **Reusable connections:** idle/available, subject to keep-alive, expiry, and socket state.

When all eligible connections are busy and the pool hits its cap, new requests **wait in the acquire queue**, are rejected if the pending queue is full, or time out if waiting too long.

~~~text
Requests -> [HTTP pool acquire queue] -> [Leased connections] -> Backend
                    |                       |
               wait/timeout             active requests
~~~

### Timeouts that are not equivalent

| Timeout / budget | Measured from where? | Example cause |
|---|---|---|
| **Pool acquisition / connection request timeout** | Waiting for pool to grant a connection | All connections busy, deep pending queue |
| **Connect timeout** | Opening TCP to physical endpoint | Unreachable IP/port, network fault |
| **TLS handshake timeout** | Completing TLS handshake per transport | TLS/network/certificates |
| **Response / read timeout** | Waiting for data/response per HTTP client semantics | Slow backend, network stall |
| **Overall operation/deadline** | Entire business call across all stages and attempts | Pool wait + connect + response + retries |
| **Backend timeout** | Downstream/DB or internal proxy | DB contention, overload |

For instance, a client setting `responseTimeout=2s` does not guarantee every operation finishes within 2 seconds if it previously **waited 1 second in the pool** or ran multiple attempts. Enforce a separate end-to-end deadline when total elapsed time must be capped.

### Connection leaks can look like bad pool sizing

If response streams are not consumed/closed per the HTTP client contract, connections may fail to return to the pool. When `leased` climbs and never drops even after traffic stops, suspect response lifecycle/stream leaks before raising `maxConnections`.

With standard Spring `RestClient.retrieve().body(...)`, the framework manages reading/closing responses. With lower-level APIs, streaming, or manual Apache/Feign clients, code must carefully consume/close responses. Never read a raw response partially and abandon it without managing resource lifecycle.

## 4. Mental formula for concurrency and capacity

A helpful steady-state approximation is **Little's Law**:

\[
L \approx \lambda \times W
\]

Where:

- `L`: average number of concurrent requests in a given stage.
- `λ`: average throughput, in requests/second.
- `W`: average time each request spends in that stage, in seconds.

If 100 requests/second hold a connection for about 0.4 seconds, concurrent **connections held average around 40**. This is not an automatic formula for picking `maxConnections=40`: you must account for bursts, per-instance distribution, HTTP protocol, pool reuse, backend capacity, and stages that do not hold connections.

More importantly, **holding RPS constant while response time rises** multiplies concurrent requests. Moving from 0.1 seconds to 0.8 seconds multiplies the connections needed for the same workload, even with zero “connection leaks.”

### Impact of one slow instance

Suppose `catalog-service` has two `ServiceInstance` replicas:

~~~text
catalog-a:8081 -> processes in 80 ms
catalog-b:8081 -> processes in 900 ms
~~~

Round robin routes requests to both. Requests hitting B hold connections much longer, saturating **route B's** pool/queue first. **Switching random to round robin or vice versa does not fix B being slow.**

To diagnose properly, break metrics down **per instance or physical route**, rather than relying on one aggregate service-ID latency chart.

## 5. Apache HttpClient 5: distinguish total pool from per-route pool

For blocking `RestClient` using Apache HttpClient 5, `PoolingHttpClientConnectionManager` manages the connection pool. Two key caps apply:

- `maxConnTotal`: total connection cap managed by **one connection manager**.
- `maxConnPerRoute`: cap per `HttpRoute`, usually tied to scheme/host/port (and proxy/tunnel depending on config).

Layout:

~~~text
catalog-service
  -> catalog-a:8081  [HttpRoute A]  max per-route: 10
  -> catalog-b:8081  [HttpRoute B]  max per-route: 10

Shared connection manager:
  maxConnTotal: 15
~~~

In this example, you **cannot** simultaneously hold 10 connections to A and 10 to B in the same manager when the total cap is 15. If A holds 10, B can obtain at most 5 until connections are released.

With Spring Cloud LoadBalancer, **the service ID is not the pool route**. LoadBalancer resolves to a physical URI first; the HTTP manager sees distinct routes per instance. When an HTTP proxy is present, verify how routes are keyed in the actual transport.

### Core metrics of Apache's manager

| Metric | Meaning | When abnormal |
|---|---|---|
| `getLeased()` | Connections leased and still in use | Sustained near `getMax()` |
| `getAvailable()` | Idle connections eligible for reuse | Low during peak load is inconclusive alone |
| `getPending()` | Requests waiting to lease a connection | Sustained growth signals queuing |
| `getMax()` | Corresponding pool cap | Inspect both total **and** per-route |

`getTotalStats()` returns a snapshot. To pinpoint which route is bottlenecked, read stats **per `HttpRoute`**, or use transport/HTTP client metrics where supported by your framework/version.

## 6. Observable RestClient configuration with connection manager

The following example illustrates **Java 17+, Spring Framework 6.1+, and Apache HttpClient 5** with matching dependencies:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.cloud:spring-cloud-starter-loadbalancer")
    implementation("org.apache.httpcomponents.client5:httpclient5")
}
~~~

Sample configuration:

~~~java
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
class CatalogRestClientConfiguration {

    @Bean("catalogConnectionManager")
    PoolingHttpClientConnectionManager catalogConnectionManager() {
        return PoolingHttpClientConnectionManagerBuilder.create()
                .setMaxConnTotal(12)
                .setMaxConnPerRoute(6)
                .build();
    }

    @Bean(value = "catalogApacheClient", destroyMethod = "close")
    CloseableHttpClient catalogApacheClient(
            @Qualifier("catalogConnectionManager")
            PoolingHttpClientConnectionManager manager) {

        RequestConfig requests = RequestConfig.custom()
                .setConnectionRequestTimeout(
                        Timeout.ofMilliseconds(300))
                .setResponseTimeout(
                        Timeout.ofSeconds(2))
                .build();

        return HttpClients.custom()
                .setConnectionManager(manager)
                .setDefaultRequestConfig(requests)
                .evictExpiredConnections()
                .build();
    }

    @Bean("catalogLbBuilder")
    @LoadBalanced
    RestClient.Builder catalogLbBuilder(
            @Qualifier("catalogApacheClient")
            CloseableHttpClient apache) {

        return RestClient.builder()
                .requestFactory(
                        new HttpComponentsClientHttpRequestFactory(
                                apache));
    }

    @Bean("catalogRestClient")
    RestClient catalogRestClient(
            @Qualifier("catalogLbBuilder")
            RestClient.Builder builder) {

        return builder
                .baseUrl("http://catalog-service")
                .build();
    }
}
~~~

**Keep these distinct:**

- `@LoadBalanced` lets Spring Cloud select an instance for `catalog-service`.
- `PoolingHttpClientConnectionManager` manages connections to the chosen target; it **does not select instances**.
- `setMaxConnTotal(12)` and `setMaxConnPerRoute(6)` are **deliberately low lab thresholds** so pending queues are easy to observe.
- `connectionRequestTimeout=300ms` bounds waiting for a pool lease; `responseTimeout=2s` bounds waiting for responses per Apache HttpClient 5.
- **Connect timeouts** and TLS/operation deadlines must be configured separately if needed; never lump them into one property.
- The connection manager is shared across HTTP calls going through `catalogApacheClient`; accidentally creating a new HttpClient/manager per request defeats pooling.

In real Spring Boot apps, the Boot-managed builder may carry observation, message converters, SSL, and customizers. When replacing it with raw `RestClient.builder()`, verify important customizations are not lost. This example shows only the minimal pipeline to analyze pooling.

### Reading pool stats safely

~~~java
import org.apache.hc.core5.pool.PoolStats;

void reportPool(
        PoolingHttpClientConnectionManager manager) {
    PoolStats stats = manager.getTotalStats();

    // Export to metrics/Micrometer rather than printing per request.
    System.out.printf(
            "leased=%d available=%d pending=%d max=%d%n",
            stats.getLeased(),
            stats.getAvailable(),
            stats.getPending(),
            stats.getMax());
}
~~~

This is an **illustrative helper**, not a metric emitted automatically by Spring Cloud. In production, poll snapshots periodically into telemetry; avoid `println` or per-request logs that add I/O overhead.

## 7. When Apache's pool runs dry: reading the numbers

Two example scenarios:

| Checkpoint | Total leased | Total pending | Available | Assessment |
|---|---:|---:|---:|---|
| Baseline | 3 / 12 | 0 | 4 | No total saturation seen |
| Peak hour | 12 / 12 | 35 | 0 | Manager saturated; requests queuing |
| After traffic drops | 12 / 12 | 30 | 0 | Suspect held response/streams or downstream still stuck |
| Once cleared | 0 / 12 | 0 | 12 | Pool returns to normal reuse |

These are **synthetic sample numbers**. Measure real values via your manager/metrics during lab runs, and **never conclude “leak” from a single snapshot**.

### Check per-route limits specifically

If total `leased=6/12`, yet `catalog-a` shows `leased=6/6` and A's pending queue grows, the **per-route pool for A** is exhausted even though **total pool headroom remains**. Raising `maxConnTotal` alone will not lift A's `maxConnPerRoute` cap.

A single route can become overloaded when:

- Only one instance passes discovery/health/zone filters.
- Other instances fail hint/region criteria, shrinking candidates.
- Sticky sessions or weighted policies intentionally concentrate traffic.
- One instance responds slowly, holding connections longer.
- Retry configs keep picking the same instance.
- A proxy funnels multiple logical targets through one upstream bottleneck instead of “one route per backend.”

**Never relax strict region/tenant filters** just to tap instances outside allowed zones; scale capacity inside valid zones or fail in a controlled manner.

## 8. Reactor Netty: ConnectionProvider is not a global service-ID pool

With `WebClient` backed by Reactor Netty, `ConnectionProvider` manages HTTP connections per **remote host** (host + port) and pool policy. Key parameters:

- `maxConnections`: connection cap **per pool**; in typical HTTP/1.1 usage, pools are per remote host. This is **not a single JVM-wide cap across all service IDs**.
- `pendingAcquireMaxCount`: cap on queued acquisition waiters; exceeding it rejects requests.
- `pendingAcquireTimeout`: max duration one request may wait to acquire a connection.
- `maxIdleTime`, `maxLifeTime`: connection lifetime bounds to mitigate stale sockets per environment.
- `metrics`: enables provider metrics collection when Micrometer is present and wired.

With Spring Cloud LoadBalancer:

~~~text
catalog-service -> catalog-a:8081  -> Reactor Netty pool A
               -> catalog-b:8081  -> Reactor Netty pool B
               -> catalog-c:8081  -> Reactor Netty pool C
~~~

If you set `maxConnections(16)` across three remote hosts, each pool can hold connections, so total physical connections **are not automatically capped at 16**. Account for host count, caller replica count, HTTP/2 multiplexing, connection sharing, proxies, and OS limits.

### Do not hardcode version assumptions

Default pool sizes, queues, and timeouts vary across Reactor Netty versions, system properties, and custom builders. Reactor Netty docs describe default per-remote-host pools and the properties above; **always inspect effective values on your running stack** instead of relying on a number from a blog post.

## 9. Configuring WebClient with explicit pool, queue, and timeout bounds

Spring WebFlux / Reactor Netty example:

~~~java
import java.time.Duration;

import io.netty.channel.ChannelOption;
import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
class CatalogWebClientConfiguration {

    @Bean(value = "catalogPool", destroyMethod = "dispose")
    ConnectionProvider catalogPool() {
        return ConnectionProvider.builder("catalog-http")
                .maxConnections(8)
                .pendingAcquireMaxCount(16)
                .pendingAcquireTimeout(
                        Duration.ofMillis(300))
                .maxIdleTime(Duration.ofSeconds(20))
                .metrics(true)
                .build();
    }

    @Bean("catalogLbWebClientBuilder")
    @LoadBalanced
    WebClient.Builder catalogLbWebClientBuilder(
            @Qualifier("catalogPool")
            ConnectionProvider pool) {

        HttpClient client = HttpClient.create(pool)
                .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 1500)
                .responseTimeout(Duration.ofSeconds(2));

        return WebClient.builder()
                .clientConnector(
                        new ReactorClientHttpConnector(client));
    }

    @Bean("catalogWebClient")
    WebClient catalogWebClient(
            @Qualifier("catalogLbWebClientBuilder")
            WebClient.Builder builder) {
        return builder
                .baseUrl("http://catalog-service")
                .build();
    }
}
~~~

Values like `maxConnections=8`, pending=16, and 300ms exist to **reproduce saturation in the lab**. `metrics(true)` requires matching Micrometer/metrics integration; omit it if testing functionality without telemetry configured.

**Do not confuse:**

- `@LoadBalanced WebClient.Builder` resolves the **service ID**.
- `ReactorClientHttpConnector` supplies the HTTP client/connection provider.
- `pendingAcquireTimeout` limits waiting for a **connection**, not waiting for the server to return a body.
- `responseTimeout` does not automatically bound the whole operation across retries.
- `ConnectionProvider` has a lifecycle and must be disposed on shutdown; Spring invokes the destroy method on the bean above.

If your app uses global Reactor Netty resources or Spring Boot WebClient auto-configurations, verify that declaring a custom client does not drop existing observation/tracing/SSL configurations. Never create a fresh `ConnectionProvider` per HTTP call.

## 10. Pending acquire errors must be classified separately from HTTP statuses

When acquiring a connection fails, requests fail **before any HTTP traffic goes to the backend**. Thus:

~~~text
HTTP client:
  -> failed to lease a connection
  -> pool acquisition timeout / pending queue full
  -> no real downstream HTTP 429/503 occurred
~~~

Several exceptions relate to pooling, though exact names vary by version/transport:

| Client stack | Exception/symptom group | What NOT to infer |
|---|---|---|
| Apache HttpClient 5 | Connection request/pool lease timeout or exception in cause chain | Do not assume backend returned 503 |
| Reactor Netty | Pending acquire timeout or pool pending limit reached | Do not conclude server overload purely from acquire failures |
| WebClient | May wrap transport errors in `WebClientRequestException` | Cannot classify solely by outer wrapper |
| OpenFeign + HC5 | Feign/HTTP client exception wrapping pool lease failure | Do not assume wrong URL/discovery |

When no HTTP response arrived, logs/metrics must distinguish `httpStatus=none` from an HTTP status returned by your app to callers. Backend access logs showing **zero requests** support this, while still checking proxies/gateways and log coverage.

### Large pending queues do not add throughput

Long queues force users to wait longer, consume memory, and inflate tail latency. They cannot exceed backend throughput or active connection processing capacity.

Never use `pendingAcquireMaxCount(-1)` or infinite timeouts to “fix” saturation. Unbounded queues turn brief spikes into prolonged backlogs.

## 11. What is the WebFlux event loop and how dangerous is blocking it?

In reactive HTTP apps on Reactor Netty, a small fixed pool of **event-loop threads** handles network events and callbacks. They excel when work is non-blocking and completes quickly.

Broken callback example:

~~~java
import reactor.core.publisher.Mono;

Mono<ProductDto> badPipeline(WebClient client) {
    return client.get()
            .uri("/products/42")
            .retrieve()
            .bodyToMono(ProductDto.class)
            .map(dto -> {
                try {
                    Thread.sleep(400); // ILLUSTRATING THE BUG ONLY
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException(ex);
                }

                return dto;
            });
}
~~~

When the `map` callback executes on an event-loop thread, `Thread.sleep` stalls that thread for 400ms, delaying all other events scheduled on it. Under concurrent load, p95/p99 spikes even when the backend is fast.

Similar risky operations:

- `Thread.sleep(...)`, `Future.get()`, `CountDownLatch.await()`.
- Blocking JDBC/JPA or blocking HTTP clients inside reactive callbacks.
- Synchronous file I/O or blocking SDK calls directly on the event loop.
- Heavy CPU computation not offloaded from the I/O scheduler.
- Contended synchronized locks held for long durations.
- Calling `block()` on `reactor-http-nio-*` threads; Reactor throws an error stating blocking is unsupported on that thread.

**Not all WebClient slowness comes from blocking the event loop.** An async request waiting on a slow backend can still take seconds while the event loop sits idle. Gather thread/CPU/metric evidence.

### Typical signs

- Multiple unrelated endpoints experience simultaneous tail-latency spikes.
- Thread dumps show `reactor-http-nio-*`, `reactor-http-epoll-*`, or similar threads stuck in blocking code.
- Event-loop task latency/pending tasks rise while processed event rates drop.
- Backends already sent responses yet the caller is slow to read/complete them.
- `Pool pending` may rise **secondarily** because connections are not freed promptly.

Exact thread names and metrics depend on Reactor Netty, runtime, and event-loop implementation.

## 12. Detect event-loop blocking with stack traces and experiments

To tell event-loop blocking apart from a slow backend:

1. Capture **two or more thread dumps** spaced slightly apart while slowness is happening.
2. Inspect Reactor Netty threads and active stack frames.
3. Look for `Thread.sleep`, blocking JDBC sockets, blocking file I/O, or lock contention on those threads.
4. Correlate timestamps with tracing: had the backend already finished its response?
5. Compare latency on a trivial in-memory reactive endpoint; if it also spikes, suspect caller-side scheduling/event-loop contention.
6. Use BlockHound in tests where appropriate to detect blocking APIs on non-blocking threads.

Command to capture a thread dump where **JDK tools are available**:

~~~powershell
jcmd 12345 Thread.print
~~~

Replace `12345` with the target JVM PID. If the container ships only a minimal JRE without `jcmd`, use JVM observability tools, JFR, a diagnostic image, or an authorized sidecar per environment policy. Do not assume shell access to every production container, and never post full thread dumps containing sensitive data to public channels.

### BlockHound is not the sole proof

BlockHound catches many blocking calls when properly installed in a **test runtime** with a compatible JDK/agent, yet not every blocking call or tight CPU loop is flagged. Passing tests with zero BlockHound violations **does not prove** the event loop is completely safe.

## 13. Offload blocking work off the event loop properly

If you must invoke a blocking repository/SDK from a reactive pipeline, wrap it in a lazily executed publisher and schedule it onto an appropriate scheduler:

~~~java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

class ProductLookup {

    private final BlockingProductRepository repository;

    ProductLookup(BlockingProductRepository repository) {
        this.repository = repository;
    }

    Mono<ProductDto> find(long id) {
        return Mono.fromCallable(
                    () -> repository.findById(id))
                .subscribeOn(Schedulers.boundedElastic());
    }
}
~~~

`BlockingProductRepository` is an illustrative interface for a blocking dependency, not a built-in Spring class. `fromCallable` defers execution until subscription; `subscribeOn(Schedulers.boundedElastic())` runs the repository call on a scheduler built for bounded blocking work.

**Wrong way:**

~~~java
Mono<ProductDto> wrong(long id) {
    ProductDto result = repository.findById(id); // blocks IMMEDIATELY
    return Mono.just(result)
            .subscribeOn(Schedulers.boundedElastic());
}
~~~

In the broken snippet, the repository call already executed **before the scheduler was applied**.

### boundedElastic is not an infinite resource

- The scheduler enforces **thread and task queue caps** per Reactor version and configuration.
- If blocking workload exceeds capacity over time, `boundedElastic`'s queue also saturates.
- Using `boundedElastic` does not replace timeouts, bulkheads, backpressure, DB pool sizing, or non-blocking drivers.
- For long/CPU-heavy work, use a dedicated worker pool or async job pattern instead of dumping everything onto the event loop.

Whenever a dependency offers a genuine reactive/non-blocking driver, prefer it over infinitely wrapping blocking calls.

### Bound concurrency when fanning out downstream

~~~java
Flux<ProductDto> results =
        Flux.fromIterable(productIds)
                .flatMap(id ->
                        catalogWebClient.get()
                                .uri("/products/{id}", id)
                                .retrieve()
                                .bodyToMono(ProductDto.class),
                        8 // At most 8 concurrent inner subscriptions here
                );
~~~

The number 8 is an **illustrative bound**, not a universal policy. It prevents a single business request from firing hundreds of concurrent HTTP calls and flooding connection pool queues. Also add overall deadlines, error/cancellation handling, and application-wide concurrency controls when many upstream requests run concurrently.

## 14. Separate Spring MVC threads from WebFlux event loops

Not every app using `RestClient`/`WebClient` runs requests on a Reactor Netty event loop.

| Caller model | Primary hazard |
|---|---|
| Spring MVC + blocking `RestClient` | Servlet worker threads tied up waiting on HTTP or pools; thread exhaustion |
| Spring MVC + `WebClient.block()` on servlet thread | Blocks servlet thread; Reactor Netty still performs underlying network I/O |
| Spring WebFlux + proper reactive `WebClient` | Efficient event loop as long as callbacks stay short and non-blocking |
| Spring WebFlux + blocking JDBC in controller/callback | Blocks event loop or scheduler unless offloaded |
| Blocking OpenFeign inside reactive handler | Can block event loop if called directly |

**Do not call `block()` “event-loop blocking” if it actually runs on a servlet thread**; it can still exhaust servlet threads, though the bottleneck and resource pool differ.

For Spring MVC, monitor `server.tomcat.threads.busy`/server thread pools per server/version, HTTP pending pools, and downstream latency. For WebFlux, monitor Netty event loops, reactive operators, and thread dumps.

Never rewrite an entire application to WebFlux just to avoid sizing a `RestClient` connection pool. Reactive stacks do not eliminate resource limits or slow downstreams.

## 15. LoadBalancer can create pool hotspots even when discovery works

LoadBalancer picks an instance from candidates. If the candidate list narrows, traffic concentrates onto fewer physical routes:

~~~text
Before:
catalog-service -> A, B, C, D  (4 physical hosts)

After health/zone/filter:
catalog-service -> A          (1 physical host)
~~~

If total throughput stays constant, A's `maxConnPerRoute` or Reactor Netty pool A's `maxConnections` can become a bottleneck.

Reasons the candidate set narrows:

- Zone preference, hints, subsets, or custom filters.
- Strict residency/tenant policies.
- Discovery registry only lists one instance.
- Health checks dropped slow/dead instances (subject to fallback semantics).
- Stale caches or lagging registrations.
- Sticky sessions or weights concentrating traffic.

### The issue may be the selected instance rather than the algorithm

Measure together:

1. `serviceId` and **candidate count** post-supplier/filter.
2. `selectedInstance` and selection counts per instance.
3. Active/pending connections per physical remote host/route.
4. Backend RPS, latency, and error rates per replica.
5. Retry attempts and instance-switching rates.

**Never relax strict zone/region filters** to relieve pending queues if they enforce safety/compliance boundaries. Scale capacity within allowed zones, shed load safely, or fail closed.

## 16. How retries and timeouts worsen pool congestion

Suppose 100 logical operations/sec arrive, each allowing up to 2 retries after the initial attempt. During widespread backend errors, HTTP attempts can climb toward **300 attempts/sec** when every retry fires.

~~~mermaid
flowchart TD
    A["Backend starts slowing down"]
    B["Connections held longer"]
    C["Pool leased hits max; pending rises"]
    D["Acquisition/response timeouts"]
    E["Retries multiply attempt rate"]
    F["Pressure on pool/backend keeps growing"]
    G["p95/p99 latency and error rate spike"]
    A --> B --> C --> D --> E --> F --> C
    C --> G
~~~

This is an illustrative feedback loop; actual rates depend on which layers retry, which exceptions trigger retries, deadlines, backoff, and request body replayability.

### Check all retry layers

- Spring Cloud LoadBalancer retries (when corresponding dependencies/configs are active).
- OpenFeign `Retryer` or other resilience libraries.
- Reactor `retryWhen`.
- Gateway/mesh/client SDK retries.
- User-facing callers or job runners re-invoking the entire operation.

When two retry layers are active together, attempts **multiply** rather than add. Align on one attempt budget and an **overall deadline**.

### Sensible timeouts do not mean shortest possible

Timeouts that are too long tie up connections/threads and bloat queues. Timeouts that are too short trigger false failures, retry storms, and oscillation. Base timeouts on SLOs, real latency distributions, backend capacity, and business semantics—separating pool acquire, connect, response, and overall operation timeouts.

**Do not automatically retry pool acquisition timeouts** without load shedding and idempotency: the request may not have been sent yet, yet immediate retries still add pressure to the queue.

## 17. Break latency down by stage instead of staring at one p99

A proper trace should answer:

~~~text
logical operation start
    -> load balancer selection
    -> wait for HTTP pool slot
    -> DNS / connect / TLS
    -> request sent
    -> backend handling
    -> first response byte
    -> body read / decode
    -> business continuation
logical operation end
~~~

| Metric / span | What it reveals |
|---|---|
| LB selection duration | Whether discovery/cache/supplier/choose is slow |
| Pool acquire wait | Whether requests queue waiting for a connection |
| Connect/TLS time | How long opening new connections takes |
| HTTP request-to-response | Whether downstream/server/network is slow |
| Decode/body read | Large payloads, streaming, codec/CPU bottlenecks |
| Event-loop task latency | Scheduling delays or callback blocking |
| Total operation duration | How long the user/caller actually waited |
| Retry attempts and backoff | How much retries multiplied total latency |

**Never add individual stage percentiles** to estimate overall operation p99: distributions and correlations differ. Measure the true total span and use stage spans to attribute contributions.

### Micrometer / Reactor Netty

With Micrometer wired, Reactor Netty can expose metrics such as:

~~~text
reactor.netty.connection.provider.active.connections
reactor.netty.connection.provider.idle.connections
reactor.netty.connection.provider.pending.connections
reactor.netty.connection.provider.pending.connections.time
~~~

Exact metric names, labels, and availability depend on Reactor Netty/Micrometer versions and enabled configuration. **Never assume these metrics exist automatically just because the Spring Cloud LoadBalancer starter is present.**

Never attach `remote.address`, raw URIs, user IDs, or ephemeral instance IDs with unbounded cardinality as metric tags. Apply appropriate whitelists/filters for your metrics backend.

## 18. Lab A: reproduce pool exhaustion with an intentionally slow backend

### 18.1. Test Spring MVC backend

Lab controller:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
class SlowCatalogController {

    @GetMapping("/lab/slow")
    String slow(@RequestParam(defaultValue = "600") long ms)
            throws InterruptedException {

        long capped = Math.max(0, Math.min(ms, 3000));
        Thread.sleep(capped); // LAB ONLY, intentionally slows server
        return "ok";
    }
}
~~~

Run two backend replicas on separate ports (e.g., 8081/8082), or just one replica to isolate per-route limits. This backend **intentionally uses Spring MVC worker blocking** to create a controlled response delay; never copy `Thread.sleep` into production.

### 18.2. Caller with a tiny pool

Adjust the lab settings in `CatalogRestClientConfiguration` from Section 6:

~~~java
.setMaxConnTotal(4)
.setMaxConnPerRoute(2)
~~~

and use:

~~~java
.setConnectionRequestTimeout(
        Timeout.ofMilliseconds(200))
.setResponseTimeout(Timeout.ofSeconds(2))
~~~

Expected behavior:

- If one instance receives 20 concurrent requests, at most 2 connections open to that route per config.
- Many requests wait for slots, and some expire in the acquire stage.
- The backend **does not necessarily receive all 20 requests**.
- `PoolStats.pending` climbs while that route's `leased` hits 2.
- Raising caller concurrency without adding capacity worsens p95/p99 and error rates.

### 18.3. Caller API

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;

@RestController
class PoolProbeController {

    private final RestClient catalog;

    PoolProbeController(
            @Qualifier("catalogRestClient") RestClient catalog) {
        this.catalog = catalog;
    }

    @GetMapping("/lab/probe")
    String probe() {
        return catalog.get()
                .uri("/lab/slow?ms=600")
                .retrieve()
                .body(String.class);
    }
}
~~~

Each request to `/lab/probe` is one logical operation calling downstream via LoadBalancer. With one or two instances, inspect the **selected route** and matching pool limits.

### 18.4. Load testing with k6

Sample script sending traffic to the **caller**, never directly to the backend:

~~~javascript
import http from "k6/http";
import { check } from "k6";

export const options = {
  scenarios: {
    saturation: {
      executor: "constant-arrival-rate",
      rate: 25,
      timeUnit: "1s",
      duration: "60s",
      preAllocatedVUs: 30,
      maxVUs: 80
    }
  },
  thresholds: {
    dropped_iterations: ["count==0"]
  }
};

export default function () {
  const response = http.get(
    "http://127.0.0.1:8080/lab/probe"
  );

  check(response, {
    "HTTP 200": (r) => r.status === 200
  });
}
~~~

This is an **illustrative workload, not measured results**. If the generator reports `dropped_iterations`, you cannot trust it sustained the intended RPS. If the app maps downstream errors to HTTP 500, `http_req_failed` also climbs; record caller-side error categories alongside actual backend request counts.

**Control comparison:** hold load constant while adding valid instances, changing server delay, or tuning pool caps. Watch leased/pending/acquire duration and latency. Never turn on retries while isolating the root cause.

## 19. Lab B: prove the event loop is blocked

Compare two `WebClient` pipelines:

### Bad pipeline (lab only)

~~~java
@GetMapping("/lab/reactive-bad")
Mono<String> bad() {
    return Mono.just("ok")
            .map(value -> {
                try {
                    Thread.sleep(300); // BLOCKS callback thread
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException(ex);
                }
                return value;
            });
}
~~~

When executed in Spring WebFlux/Reactor Netty on the event loop, the callback holds the event-loop thread. Under load, **concurrently** call another fast reactive endpoint to observe its tail latency spiking even though it touches no slow backend.

### Proper pipeline if blocking work must run

~~~java
@GetMapping("/lab/reactive-offloaded")
Mono<String> offloaded() {
    return Mono.fromCallable(() -> {
                Thread.sleep(300); // LAB ONLY
                return "ok";
            })
            .subscribeOn(Schedulers.boundedElastic());
}
~~~

The second snippet still runs a blocking task, yet **does not hold the event loop during sleep**; waiting shifts onto `boundedElastic`. Under very heavy load, `boundedElastic` can still saturate, so monitor queues and bound concurrency.

### Expectation matrix

| Experiment | Pool pending | Event loop | Symptom |
|---|---|---|---|
| Slow backend, tiny HTTP pool | Typically rises | Likely normal | Requests wait to acquire |
| Callback sleeps on event loop | May rise secondarily | Thread blocked | Many unrelated reactive endpoints slow down |
| Blocking offloaded, within capacity | Likely stable | Event-loop blocking drops | Event loop keeps serving other callbacks |
| Slow backend, generous pool | Likely low | Likely normal | High HTTP span / backend latency |
| Retry storm into slow backend | Rises rapidly | Implementation-dependent | Backend attempts/RPS climb |

**Never treat prediction tables as substitutes for measurement.** Run the same workload, capture thread dumps/metrics, and record real timings and test settings.

## 20. 10-step runbook when p95/p99 spikes suddenly

1. **Scope the impact:** all services or only `catalog-service`? One instance or all instances? Did it start after a deploy, scale event, or traffic spike?

2. **Check whether an instance was selected:** if `NO_INSTANCE`, troubleshoot discovery/filters first. If selected, record the physical endpoint category via allowed telemetry.

3. **Check total and per-route/host pools:** Apache leased/available/pending/max; Reactor active/idle/pending/acquire time. Do not look at one global number and miss a hot route.

4. **Inspect error causes:** pool wait, connect timeout, TLS, response timeout, HTTP 503, and decode errors are separate branches.

5. **Compare against the backend:** did requests reach the backend? How are backend latency, DB pools, CPU/GC, and queue depths?

6. **Inspect event loops and thread pools:** grab thread dumps/JFR during the spike; look for `block()`, `Thread.sleep`, JDBC/file I/O on event loops, or servlet worker saturation.

7. **Count logical requests vs. HTTP attempts:** are retries multiplying load and queues? Are multiple retry layers active simultaneously?

8. **Check membership changes:** did LoadBalancer shrink to one instance due to health/zone/strict filters or stale discovery? Is a proxy/gateway funneling multiple targets into one bottleneck?

9. **Apply controlled mitigations:** curb bursts/concurrency/retries, recover the backend, roll back blocking changes, bound queues/deadlines; only enlarge pools after confirming backend headroom.

10. **Test and monitor post-fix:** replay the same workload and compare p95/p99, pending, active, backend saturation, errors, and retry amplification; keep a rollback plan ready.

### Quick localization diagram

~~~mermaid
flowchart TD
    A["p95/p99 spike or timeout"]
    B{"Has ServiceInstance?"}
    C["Discovery / filters / cache"]
    D{"Pool pending rising<br/>and active at cap?"}
    E["Pool acquisition / per-route bottleneck"]
    F{"Event-loop thread<br/>blocked?"}
    G["Offload/remove blocking,<br/>bound concurrency"]
    H{"Backend latency /<br/>resources rising?"}
    I["Fix backend / DB / network"]
    J["Check DNS/TCP/TLS, retries,<br/>decode, locks, GC, and tracing"]
    A --> B
    B -->|"No"| C
    B -->|"Yes"| D
    D -->|"Yes"| E
    D -->|"No / inconclusive"| F
    F -->|"Yes"| G
    F -->|"No"| H
    H -->|"Yes"| I
    H -->|"No"| J
~~~

This is a **priority order**, not a claim that only one branch applies. A slow backend can be the root cause driving pool pending up, while a blocked event loop further delays returning connections.

## 21. Common wrong fixes

### 21.1. “Set maxConnections really high”

Huge connection limits can overwhelm backends, exhaust file descriptors/sockets, trigger handshake storms, and spike GC. If the backend is already slow from a small DB pool, opening more caller connections simply shifts queues from client to server. **Verify end-to-end capacity before raising limits.**

### 21.2. “Make the pending queue unlimited”

Unbounded queues make user requests miss deadlines and create memory pressure. Use **bounded queues + timeouts + backpressure/bulkheads** aligned with SLOs.

### 21.3. “Enable retries on every exception”

Retrying when pools are full or backends are overloaded creates an amplification loop. Never retry contract errors, never replay mutating calls without idempotency, and always enforce attempt/deadline budgets.

### 21.4. “Raise responseTimeout to fix pool wait errors”

If failures happen during **connection acquisition**, raising `responseTimeout` does not change acquire queue/wait limits. Check whether requests ever leased a connection and sent HTTP bytes.

### 21.5. “Using WebFlux means blocking is impossible”

Blocking JDBC/JPA or SDK calls placed directly in reactive callbacks still stall threads. Even `boundedElastic` has thread and queue caps.

### 21.6. “RestClient and WebClient share the same pool”

Never assume that: Apache HttpClient managers and Reactor Netty ConnectionProviders are separate infrastructures, and OpenFeign may use its own delegate. Identify the **actual HTTP client** and how many managers/providers exist in the process.

### 21.7. “No more 503s means congestion is gone”

If the app maps pool timeouts to HTTP 200 with empty fallbacks, HTTP error metrics drop while tail latency, data completeness, and business SLOs remain broken. Track both logical outcomes and error categories.

### 21.8. “Blame LoadBalancer when requests already reached the server”

LoadBalancer can contribute to hotspots via filters/weights/stickiness, yet slow servers/DBs, connection leaks, and event-loop blocking belong to other layers. Never swap round-robin without evidence of skewed distribution.

### 21.9. “Turn on wiretap/FULL logs to find the bug”

Feign `FULL`, Reactor Netty wiretap, and HTTP transport debug logs can record tokens, cookies, signed query URLs, and bodies. In production, rely on allowlisted metrics/tracing and thread dumps over secured channels.

## 22. Choose remediation matched to the confirmed cause

| Evidence-backed root cause | Priority remediation | What to verify post-change |
|---|---|---|
| Apache `maxConnPerRoute` too low, backend has headroom | Tune per-route and total sensibly; reuse pool | Pending drops; backend stays unsaturated |
| Reactor Netty pending acquire timing out | Bound fan-out, fix slow backend, consider pool/queue tuning | p95, pending, max connections per host |
| Slow backend/DB | Optimize DB/locks/cache, scale, or protect capacity | Server latency and caller pools improve together |
| Event loop blocked | Remove blocking or bounded-offload; optimize CPU | Thread dumps clear of event-loop blocking |
| Servlet workers tied up by blocking HTTP | Sensible timeouts, bulkheads, concurrency caps, capacity | Busy threads, request backlog, p95 |
| Retry amplification | Curb attempts, backoff/jitter, deadlines, and idempotency | Attempts / operations back under control |
| Unclosed response bodies | Fix response lifecycle; try-with-resources where needed | Leased returns to baseline after load |
| One hot instance from filter/stickiness | Audit policy and valid replica count | Per-instance traffic and pool stats |
| Stale cache picks dead instance | Tune discovery/health/cache and graceful shutdown | Invalid selections drop after refresh |
| Sudden traffic spike past SLO | Admission control, backpressure, circuit breakers/bulkheads, scale right tier | Bounded errors and clean recovery |

**Safety rule:** never “widen the instance set” in violation of data-residency/tenant policies, and never size pools past what downstream can handle. Roll out changes under control with before/after comparisons and a rollback plan.

## 23. Diagnostic verification checklist

- Clearly separated **LB selection**, **pool acquisition**, **TCP/TLS/HTTP**, **body decode**, and **event-loop/threads**?
- Know whether the actual client uses Apache HttpClient 5, Reactor Netty, an OpenFeign HTTP delegate, or another request factory?
- Have **leased/pending/available/max** metrics both globally and **per route** for HC5?
- Have **active/idle/pending/acquire time** metrics per remote host for Reactor Netty?
- Distinguished `connectionRequestTimeout`/`pendingAcquireTimeout` from connect and response timeouts?
- Confirmed requests actually reached the backend before concluding “the server is slow”?
- For WebFlux, checked for blocking calls in callbacks and event-loop thread dumps?
- For Spring MVC, checked servlet thread exhaustion instead of blaming event loops?
- Distinguished a slow backend causing pool saturation from an undersized pool as the primary cause?
- Tracked retry attempts/operation, overall deadlines, and retry-storm risk?
- Checked whether LoadBalancer filters/health/zones reduced valid physical routes?
- Checked response/stream lifecycles if `leased` fails to return to baseline?
- Accounted for HTTP/2 multiplexing, proxies, and per-host pools before converting RPS into connection counts?
- Ran load tests **through the caller** and reported only actual measured numbers?
- Applied concurrency caps/backpressure/bulkheads at the right layer?
- Avoided logging tokens, cookies, raw URLs, and bodies when enabling observability?
- Re-measured p95/p99, error rates, pool pending, threads/CPU/GC, and backend saturation after fixing?
- Have regression tests and a rollback plan for HTTP client/LoadBalancer configuration changes?

**Conclusion:** When service-ID calls through Spring Cloud LoadBalancer slow down, do not assume the `ServiceInstance` selection algorithm is at fault. Measure **exactly which stage delays the request**: connection pool queues, DNS/TCP/TLS, backend execution, response decoding, or event-loop/servlet threads. `RestClient`/Apache HC5 enforces **total and per-route** caps; `WebClient`/Reactor Netty typically manages pools **per remote host**; blocking code on the event loop spikes latency from a completely different angle. Fix the proven bottleneck, bound queues and retries, and verify with metrics and load tests to restore stable inter-service communication.

**Official references:**

- [Spring Cloud Commons – Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html)
- [Spring Framework – REST Clients and HttpComponents request factory](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html)
- [Reactor Netty – HTTP Client, Connection Pool, and Metrics](https://projectreactor.io/docs/netty/release/reference/http-client.html)
- [Project Reactor – Schedulers and blocking calls](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html)
- [Spring Framework – WebFlux, Reactive Core, and concurrency model](https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html)
- [Apache HttpClient 5 – Connection Management](https://hc.apache.org/httpcomponents-client-5.4.x/current/httpclient5/apidocs/)
