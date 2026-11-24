# Connect Timeout, Response Timeout, and Connection Acquire Wait Time

When making HTTP calls with **Spring WebClient** on Reactor Netty, a request can wait at several stages: waiting for an idle connection in the pool, establishing a new TCP connection, completing the TLS handshake, sending the request, waiting for the server to respond, and reading the response body. Each stage has different causes of slowness and different timeout configuration mechanisms.

Three timeouts are commonly confused:

- **Connection timeout**: limits the time to establish a connection to the remote peer when a new connection must be created.
- **Pending acquire timeout**: limits the time spent waiting to borrow a connection from the connection pool when the pool is busy.
- **Response timeout**: in Reactor Netty, limits the maximum interval between network read operations while receiving a response.

In addition to these three timeouts, Reactor provides a **publisher-level timeout** to set a deadline on a reactive operation. With §Mono.timeout(Duration)§, the deadline applies to the entire Mono from subscription until a terminal signal arrives. With Flux, §timeout(Duration)§ normally limits the silent interval between signals rather than automatically bounding the total duration of the entire stream.

To design timeouts properly, first identify where the request is slow. Increasing the connection timeout does not solve a full pool; increasing the response timeout does not shorten the acquire queue; and an overall deadline does not replace specialized timeouts needed to diagnose individual stages.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish connect timeout, pending acquire timeout, response timeout, and end-to-end timeout.
2. Describe the lifecycle of a WebClient request across DNS, connection pool, TCP, TLS, request write, and response read.
3. Configure §ConnectionProvider§ with connection and pending queue limits.
4. Configure §HttpClient§ with §CONNECT_TIMEOUT_MILLIS§ and §responseTimeout§.
5. Connect `HttpClient` to `WebClient` using §ReactorClientHttpConnector§.
6. Understand TLS, proxy, and DNS timeouts as separate stages.
7. Set an overall deadline using Reactor's `timeout` operator and build a timeout budget.
8. Distinguish pool saturation errors from network errors or slow server responses.
9. Design bounded retries with backoff that do not duplicate non-idempotent operations.
10. Monitor connection pools, latency, and timeouts using metrics.
11. Write and test WebClient on Java 17 with MockWebServer.

## 2. Lifecycle of a WebClient Request

A request passes through the following general stages:

~~~text
WebClient request
      |
      v
DNS hostname resolution
      |
      v
Acquire connection from pool
      |
      +---- pool has idle connection --> reuse connection
      |
      +---- pool out of connections ---> pending acquire queue
      |                                  |
      |                                  +--> acquire timeout
      v
Create TCP connection (if needed)
      |
      +--> connect timeout
      v
TLS handshake (if HTTPS)
      |
      +--> TLS handshake timeout
      v
Write HTTP request
      |
      +--> write/network failure
      v
Wait for and read response
      |
      +--> response/read timeout
      v
Decode response body
      |
      v
Publisher complete
~~~

Not every request goes through all steps. If the pool already has a suitable idle connection, the request can skip opening a new TCP connection and TLS handshake. If DNS is already cached, hostname resolution can be faster. If the request does not use HTTPS, there is no TLS handshake.

A timeout at each step applies only to the stage it governs. A request may not violate any individual timeout yet still take too long overall; in that case, an overall deadline is needed at the publisher or service layer.

## 3. Connection Timeout

### 3.1. What Does Connection Timeout Control?

Connection timeout limits the time to establish a TCP connection to the remote peer. With Reactor Netty, the common configuration is the Netty channel option:

~~~java
.option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 2_000)
~~~

The value is specified in milliseconds. If the TCP connection is not established before the time expires, the connect operation fails.

Connection timeout only matters when the client has to create a new connection. If the request borrows an idle connection from the pool, there is no new TCP connect for this timeout to apply to.

Reactor Netty currently documents a default connect timeout of 30 seconds. However, Spring Boot manages the Reactor Netty version via dependency management; check the documentation for the actual version in use and explicitly configure timeouts according to your application's SLA rather than relying implicitly on defaults.

### 3.2. Configuring with WebClient

Spring WebClient does not define an independent connect timeout of its own. When using Reactor Netty, configure `HttpClient` and pass it to the connector:

~~~java
HttpClient httpClient = HttpClient.create()
    .option(
        ChannelOption.CONNECT_TIMEOUT_MILLIS,
        2_000
    );

WebClient client = WebClient.builder()
    .clientConnector(
        new ReactorClientHttpConnector(httpClient)
    )
    .build();
~~~

