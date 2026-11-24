# Measuring Connection Exhaustion, Idle Connections, and Target Service Load in Spring WebFlux

> **Module:** Spring Framework – reactive · **Parent topic:** Connections and Timeouts. This lesson builds an observability and diagnostics approach for `WebClient` outbound HTTP on Reactor Netty. The focus is distinguishing connection pool exhaustion, idle or stale connections, DNS/connect/TLS errors, slow responses, and target service overload; enabling the right Micrometer metrics; setting pool/timeout limits; and load-testing to select safe capacity.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain Reactor Netty's connection pool and the acquire → active → release → idle → eviction lifecycle.
2. Distinguish `maxConnections`, the pending acquire queue, `pendingAcquireTimeout`, `maxIdleTime`, and `maxLifeTime`.
3. Read gauges/timers for total, active, idle, pending connections, and acquire wait time.
4. Measure DNS resolution, TCP connect, TLS handshake, data sent/received, response time, and HTTP client errors.
5. Distinguish client-side pool exhaustion from a slow or overloaded target service.
6. Handle stale idle connections, layered timeouts, retry amplification, and connection churn.
7. Enable Reactor Netty metrics and Spring Boot `http.client.requests` using Micrometer/Actuator.
8. Design dashboards, alerts, load tests, and concurrency limits aligned with downstream capacity.
9. Build a WebClient with a dedicated pool, intentional timeouts, and HTTP integration tests using Java 17+.

**Operational principle:** a larger connection pool does not automatically make a system faster. The pool must fit expected concurrency, the queue must be bounded, timeouts must reflect SLOs, and total connections across all replicas must not exceed the target system's serving capacity.

## 2. Outbound Request and Connection Pool Map

`WebClient` is Spring's reactive API. When running on Reactor Netty, the HTTP client typically uses `ConnectionProvider` to manage connections to each remote host. A request must obtain a connection or stream before sending/receiving data.

~~~text
Controller / Service
       |
       v
     WebClient
       |
       v
 ConnectionProvider
       |
       +---- idle connection available
       |          |
       |          v
       |       acquire
       |
       +---- no idle connection
                  |
                  v
        active < maxConnections?
             /           \
           yes            no
            |              |
       open connection   pending queue
            |              |
            +-------+------+
                    |
                    v
             TCP / TLS / HTTP
                    |
                    v
             Target service
                    |
                    v
             response body
                    |
                    v
           consume response fully
                    |
                    v
             release connection
                    |
                    v
              idle / evict
~~~

States to distinguish:

- **Total:** total connections currently managed by the pool, consisting of active and idle.
- **Active:** connections acquired and currently serving a request.
- **Idle:** connections returned to the pool and available for reuse.
- **Pending:** requests waiting for an available connection.
- **Acquire time:** time a request spends waiting to borrow a connection.
- **Response time:** time to execute the request/response; it may include wait time, network time, and target processing depending on the metric/observation viewed.

An idle connection is not an error. It is pre-established capacity ready for reuse, avoiding TCP/TLS handshakes for the next request. Tuning is only needed when idle connections become stale or the pool retains too many resources.

## 3. Understanding ConnectionProvider Limits

### 3.1. `maxConnections`

`maxConnections` limits concurrent connections in each pool to a remote host. When the pool reaches its limit, new requests can wait in the pending queue if queue capacity remains.

Example:

~~~java
ConnectionProvider provider =
    ConnectionProvider.builder("catalog-pool")
        .maxConnections(32)
        .build();
~~~

The value `32` is only an example for a single instance. It does not mean the entire system has only 32 connections. With 20 replicas, each having its own pool, total potential open connections can reach around 640 connections to the same downstream, not counting other services.

### 3.2. Pending Acquire Queue

When no idle connection is available and `maxConnections` is reached, new requests can sit in the pending queue:

- `pendingAcquireMaxCount` limits the number of queued requests.
- `pendingAcquireTimeout` limits how long a request is allowed to wait.
- If the queue is full or the wait time expires, acquire fails.

A bounded queue helps the system fail fast when the downstream cannot handle the load. An unbounded queue can hold requests too long, increase memory, increase latency, and keep an overload lingering even after traffic drops.

~~~java
ConnectionProvider provider =
    ConnectionProvider.builder("catalog-pool")
        .maxConnections(32)
        .pendingAcquireMaxCount(64)
        .pendingAcquireTimeout(Duration.ofMillis(500))
        .build();
~~~

In this configuration, up to 32 connections are managed concurrently; up to 64 other requests can wait to acquire; a request waiting longer than 500 ms fails. These are illustrative limits and must be tuned to the latency SLO and actual capacity of the downstream.

### 3.3. `maxIdleTime`, `maxLifeTime`, and Eviction

| Configuration | Meaning | Used For |
| --- | --- | --- |
| `maxIdleTime` | Maximum time a connection may remain idle | Avoiding reuse of connections already closed by server/load balancer |
| `maxLifeTime` | Maximum lifetime of a connection since creation | Rotating old connections and changed endpoints/DNS |
| `maxLifeTimeVariance` | Jitter for lifetime expiration | Avoiding many connections created together expiring all at once |
| `evictInBackground` | Interval for checking and removing connections eligible for eviction | Cleaning idle connections on a background schedule |

Example:

~~~java
ConnectionProvider provider =
    ConnectionProvider.builder("catalog-pool")
        .maxConnections(32)
        .pendingAcquireMaxCount(64)
        .pendingAcquireTimeout(Duration.ofMillis(500))
        .maxIdleTime(Duration.ofSeconds(25))
        .maxLifeTime(Duration.ofMinutes(5))
        .maxLifeTimeVariance(5)
        .evictInBackground(Duration.ofSeconds(30))
        .metrics(true)
        .build();
~~~

`maxIdleTime` should be less than or equal to the target server/load balancer's idle timeout. For example, if the load balancer closes connections after 60 seconds idle, setting the client around 45–50 seconds helps the pool evict connections before attempting reuse. Exact numbers must follow your infrastructure's actual timeouts.

