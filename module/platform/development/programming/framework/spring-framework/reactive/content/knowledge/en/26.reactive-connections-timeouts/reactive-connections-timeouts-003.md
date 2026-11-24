# Connection Pool, Connection Limits, and Pending Queue in Spring WebClient

WebClient typically runs on Reactor Netty and reuses HTTP connections through a connection pool. When a request needs to be sent, the client borrows an idle connection from the pool. If no idle connection is available and the pool has reached its limit, the request must wait for a connection to be returned or fail when the pending queue is full or times out.

Pool configuration directly affects latency, throughput, and the system's ability to protect itself under increasing load. A pool that is too small can cause many requests to wait and time out. A pool that is too large can open too many connections to the upstream, increasing sockets, file descriptors, TLS handshakes, and load on the remote service. An unbounded queue can turn a transient overload into prolonged latency and memory consumption.

This lesson belongs to the **Connections and Timeouts** topic and focuses on Reactor Netty's `ConnectionProvider`, connection limits, the pending acquire queue, timeout types, connection lifecycle, metrics, and how to choose appropriate configurations for WebClient.

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain how a connection pool enables TCP connection reuse.
- Distinguish `WebClient`, `ReactorClientHttpConnector`, `HttpClient`, and `ConnectionProvider`.
- Configure `maxConnections` for a pool.
- Limit waiting requests using `pendingAcquireMaxCount`.
- Set `pendingAcquireTimeout` to limit how long requests wait to acquire a connection.
- Distinguish acquire timeout, connect timeout, response timeout, and overall timeout.
- Use `maxIdleTime`, `maxLifeTime`, and eviction to manage aging connections.
- Understand the difference between HTTP/1.1 and HTTP/2 when calculating concurrency.
- Monitor active, idle, pending, and total connections using metrics.
- Estimate pool size based on request rate and processing time.
- Manage the lifecycle of `ConnectionProvider` and shared resources.
- Test connection limits and the pending queue using MockWebServer.

## 2. What Problem Does a Connection Pool Solve?

Establishing a TCP connection has overhead: DNS lookup, TCP handshake, TLS handshake if using HTTPS, protocol negotiation, and other initialization steps. If every HTTP request creates a new connection, the application pays this cost repeatedly and creates many short-lived sockets.

A connection pool retains reusable connections. When a request completes, the connection is usually returned to the pool for another request to reuse, provided the connection is still valid and the protocol allows it.

~~~text
Request A ----+
Request B ----+----> Connection pool ----> HTTP upstream
Request C ----+         |
                         +-- active connection
                         +-- idle connection
                         +-- pending acquire queue
~~~

States to distinguish:

- **Active connection:** currently in use for one or more exchanges/streams.
- **Idle connection:** returned to the pool and available to be granted to another request.
- **Pending acquire:** a request waiting to be granted a connection.
- **Total connection:** total connections currently managed by the pool, typically comprising active and idle connections.
- **Maximum connection:** the limit on connections the pool is allowed to create for a remote destination.

With standard HTTP/1.1, one connection typically serves one request-response exchange at a time. With HTTP/2, one connection can multiplex multiple concurrent streams, so the number of connections does not equal the number of running requests.

## 3. Components in the WebClient Connection Stack

In a WebFlux application using Reactor Netty, the components are typically wired as follows:

~~~text
Application service
       |
       v
WebClient
       |
       v
ReactorClientHttpConnector
       |
       v
Reactor Netty HttpClient
       |
       v
ConnectionProvider
       |
       v
TCP / TLS connection pool
       |
       v
Remote HTTP service
~~~

Role of each component:

- **WebClient:** high-level API for building requests, declaring headers/bodies, and decoding responses.
- **ReactorClientHttpConnector:** adapter connecting WebClient to a concrete HTTP client.
- **HttpClient:** Reactor Netty transport configuration, such as connect timeout, response timeout, proxy, and TCP options.
- **ConnectionProvider:** manages the pool, max connections, pending queue, acquire wait time, idle/lifetime limits, and metrics.
- **Remote service:** the upstream called by the client.

Not every WebClient is required to use Reactor Netty. WebClient can use other connectors. The `ConnectionProvider` configurations in this lesson apply to Reactor Netty; if the application uses Jetty or another connector, use the corresponding pool mechanism.

## 4. maxConnections: Limiting the Number of Connections

With Reactor Netty, create a `ConnectionProvider` using the builder:

~~~java
ConnectionProvider provider = ConnectionProvider.builder("catalog-pool")
    .maxConnections(50)
    .build();
~~~

`maxConnections` sets the limit on connections in the pool for a remote destination. Pools are managed per remote address; when a WebClient calls multiple different hosts, each destination can have its own pool as managed by `ConnectionProvider`.