§CONNECT_TIMEOUT_MILLIS§ is not a timeout for the entire request. It does not limit pool wait time, server processing time, or response body read time after the connection is established.

### 3.3. DNS and TLS Are Not Connect Timeout

Hostname resolution can occur before TCP connect. If DNS is slow, the request can spend time before the connect step even begins. Reactor Netty uses its own resolver and has DNS timeout/cache settings; do not diagnose every slow pre-connect request as a connect timeout error.

With HTTPS, the TLS handshake happens after the TCP connection is created. Reactor Netty has a separate §handshakeTimeout§; current documentation notes a default TLS handshake timeout of 10 seconds. A short connect timeout does not automatically impose a corresponding limit on the TLS handshake.

### 3.4. When Should It Be Adjusted?

Consider adjusting the connect timeout when:

- The remote host is on a high-latency network that is known and has a clear SLA.
- Some new connections hang for a long time due to network paths or firewalls.
- You want to fail fast so an upper service layer can execute a fallback.
- An appropriate retry policy exists for transient connection errors.

Do not increase the connect timeout simply because the pool is full or the server is slow to process. Before changing it, check DNS latency, connect latency, pool pending counts, and TLS handshake metrics.

## 4. Connection Pool Pending Acquire Timeout

### 4.1. Why Wait to Acquire a Connection?

Reactor Netty `HttpClient` typically uses a connection pool. The pool retains created connections for reuse. When a new request arrives:

1. If a suitable idle connection is available, the pool grants that connection.
2. If the connection limit has not been reached, the pool can create a new connection.
3. If §maxConnections§ is reached, the request may have to wait in the pending queue.
4. If it waits too long, §pendingAcquireTimeout§ emits an error.
5. If the pending queue is full, the new request may be rejected immediately.

§pendingAcquireTimeout§ is not the time to open a TCP connection. It is the time spent waiting for a connection to be returned or granted from the pool. When the wait time expires, Reactor Netty typically emits §PoolAcquireTimeoutException§; the exception may be wrapped by the connector layer or the application's error handler.

### 4.2. Configuring ConnectionProvider

Example pool limits per remote host:

~~~java
ConnectionProvider provider =
    ConnectionProvider.builder("catalog-pool")
        .maxConnections(50)
        .pendingAcquireMaxCount(100)
        .pendingAcquireTimeout(Duration.ofSeconds(2))
        .maxIdleTime(Duration.ofSeconds(20))
        .maxLifeTime(Duration.ofMinutes(5))
        .evictInBackground(Duration.ofSeconds(30))
        .build();
~~~

Meaning:

| Configuration | Role |
| --- | --- |
| §maxConnections§ | Maximum number of connections per pool/remote host. |
| §pendingAcquireMaxCount§ | Maximum number of requests held in the queue waiting for a connection. |
| §pendingAcquireTimeout§ | Maximum time a request may wait in the pending queue. |
| §maxIdleTime§ | Maximum idle age before a connection is eligible for eviction. |
| §maxLifeTime§ | Maximum age of a connection, even when reused. |
| §evictInBackground§ | Interval for checking and evicting expired connections in the background. |

Reactor Netty currently documents a default pending acquire timeout of 45 seconds. Default connection counts can depend on how `HttpClient`/`ConnectionProvider` is created and the version; configure `maxConnections`, `pendingAcquireMaxCount`, and `pendingAcquireTimeout` explicitly for your workload.

### 4.3. Pool Saturation Is Not Connect Timeout

Suppose the pool for a host only allows 20 connections and all 20 are busy:

- The 21st request can enter the pending queue.
- If a connection is returned within 2 seconds, the request can proceed.
- If 2 seconds elapse without a connection, the request receives a pool acquire timeout.
- The request has not started a new TCP connect yet, so increasing connect timeout will not help this request.

An overly long queue only increases latency and holds more requests in the system. The pending queue should be bounded; an unbounded queue can turn transient overload into prolonged latency and memory consumption.

### 4.4. Choosing maxConnections and Queue Size

Do not set `maxConnections` huge just to eliminate acquire timeouts. Too many concurrent connections can put pressure on:

- The remote service and the database behind it.
- File descriptors and sockets.
- Event loops, TLS state, and direct memory.
- NAT gateways, firewalls, and load balancers.
- Threads/queues in downstream layers.

Choose limits based on the remote service's capacity, actual concurrent requests, and how long a request holds a connection. Keep the pending queue small enough to absorb short bursts without masking prolonged overload.

### 4.5. maxIdleTime and Stale Connections