An overly short `maxLifeTime` can cause connection churn: frequent TCP/TLS handshakes, higher CPU, and extra load on the target. When many connections are created around the same time, jitter prevents them from expiring and reconnecting in a single wave.

Reactor Netty checks timeouts on acquire/release; `evictInBackground` adds periodic background checks. There is no need for an overly short interval if checking overhead outweighs the benefit.

### 3.4. HTTP/2 Is Not Like HTTP/1.1

With HTTP/1.1, a connection usually serves one active request at a time in the standard client model. With HTTP/2, one connection can multiplex multiple concurrent streams.

Therefore:
- `active.connections` does not fully reflect HTTP/2 concurrency.
- Also monitor `active.streams` and `pending.streams`.
- A pool with only a few connections can still serve many requests in parallel.
- Stream concurrency limits and server-side capacity remain important.

Do not apply HTTP/1.1 pool formulas directly to HTTP/2 without considering stream limits.

## 4. Reading Reactor Netty Metrics

Reactor Netty has two key metric groups: pool metrics and HTTP client metrics. They have distinct prefixes and must be enabled on the right objects.

### 4.1. Pool Metrics

Enable with:

~~~java
ConnectionProvider.builder("catalog-pool")
    .metrics(true)
    .build();
~~~

Primary meters:

| Meter | Type | Meaning |
| --- | --- | --- |
| `reactor.netty.connection.provider.total.connections` | Gauge | Total active + idle connections |
| `reactor.netty.connection.provider.active.connections` | Gauge | Connections currently acquired |
| `reactor.netty.connection.provider.max.connections` | Gauge | Active connection limit |
| `reactor.netty.connection.provider.idle.connections` | Gauge | Connections waiting for reuse |
| `reactor.netty.connection.provider.pending.connections` | Gauge | Requests waiting to acquire |
| `reactor.netty.connection.provider.pending.connections.time` | Timer | Acquire wait duration |
| `reactor.netty.connection.provider.max.pending.connections` | Gauge | Pending queue limit |

This is the most direct metric group for spotting pool saturation. If `active` hits `max`, `pending` rises, and `pending.connections.time` increases, requests are waiting for the pool to grant connections.

### 4.2. HTTP Client Metrics

Enable on `HttpClient`:

~~~java
HttpClient httpClient =
    HttpClient.create(provider)
        .metrics(true, uri -> {
            if (uri.startsWith("/items/")) {
                return "/items/{id}";
            }
            return uri;
        });
~~~

The URI normalization mapper prevents creating a separate meter for each path with a different ID. For example, `/items/42` and `/items/43` are both recorded under `/items/{id}`.

Primary meters:

| Meter | Meaning |
| --- | --- |
| `reactor.netty.http.client.address.resolver` | Hostname/DNS resolution time |
| `reactor.netty.http.client.connect.time` | Connection establishment time |
| `reactor.netty.http.client.tls.handshake.time` | TLS handshake time |
| `reactor.netty.http.client.data.sent` | Bytes sent |
| `reactor.netty.http.client.data.sent.time` | Data send duration |
| `reactor.netty.http.client.data.received` | Bytes received |
| `reactor.netty.http.client.data.received.time` | Data receive/consumption duration |
| `reactor.netty.http.client.response.time` | Request/response duration |
| `reactor.netty.http.client.errors` | HTTP client error count |

HTTP/2 also includes:

- `reactor.netty.connection.provider.active.streams`
- `reactor.netty.connection.provider.pending.streams`

When diagnosing latency causes, inspect DNS, connect, TLS, pending acquire, and response times separately. If you only check `response.time`, you will not know whether requests waited on a connection or the remote service processed slowly.

### 4.3. Spring Boot `http.client.requests` Is a Different Observation Layer

Spring Boot Actuator can automatically instrument `WebClient` and create the `http.client.requests` meter. To receive this instrumentation, inject Spring Boot's auto-configured `WebClient.Builder` and build clients from that builder.

The metric groups serve different purposes:

| Group | What Does It Measure? | Where Is It Enabled? |
| --- | --- | --- |
| `http.client.requests` | Outbound request observation at the Spring layer | Use auto-configured `WebClient.Builder` |
| `reactor.netty.connection.provider.*` | Pool counts/states and pending acquires | `ConnectionProvider.metrics(true)` |
| `reactor.netty.http.client.*` | DNS/connect/TLS/data/response and errors at the Reactor Netty layer | `HttpClient.metrics(true, uriMapper)` |

All three can be enabled. When analyzing, do not sum durations across meters because they may measure overlapping intervals or different boundaries.

## 5. Distinguishing Pool Exhaustion from Target Service Overload

This is the most critical diagnostic step. Both situations can raise `active.connections`, yet their causes and remedies differ.

### 5.1. Signs of Client-Side Pool Exhaustion

Commonly observed:

- `active.connections` approaches `max.connections`.
- `pending.connections` rises and stays elevated continuously.
- `pending.connections.time` increases.
- Requests fail with `PoolAcquireTimeoutException` or an equivalent acquire error.
- DNS/connect times may stay normal because requests have not yet obtained a connection to begin network I/O.
- The target server may still be healthy if actual request volume reaching the target has not exceeded capacity.

Common causes:
- `maxConnections` is too low for valid concurrency.
- Response bodies are not fully consumed, preventing connections from returning to the pool promptly.
- Requests/streams are too long or downstream responses hang.
- Certain operations hold connections longer than expected.
- Target is slow, keeping active connections from being released.

### 5.2. Signs of Target Service Overload

Commonly observed:

- `reactor.netty.http.client.response.time` rises, especially p95/p99.
- `active.connections` rises because requests hold connections longer.
- Pending acquires may rise secondarily once the pool fills up.
- Target returns many `429`, `503`, or `5xx` responses.
- Target-side metrics show queues, workers, event loops, CPU, memory, or concurrency hitting limits.
- Latency rises even though connect/TLS remain fast.