Examples:

- `maxConnections = 1`: at most one connection to the destination.
- `maxConnections = 20`: at most twenty connections to the destination.
- `maxConnections = 100`: can maintain up to one hundred connections to the destination, if load and pool demand reach that level.

Do not pick a large number just to eliminate the pending queue. The connection count must match upstream capacity, machine socket limits, the number of application instances, and truly concurrent requests.

### maxConnections Is Not an Application-Wide Request Limit

If an application has three WebClients using three different `ConnectionProvider`s, each pool can have its own limit. If they share the same provider and call the same destination, they can share the corresponding pool.

A service with multiple instances also needs to account for total load:

~~~text
Number of application instances × maxConnections per instance
    = potential connection limit to upstream
~~~

For example, 8 instances, each with a pool of up to 40 connections, can open up to 320 connections to the same upstream. The upstream must have sufficient capacity to serve this total.

## 5. pendingAcquireMaxCount: Limiting the Pending Queue

When all connections are busy, new requests can be placed in a queue waiting to acquire a connection. Reactor Netty lets you limit the number of waiting requests with `pendingAcquireMaxCount`.

~~~java
ConnectionProvider provider = ConnectionProvider.builder("catalog-pool")
    .maxConnections(50)
    .pendingAcquireMaxCount(100)
    .build();
~~~

Meaning:

- **0:** do not allow requests to queue when no connection is available; requests unable to acquire a connection are rejected.
- **Positive number:** at most that many requests may wait to acquire a connection.
- **-1:** unbounded queue; use caution because traffic spikes can create a very long queue.

Example with `maxConnections = 2` and `pendingAcquireMaxCount = 3`:

~~~text
Connection #1: in use by Request A
Connection #2: in use by Request B

Pending queue:
  1. Request C
  2. Request D
  3. Request E

Request F:
  Rejected because the queue is full
~~~

The pending queue is where requests wait to be granted a connection, not where bodies or responses are buffered. Requests remain subject to timeouts and cancellation. If the queue is full, Reactor Netty can emit an error like `PoolAcquirePendingLimitException`.

### Why Should You Avoid an Unbounded Queue?

A long queue can hide insufficient upstream capacity. Requests remain in memory, response times climb, and many requests may expire before being processed.

An unbounded queue often prolongs overload conditions:

1. Load exceeds upstream capacity.
2. Waiting requests accumulate in the pending queue.
3. Wait times increase.
4. Clients time out and retry.
5. Retries generate additional new requests.
6. The system absorbs even more load while already overloaded.

Choose a bounded queue, clear timeouts, and an appropriate backpressure/rejection policy. A queue only absorbs short bursts; it cannot fix a system whose average load exceeds capacity.

## 6. pendingAcquireTimeout: Wait Time to Acquire a Connection

`pendingAcquireTimeout` limits how long a request can wait in the pending queue to be granted a connection.

~~~java
ConnectionProvider provider = ConnectionProvider.builder("catalog-pool")
    .maxConnections(50)
    .pendingAcquireMaxCount(100)
    .pendingAcquireTimeout(Duration.ofSeconds(2))
    .build();
~~~

In the example, a request waits at most two seconds to acquire a connection. If no connection becomes available within that time, the publisher emits an acquire timeout error, typically `PoolAcquireTimeoutException`.

These two limits solve two different problems:

| Configuration | Limits |
| --- | --- |
| maxConnections | Number of connections created/held in the pool |
| pendingAcquireMaxCount | Number of requests waiting to be granted a connection |
| pendingAcquireTimeout | Time each request is allowed to wait for a connection |

A request may fail immediately because the queue is full, or wait for a period and then fail because `pendingAcquireTimeout` expired.

### The Queue Is Not an Overall Timeout

`pendingAcquireTimeout` only measures the time spent waiting to acquire a connection. After getting a connection, the request may still spend time connecting, sending the request, waiting for the response, and reading the body. Therefore, other timeouts must be configured separately.

## 7. Distinguishing Timeout Types

WebClient/Reactor Netty has multiple timeouts at different stages. Using the wrong timeout can cause the application to hang longer than expected or cancel requests too early.

| Timeout | Where Does It Begin to Apply? | Common Configuration |
| --- | --- | --- |
| Pending acquire timeout | Waiting to borrow a connection from the pool | ConnectionProvider.pendingAcquireTimeout |
| Connect timeout | Establishing a new TCP connection | ChannelOption.CONNECT_TIMEOUT_MILLIS |
| TLS handshake timeout | TLS negotiation when using HTTPS | HttpClient secure configuration |
| Response timeout | Interval waiting between network data reads | HttpClient.responseTimeout |
| Read/write timeout | Network read or write via handlers | Netty ReadTimeoutHandler/WriteTimeoutHandler |
| Overall operation timeout | Entire publisher of the operation | Reactor Mono/Flux.timeout |