If the server or load balancer closes idle connections after 30 seconds, the client should consider setting §maxIdleTime§ less than or equal to that idle timeout interval. This reduces the chance of borrowing a connection that the remote peer has already closed while idle.

§maxLifeTime§ limits the overall age of a connection. It is not a request timeout. §evictInBackground§ enables periodic pool checks rather than checking only during acquire/release.

## 5. Reactor Netty Response Timeout

### 5.1. Response Timeout Is the Interval Between Reads

Reactor Netty §HttpClient.responseTimeout(Duration)§ defines the maximum time allowed between network-level read operations while receiving a response.

~~~java
HttpClient httpClient = HttpClient.create()
    .responseTimeout(Duration.ofSeconds(3));
~~~

This is the **maximum read-operation interval**, not a limit on the total duration from sending the request until the body finishes.

Example:

- The server sends response headers and then stays silent for 5 seconds before the first chunk.
- The client sets `responseTimeout` to 2 seconds.
- The client can time out because the wait between reads exceeds 2 seconds.

With a streaming response, if the server steadily sends a chunk every second, the stream can run longer than 2 seconds in total without violating a 2-second `responseTimeout`. Conversely, a stream that stops emitting data partway through can time out when the silent gap exceeds the threshold.

### 5.2. Configuring responseTimeout

~~~java
HttpClient httpClient = HttpClient.create()
    .responseTimeout(Duration.ofSeconds(3));

WebClient client = WebClient.builder()
    .clientConnector(
        new ReactorClientHttpConnector(httpClient)
    )
    .build();
~~~

Reactor Netty currently does not set a default `responseTimeout`. Documentation recommends configuring an appropriate response timeout rather than allowing a response to wait silently forever.

### 5.3. responseTimeout vs. ReadTimeoutHandler

Netty §ReadTimeoutHandler§ can be configured using §doOnConnected§:

~~~java
HttpClient httpClient = HttpClient.create()
    .doOnConnected(connection ->
        connection.addHandlerLast(
            new ReadTimeoutHandler(5)
        )
    );
~~~

This is a channel-level read timeout. For HTTP clients, Reactor Netty's §responseTimeout§ more clearly expresses the goal of bounding the interval between response reads and is managed along the request/response lifecycle.

Do not stack multiple read timeout handlers without understanding their ordering and lifecycle. Choose the appropriate mechanism, test against real response patterns, and clearly record which timeout is raising errors.

### 5.4. Response Timeout and Long Downloads/Streams

Do not set `responseTimeout` too short for endpoints that may send chunks far apart, such as large exports or server-sent events. For streams, choose the timeout based on the maximum valid silent interval, not the total transfer time.

If you need to limit the total duration of a stream, add a separate deadline at the publisher or service layer. Also account for network speed and potentially slow client reads; response timeout is the wait interval for reading from the peer, not a body size limit.

## 6. Overall Timeout with Reactor

### 6.1. Mono.timeout(Duration)

Reactor provides the operator:

~~~java
Mono<Product> product = webClient.get()
    .uri("/products/{id}", id)
    .retrieve()
    .bodyToMono(Product.class)
    .timeout(Duration.ofSeconds(8));
~~~

With `Mono`, `timeout` bounds the time from subscription until the publisher emits a value or terminal signal. It encompasses acquire wait, DNS/connect, TLS, request write, server response, and body decoding within the same publisher chain.

If the deadline is exceeded, Reactor emits §java.util.concurrent.TimeoutException§ and cancels the upstream subscription. Cancellation propagates down to WebClient/transport to stop work if possible.

### 6.2. Flux.timeout(Duration) Is Not an Overall Deadline

With `Flux`, §timeout(Duration)§ typically limits the wait time for the next signal. If the stream keeps emitting items at intervals shorter than the timeout, the stream can run for a very long time.

Example:

~~~java
Flux<Event> events = webClient.get()
    .uri("/events")
    .retrieve()
    .bodyToFlux(Event.class)
    .timeout(Duration.ofSeconds(10));
~~~

This emits an error when there is a 10-second silent gap between signals; it does not mean the entire event stream must finish within 10 seconds.

If the business requirement needs a wall-clock deadline for the stream, design a separate deadline/cancellation mechanism at the caller layer. Do not use §timeout(Duration)§ on `Flux` assuming it is a total duration limit.

### 6.3. Specialized Timeouts and Overall Timeouts Complement Each Other

Specialized timeouts help pinpoint the stage:

- Pending acquire timeout: the pool did not grant a connection in time.
- Connect timeout: failed to establish a TCP connection in time.
- Response timeout: the response had no further data to read within the allowed interval.
- TLS handshake timeout: the TLS handshake did not finish in time.