In this scenario, increasing `maxConnections` can push more requests onto an already overloaded target and worsen the outage. You need to limit concurrency, slow down send rates, shed load, or scale target capacity.

### 5.3. Signal-Based Diagnostic Table

| Observation | Likely Cause | What to Check |
| --- | --- | --- |
| Active = max, pending > 0, acquire timer rising | Pool saturation | Which requests hold connections long? Are pool max and queue sensible? |
| Pending acquire timeouts rising while target latency stays low | Pool too small or many requests holding connections | Are bodies consumed? Are there long streams or leaks? |
| Response time high, connect/TLS low, target 5xx/429 rising | Target overload | Server queues, CPU, concurrency, rate limits, and Retry-After |
| DNS resolver time rising | Slow DNS or resolver | DNS server, cache, service discovery, and hostnames |
| Connect time rising | TCP connect/network/target accept backlog | Network path, SYN backlog, firewalls, target listener |
| TLS handshake time rising | TLS/certificate/crypto or excessive reconnects | Handshakes, certificates, connection churn, TLS termination |
| First request after idle fails, subsequent requests succeed | Stale idle connection | Target/LB idle timeout and client `maxIdleTime` |
| Total connections rising rapidly, connect/TLS time and errors rising | Connection churn | `maxIdleTime`, `maxLifeTime`, pool disposal, and traffic bursts |
| High idle, low active, pending equals 0 | Pool has spare capacity | Not an error yet; evaluate whether too many connections are retained |
| HTTP/2 active streams high, pending streams rising | Stream capacity or slow target | Server max concurrent streams and H2 allocation strategy |

Do not conclude target overload solely from `active.connections = max`. Combine pending acquire, response time, status codes, and target-side metrics.

## 6. Measuring Target Service Load

Client metrics show what the client is waiting for, sending, receiving, and failing on. They do not directly expose the target server's full queues or CPU. To know whether the target is genuinely overloaded, observe both sides.

### 6.1. Signals to Collect on the Target

| Target-Side Signal | Question to Answer |
| --- | --- |
| Request rate (RPS) | Is inbound request volume rising or stable? |
| In-flight requests | How many requests are currently processing concurrently? |
| p50/p95/p99 latency | How are typical and tail latencies changing? |
| 4xx/429/5xx | Is the target rejecting, rate-limiting, or failing to process? |
| Queue depth / queue wait | Are requests waiting on workers, threads, event loops, or databases? |
| CPU and memory | Is the service hitting resource limits? |
| Worker/event-loop utilization | Is request-handling capacity saturated? |
| Database/cache dependency | Are requests slow due to a backend dependency? |
| Open connections/streams | Are connections or streams exceeding server capacity? |

Use the same distributed trace to link client spans with server spans. Record service name, operation/route template, status, and duration; avoid putting user IDs or dynamic URLs into metric tags.

### 6.2. Little’s Law for Estimating Concurrency

In a steady system:

\[
L = \lambda \times W
\]

Where:

- \(L\): average number of requests in the system.
- \(\lambda\): throughput, e.g., requests/second.
- \(W\): average time a request spends in the system, in seconds.

Example: one instance sends 200 requests/second to a target; average response time is 150 ms = 0.15 seconds.

\[
L = 200 \times 0.15 = 30
\]

The number 30 is the approximate average concurrency under steady-state conditions, not a mandatory `maxConnections` value. Tail latency, bursts, retries, replica count, HTTP/2 streams, and target capacity all affect the actual limit.

If latency doubles while throughput stays constant, average concurrent requests in the system also roughly double. This is why a slow target can exhaust the pool even without an increase in incoming traffic.

### 6.3. Total Connections Across Multiple Replicas

Calculate per service/target:

~~~text
Potential total connections
    ≈ number of client replicas
      × maxConnections per replica
      × number of independent pools/clients calling the target
~~~

Example:

- 12 replicas of checkout.
- Each replica has a pool with `maxConnections=40`.
- Two independent WebClients point to the same target.

The potential limit can reach \(12 \times 40 \times 2 = 960\) connections. If the two WebClients share a suitable `ConnectionProvider`, duplicate pools can be reduced. Also count other workers, cron jobs, and other services calling the same target.

Pool capacity must be evaluated across the entire deployment, not just a single pod.

## 7. Distinguishing Timeout Types

Similar-sounding timeouts measure different stages:

| Timeout | Starts/Ends | Common Errors |
| --- | --- | --- |
| DNS query timeout | Waiting for hostname resolution | Resolver timeout |
| Connect timeout | Establishing a TCP connection | Connect timeout/refused |
| TLS handshake timeout | TLS negotiation | SSL handshake timeout |
| Pending acquire timeout | Waiting for the pool to grant a connection | Pool acquire timeout |
| Response timeout | Waiting for response data per Reactor Netty configuration | Response timeout |
| Overall operation timeout | Covers the entire reactive operation | `TimeoutException` from `Mono.timeout` |

Example configuration:

~~~java
HttpClient httpClient =
    HttpClient.create(provider)
        .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 1_000)
        .responseTimeout(Duration.ofSeconds(2));
~~~

You can add an overall timeout in the service:

~~~java
Mono<String> response = webClient.get()
    .uri("/work")
    .retrieve()
    .bodyToMono(String.class)
    .timeout(Duration.ofSeconds(3));
~~~

`Mono.timeout` spans the entire operation from subscription until a terminal signal arrives; it does not replace specialized timeouts for pool, DNS, connect, or response. Configuring layered timeouts helps identify where requests fail.

Do not set `pendingAcquireTimeout` overly long just to reduce error counts. Long queues raise tail latency and hold requests unnecessarily. Timeouts should fit inside the request's overall budget so the service calling WebClient still has time to run a fallback or return an error to the caller.

## 8. Handling Idle Connections and Stale Connections

### 8.1. Normal Idle Connections

When a response finishes and the body is consumed, the connection can return to the pool. It stays idle until another request reuses it or eviction removes it.