### Connect Timeout

Connect timeout limits the time to establish a new TCP connection. It is not the time spent waiting to borrow a connection from the pool. If the pool has an idle connection, the request may not need to open a new TCP connection.

~~~java
HttpClient httpClient = HttpClient.create(provider)
    .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 2_000);
~~~

The value in the example is two seconds.

### Response Timeout

Reactor Netty's `responseTimeout` sets a time limit between network data reads. It is useful for detecting when an upstream stops sending data for too long. It is not an overall timeout for the entire request.

~~~java
HttpClient httpClient = HttpClient.create(provider)
    .responseTimeout(Duration.ofSeconds(5));
~~~

A long stream can run longer than five seconds if it keeps receiving data steadily; conversely, a stream that emits no data for the configured duration can time out.

### Overall Timeout

If you want to limit the entire operation, you can place a timeout on the publisher:

~~~java
Mono<Product> product = webClient.get()
    .uri("/products/{id}", id)
    .retrieve()
    .bodyToMono(Product.class)
    .timeout(Duration.ofSeconds(8));
~~~

This timeout applies to the entire publisher from subscription time, including pool wait, connection, response, and pipeline decoding. Consider how it interacts with transport-layer timeouts.

### Do Not Mechanically Set Every Timeout to the Same Number

A sound configuration usually has a budgeted ordering:

- Short acquire timeout so requests do not queue too long.
- Connect timeout sufficient for the network/TCP handshake.
- Response timeout matched to the upstream's maximum silent interval.
- Overall timeout larger than the sum of required step budgets, while staying within the caller request's deadline.

For long-lived streams, an overall timeout may be inappropriate; use an idle timeout or protocol-specific lifetime policy instead.

## 8. maxIdleTime, maxLifeTime, and Eviction

A connection pool should not reuse a connection forever. Connections can be closed by the upstream after an idle period, network paths can change, or servers can enforce lifetime limits.

### maxIdleTime

Limits how long a connection is allowed to remain idle in the pool before being evicted.

~~~java
.maxIdleTime(Duration.ofSeconds(20))
~~~

Setting `maxIdleTime` less than or equal to the upstream/load balancer's idle timeout usually reduces the chance of borrowing a connection already closed by the peer. For example, if the upstream closes idle connections after 30 seconds, the pool can set `maxIdleTime` to around 20 seconds to evict connections beforehand.

This choice depends on the environment; check the actual timeouts of the upstream and proxies.

### maxLifeTime

Limits the maximum lifetime of a connection, even when the connection is still working well.

~~~java
.maxLifeTime(Duration.ofMinutes(5))
~~~

`maxLifeTime` helps rotate connections to avoid holding a connection too long, and can also help rebalance across upstream nodes when DNS/load balancers change. In-use connections are normally handled according to pool lifecycle rules; do not assume this setting cuts off an in-flight response mid-transfer.

### Periodic Eviction

You can instruct the pool to scan for old connections periodically:

~~~java
.evictInBackground(Duration.ofSeconds(30))
~~~

Eviction cleans up idle/expired connections on a schedule, rather than only checking when a new request needs a connection. Choose an interval suited to the pool size and operational needs.

### Combining Policies

~~~java
ConnectionProvider provider = ConnectionProvider.builder("catalog-pool")
    .maxConnections(50)
    .pendingAcquireMaxCount(100)
    .pendingAcquireTimeout(Duration.ofSeconds(2))
    .maxIdleTime(Duration.ofSeconds(20))
    .maxLifeTime(Duration.ofMinutes(5))
    .evictInBackground(Duration.ofSeconds(30))
    .build();
~~~

This is an illustrative configuration. The numbers must be measured and tuned based on latency, traffic, upstream keep-alive, and resource limits.

## 9. How Do HTTP/1.1 and HTTP/2 Affect the Pool?

With HTTP/1.1, a connection normally serves one exchange at a time. Only when the request completes and the connection is returned to the pool can another request reuse that connection.

With HTTP/2, a single TCP connection can carry multiple concurrent streams via multiplexing. Therefore:

- A single HTTP/2 connection can serve multiple concurrent requests.
- `maxConnections` no longer equals the number of concurrent requests.
- Concurrent streams per connection also depend on limits negotiated with the peer and client/server configuration.
- Increasing the connection count does not necessarily increase throughput if one HTTP/2 connection already provides enough stream capacity.

Measure which protocol is actually in use. Do not apply the HTTP/1.1 one-connection-per-request formula to HTTP/2.

## 10. Estimating Pool Size from Real Traffic

A basic estimation method uses Little's Law:

\[
L = \lambda \times W
\]

Where:

- L is the average number of requests in the system.
- λ is the arrival rate of requests, in requests/second.
- W is the average processing time, in seconds.

Example:

- The upstream receives 100 requests/second.
- Average processing time is 0.2 seconds.
- Average concurrent requests: 100 × 0.2 = 20.

The number 20 is the average concurrency under simplifying assumptions, not a mandatory `maxConnections` value. In practice, there are also bursts, p95/p99 latency, HTTP/2 multiplexing, retries, connection hold times, and upstream limits.

### Pool Selection Process

1. Measure request rate and latency per upstream.
2. Estimate average concurrency using Little's Law.
3. Inspect p95/p99 and bursts to determine headroom.
4. Check connection and concurrent request limits allowed by the upstream.
5. Calculate total pool size across all application instances.
6. Choose `maxConnections` aligned with upstream capacity.
7. Choose a small, bounded `pendingAcquireMaxCount` to absorb short bursts.
8. Choose `pendingAcquireTimeout` based on the request deadline.
9. Measure active/pending/idle counts and error rates as load rises.
10. Tune based on load test results, not just a single formula.

### Guiding Example

Suppose 4 instances, each expected to have 25 average concurrent requests to an upstream. If each instance sets `maxConnections = 40`, the potential total connection limit is 160. Before deploying, confirm the upstream can accept this many connections and has sufficient capacity to handle the corresponding requests.

Do not set `maxConnections` higher than upstream capacity just to make the pending queue appear less often. When the upstream is overloaded, you need backpressure, rate limiting, circuit breakers, or early rejection.

## 11. Monitoring Pool Metrics

Reactor Netty can export metrics for the connection provider. Enable metrics on the provider:

~~~java
ConnectionProvider provider = ConnectionProvider.builder("catalog-pool")
    .maxConnections(50)
    .pendingAcquireMaxCount(100)
    .metrics(true)
    .build();
~~~

To integrate metrics with Micrometer in Spring Boot, add the Spring Boot Actuator dependency or configure an appropriate registry.

Important metrics typically have the prefix `reactor.netty.connection.provider`:

| Metric | Meaning |
| --- | --- |
| total.connections | Total connections currently in the pool |
| active.connections | Active connections in use |
| idle.connections | Idle connections |
| pending.connections | Requests waiting for a connection |
| pending.connections.time | Wait time to acquire a connection |
| max.connections | Configured connection limit |
| max.pending.connections | Pending queue limit |

Metric names may be tagged by provider name and remote address. Check tags when querying via Micrometer/Actuator.

### How to Read Operational Signals

- **active consistently near max, pending rising:** the pool may be too small for the load or the upstream is processing slowly.
- **pending rises then drops quickly:** likely a short burst; check latency and acquire wait time.
- **pending rising alongside acquire timeouts:** requests are waiting longer than their allowed budget.
- **high idle and low active:** the pool may be holding more connections than needed; review `maxIdleTime`/`maxConnections`.
- **total connections continuously created/closed:** possible churn due to overly short idle/lifetime settings, the upstream closing connections, or mismatched pool settings.
- **pool rejections rising:** the pending queue is full or unable to grant connections; inspect load and upstream capacity.

Metrics should be tracked per upstream. Aggregating all hosts into one chart can hide a single overloaded dependency.

## 12. Managing Lifecycle and Sharing ConnectionProvider

`ConnectionProvider` is a lifecycle-managed resource. In a Spring application, create the provider as a shared bean for the corresponding WebClient, rather than creating a new one per request.

Example:

~~~java
@Bean(destroyMethod = "dispose")
ConnectionProvider catalogConnectionProvider() {
    return ConnectionProvider.builder("catalog-pool")
        .maxConnections(50)
        .pendingAcquireMaxCount(100)
        .pendingAcquireTimeout(Duration.ofSeconds(2))
        .build();
}
~~~

Spring calls `dispose` when the application context closes. This releases the pool during shutdown.

### Do Not Create a Pool per Request

Do not do the following:

~~~java
public Mono<Product> getProduct(String id) {
    ConnectionProvider provider =
        ConnectionProvider.builder("temporary").build();

    HttpClient httpClient = HttpClient.create(provider);
    WebClient client = WebClient.builder()
        .clientConnector(new ReactorClientHttpConnector(httpClient))
        .build();

    return client.get()
        .uri("https://catalog.example/products/{id}", id)
        .retrieve()
        .bodyToMono(Product.class);
}
~~~

This code recreates the provider and client on every call, losing the benefits of connection reuse, causing churn, and making disposal hard to control.

Create WebClient/`ConnectionProvider` in application configuration, then inject them into services.

### Reactor Netty Global Resources