The overall timeout protects the SLA of the end-to-end operation. For example, a service sets an 8-second deadline while allowing at most 1 second for acquire, 2 seconds for connect, and a 3-second maximum response read gap. Sub-timeouts should be designed so they do not conflict with the overall deadline.

If the overall deadline is shorter than a sub-timeout, the overall timeout can fire first. This is intentional if the service cannot wait longer than its SLA.

## 7. DNS, TLS, and Proxy Timeouts

Not every stage uses the same setting:

| Stage | Mechanism | Notes |
| --- | --- | --- |
| DNS lookup | Resolver timeout/cache | Occurs before TCP connect; depends on resolver. |
| Connection pool wait | pendingAcquireTimeout | Only when the pool has to wait for a connection. |
| TCP connect | CONNECT_TIMEOUT_MILLIS | Only when creating a new connection. |
| TLS handshake | handshakeTimeout | Applies when connecting via HTTPS/TLS. |
| Proxy connect | ProxyProvider connect timeout | Has separate configuration when routing through a proxy. |
| Response read | responseTimeout | Limits the interval between network reads. |
| Publisher deadline | Mono/Flux timeout | Set by the application on the reactive chain. |

TLS handshake timeout currently defaults to 10 seconds in Reactor Netty; proxy connect timeout also has its own default. Default values vary by version and transport configuration. If requests use a proxy or HTTPS, include those steps in the timeout budget.

TCP keepalive is a different mechanism: it sends probes on idle connections to detect lost peers or broken network paths. Keepalive does not replace connect timeout, response timeout, or application deadlines.

## 8. Complete WebClient Configuration with ConnectionProvider

The example below uses Java 17, Spring Boot 3.3.5, and Reactor Netty. The numbers are merely an illustrative baseline for a catalog client; adjust them according to your remote service's SLA and capacity.

### 8.1. Configuring ConnectionProvider and HttpClient

~~~java
package demo;

import java.time.Duration;

import io.netty.channel.ChannelOption;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.netty.resources.ConnectionProvider;
import reactor.netty.http.client.HttpClient;

@Configuration
class CatalogWebClientConfig {

    @Bean(destroyMethod = "dispose")
    ConnectionProvider catalogConnectionProvider() {
        return ConnectionProvider.builder("catalog-pool")
            .maxConnections(50)
            .pendingAcquireMaxCount(100)
            .pendingAcquireTimeout(Duration.ofSeconds(2))
            .maxIdleTime(Duration.ofSeconds(20))
            .maxLifeTime(Duration.ofMinutes(5))
            .evictInBackground(Duration.ofSeconds(30))
            .build();
    }

    @Bean
    WebClient catalogWebClient(
            ConnectionProvider catalogConnectionProvider) {

        HttpClient httpClient = HttpClient
            .create(catalogConnectionProvider)
            .option(
                ChannelOption.CONNECT_TIMEOUT_MILLIS,
                2_000
            )
            .responseTimeout(Duration.ofSeconds(3));

        return WebClient.builder()
            .baseUrl("https://catalog.example.test")
            .clientConnector(
                new ReactorClientHttpConnector(httpClient)
            )
            .build();
    }
}
~~~

`ConnectionProvider` is a lifecycle-managed resource. When creating a dedicated provider, register it as a Spring bean so it is disposed when the ApplicationContext closes. If using default global Reactor Netty resources, they are shared and typically live for the lifetime of the process; do not create and dispose a new pool for every request.

### 8.2. Service Setting an Overall Deadline

~~~java
package demo;

import java.time.Duration;

import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

record Product(String id, String name) {}

@Service
class CatalogService {

    private final WebClient client;

    CatalogService(WebClient catalogWebClient) {
        this.client = catalogWebClient;
    }

    Mono<Product> findProduct(String id) {
        return client.get()
            .uri("/products/{id}", id)
            .retrieve()
            .bodyToMono(Product.class)
            .timeout(Duration.ofSeconds(8));
    }
}
~~~

`HttpClient` manages connect/response timeouts; `ConnectionProvider` manages pool acquire; the service manages the overall deadline. When a timeout occurs, record the specific stage/error so operations can distinguish pool saturation, connect failure, response stall, and SLA deadline expiration.

### 8.3. Configuring Different Workloads

You do not have to use a single timeout for every endpoint. For example:

- Catalog lookup: small responses, short deadline.
- Report export: long response stream, larger deadline and suitable response read gap.
- Upload: large request body, write timeout and overall deadline designed for throughput.
- Long polling/SSE: responses can last long; response timeout must exceed the maximum heartbeat interval or be designed around the protocol.

You can create multiple WebClients/HttpClients configured separately per remote service or workload. Avoid creating a client/pool per invocation because that loses reuse benefits and creates too many connection pools.

## 9. Timeout Budgets and How to Choose Values

### 9.1. Starting from the End-to-End SLA

Suppose a service must complete a catalog request in at most 8 seconds. An illustrative budget might be:

| Stage | Illustrative Budget |
| --- | ---: |
| Pool acquire wait | 1 second |
| DNS and TCP connect | 2 seconds |
| TLS handshake | 1 second |
| Wait/read response | 3 seconds max silent gap |
| Entire Mono deadline | 8 seconds |

This is not a simple additive formula guaranteeing every case; some stages only happen when creating a new connection, and response timeout is the interval between reads rather than total read time. Use real latency measurements to set thresholds.

### 9.2. Choosing Timeouts by Percentile

Measure stage latencies in production or staging:

- p50: typical latency.
- p95: slow tail for most requests.
- p99/p99.9: extreme tail latency.
- Error rate and timeout rate by remote host.
- Pending acquire time and pending request count.

Timeouts should generally sit above valid latency at the target percentile while remaining short enough to protect the caller. If set too low, valid requests get canceled and retries can amplify load. If set too high, failing requests hold connections and resources too long.

### 9.3. Timeouts Are Not Concurrency Limits

Timeouts only limit how long to wait. They do not replace:

- `maxConnections`.
- `pendingAcquireMaxCount`.
- Rate limiting.
- Bulkheads/semaphores.
- Circuit breakers.
- Request body and response body size limits.

A pool with reasonable timeouts but a huge queue can still accumulate too many requests. Bound both the amount of concurrent work and its lifetime.

## 10. Retries and Timeouts Must Be Designed Together

Retries can help overcome transient network errors, but retries also create new requests and consume additional connections.

### 10.1. Retrying with Backoff and Attempt Limits

~~~java
Mono<Product> load(String id) {
    return client.get()
        .uri("/products/{id}", id)
        .retrieve()
        .bodyToMono(Product.class)
        .retryWhen(
            Retry.backoff(2, Duration.ofMillis(100))
                .maxBackoff(Duration.ofSeconds(1))
        )
        .timeout(Duration.ofSeconds(8));
}
~~~

The example allows up to two retries with exponential backoff and an 8-second overall deadline. The deadline covers the entire retry sequence because the `timeout` operator is placed outside `retryWhen`.

In a real application, add a filter on exception/status types; do not retry every error.

### 10.2. Do Not Retry Errors That Retrying Cannot Fix

Normally, do not blindly retry:

- 400 validation errors.
- 401/403 authentication/authorization errors.
- 404 when the resource genuinely does not exist.
- Pool acquire timeouts caused by prolonged system overload.
- Response decode errors caused by malformed payloads.

Some connect/reset/503 errors may be transient, but require an explicit per-API policy.

### 10.3. Beware Non-Idempotent Operations

If a POST creating an order times out after the server processed it but before the client received the response, the client does not know whether the operation completed. Retrying can create duplicate orders.

For non-idempotent operations:

- Use an idempotency key or request ID stored and checked by the server.
- Retry only when the API contract guarantees safety.
- Provide a lookup mechanism if the client does not know whether the previous attempt succeeded.

### 10.4. Deadlines Must Account for Retries

If each retry attempt has an 8-second timeout and you retry 3 times, total time can exceed 24 seconds plus backoff. Place the overall deadline outside the retry chain to preserve the SLA:

~~~java
return oneAttempt()
    .retryWhen(retryPolicy)
    .timeout(Duration.ofSeconds(8));
~~~

If you place a timeout inside each attempt, that timeout only limits a single call; it does not limit the total number of attempts or backoff duration.

## 11. Metrics and Timeout Diagnostics

When using Reactor Netty, enable metrics for the connection pool/HttpClient if the application has Micrometer configured:

~~~java
ConnectionProvider provider =
    ConnectionProvider.builder("catalog-pool")
        .maxConnections(50)
        .pendingAcquireMaxCount(100)
        .pendingAcquireTimeout(Duration.ofSeconds(2))
        .metrics(true)
        .build();
~~~

Important metrics may include:

| Metric | Meaning |
| --- | --- |
| §reactor.netty.connection.provider.active.connections§ | Number of connections currently in use. |
| §reactor.netty.connection.provider.idle.connections§ | Number of idle connections in the pool. |
| §reactor.netty.connection.provider.pending.connections§ | Number of requests waiting for a connection. |
| §reactor.netty.connection.provider.max.connections§ | Pool connection limit. |
| §reactor.netty.connection.provider.pending.connections.time§ | Time spent waiting to acquire a connection. |
| §reactor.netty.http.client.connect.time§ | Time to establish a connection. |
| §reactor.netty.http.client.tls.handshake.time§ | TLS handshake duration. |
| §reactor.netty.http.client.errors§ | HTTP client error count. |
| §reactor.netty.http.client.response.time§ | Request/response duration per client metrics. |

Exact metric names and tags depend on the Reactor Netty version, transport, and Micrometer registry. Check the metrics actually exported rather than assuming every metric is available.

### 11.1. Reading Operational Signals

| Observation | Possible Cause | What to Check |
| --- | --- | --- |
| Pending connections rising, active hitting max | Pool saturation | `maxConnections`, request concurrency, unconsumed bodies |
| Pending acquire timeouts rising | Connections not returned in time | Downstream latency, pool limits, connection leaks |
| Connect time rising | DNS/network/TCP path | DNS resolver, firewalls, remote reachability |
| TLS handshake time rising | TLS server/certificate/network | TLS config, handshake latency, proxy |
| Response timeouts rising | Server stopped sending or read gap too long | Remote latency, slow streaming, network stalls |
| Overall Mono timeouts rising while individual timeouts stay low | Sum of stages or retries/backoff exceeding SLA | Trace per phase, deadline, and retry count |
| Connection reset/premature close | Peer/proxy closing connection or network interruption | Idle timeout alignment, stale connections, proxy/load balancer |

Do not diagnose from exception messages alone. Combine metrics, traces, remote host, request ID, and phase timings.

## 12. Common Mistakes and How to Fix Them

| Mistake | Consequence | How to Fix |
| --- | --- | --- |
| Confusing pending acquire timeout with connect timeout | Increasing the wrong timeout while requests still wait on the pool | Check pending queue and configure `ConnectionProvider` |
| Thinking responseTimeout is total request duration | Long streams can still run long if data arrives steadily | Use a separate overall deadline |
| Using Mono.timeout as a dedicated TCP timeout | Cannot tell which phase slowed down | Configure dedicated connect/acquire/response timeouts |
| Not setting a response timeout | Responses can hang silently too long | Set `responseTimeout` per API contract |
| Setting responseTimeout too short for SSE | Valid streams time out when no events arrive | Choose a read-gap suited to the heartbeat |
| Increasing maxConnections to hide pool saturation | Increases load on remote service and network | Measure concurrency/latency, bound queues and bulkheads |
| Unbounded pending queue | Requests accumulate, memory and latency grow | Set a bounded `pendingAcquireMaxCount` |
| Retrying every exception | Amplifies load on permanent errors or overload | Retry with filters, backoff, jitter, and limits |
| Retrying POST without idempotency | Creates duplicate data | Use idempotency keys or do not retry |
| Setting timeout per attempt without an overall deadline | Total duration exceeds SLA | Place `timeout` outside the retry chain |
| Ignoring DNS/TLS/proxy | Misdiagnosing which stage is slow | Monitor resolver, handshake, and proxy timeouts |
| Using one timeout for every endpoint | File streams/SSE get cut off | Configure per workload/remote service |
| Creating a ConnectionProvider per request | Loses pooling and opens many sockets | Use shared providers per remote/workload |
| Not disposing custom providers | Client resources remain alive after context closes | Manage lifecycle via Spring beans |
| Looking only at exceptions without monitoring pool metrics | Cannot distinguish overload from network failure | Enable metrics and trace by phase |

## 13. Runnable Java 17 Example and Timeout Testing

The example uses Spring Boot 3.3.5, Java 17, WebFlux, and MockWebServer. Tests use a local server to produce slow responses and pool contention; they do not depend on the Internet or any external IP address.

### 13.1. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
    testImplementation 'com.squareup.okhttp3:mockwebserver:4.12.0'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

### 13.2. WebClientTimeoutApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebClientTimeoutApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebClientTimeoutApplication.class, args);
    }
}
~~~

### 13.3. CatalogClientConfiguration.java

~~~java
package demo;

import java.time.Duration;

import io.netty.channel.ChannelOption;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;

@Configuration
class CatalogClientConfiguration {