The idle gauge may:
- Rise after a traffic burst and then drop via eviction.
- Consistently hold a few connections under steady traffic.
- Equal 0 when the pool is busy or retains no connections.

Do not alert just because `idle.connections > 0`. Compare idle against active, pending, max, and socket-holding cost.

### 8.2. Stale Idle Connections

Some load balancers, proxies, or target servers close connections after an idle interval. If the client keeps that connection and tries to reuse it, the next request may encounter an early reset/close, such as `PrematureCloseException` or connection reset.

How to handle:

1. Identify the actual idle timeouts of the target, proxies, and load balancers.
2. Set client `maxIdleTime` less than or equal to the shortest timeout along the path.
3. Consider `evictInBackground` to remove eligible connections.
4. Set a reasonable `maxLifeTime` if connections need rotation.
5. Watch for errors concentrated on the first request after a quiet period.
6. Check HTTP/2 keepalive/PING if using HTTP/2.

Example if the load balancer closes connections after 60 seconds idle:

~~~java
ConnectionProvider provider =
    ConnectionProvider.builder("catalog-pool")
        .maxIdleTime(Duration.ofSeconds(45))
        .evictInBackground(Duration.ofSeconds(20))
        .build();
~~~

45 seconds is an illustrative value; leave a buffer aligned with network policies and timeouts at every hop.

### 8.3. HTTP/2 Keepalive

With HTTP/2, Reactor Netty supports PING frames to check idle connections. Configuring PING health checks depends on `maxIdleTime`; if needed, configure idle timeout alongside `pingAckTimeout` and retry thresholds per the documentation of the Reactor Netty version in use.

PING helps detect an unresponsive peer. It does not replace request timeouts, stream limits, or business health checks.

## 9. Configuring WebClient with a Dedicated Pool and Metrics

The example below uses Spring Boot, WebFlux, Reactor Netty, and Micrometer. It uses a named `ConnectionProvider` to distinguish the Catalog downstream pool.

~~~java
@Configuration(proxyBeanMethods = false)
public class CatalogWebClientConfiguration {

    @Bean(destroyMethod = "dispose")
    ConnectionProvider catalogConnectionProvider() {
        return ConnectionProvider.builder("catalog-pool")
            .maxConnections(32)
            .pendingAcquireMaxCount(64)
            .pendingAcquireTimeout(Duration.ofMillis(500))
            .maxIdleTime(Duration.ofSeconds(25))
            .maxLifeTime(Duration.ofMinutes(5))
            .maxLifeTimeVariance(5)
            .evictInBackground(Duration.ofSeconds(30))
            .metrics(true)
            .build();
    }

    @Bean
    WebClient catalogWebClient(
            WebClient.Builder builder,
            ConnectionProvider catalogConnectionProvider,
            @Value("${catalog.base-url}") String baseUrl) {

        HttpClient httpClient =
            HttpClient.create(catalogConnectionProvider)
                .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 1_000)
                .responseTimeout(Duration.ofSeconds(2))
                .metrics(true, uri -> {
                    if (uri.startsWith("/items/")) {
                        return "/items/{id}";
                    }
                    return uri;
                });

        return builder
            .baseUrl(baseUrl)
            .clientConnector(
                new ReactorClientHttpConnector(httpClient))
            .build();
    }
}
~~~

Key points:

- `ConnectionProvider.metrics(true)` enables pool metrics.
- `HttpClient.metrics(true, uriMapper)` enables HTTP client metrics and normalizes URI tags.
- `WebClient.Builder` is injected from Spring Boot to preserve `http.client.requests` instrumentation.
- `maxConnections` and the pending queue are set explicitly rather than relying on defaults.
- `destroyMethod="dispose"` releases the custom provider when the Spring context stops.
- Pool name `catalog-pool` helps distinguish downstreams in metric tags.

If there are multiple downstreams, consider a separate `ConnectionProvider` per trust boundary or workload with different timeouts/capacities. Never create a new provider per request.

### 9.1. Service Calling the Target

~~~java
@Service
public class CatalogClient {

    private final WebClient catalogWebClient;

    public CatalogClient(WebClient catalogWebClient) {
        this.catalogWebClient = catalogWebClient;
    }

    public Mono<String> fetchWork() {
        return catalogWebClient.get()
            .uri("/work")
            .retrieve()
            .bodyToMono(String.class);
    }
}
~~~

The response body is consumed via `bodyToMono`. If using `exchangeToMono` or `ResponseEntity<Flux<T>>`, the caller must ensure the body is consumed or released so the connection can return to the pool.

### 9.2. Demo Endpoint

~~~java
@RestController
@RequestMapping("/api/catalog")
public class CatalogProbeController {

    private final CatalogClient client;

    public CatalogProbeController(CatalogClient client) {
        this.client = client;
    }

    @GetMapping("/probe")
    public Mono<ResponseEntity<String>> probe() {
        return client.fetchWork()
            .map(ResponseEntity::ok)
            .onErrorResume(WebClientException.class, error ->
                Mono.just(ResponseEntity
                    .status(HttpStatus.SERVICE_UNAVAILABLE)
                    .body("Catalog service is temporarily unavailable")));
    }
}
~~~

The controller maps outbound errors to a safe response. In production, you can distinguish timeout/pool capacity, connection errors, and 5xx statuses to choose appropriate error codes; do not return raw exception messages to clients.

## 10. Configuring Spring Boot Actuator and Prometheus

Add the dependencies:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Configure `application.properties`:

~~~properties
catalog.base-url=http://localhost:9090

management.endpoints.web.exposure.include=health,info,metrics,prometheus
management.metrics.distribution.percentiles-histogram.http.client.requests=true
~~~

When the application runs, you can inspect:

~~~text
GET /actuator/health
GET /actuator/metrics
GET /actuator/metrics/http.client.requests
GET /actuator/metrics/reactor.netty.connection.provider.active.connections
GET /actuator/metrics/reactor.netty.connection.provider.pending.connections
GET /actuator/prometheus
~~~