Reactor Netty can use shared global resources. Spring Boot often integrates these shared resources to reduce the overhead of creating event loops and pools. If you create a custom provider, you must manage the lifecycle of that provider itself; do not arbitrarily dispose global resources that other clients are still using.

## 13. Complete Java 17+ Example with Spring Boot WebFlux

The example below configures a WebClient calling a Catalog API using Reactor Netty:

- `maxConnections` = 20.
- `pendingAcquireMaxCount` = 40.
- `pendingAcquireTimeout` = 1 second.
- `maxIdleTime` = 20 seconds.
- `maxLifeTime` = 5 minutes.
- connect timeout = 2 seconds.
- response timeout = 5 seconds.
- metrics enabled.
- `ConnectionProvider` is disposed when the Spring context closes.

### Project Structure

~~~text
webclient-pool-demo/
├── pom.xml
└── src
    ├── main/java/com/example/pool
    │   ├── PoolDemoApplication.java
    │   ├── WebClientPoolConfiguration.java
    │   ├── Product.java
    │   └── CatalogClient.java
    └── test/java/com/example/pool
        └── ConnectionPoolTests.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.5</version>
    <relativePath/>
  </parent>

  <groupId>com.example</groupId>
  <artifactId>webclient-pool-demo</artifactId>
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
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>io.projectreactor</groupId>
      <artifactId>reactor-test</artifactId>
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

Spring Boot 3.3.5 manages compatible versions of Spring Framework, Reactor Netty, and Micrometer. Actuator provides metrics integration; MockWebServer is used only in tests.

### PoolDemoApplication.java

~~~java
package com.example.pool;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PoolDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(PoolDemoApplication.class, args);
    }
}
~~~

### Product.java

~~~java
package com.example.pool;

public record Product(String id, String name) {
}
~~~

### WebClientPoolConfiguration.java

~~~java
package com.example.pool;

import java.time.Duration;

import io.netty.channel.ChannelOption;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;

import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;

@Configuration
public class WebClientPoolConfiguration {

    @Bean(destroyMethod = "dispose")
    ConnectionProvider catalogConnectionProvider() {
        return ConnectionProvider.builder("catalog-pool")
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
    WebClient catalogWebClient(
            WebClient.Builder builder,
            ConnectionProvider catalogConnectionProvider) {

        HttpClient httpClient = HttpClient
            .create(catalogConnectionProvider)
            .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 2_000)
            .responseTimeout(Duration.ofSeconds(5));

        String baseUrl = System.getProperty(
            "catalog.base-url", "http://localhost:8081");

        return builder
            .baseUrl(baseUrl)
            .clientConnector(
                new ReactorClientHttpConnector(httpClient))
            .build();
    }
}
~~~

Key points to note:

1. `ConnectionProvider` is created once and managed as a Spring bean.
2. `maxConnections` limits connections; `pendingAcquireMaxCount` limits waiting requests.
3. `pendingAcquireTimeout` limits wait time to acquire a connection, not the TCP timeout.
4. `CONNECT_TIMEOUT_MILLIS` limits establishing a new TCP connection.
5. `responseTimeout` limits the wait interval between network data reads.
6. `metrics(true)` enables pool metrics; Actuator/Micrometer exports and exposes the metrics for observation.
7. `destroyMethod=dispose` releases the provider when the application context closes.

### CatalogClient.java

~~~java
package com.example.pool;

import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

@Component
public class CatalogClient {

    private final WebClient webClient;

    public CatalogClient(WebClient catalogWebClient) {
        this.webClient = catalogWebClient;
    }

    public Mono<Product> findById(String id) {
        return webClient.get()
            .uri("/products/{id}", id)
            .retrieve()
            .bodyToMono(Product.class);
    }
}
~~~

`CatalogClient` receives the pool-configured `WebClient`. Do not create a connection provider inside individual methods.

## 14. Testing Connection Limits and the Pending Queue with MockWebServer

You can simulate a slow upstream to test that a second request must wait or that subsequent requests are rejected when the queue is full.

### ConnectionPoolTests.java

~~~java
package com.example.pool;

import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.time.Duration;
import java.util.Locale;
import java.util.concurrent.TimeUnit;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.Exceptions;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;
import reactor.test.StepVerifier;

class ConnectionPoolTests {

    private MockWebServer server;
    private ConnectionProvider provider;

    @BeforeEach
    void setUp() throws IOException {
        server = new MockWebServer();
        server.start();
    }

    @AfterEach
    void tearDown() throws IOException {
        if (provider != null) {
            provider.dispose();
        }
        server.shutdown();
    }