    @Bean(destroyMethod = "dispose")
    ConnectionProvider catalogPool() {
        return ConnectionProvider.builder("catalog")
            .maxConnections(20)
            .pendingAcquireMaxCount(40)
            .pendingAcquireTimeout(Duration.ofSeconds(1))
            .maxIdleTime(Duration.ofSeconds(20))
            .maxLifeTime(Duration.ofMinutes(5))
            .evictInBackground(Duration.ofSeconds(30))
            .metrics(true)
            .build();
    }

    @Bean
    WebClient catalogWebClient(ConnectionProvider catalogPool) {
        HttpClient httpClient = HttpClient.create(catalogPool)
            .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 2_000)
            .responseTimeout(Duration.ofSeconds(3));

        return WebClient.builder()
            .baseUrl("https://catalog.example.test")
            .clientConnector(
                new ReactorClientHttpConnector(httpClient)
            )
            .build();
    }
}
~~~

Actuator puts Micrometer on the classpath so metrics can be exported through an appropriate registry. Metrics configuration alone does not create dashboards; the application needs a registry/exporter and corresponding endpoint/monitoring configuration.

### 13.4. TimeoutClient.java

~~~java
package demo;

import java.time.Duration;
import java.util.concurrent.TimeoutException;

import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

record Item(String id, String name) {}

@Component
class TimeoutClient {

    private final WebClient client;

    TimeoutClient(WebClient catalogWebClient) {
        this.client = catalogWebClient;
    }

    Mono<Item> getItem(String id) {
        return client.get()
            .uri("/items/{id}", id)
            .retrieve()
            .bodyToMono(Item.class)
            .timeout(Duration.ofSeconds(8));
    }

    Mono<Item> getItemWithMappedDeadline(String id) {
        return getItem(id)
            .onErrorMap(
                TimeoutException.class,
                error -> new CatalogDeadlineExceededException(
                    "Catalog call exceeded its deadline"
                )
            );
    }
}

class CatalogDeadlineExceededException extends RuntimeException {
    CatalogDeadlineExceededException(String message) {
        super(message);
    }
}
~~~

### 13.5. TimeoutClientTest.java

~~~java
package demo;

import java.io.IOException;
import java.time.Duration;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import reactor.core.Disposable;
import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;

import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertNotNull;

class TimeoutClientTest {

    private MockWebServer server;

    @BeforeEach
    void startServer() throws IOException {
        server = new MockWebServer();
        server.start();
    }

    @AfterEach
    void stopServer() throws IOException {
        server.shutdown();
    }

    private WebClient createClient(
            ConnectionProvider provider,
            Duration responseTimeout) {

        HttpClient httpClient = HttpClient.create(provider)
            .responseTimeout(responseTimeout);

        return WebClient.builder()
            .baseUrl(server.url("/").toString())
            .clientConnector(
                new ReactorClientHttpConnector(httpClient)
            )
            .build();
    }

    @Test
    void responseTimeoutFailsWhenReadGapIsTooLong() {
        ConnectionProvider provider =
            ConnectionProvider.newConnection();

        try {
            WebClient client = createClient(
                provider,
                Duration.ofMillis(150)
            );

            server.enqueue(new MockResponse()
                .setResponseCode(200)
                .setBodyDelay(500, TimeUnit.MILLISECONDS)
                .setBody("{\"id\":\"1\",\"name\":\"slow\"}"));

            StepVerifier.create(
                    client.get()
                        .uri("/slow")
                        .retrieve()
                        .bodyToMono(String.class)
                )
                .expectError()
                .verify(Duration.ofSeconds(3));
        }
        finally {
            provider.disposeLater().block(Duration.ofSeconds(2));
        }
    }

    @Test
    void pendingAcquireTimeoutFailsWhenPoolIsBusy() throws Exception {
        ConnectionProvider provider =
            ConnectionProvider.builder("one-connection-test")
                .maxConnections(1)
                .pendingAcquireMaxCount(1)
                .pendingAcquireTimeout(Duration.ofMillis(100))
                .build();

        try {
            WebClient client = createClient(
                provider,
                Duration.ofSeconds(3)
            );

            server.enqueue(new MockResponse()
                .setResponseCode(200)
                .setBodyDelay(800, TimeUnit.MILLISECONDS)
                .setBody("first"));

            server.enqueue(new MockResponse()
                .setResponseCode(200)
                .setBody("second"));

            Disposable firstRequest = client.get()
                .uri("/first")
                .retrieve()
                .bodyToMono(String.class)
                .subscribe();

            try {
                RecordedRequest received =
                    server.takeRequest(1, TimeUnit.SECONDS);
                assertNotNull(received);

                StepVerifier.create(
                        client.get()
                            .uri("/second")
                            .retrieve()
                            .bodyToMono(String.class)
                    )
                    .expectError()
                    .verify(Duration.ofSeconds(2));
            }
            finally {
                firstRequest.dispose();
            }
        }
        finally {
            provider.disposeLater().block(Duration.ofSeconds(2));
        }
    }