`/actuator/metrics` is a diagnostic endpoint by meter name; `/actuator/prometheus` exports scrape format if the Prometheus registry is present. In production, expose Actuator only under proper network/security policies; do not expose metrics endpoints publicly to the Internet.

### 10.1. Querying Metrics via Actuator

Examples:

~~~bash
curl -s http://localhost:8080/actuator/metrics/reactor.netty.connection.provider.active.connections
curl -s http://localhost:8080/actuator/metrics/reactor.netty.connection.provider.pending.connections
curl -s http://localhost:8080/actuator/metrics/reactor.netty.connection.provider.pending.connections.time
curl -s http://localhost:8080/actuator/metrics/reactor.netty.http.client.response.time
~~~

The endpoint can return measurements and available tags. Use the `tag` query parameter to filter by pool/service if the meter registers those tags. Exact tag names and how they convert to Prometheus labels depend on the meter/registry; inspect actual output before building dashboards.

## 11. What Should a Dashboard Include?

Do not build just a single “connection count” chart. A good dashboard for each downstream should group metrics along the same timeline.

### 11.1. Pool Saturation

- Active connections.
- Max connections.
- Idle connections.
- Pending connections.
- Pending acquire duration p50/p95/p99.
- Pending queue limit and acquire timeout/rejection counts.

You can calculate utilization:

\[
\text{pool utilization} =
\frac{\text{active connections}}{\text{max connections}}
\]

A high ratio for a short time is not necessarily an incident. View it alongside the pending queue and acquire wait time. Active near max while pending stays at 0 can mean the pool is being used efficiently.

### 11.2. Network and HTTP

- DNS resolution time.
- TCP connect time.
- TLS handshake time.
- Request/response duration.
- Data sent/received.
- HTTP client error rate.
- Status codes from target.
- Timeout and retry counts.

### 11.3. Target Service

- RPS/in-flight requests.
- Server-side p95/p99 latency.
- 429/503/5xx rate.
- Queue depth/worker saturation.
- CPU/memory/event-loop utilization.
- Target's database/cache latency and connection pools.

### 11.4. Application Impact

- Caller API latency.
- Request error rate.
- Number of shed or rejected requests.
- Retry amplification.
- In-flight outbound operations.
- Cancellations and timeouts.

The dashboard should show the same load spike propagating from caller to downstream and back in the response.

## 12. Alerting on Symptoms and SLOs

Do not use a single `active/max > 80%` threshold as your only alert. Alerts should combine sustained duration, pending queue, and user impact.

Example alerting guide:

| Condition | Meaning | Action |
| --- | --- | --- |
| Sustained pending connections > 0 and rising acquire p95 | Pool is starting to queue | Check concurrency, body consumption, and response time |
| Pending acquire timeouts rising | Callers fail to get connections in time | Reduce load or tune pool after identifying root cause |
| Target p99 rising alongside 429/503 | Target is saturated/rate-limiting | Shed load, reduce concurrency, coordinate scaling target |
| Connect/TLS time spiking | Network issue or connection churn | Inspect DNS, network, TLS termination, and idle eviction |
| Stale connection errors after idle | Client/server timeouts misaligned | Adjust `maxIdleTime` and check load balancer |
| Connection count/FD growing without bound | Pool leak or dynamic pool creation | Check provider lifecycle, host cardinality, and bean scope |

Alerts should have:
- A `for` duration to avoid firing on brief spikes.
- Thresholds based on SLOs/traffic baselines.
- Separation between warning (pending rising) and critical (acquire timeouts + user-facing errors).
- Runbooks pointing directly to which metrics, logs, traces, and dashboards to open.

Do not alert solely because `idle connections > 0` or `active connections` approaches max for a few seconds.

## 13. Designing Pool Size and Pending Queue

### 13.1. Estimating from Traffic and Latency

Start with average concurrency:

\[
C_{\text{avg}} \approx RPS_{\text{per instance}} \times W_{\text{avg}}
\]

Then measure bursts, tail latency, and safe target concurrency. Pool max needs to:
- Handle valid peaks.
- Not be so large that a single replica can overload the target.
- Account for replica counts and other client pools.
- Bound the pending queue and timeouts.
- Leave margin for slow requests, retries, and expected traffic bursts.

### 13.2. A Queue Is Not Capacity

Increasing the pending queue only allows more requests to wait. It does not make the target process faster. If a server handles 100 concurrent requests yet the client queues 10,000 requests, latency can balloon and memory stays tied up.

Choose:
- Small queue and short timeout when callers need fast responses.
- Moderate queue when workloads have short bursts and the target can recover.
- Fast fail/load shed when the downstream is already saturated.
- Durable queues/message brokers for background work that can wait long; do not use a connection pending queue as a business work queue.

### 13.3. Do Not Increase maxConnections to Fix a Slow Target

If target latency increases due to a slow database, enlarging the pool makes more requests wait on the database simultaneously and can add extra pressure. Before increasing max:
1. Check target p95/p99 and queues.
2. Check how long requests hold connections.
3. Check whether response bodies are consumed.
4. Check target safe concurrency.
5. Sum connections across all replicas.
6. Test small changes in a load test and compare SLOs before/after.

## 14. Shedding Load and Protecting Downstreams

### 14.1. Bulkheads and Concurrency Limits

You can bound concurrent requests to a dependency at the application layer, independent of the connection pool. For example, using `flatMap` with bounded concurrency for a batch:

~~~java
Flux<Result> processBatch(Flux<Command> commands) {
    return commands.flatMap(
        command -> catalogClient.fetch(command),
        16
    );
}
~~~

The `16` bounds concurrency within this pipeline. It does not replace pool max, yet prevents a batch stream from consuming all outbound capacity.

### 14.2. Selective Retries

Retries can multiply load when the target is failing. Only retry:
- Identified transient errors.
- Idempotent operations or ones using an idempotency key.
- Small attempt counts, with backoff and jitter.
- With an overall timeout.
- Respecting `Retry-After` when applicable.