    private WebClient client(
            int maxConnections,
            int pendingAcquireMaxCount,
            Duration pendingAcquireTimeout) {

        provider = ConnectionProvider.builder(
                "test-pool-" + System.nanoTime())
            .maxConnections(maxConnections)
            .pendingAcquireMaxCount(pendingAcquireMaxCount)
            .pendingAcquireTimeout(pendingAcquireTimeout)
            .build();

        HttpClient httpClient = HttpClient.create(provider)
            .responseTimeout(Duration.ofSeconds(3));

        return WebClient.builder()
            .baseUrl(server.url("/").toString())
            .clientConnector(new ReactorClientHttpConnector(httpClient))
            .build();
    }

    private Mono<String> get(WebClient client, String path) {
        return client.get()
            .uri(path)
            .retrieve()
            .bodyToMono(String.class);
    }

    @Test
    void requestSucceedsThroughConfiguredPool() {
        server.enqueue(new MockResponse()
            .setResponseCode(200)
            .addHeader("Content-Type", "text/plain")
            .setBody("catalog-ok"));

        WebClient client = client(
            2, 2, Duration.ofSeconds(1));

        StepVerifier.create(get(client, "/health"))
            .expectNext("catalog-ok")
            .verifyComplete();
    }

    @Test
    void onePendingRequestCanWaitForTheOnlyConnection() {
        server.enqueue(new MockResponse()
            .setResponseCode(200)
            .addHeader("Content-Type", "text/plain")
            .setBody("first")
            .setBodyDelay(150, TimeUnit.MILLISECONDS));

        server.enqueue(new MockResponse()
            .setResponseCode(200)
            .addHeader("Content-Type", "text/plain")
            .setBody("second"));

        WebClient client = client(
            1, 1, Duration.ofSeconds(2));

        Mono<String> first = get(client, "/first");
        Mono<String> second = get(client, "/second");

        StepVerifier.create(Flux.merge(first, second))
            .expectNextCount(2)
            .expectComplete()
            .verify(Duration.ofSeconds(3));
    }

    @Test
    void requestIsRejectedWhenPendingQueueIsDisabled() {
        server.enqueue(new MockResponse()
            .setResponseCode(200)
            .addHeader("Content-Type", "text/plain")
            .setBody("slow")
            .setBodyDelay(700, TimeUnit.MILLISECONDS));

        server.enqueue(new MockResponse()
            .setResponseCode(200)
            .addHeader("Content-Type", "text/plain")
            .setBody("second"));

        WebClient client = client(
            1, 0, Duration.ofSeconds(1));

        Mono<String> first = get(client, "/first");
        Mono<String> second = get(client, "/second");

        StepVerifier.create(Flux.merge(first, second))
            .expectErrorMatches(error -> {
                Throwable cause = Exceptions.unwrap(error);
                String name = cause.getClass().getSimpleName();
                String message = String.valueOf(cause.getMessage())
                    .toLowerCase(Locale.ROOT);

                return name.contains("PoolAcquirePendingLimit")
                    || message.contains("pending acquire queue");
            })
            .verify(Duration.ofSeconds(3));
    }
}
~~~

The first test confirms WebClient sends requests through the pool and reads responses normally.

The second test sets `maxConnections=1` and `pendingAcquireMaxCount=1`. The first request holds the connection while the body is delayed; the second request is queued and then proceeds once the connection is returned.

The third test sets `pendingAcquireMaxCount=0`. While the single connection is busy, the next request is not queued and must receive a pool acquire error. Exact exception details may vary depending on the Reactor Netty version managed by Spring Boot.

Run tests:

~~~bash
mvn -q test
~~~

If all three tests pass, Maven exits with code 0. The tests do not measure production throughput; they only verify pool and queue semantics against a controlled upstream.

## 15. Pool Configuration in Real-World Applications

Pool configuration should be decided per dependency. A fast search API, a slow reporting service, and a message gateway may need different pools/timeouts.

Example:

~~~java
@Bean(destroyMethod = "dispose")
ConnectionProvider reportingConnectionProvider() {
    return ConnectionProvider.builder("reporting-pool")
        .maxConnections(10)
        .pendingAcquireMaxCount(20)
        .pendingAcquireTimeout(Duration.ofSeconds(3))
        .maxIdleTime(Duration.ofSeconds(30))
        .maxLifeTime(Duration.ofMinutes(10))
        .build();
}
~~~

A low-latency catalog API might use a larger `maxConnections` but a shorter `pendingAcquireTimeout`.

### One WebClient per Upstream with Different Policies

You do not have to share a single pool for all services. Separate providers and WebClients can be created:

- `catalog-pool`: serves product queries.
- `reporting-pool`: serves long-running reports.
- `payment-pool`: strictly limits connection count and uses short timeouts.

Separating pools prevents a slow upstream from exhausting connections meant for another upstream. However, each pool increases total resources and must be accounted for in the application's connection budget.