    @Test
    void monoTimeoutIsAnEndToEndDeadline() {
        ConnectionProvider provider =
            ConnectionProvider.newConnection();

        try {
            WebClient client = createClient(
                provider,
                Duration.ofSeconds(2)
            );

            server.enqueue(new MockResponse()
                .setResponseCode(200)
                .setBodyDelay(500, TimeUnit.MILLISECONDS)
                .setBody("{\"id\":\"1\",\"name\":\"slow\"}"));

            StepVerifier.create(
                    client.get()
                        .uri("/slow")
                        .retrieve()
                        .bodyToMono(String.class)
                        .timeout(Duration.ofMillis(100))
                )
                .expectError(TimeoutException.class)
                .verify(Duration.ofSeconds(2));
        }
        finally {
            provider.disposeLater().block(Duration.ofSeconds(2));
        }
    }
}
~~~

The tests have three distinct goals:

- Response timeout: the server stops sending body data longer than the allowed read interval.
- Pending acquire timeout: the pool only has one connection, which is busy; the second request must wait and times out acquiring.
- Mono timeout: response timeout is longer, yet the publisher's overall deadline is shorter so the operation still times out.

Connect timeout is difficult to test reliably using a public IP address or an unroutable address because results depend on the OS, firewalls, and CI network. In production, verify the connector configuration and optionally use a TCP proxy/test harness capable of delaying SYN/connect to validate this phase specifically.

### 13.6. Running the Tests

~~~bash
./gradlew test
~~~

On Windows:

~~~powershell
.\gradlew.bat test
~~~

The tests use short durations to finish quickly in CI. When running on a heavily loaded machine, the scheduler and OS can cause timing jitter; if more stable testing is needed, widen the gap between delays and timeouts, and avoid asserting overly specific transport exception classes if connector versions may wrap exceptions differently.

## 14. Production Timeout Configuration Checklist

Before putting WebClient into production, check:

1. **Remote service:** Are the remote host/port and SLA clearly defined?
2. **Connection pool:** Does `maxConnections` match downstream capacity?
3. **Pending queue:** Is `pendingAcquireMaxCount` bounded and small enough?
4. **Acquire timeout:** Does pool wait time fit the caller's deadline?
5. **Connect timeout:** Does TCP connect fail fast when the network is unresponsive?
6. **DNS/TLS/proxy:** Do these stages have appropriate timeouts and metrics?
7. **Response timeout:** Does the allowed silent interval suit JSON, download streams, SSE, or long polling?
8. **Overall deadline:** Does the Mono/service have a deadline covering all stages and retries?
9. **Retry:** Do retries target only transient errors, with backoff/jitter and idempotency?
10. **Cancellation:** On timeout, are upstream requests/responses canceled and resources released?
11. **Metrics:** Are active/idle/pending connections, acquire time, connect time, TLS time, and response time monitored?
12. **Lifecycle:** Is a custom `ConnectionProvider` disposed when the application context closes?
13. **Testing:** Are pool saturation, response stalls, end-to-end deadlines, and error mapping tested?
14. **Workload:** Do file streams/SSE have dedicated timeouts suited to valid silent intervals?

**Key Takeaways:** pending acquire timeout limits wait time for a connection in the pool; connect timeout limits opening a new TCP connection; response timeout limits the interval between response reads; Reactor `timeout` bounds the publisher per Mono/Flux semantics. Measure the right phase, set a timeout budget aligned with the SLA, bound both connections and the pending queue, and design retries/cancellation to avoid overloading the system when a downstream is slow.

## References

- Reactor Netty — HTTP Client, Connection Pool and Timeout Configuration: https://projectreactor.io/docs/netty/release/reference/http-client.html
- Reactor Netty — HttpClientRequest responseTimeout API: https://projectreactor.io/docs/netty/release/api/reactor/netty/http/client/HttpClientRequest.html
- Spring Framework — WebClient Configuration and Reactor Netty Connector: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html
- Spring Framework — WebClient API and usage: https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html
- Spring Boot — Configure the Reactor Netty client used by WebClient: https://docs.spring.io/spring-boot/how-to/http-clients.html