Do not blindly retry pool acquire timeouts; the caller lacks local capacity, and immediate retries can grow the queue further. Do not retry 400/401/403 by default. For 429/503, coordinate rate limits and a retry budget.

### 14.3. Circuit Breakers and Load Shedding

A circuit breaker can temporarily stop sending requests when failure/slow-call rates cross a threshold, then probe again after an open period. Load shedding rejects lower-priority work before queues swell.

Fallbacks must have clear bounds and semantics. Do not create a fallback that calls another dependency that is also overloaded.

### 14.4. Response Bodies and Connection Release

An unconsumed response body can prevent the connection from returning to the pool as expected. With `retrieve().bodyToMono(...)` or `bodyToFlux(...)`, consume the body within the reactive chain. With `exchangeToMono`, ensure every status-handling branch reads, releases, or hands off the body.

Do not fire an auxiliary `subscribe()` to read the response and return early. Do not call `block()` on a WebFlux event loop.

## 15. Load Testing to Find Safe Limits

A useful load test must exercise both the pool and the target. Run in staging or an environment with approved capacity; avoid generating unbounded load against production.

### 15.1. Test Phases

1. **Warm-up:** initialize event loops, DNS, TLS, and pools; do not treat cold-start latency as steady-state baseline.
2. **Baseline:** low traffic, confirm metrics and connection reuse.
3. **Ramp-up:** increase RPS/concurrency in steps.
4. **Steady state:** hold load at each level long enough for pending/latency to stabilize.
5. **Burst:** inject short spikes to observe queueing and recovery.
6. **Idle gap:** stop traffic and send a first request to catch stale idle connections.
7. **Target degradation:** slow the target or return 503 under control to verify timeouts/circuit breakers.
8. **Recovery:** drop load and watch pending queue, active connections, and error rate return to normal.

### 15.2. What to Record at Each Load Level

| Group | Metrics |
| --- | --- |
| Load generator | Offered RPS, completed RPS, concurrency, dropped iterations |
| Client pool | Active/max, idle, pending, acquire p95/p99 |
| HTTP client | DNS/connect/TLS/response p95/p99, errors, statuses |
| Target | RPS, in-flight, queue depth, p95/p99, 429/503/5xx |
| Runtime | CPU, heap/direct memory, event-loop pending tasks, file descriptors |
| Business | API latency and error rate seen by callers |

Record both offered load and completed throughput. Looking only at completed RPS can make the system appear healthy while the load generator is dropping or queueing requests.

### 15.3. Example k6 Test Script

~~~javascript
import http from "k6/http";
import { check } from "k6";

export const options = {
  scenarios: {
    steady: {
      executor: "constant-arrival-rate",
      rate: 100,
      timeUnit: "1s",
      duration: "3m",
      preAllocatedVUs: 40,
      maxVUs: 160
    }
  },
  thresholds: {
    http_req_failed: ["rate<0.01"],
    http_req_duration: ["p(95)<500", "p(99)<1000"]
  }
};

export default function () {
  const response = http.get(`${__ENV.BASE_URL}/api/catalog/probe`);
  check(response, {
    "status is 200": (r) => r.status === 200
  });
}
~~~

Run:

~~~bash
BASE_URL=http://localhost:8080 k6 run load-test.js
~~~

On Windows PowerShell:

~~~powershell
$env:BASE_URL = "http://localhost:8080"
k6 run load-test.js
~~~

This script is an illustrative baseline. Ramp load from low to high, set thresholds aligned with real SLOs, and verify `maxVUs` suffices for the arrival rate. If the target returns errors, do not increase traffic endlessly to “push harder.”

## 16. Runnable Java 17+ Project Example

The following project creates a dedicated WebClient to Catalog, enables pool/HTTP metrics, configures timeouts, and tests success/error requests with MockWebServer.

### 16.1. Structure

~~~text
webclient-pool-observability/
├── pom.xml
├── src/main/resources/application.properties
├── src/main/java/com/example/pool/
│   ├── PoolObservabilityApplication.java
│   ├── CatalogWebClientConfiguration.java
│   ├── CatalogClient.java
│   └── CatalogProbeController.java
└── src/test/java/com/example/pool/
    └── CatalogClientIntegrationTest.java
~~~

### 16.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.0.9</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>webclient-pool-observability</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-registry-prometheus</artifactId>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>com.squareup.okhttp3</groupId>
            <artifactId>mockwebserver</artifactId>
            <version>4.12.0</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 16.3. application.properties

~~~properties
catalog.base-url=http://localhost:9090

management.endpoints.web.exposure.include=health,info,metrics,prometheus
management.metrics.distribution.percentiles-histogram.http.client.requests=true
~~~

In production, set `catalog.base-url` via environment/config management and protect Actuator endpoints with network policies/authentication.

### 16.4. PoolObservabilityApplication.java

~~~java
package com.example.pool;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PoolObservabilityApplication {

    public static void main(String[] args) {
        SpringApplication.run(PoolObservabilityApplication.class, args);
    }
}
~~~

### 16.5. CatalogWebClientConfiguration.java

~~~java
package com.example.pool;

import java.time.Duration;

import io.netty.channel.ChannelOption;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;

@Configuration(proxyBeanMethods = false)
public class CatalogWebClientConfiguration {

    @Bean(destroyMethod = "dispose")
    ConnectionProvider catalogConnectionProvider() {
        return ConnectionProvider.builder("catalog-pool")
            .maxConnections(32)
            .pendingAcquireMaxCount(64)
            .pendingAcquireTimeout(Duration.ofMillis(500))
            .maxIdleTime(Duration.ofSeconds(25))
            .maxLifeTime(Duration.ofMinutes(5))
            .maxLifeTimeVariance(5)
            .evictInBackground(Duration.ofSeconds(30))
            .metrics(true)
            .build();
    }