### Connection Limits Do Not Replace Rate Limiting

`maxConnections` limits concurrent connections. It does not directly limit requests per second. A small pool can reuse connections quickly and still send many requests per second.

If an upstream requires request rate limits, use a rate limiter/token bucket or an appropriate quota mechanism. Do not use `maxConnections` as a substitute for rate limiting.

## 16. Backpressure, Queueing, and Overload Protection

Connection pools and pending queues are part of load protection, but they do not solve all overload issues on their own.

A safe design typically combines:

- **Bounded pending queue:** limits how many requests are allowed to wait.
- **Acquire timeout:** limits how long requests wait for a connection.
- **Overall deadline:** limits the total duration of the request.
- **Rate limiting:** limits the send rate to the upstream.
- **Circuit breaker:** temporarily stops calling the upstream when consecutive errors cross a threshold.
- **Bulkhead:** isolates resources across dependencies.
- **Retry policy:** bounded retries with backoff and only for suitable operations.
- **Backpressure:** avoids creating unbounded downstream queues.

When the pool is full, decide which layer translates the acquire error into an appropriate response. An API gateway may return 503 or 429 depending on the cause and contract. You should not return 200 with an empty body just to hide pool errors.

## 17. Common Mistakes and How to Fix Them

1. **Creating a new WebClient for each request.** This causes churn and loses reuse benefits. Create shared WebClient/providers aligned with the application lifecycle.
2. **Setting maxConnections too high.** The upstream can be overloaded and the client machine uses too many sockets. Sum connections across all instances.
3. **Setting maxConnections too low.** Requests queue and hit acquire timeouts even when the upstream still has capacity. Measure concurrency and latency to tune.
4. **Using pendingAcquireMaxCount=-1 without justification.** Unbounded queues can accumulate requests and increase memory/latency. Prefer bounded queues.
5. **Not setting pendingAcquireTimeout.** Requests can wait longer than the caller's deadline. Set a timeout based on the request budget.
6. **Confusing pendingAcquireTimeout with connect timeout.** One waits for a connection from the pool; the other establishes a new TCP connection. Configure them separately.
7. **Confusing responseTimeout with overall timeout.** `responseTimeout` limits the wait interval between network reads, not the entire processing duration.
8. **Setting timeouts too short for valid streams.** A stream with long silent intervals can be closed even when functionally valid. Choose timeouts based on idle semantics.
9. **Setting maxIdleTime larger than the upstream's idle timeout.** The pool can hand out connections already closed by the peer. Set a value aligned with the server/proxy keep-alive.
10. **Not configuring maxLifeTime when the upstream requires connection rotation.** Long-lived connections can stick to old routes/nodes. Choose lifetime based on the environment.
11. **Not enabling or reading metrics.** Pool exhaustion is only discovered through user-facing errors. Monitor active, idle, pending, and acquire times.
12. **Sharing one pool for upstreams with different characteristics.** A slow dependency can starve resources of a fast dependency. Consider separating pools per upstream.
13. **Creating a ConnectionProvider without disposing it.** Can retain resources after shutdown/tests. Manage lifecycle via bean destroy methods.
14. **Disposing global resources while other WebClients in the app still use them.** Can break other clients. Only dispose providers owned by the application.
15. **Assuming maxConnections equals concurrent requests with HTTP/2.** HTTP/2 multiplexes multiple streams over one connection; stream limits must be considered.
16. **Retrying immediately when pool acquire fails.** Retries can make the queue even fuller. Retries must have backoff, limits, and deadlines.
17. **Using a connection pool to limit requests/second.** Pools limit concurrent connections, not rate. Use a rate limiter if a quota is needed.
18. **Not checking total connections from multiple instances.** Each instance has its own pool; the upstream sees the sum across all instances.
19. **Not distinguishing pool exhaustion from an upstream 503 response.** One error occurs before getting a response; the other is a status from the upstream. Record and map them separately.
20. **Not load-testing burst traffic.** A configuration that works under low load can build a large pending queue during bursts. Test concurrency, latency, and failure rates.

## 18. Connection Pool Configuration Checklist

Before releasing a WebClient client, verify:

- **Connector:** is it using Reactor Netty or another connector?
- **Destination:** which host/port does the pool apply to?
- **maxConnections:** how many connections from all instances can the upstream serve?
- **pendingAcquireMaxCount:** is the queue bounded and sized for bursts?
- **pendingAcquireTimeout:** how long may a request wait before failing?
- **Connect timeout:** does opening a new TCP connection have a time limit?
- **Response timeout:** is the silent interval between reads appropriately bounded?
- **Overall deadline:** does the whole request fit within the caller's deadline?
- **Idle policy:** does `maxIdleTime` match the upstream/proxy keep-alive?
- **Lifetime:** are `maxLifeTime` and background eviction needed?
- **Protocol:** HTTP/1.1 or HTTP/2? Is multiplexing enabled?
- **Metrics:** are active, idle, total, pending, and acquire time observed?
- **Lifecycle:** is the provider shared and disposed at the right time?
- **Overload:** how are queue full/acquire timeouts mapped to application errors?
- **Retry:** are retries bounded, backed off, and non-amplifying?
- **Testing:** are normal pool operation, pending queue, and queue rejection tested?

## 19. Self-Check Exercises

**Exercise 1.** What does `maxConnections` limit?  
**Answer:** The number of connections the pool can create/hold for a remote destination per its configuration.

**Exercise 2.** What does `pendingAcquireMaxCount` limit?  
**Answer:** The number of requests waiting to be granted a connection when no connection is available.

**Exercise 3.** What does `pendingAcquireMaxCount=0` mean?  
**Answer:** Do not allow requests to queue; if a connection cannot be acquired immediately, the request is rejected.

**Exercise 4.** How does `pendingAcquireTimeout` differ from connect timeout?  
**Answer:** Acquire timeout is the time spent waiting for a connection from the pool; connect timeout is the time spent establishing a new TCP connection.

**Exercise 5.** Is `responseTimeout` an overall request timeout?  
**Answer:** No. It limits the time interval between network data reads. Use Reactor `timeout` if an overall deadline is needed.

**Exercise 6.** What is `maxIdleTime` used for?  
**Answer:** To evict connections that sit idle in the pool longer than allowed, reducing the risk of reusing stale connections.

**Exercise 7.** How does `maxLifeTime` differ from `maxIdleTime`?  
**Answer:** `maxLifeTime` limits the total age of a connection; `maxIdleTime` limits how long a connection sits inactive.

**Exercise 8.** Why is an unbounded pending queue dangerous?  
**Answer:** It can accumulate requests, increase memory and latency, and mask upstream overload.

**Exercise 9.** Can one HTTP/2 connection serve multiple concurrent requests?  
**Answer:** Yes. HTTP/2 multiplexes multiple streams over the same connection, subject to negotiated stream limits.

**Exercise 10.** Why do you need to sum pools across all instances?  
**Answer:** Each instance has its own pool; the upstream receives the sum of connections from all instances.

**Exercise 11.** Which pool metric shows requests waiting for a connection?  
**Answer:** `pending.connections`; inspect it alongside `active.connections` and `pending.connections.time`.

**Exercise 12.** Why should you not create a `ConnectionProvider` inside every API call method?  
**Answer:** It causes churn, loses connection reuse, and makes resource lifecycle hard to manage.

## 20. Key Takeaways

`ConnectionProvider` manages Reactor Netty's connection pool. `maxConnections` limits the number of connections; `pendingAcquireMaxCount` limits the number of waiting requests; `pendingAcquireTimeout` limits how long requests wait to be granted a connection. A bounded queue helps the application fail fast under overload rather than accumulating unbounded requests.

Acquire timeout, connect timeout, response timeout, and overall timeout protect different stages. `maxIdleTime`, `maxLifeTime`, and eviction manage aging connections. HTTP/2 multiplexes multiple streams, so the number of connections does not equal the number of concurrent requests.

Configure a shared provider aligned with the application lifecycle, monitor active/idle/pending metrics, and calculate total connections across all instances. Size pools based on request rate, latency, upstream capacity, and load tests. A connection pool is one part of overload protection; it must work together with bounded queues, deadlines, rate limiting, circuit breakers, bulkheads, and controlled retries.

### References

- Spring Framework, [WebClient – Client Connector and Configuration](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html).
- Spring Framework, [WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html).
- Reactor Netty, [HTTP Client – Connection Pool](https://projectreactor.io/docs/netty/release/reference/http-client.html#_connection_pool).
- Reactor Netty, [HTTP Client – Timeout Configuration](https://projectreactor.io/docs/netty/release/reference/http-client.html#_timeout_configuration).
- Reactor Netty, [Metrics](https://projectreactor.io/docs/netty/release/reference/metrics.html).
- Reactor Netty Javadoc, [ConnectionProvider](https://projectreactor.io/docs/netty/release/api/reactor/netty/resources/ConnectionProvider.html).
- Reactor Netty Javadoc, [HttpClient](https://projectreactor.io/docs/netty/release/api/reactor/netty/http/client/HttpClient.html).
- Project Reactor, [Reactor Core Reference](https://projectreactor.io/docs/core/release/reference/).
- Spring Boot, [Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html).
- OkHttp, [MockWebServer](https://square.github.io/okhttp/4.x/mockwebserver/).