    @Bean
    WebClient catalogWebClient(
            WebClient.Builder builder,
            ConnectionProvider catalogConnectionProvider,
            @Value("${catalog.base-url}") String baseUrl) {

        HttpClient httpClient =
            HttpClient.create(catalogConnectionProvider)
                .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 1_000)
                .responseTimeout(Duration.ofSeconds(2))
                .metrics(true, uri -> {
                    if (uri.startsWith("/items/")) {
                        return "/items/{id}";
                    }
                    return uri;
                });

        return builder
            .baseUrl(baseUrl)
            .clientConnector(
                new ReactorClientHttpConnector(httpClient))
            .build();
    }
}
~~~

### 16.6. CatalogClient.java

~~~java
package com.example.pool;

import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

@Service
public class CatalogClient {

    private final WebClient catalogWebClient;

    public CatalogClient(WebClient catalogWebClient) {
        this.catalogWebClient = catalogWebClient;
    }

    public Mono<String> fetchWork() {
        return catalogWebClient.get()
            .uri("/work")
            .retrieve()
            .bodyToMono(String.class);
    }
}
~~~

### 16.7. CatalogProbeController.java

~~~java
package com.example.pool;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClientException;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/catalog")
public class CatalogProbeController {

    private final CatalogClient client;

    public CatalogProbeController(CatalogClient client) {
        this.client = client;
    }

    @GetMapping("/probe")
    public Mono<ResponseEntity<String>> probe() {
        return client.fetchWork()
            .map(ResponseEntity::ok)
            .onErrorResume(WebClientException.class, error ->
                Mono.just(ResponseEntity
                    .status(HttpStatus.SERVICE_UNAVAILABLE)
                    .body("Catalog service is temporarily unavailable")));
    }
}
~~~

### 16.8. CatalogClientIntegrationTest.java

~~~java
package com.example.pool;

import java.io.IOException;
import java.time.Duration;
import java.util.concurrent.TimeUnit;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.web.reactive.function.client.WebClientResponseException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.NONE)
class CatalogClientIntegrationTest {

    private static final MockWebServer SERVER = startServer();

    @Autowired
    CatalogClient catalogClient;

    private static MockWebServer startServer() {
        MockWebServer server = new MockWebServer();
        try {
            server.start();
            return server;
        }
        catch (IOException error) {
            throw new ExceptionInInitializerError(error);
        }
    }

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add(
            "catalog.base-url",
            () -> SERVER.url("/").toString());
    }

    @AfterAll
    static void stopServer() throws IOException {
        SERVER.shutdown();
    }

    @Test
    void successfulRequestUsesTargetAndConsumesBody()
            throws Exception {

        SERVER.enqueue(new MockResponse()
            .setResponseCode(200)
            .addHeader("Content-Type", "text/plain")
            .setBody("catalog-ready"));

        String body = catalogClient.fetchWork()
            .block(Duration.ofSeconds(3));

        assertEquals("catalog-ready", body);

        RecordedRequest request =
            SERVER.takeRequest(2, TimeUnit.SECONDS);

        assertNotNull(request);
        assertEquals("GET", request.getMethod());
        assertEquals("/work", request.getPath());
    }

    @Test
    void target503BecomesWebClientResponseException() {
        SERVER.enqueue(new MockResponse()
            .setResponseCode(503)
            .addHeader("Content-Type", "text/plain")
            .setBody("temporarily unavailable"));

        WebClientResponseException error = assertThrows(
            WebClientResponseException.class,
            () -> catalogClient.fetchWork()
                .block(Duration.ofSeconds(3)));

        assertEquals(503, error.getStatusCode().value());
    }
}
~~~

`block()` appears only in tests for synchronous assertions. In production controllers/services, keep `Mono` and compose the reactive chain.

### 16.9. Running and Observing

Requires JDK 17+ and Maven:

~~~bash
java -version
mvn -version
mvn test
mvn spring-boot:run
~~~

When the target service is running at `catalog.base-url`, try:

~~~bash
curl -i http://localhost:8080/api/catalog/probe
curl -s http://localhost:8080/actuator/metrics/reactor.netty.connection.provider.active.connections
curl -s http://localhost:8080/actuator/metrics/reactor.netty.connection.provider.pending.connections
curl -s http://localhost:8080/actuator/metrics/reactor.netty.http.client.response.time
curl -s http://localhost:8080/actuator/prometheus
~~~

The MockWebServer tests verify the client sends requests and handles status codes. To verify real pool saturation/idle eviction, run a separate load test against a target with controlled latency and concurrency; short functional tests do not prove sizing is optimal.

## 17. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Looking only at `active.connections` | Cannot tell whether requests are waiting | Inspect `max`, `pending`, and acquire timer together |
| Treating idle connections as an error | Unnecessarily scaling down the pool | Idle is reusable capacity; evaluate alongside traffic and eviction |
| Increasing `maxConnections` when the target is slow | Increases pressure on the target | Inspect server queues/latency, limit concurrency |
| Unbounded pending queue | Queue and latency swell | Set a bounded `pendingAcquireMaxCount` |
| `pendingAcquireTimeout` too long | Requests hold resources too long | Align timeout with the overall budget |
| Not setting `maxIdleTime` | Reuses stale connections after idle | Choose based on the shortest idle timeout of target/LB |
| `maxLifeTime` too short | TCP/TLS churn | Set lifetime based on needs and measure handshakes |
| Creating a new `ConnectionProvider` in every service method | Multiple duplicate pools | Use a singleton provider per dependency |
| Not consuming the response body | Connections stay held long or are not released promptly | Consume/release on every response branch |
| Using dynamic URIs as metric tags | Cardinality and memory grow sharply | Normalize route templates and limit tags |
| Enabling only Boot HTTP metrics, omitting pool metrics | Cannot see pending acquires | Enable `ConnectionProvider.metrics(true)` |
| Enabling only pool metrics, omitting HTTP client metrics | Missing DNS/connect/TLS/response timing | Enable `HttpClient.metrics(true, uriMapper)` |
| Summing timers with different boundaries | Double-counts total latency | Understand each meter's semantics before combining |
| Retrying immediately on acquire timeout | Creates extra pool contention | Fail fast, shed load, or limit concurrency |
| Measuring only the client, ignoring the target | Cannot see server queues/CPU | Correlate client metrics with server metrics and traces |
| Testing only local happy paths | Misses stale/overload behavior | Add idle gaps, slow targets, 429/503, and load tests |
| Exposing Actuator metrics to the Internet | Leaks operational details | Protect endpoints with auth/network policies |

## 18. Connection Exhaustion Incident Investigation Procedure

When an alert fires for pending acquires or timeouts:

1. Select the exact downstream/pool and incident start time.
2. Check `active`, `max`, `idle`, `pending`, and the acquire timer.
3. Check HTTP client DNS, connect, TLS, and response times.
4. Check 429/503/5xx statuses, request rate, and retry counts.
5. Correlate target-side in-flight requests, queues, CPU, workers, and databases.
6. Check whether response bodies are consumed on every branch.
7. Check long requests/streams, timeouts, cancellations, and connection lifecycles.
8. Check replica count multiplied by pool max and the number of independent WebClients/providers.
9. If failures happen after idle periods, compare client `maxIdleTime` with target/load balancer timeouts.
10. Pick one small change, re-run load tests, and compare SLOs before/after.

Use traces to pinpoint whether a request spent time in the client pool, network, or server handler. Correlation IDs/trace IDs link a specific request; metrics reveal system-wide trends and severity.

## 19. Production Checklist

- [ ] Each downstream has its own pool identity and dashboard.
- [ ] `maxConnections` is calculated per replica and across the entire deployment.
- [ ] `pendingAcquireMaxCount` is bounded.
- [ ] `pendingAcquireTimeout` fits within the request budget.
- [ ] `maxIdleTime` does not exceed the shortest idle timeout of target/LB.
- [ ] `maxLifeTime` and eviction are chosen based on traffic/network.
- [ ] Pool metrics are enabled via `ConnectionProvider.metrics(true)`.
- [ ] HTTP client metrics are enabled via `HttpClient.metrics(true, uriMapper)`.
- [ ] WebClient uses Boot's auto-configured builder to retain `http.client.requests`.
- [ ] URI tags are normalized; never use dynamic IDs/paths, user IDs, or correlation IDs as metric tags.
- [ ] Dashboard includes active/max/idle/pending/acquire time, DNS/connect/TLS/response, and status/error rates.
- [ ] Target-side metrics include RPS, in-flight, p95/p99, queues, CPU, workers, and dependency latency.
- [ ] HTTP/2 monitors stream metrics, not just connection counts.
- [ ] Response bodies are consumed/released in every branch.
- [ ] Retries are bounded, with backoff, jitter, and an idempotency policy.
- [ ] Bulkheads/load shedding protect targets when saturated.
- [ ] Actuator is exposed under controlled policies.
- [ ] Load tests cover steady, burst, idle gap, slow/error target, and recovery phases.
- [ ] Runbooks exist to look up by pool name, service, trace, and timestamp.

## 20. Hands-On Exercises

**Exercise 1 – Enable pool metrics.** Create a named `ConnectionProvider` with `maxConnections=8`, a bounded pending queue, and `metrics(true)`. Send multiple concurrent requests and observe active/idle/pending.

**Exercise 2 – Distinguish acquire vs. response timeout.** Set a low pool max and slow the target in a controlled way. Observe the pending acquire timer before requests are sent and the response timer after requests reach the target.

**Exercise 3 – Idle connections.** Pause traffic longer than the load balancer's idle timeout, then send a request. Compare errors before and after setting client `maxIdleTime` lower than that timeout.

**Exercise 4 – Target overload.** Have the target return 503 or increase latency. Monitor client response time, active/pending connections, and server queues; try lowering concurrency.

**Exercise 5 – Multiple replicas.** Calculate total connection potential from replica count, pool count, and max connections. Compare against the target's published capacity.

**Exercise 6 – HTTP/2.** Run an HTTP/2 client, observe active/pending streams, and compare with connection metrics.

**Exercise 7 – Load test.** Use k6/Gatling to ramp arrival rate in steps. Record p95/p99, error rate, completed throughput, and pool saturation.

**Exercise 8 – Retry budget.** Simulate a target returning 429/503; compare retrying with backoff/jitter versus no retries. Compare total requests received by the target to observe retry amplification.

**Exercise 9 – Body consumption.** Create one WebClient branch that does not consume the response body and one that consumes it fully; observe connection release/pool reuse and fix the lifecycle.

**Exercise 10 – Alerting.** Create an alert when pending acquires persist alongside p95 exceeding SLO or rising acquire timeouts; verify the alert does not fire merely because `idle connection > 0`.

## 21. Official References

1. Reactor Netty Reference Guide – HTTP Client, Connection Pool, Metrics and Timeout Configuration: https://projectreactor.io/docs/netty/release/reference/http-client.html
2. Spring Boot 4.0 – Actuator Metrics and HTTP Client Metrics: https://docs.spring.io/spring-boot/4.0/reference/actuator/metrics.html
3. Spring Framework – WebClient: https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html
4. Spring Framework – WebClient filters and exchange handling: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-filter.html
5. Micrometer – Meters, Timer, Counter, Gauge and Tags: https://docs.micrometer.io/micrometer/reference/concepts/meters.html
6. Micrometer – Histograms and Percentiles: https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html
7. Reactor Core – Backpressure and Reactor reference: https://projectreactor.io/docs/core/release/reference/
8. Spring Boot – System Requirements: https://docs.spring.io/spring-boot/system-requirements.html

**Final Self-Assessment:** When `active.connections` hits max and pending rises, what must you check to tell whether the pool is too small or the target is slow? Why is an idle connection not automatically an error? How does `pendingAcquireTimeout` differ from `responseTimeout`? Why can enlarging pools across all replicas overload the target? When your dashboard combines pool, network, response, and server-side saturation metrics, you can pinpoint the exact bottleneck layer instead of blindly increasing connection counts.
