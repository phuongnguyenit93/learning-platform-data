# Configuring HttpClient and Shared Resources

**Context:** Spring Framework Reactive → **Connections and Timeouts**.

`WebClient` is the HTTP client API at the Spring layer; `ClientHttpConnector` connects that API to a concrete transport. With Reactor Netty, the connector uses `reactor.netty.http.client.HttpClient` to manage sockets, TLS, event loops, connection pools, timeouts, and I/O operations. When transport tuning is needed, configure an `HttpClient` and attach it to `ReactorClientHttpConnector`.

This topic has two closely related parts:

- **Connection configuration:** addresses, connection pools, timeouts, TLS, proxies, redirects, HTTP/2, and observability.
- **Shared resources:** event-loop threads, connection providers/pools, DNS resolvers, and their startup/shutdown lifecycle.

Key principle: **transport resources live longer than a single request**. Share them across requests and clients that share the same policy. Creating a new pool/event loop per request increases threads, sockets, memory, and connection overhead.

## 1. WebClient, Connector, and HttpClient

The three layers have distinct responsibilities:

| Component | Responsibility | Example |
|---|---|---|
| `WebClient` | Application-level API for building HTTP requests, encoding/decoding bodies, and composing publishers | `retrieve().bodyToMono(Book.class)` |
| `ClientHttpConnector` | Bridge between WebClient and the HTTP runtime | `ReactorClientHttpConnector` |
| Reactor Netty `HttpClient` | Transport configuration: pools, event loops, TLS, proxies, timeouts | `HttpClient.create()` |

Processing flow:

```text
Application service
       |
       v
WebClient request specification
       |
       v
WebClient ExchangeFunction
       |
       v
ClientHttpConnector
       |
       v
ReactorClientHttpConnector
       |
       v
Reactor Netty HttpClient
       |
       +-- ConnectionProvider / pool
       +-- LoopResources / event loops
       +-- DNS resolver
       +-- TCP / TLS / HTTP
       |
       v
Remote service
```

`WebClient` focuses on HTTP contracts and reactive bodies. `HttpClient` focuses on the network runtime. For example, `defaultHeader` belongs to WebClient configuration; `CONNECT_TIMEOUT_MILLIS` belongs to Netty transport configuration.

Not every WebClient uses Reactor Netty. Spring provides connectors for JDK HttpClient, Jetty, and other implementations. The APIs in this lesson apply when the application uses Reactor Netty.

## 2. Creating HttpClient and Attaching It to WebClient

Minimal configuration:

```java
HttpClient httpClient = HttpClient.create()
        .responseTimeout(Duration.ofSeconds(5));

WebClient webClient = WebClient.builder()
        .clientConnector(
                new ReactorClientHttpConnector(httpClient))
        .build();
```

`HttpClient.create()` creates a Reactor Netty client with default resources. `responseTimeout` sets the response read limit at the transport layer. `ReactorClientHttpConnector` makes WebClient use that `HttpClient`.

In Spring Boot, you typically inject the auto-configured builder:

```java
@Configuration
class PartnerClientConfiguration {

    @Bean
    WebClient partnerClient(WebClient.Builder builder) {
        HttpClient httpClient = HttpClient.create()
                .responseTimeout(Duration.ofSeconds(5));

        return builder
                .baseUrl("https://partner.example.com")
                .clientConnector(
                        new ReactorClientHttpConnector(httpClient))
                .build();
    }
}
```

The example requires appropriate imports and component scanning configuration. The Boot-provided builder may carry codecs, observation, and application customizers. When creating a brand-new builder manually, do not assume it has all of Boot's customizations.

`HttpClient` is designed in a fluent style, and configuration operations return a configured instance. Configure it at startup and share the instance; do not recreate the client inside every service method.

## 3. What Are Shared Transport Resources?

An HTTP client is not just a small Java object. Reactor Netty requires background resources:

- **Event-loop group:** a group of threads handling asynchronous I/O, socket registration, and network callbacks.
- **ConnectionProvider:** manages the connection pool, acquire/release operations, and the queue of requests waiting for a connection.
- **DNS resolver:** resolves hostnames to IP addresses.
- **TLS/native resources:** native libraries or SSL contexts when used by the transport/security provider.
- **Internal timers and schedulers:** for timeouts, eviction, and background work.

Model:

```text
JVM / ApplicationContext
        |
        +------------------------------+
        |                              |
        v                              v
 Shared LoopResources           Shared ConnectionProvider
        |                              |
        +---------------+--------------+
                        |
             +----------+----------+
             |          |          |
             v          v          v
          Client A   Client B   WebFlux server
             |          |          |
             v          v          v
          requests   requests   incoming requests
```

Reactor Netty uses global resources in `HttpResources` by default. Event loops are shared between Reactor Netty clients and servers in the same JVM; connection pools are managed per remote origin. This is the recommended model for most applications because fixed, shared event loops have lower overhead than creating many separate groups.

**Sharing an event loop does not mean every client shares a single connection pool for all hosts.** Connection pools are organized per remote host/port and provider policy. Clients can share a provider while each origin has its own pool.

## 4. Global Resources and Spring Boot

When using Reactor Netty defaults, `HttpClient.create()` participates in global resources. These resources typically live until the JVM exits.

Spring Framework allows declaring a `ReactorResourceFactory` to tie the lifecycle of global Reactor Netty resources to the Spring `ApplicationContext`:

```java
@Configuration
class ReactorResourcesConfiguration {

    @Bean
    ReactorResourceFactory reactorResourceFactory() {
        return new ReactorResourceFactory();
    }
}
```

By default, `ReactorResourceFactory` uses global resources. When the ApplicationContext closes, the factory manages stopping resources according to Spring's lifecycle. This is useful for applications that may start/stop contexts multiple times in the same JVM, such as containers or test environments.

Spring Boot also has a mechanism for sharing server/client resources. When the server uses Reactor Netty and the client uses the same transport, a client built from Boot's auto-configured `WebClient.Builder` can share resources with the server. If a custom `ReactorResourceFactory` bean is provided, that configuration applies to both server and client via auto-configuration.

Do not manually call `HttpResources.disposeLoopsAndConnections()` from a service or when a single WebClient is destroyed. This call stops global resources that other clients/servers may still be using.

## 5. When Are Dedicated Resources Needed?

Global resources are a sensible default. Only separate resources when there is a concrete operational reason:

- A high-traffic upstream needs an independent pool so it does not exhaust connections for other upstreams.
- A client has a different lifecycle from the application, such as a module created and stopped dynamically.
- The application runs multiple independent contexts in the same JVM and needs resource isolation.
- A transport needs dedicated event-loop or pool configuration due to load characteristics.
- A client uses a special proxy/TLS/network path requiring separate quotas and observability.

Each separate resource group increases threads, pools, sockets, timers, and shutdown complexity. Do not create a dedicated event-loop group per WebClient bean unless measurements prove it is necessary.

There are two options:

1. Use global resources and configure clients/pools appropriately.
2. Use `ReactorResourceFactory` with `setUseGlobalResources(false)`, then ensure all clients/servers in that group use the same factory.

## 6. ConnectionProvider and Connection Pools

`HttpClient.create()` uses a shared connection pool by default. After a request completes, a still-usable connection can be returned to the pool and reused for subsequent requests to the same origin.

Creating a dedicated provider:

```java
ConnectionProvider provider =
        ConnectionProvider.builder("partner-pool")
                .maxConnections(80)
                .pendingAcquireMaxCount(160)
                .pendingAcquireTimeout(Duration.ofSeconds(5))
                .maxIdleTime(Duration.ofSeconds(30))
                .maxLifeTime(Duration.ofMinutes(5))
                .evictInBackground(Duration.ofSeconds(60))
                .build();

HttpClient httpClient = HttpClient.create(provider);
```

The values are illustrative examples. Choose them based on actual latency, concurrency, upstream quota, number of origins, and processing time. Reactor Netty defaults can change across versions; check the exact version managed by the Spring Boot BOM.

### 6.1. Important Pool Limits

| Property | Meaning | Questions When Configuring |
|---|---|---|
| `maxConnections` | Maximum connections per pool | How many concurrent connections can the upstream handle? |
| `pendingAcquireMaxCount` | Maximum requests queued waiting for a connection | What is the maximum backlog before rejecting? |
| `pendingAcquireTimeout` | Maximum time to wait to acquire a connection | How long before a request fails when the pool is busy? |
| `maxIdleTime` | Maximum idle age before a connection is eligible for eviction | After how long does the upstream/proxy close idle connections? |
| `maxLifeTime` | Maximum total lifetime of a connection | Do connections need periodic rotation? |
| `evictInBackground` | Interval for checking/evicting connections in the background | Should expired connections be cleaned up when pool traffic is low? |

The pool limits the number of concurrent sockets. When the pool is full, new requests can sit in the pending queue. If the queue is full or waits too long, acquire fails instead of holding an unbounded number of requests.

Do not increase `maxConnections` just to eliminate timeout errors. If the upstream is already overloaded, opening more sockets can make matters worse. Observe active, idle, pending, acquire time, and upstream latency before tuning.

### 6.2. maxIdleTime and maxLifeTime

`maxIdleTime` limits how long a connection sits idle in the pool. When setting this value, choose a value less than or equal to the target server/proxy idle timeout to reduce the chance of borrowing a connection that the remote side has already closed.

`maxLifeTime` limits the total lifetime of a connection, even when used frequently. It helps rotate connections and avoids holding a single connection too long in environments with load balancers or changing DNS/service discovery.

The two properties differ: a connection may be relatively new yet idle too long, or continuously used yet past its maximum lifetime.

### 6.3. FIFO, LIFO, and Eviction

The pool can select idle connections using different strategies:

- **FIFO:** picks the longest-idle connection (least recently used).
- **LIFO:** picks the most recently used connection.

LIFO can leave older connections sitting longer in the pool; eviction removes connections that have exceeded idle/lifetime criteria. Examine server and load balancer characteristics before choosing a strategy.

`evictInBackground` enables periodic checks. When disabled, expiration conditions can still be evaluated during acquire/release; background eviction is useful when you want to clean the pool even during low request periods.

### 6.4. HTTP/2 Is Not Like an HTTP/1.1 Pool

HTTP/2 supports multiplexing multiple streams over a single connection. Therefore, the number of connections does not equate to concurrent requests as in HTTP/1.1. Reactor Netty has a distinct allocation strategy and pool behavior for HTTP/2.

If HTTP/2 is enabled, observe both connections and active/pending streams. Do not copy an HTTP/1.1 `maxConnections` number straight to HTTP/2 and treat it as an exact concurrency limit.

## 7. Types of Timeouts That Must Be Separated

A request can wait at multiple stages. Using a single timeout number for everything often makes root-cause analysis difficult:

```text
Request
  |
  +--> DNS resolution
  |
  +--> Acquire connection from pool
  |
  +--> TCP connect
  |
  +--> TLS handshake
  |
  +--> Send request
  |
  +--> Wait/read response
  |
  +--> Decode body / finish application workflow
```

| Timeout | Which Stage Does It Protect? | Error Example |
|---|---|---|
| DNS query timeout | Hostname resolution | Resolver unresponsive |
| Pending acquire timeout | Waiting for a connection in the pool | Pool saturated |
| Connect timeout | Establishing a TCP connection | Remote host refuses/drops connection |
| TLS handshake timeout | TLS negotiation | Handshake hangs |
| Proxy connect timeout | Establishing a tunnel through a proxy | Proxy unresponsive |
| Response timeout | Waiting for response data per transport semantics | Upstream silent |
| Whole-operation timeout | Entire business publisher | Request + decode + processing exceeds SLA |

### 7.1. Pending Acquire Timeout

Set on `ConnectionProvider`:

```java
ConnectionProvider provider =
        ConnectionProvider.builder("orders")
                .maxConnections(40)
                .pendingAcquireMaxCount(80)
                .pendingAcquireTimeout(Duration.ofSeconds(4))
                .build();
```

This is the time spent waiting for a connection to be returned to the pool. It is not the time spent waiting for the server to return a response after a connection is acquired.

### 7.2. TCP Connect Timeout

Uses Netty `ChannelOption.CONNECT_TIMEOUT_MILLIS`:

```java
HttpClient httpClient = HttpClient.create()
        .option(
                ChannelOption.CONNECT_TIMEOUT_MILLIS,
                3_000);
```

This timeout applies to establishing the connection. It does not include the server's total processing time once the connection is open.

### 7.3. TLS Handshake Timeout

Can be configured via `secure`:

```java
HttpClient httpClient = HttpClient.create()
        .secure(ssl -> ssl
                .handshakeTimeout(Duration.ofSeconds(10)));
```

TLS handshake has its own timeout. If the upstream is distant or the handshake has special characteristics, choose a value according to the network and SLA. Do not disable certificate verification to fix handshake errors; fix the trust store, hostname, or certificate chain instead.

### 7.4. Response Timeout

`responseTimeout` sets the response read limit at the Reactor Netty layer:

```java
HttpClient httpClient = HttpClient.create()
        .responseTimeout(Duration.ofSeconds(5));
```

It can be set as a default for all requests of the client or overridden for a request that needs a different duration. This is not the overall timeout of all application processing; it has specific semantics at the response I/O layer.

For continuous streams, understand that response timeout can apply to the silence interval between reads. A stream with regular heartbeats can continue longer than the total duration of an ordinary request.

### 7.5. Whole-Operation Timeout

Use Reactor `timeout` when you need to bound the entire publisher from start to finish:

```java
Mono<Order> order = webClient.get()
        .uri("/orders/{id}", id)
        .retrieve()
        .bodyToMono(Order.class)
        .timeout(Duration.ofSeconds(8));
```

The `timeout` operator applies to the entire composed publisher chain. When exceeded, it cancels the upstream subscription and emits a timeout error. If you need to distinguish pool/connect/read timeouts clearly, configure specific transport timeouts alongside the business deadline.

Do not mechanically sum every timeout into an SLA if they do not occur sequentially on every execution path. Design an overall deadline and allocate a budget for each stage.

## 8. ReadTimeoutHandler and WriteTimeoutHandler

Netty handlers can be added when timeouts at the read/write operation level are needed:

```java
HttpClient httpClient = HttpClient.create()
        .doOnConnected(connection -> connection
                .addHandlerLast(
                        new ReadTimeoutHandler(10))
                .addHandlerLast(
                        new WriteTimeoutHandler(10)));
```

These handlers monitor I/O activity on the channel. They are not synonymous with `responseTimeout` or the overall business timeout. A valid stream that temporarily emits no data can hit a read timeout if the policy is unsuitable.

Do not attach overly short timeout handlers to every client and then be surprised when streams/SSE or large uploads get cut off. Choose based on the I/O pattern and use separate configurations per client where appropriate.

## 9. TLS, Certificates, and Hostname Verification

`HttpClient.secure` enables TLS for HTTPS or customizes the SSL context. Example:

```java
HttpClient httpClient = HttpClient.create()
        .secure(ssl -> ssl
                .handshakeTimeout(Duration.ofSeconds(10)));
```

In production:

- Keep certificate chain validation and hostname verification enabled.
- Use the proper trust store when the upstream uses an internal CA.
- Configure a client certificate/key store if the upstream requires mutual TLS.
- Rotate certificates and secrets under a managed lifecycle.
- Monitor certificate expiration ahead of time.
- Do not log private keys, tokens, or TLS secrets.

Do not use a trust manager that accepts all certificates to bypass SSL errors. That turns a configuration issue into a MITM vulnerability.

If there are multiple upstreams with different trust policies, create separate connectors/clients for each trust boundary. Do not attach an overly broad trust policy to a client used for all hosts.

## 10. Proxy, Redirect, and Compression

### 10.1. Proxy

Reactor Netty supports HTTP proxies. Example:

```java
HttpClient httpClient = HttpClient.create()
        .proxy(proxy -> proxy
                .type(ProxyProvider.Proxy.HTTP)
                .host("proxy.internal")
                .port(8080)
                .connectTimeoutMillis(5_000)
                .nonProxyHosts("localhost|127\\.0\\.0\\.1"));
```

This is a proxy configuration example; the non-proxy host expression syntax depends on the Netty API and version. Protect proxy credentials, do not log passwords, and verify proxy policy for HTTPS CONNECT.

Proxy connect timeout differs from TCP connect timeout to the origin. When using a proxy, the connection path has an extra hop and can incur additional DNS, TLS, or timeout behavior.

### 10.2. Redirect

Redirects can be enabled:

```java
HttpClient httpClient = HttpClient.create()
        .followRedirect(true);
```

Reactor Netty can follow standard HTTP redirects; custom predicates are also available for specific policies. Redirects can change host, path, or scheme. Check how sensitive credentials/headers are handled when redirecting to another origin; do not send Authorization/cookies to untrusted hosts.

### 10.3. Compression

```java
HttpClient httpClient = HttpClient.create()
        .compress(true);
```

Compression can reduce bytes transferred over the network, but consumes CPU for compression/decompression and affects decompressed size. Weigh payload size, CPU, latency, and upstream support. Do not compress already compressed data or small payloads if the benefit is negligible.

## 11. Event Loops and LoopResources

Reactor Netty uses event loops to perform non-blocking network I/O. A group of worker threads is shared among clients/servers in the JVM under default global resources.

A single event-loop thread can serve many connections. Therefore:

- Do not call `block()` on an event loop.
- Do not perform file I/O or blocking JDBC directly in callbacks.
- Do not run long CPU-heavy processing on an event loop.
- Use reactive drivers or offload legacy blocking calls to an appropriate scheduler.
- Do not increase event-loop threads just to compensate for blocking code.

If dedicated event loops are needed, you can create `LoopResources`:

```java
LoopResources loops =
        LoopResources.create("partner-http");

HttpClient httpClient = HttpClient.create()
        .runOn(loops);
```

`LoopResources` is also a lifecycle-managed resource. If created manually, it must be disposed when the application ends. Do not call dispose on each request or when just one WebClient stops using it if other clients still share the same loops.

Event-loop thread counts should not be chosen arbitrarily. Measure CPU, connection count, callback latency, and blocking levels before changing them.

## 12. ReactorResourceFactory with Independent Resources

When you do not want to participate in global resources, Spring provides `ReactorResourceFactory` to manage pools and event loops according to the ApplicationContext lifecycle.

Example custom resource factory configuration:

```java
@Configuration
class IsolatedReactorResources {

    @Bean
    ReactorResourceFactory reactorResourceFactory() {
        ReactorResourceFactory factory =
                new ReactorResourceFactory();

        factory.setUseGlobalResources(false);

        factory.setConnectionProviderSupplier(() ->
                ConnectionProvider.builder("partner-isolated")
                        .maxConnections(60)
                        .pendingAcquireMaxCount(120)
                        .pendingAcquireTimeout(
                                Duration.ofSeconds(5))
                        .maxIdleTime(Duration.ofSeconds(30))
                        .maxLifeTime(Duration.ofMinutes(5))
                        .evictInBackground(
                                Duration.ofSeconds(60))
                        .build());

        factory.setLoopResourcesSupplier(() ->
                LoopResources.create("partner-isolated"));

        return factory;
    }
}
```

The factory creates and manages independent resources. The suppliers are only used when the factory does not participate in global resources. Do not manually create additional providers or loops outside the factory if the goal is a unified lifecycle.

To make WebClient use that factory:

```java
@Bean
WebClient partnerClient(
        WebClient.Builder builder,
        ReactorResourceFactory reactorResourceFactory) {

    ReactorClientHttpConnector connector =
            new ReactorClientHttpConnector(
                    reactorResourceFactory,
                    httpClient -> httpClient
                            .option(
                                    ChannelOption.CONNECT_TIMEOUT_MILLIS,
                                    3_000)
                            .responseTimeout(
                                    Duration.ofSeconds(5)));

    return builder
            .baseUrl("https://partner.example.com")
            .clientConnector(connector)
            .build();
}
```

If multiple clients must share the same resource group, inject the same factory into each connector. If the server also belongs to this group, configure the server to use the same factory. When the context closes, the factory manages stopping the resources.

This is an advanced option. If you only need a few timeouts for WebClient, default global resources are usually simpler.

## 13. Dedicated Connection Pools and Resources per Upstream

You can have a separate client per upstream while still sharing event loops:

| Upstream | Client | Pool policy | Reason |
|---|---|---|---|
| Catalog | `catalogClient` | 40 connections, acquire 3s | Many short read requests |
| Payment | `paymentClient` | 12 connections, acquire 2s | Low upstream quota |
| Reporting | `reportClient` | 8 connections, response 30s | Long queries |
| Internal API | `internalClient` | Default shared pool | Same latency and quota |

One implementation approach is creating separate `ConnectionProvider` instances while sharing `LoopResources` or global event loops. However, separate pools increase sockets and pending queues. Split only when there are clear quota, SLA, or isolation requirements.

Do not create one pool per tenant if the number of tenants is large and each pool has low activity; that causes fragmentation and increases overhead. Instead, organize pools by upstream/policy, while keeping tenant identity in request headers/context.

## 14. HTTP/2, Keep-Alive, and Connection Health

HTTP/1.1 keep-alive allows multiple sequential requests to reuse a single connection. HTTP/2 allows multiple concurrent streams over a single connection.

When configuring:

- Verify protocol negotiation and ALPN with TLS.
- Observe active connections and active streams.
- Use a pool/allocation strategy suitable for HTTP/2.
- Set idle timeouts aligned with the server/load balancer.
- With HTTP/2, PING health checks can be configured to detect unresponsive connections when idle timeout is enabled.
- Do not treat TCP keepalive and HTTP/2 PING as the same mechanism.

TCP keepalive is a TCP-layer probe, usually with a long OS-dependent default interval. HTTP/2 PING is an HTTP/2 protocol frame. Both can help detect stale connections, but they operate at different layers.

## 15. Warmup and First-Request Latency

Reactor Netty initializes some resources on demand. The first request may incur extra cost for creating event loops, DNS resolvers, or loading native libraries.

You can warm up the client:

```java
HttpClient httpClient = HttpClient.create();

httpClient.warmup().block();
```

In a real application, place warmup in a startup hook with a clear lifecycle; do not call it on every request. Warmup initializes some background resources; DNS resolution and connecting to the origin may still happen when the first real request is sent.

Do not warm up by calling a business API that has side effects. If you want to verify upstream readiness, use a dedicated health check with appropriate timeouts and policies.

## 16. Metrics and Pool Observability

Reactor Netty supports metrics for connection pools and HTTP clients. You can enable metrics on the provider:

```java
ConnectionProvider provider =
        ConnectionProvider.builder("partner")
                .maxConnections(40)
                .metrics(true)
                .build();
```

When integrating with Micrometer, monitor relevant metrics such as:

- Active connections.
- Idle connections.
- Pending connections.
- Pending acquire time.
- Total connections and pool size.
- Request latency, response status, and transport errors.
- Connect timeout, response timeout, pool acquire timeout.
- Number of closed/evicted connections and retry counts.

Exact metric names and tags depend on the Reactor Netty version and registry. Avoid attaching full URLs, user IDs, or sensitive query strings as metric tags due to cardinality and personal data concerns.

A pool with many pending requests while active connections stay at max can indicate a slow upstream or an undersized pool. A pool with many active connections but low latency may just reflect normal concurrency. Always combine client metrics with upstream latency/errors and quota limits.

## 17. Shutdown and Disposing with Proper Ownership

Shutdown rules depend on who owns the resource:

| Resource | Management Approach |
|---|---|
| Global Reactor Netty resources | Let the JVM or Spring-managed `ReactorResourceFactory` manage them |
| Custom `ConnectionProvider` | Dispose the provider when its owner finishes |
| Custom `LoopResources` | Dispose loops when their owner finishes |
| `ReactorResourceFactory` | Spring lifecycle start/stop manages resources |
| WebClient bean using shared global resources | Do not dispose the global pool arbitrarily from a bean/service |

If creating a provider manually:

```java
provider.disposeLater().block();
```

This example is only appropriate at an imperative shutdown boundary; do not call it on an event loop or inside a request handler. In Spring, prefer factory/lifecycle beans to close resources in order and await shutdown properly.

Calling `HttpResources.disposeLoopsAndConnections()` affects all clients/servers using global resources. Do not call it just because one client is no longer needed.

For dedicated pools, stop accepting new requests, allow in-flight requests to finish within a grace period, and then dispose. Shutting down too early can cause in-flight requests using the pool to fail.

## 18. Runnable Java 17+ Example: Dedicated Pool and Shared Event Loop

The following example sets up a local Reactor Netty server and a WebClient. The server and client share a `LoopResources` to illustrate event-loop sharing; the outbound client uses a dedicated `ConnectionProvider` with limits and timeouts. The program sends two requests and then properly disposes the resources it owns.

Project structure:

```text
http-client-resource-demo/
├── pom.xml
└── src/main/java/demo/HttpClientResourceDemo.java
```

### 18.1. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>http-client-resource-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.4.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### 18.2. HttpClientResourceDemo.java

```java
package demo;

import java.time.Duration;

import io.netty.channel.ChannelOption;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;
import reactor.netty.DisposableServer;
import reactor.netty.http.client.HttpClient;
import reactor.netty.http.server.HttpServer;
import reactor.netty.resources.ConnectionProvider;
import reactor.netty.resources.LoopResources;

public class HttpClientResourceDemo {

    public static void main(String[] args) {
        LoopResources loops =
                LoopResources.create("lesson-http");

        ConnectionProvider pool =
                ConnectionProvider.builder("lesson-outbound")
                        .maxConnections(8)
                        .pendingAcquireMaxCount(16)
                        .pendingAcquireTimeout(
                                Duration.ofSeconds(3))
                        .maxIdleTime(Duration.ofSeconds(20))
                        .maxLifeTime(Duration.ofMinutes(2))
                        .evictInBackground(
                                Duration.ofSeconds(30))
                        .build();

        DisposableServer server = HttpServer.create()
                .runOn(loops)
                .host("127.0.0.1")
                .port(0)
                .route(routes -> routes.get(
                        "/ping",
                        (request, response) ->
                                response.sendString(Mono.just("pong"))))
                .bindNow();

        HttpClient nettyClient = HttpClient.create(pool)
                .runOn(loops)
                .option(
                        ChannelOption.CONNECT_TIMEOUT_MILLIS,
                        3_000)
                .responseTimeout(Duration.ofSeconds(3));

        WebClient webClient = WebClient.builder()
                .clientConnector(
                        new ReactorClientHttpConnector(nettyClient))
                .build();

        try {
            String baseUrl =
                    "http://127.0.0.1:" + server.port();

            String first = webClient.get()
                    .uri(baseUrl + "/ping")
                    .retrieve()
                    .bodyToMono(String.class)
                    .block();

            String second = webClient.get()
                    .uri(baseUrl + "/ping")
                    .retrieve()
                    .bodyToMono(String.class)
                    .block();

            System.out.println("first=" + first);
            System.out.println("second=" + second);
        }
        finally {
            server.disposeNow();
            pool.disposeLater().block();
            loops.disposeLater().block();
        }
    }
}
```

Run from the directory containing `pom.xml` with JDK 17+ and Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.HttpClientResourceDemo
```

**Standard output:**

```text
first=pong
second=pong
```

Explanation:

1. `LoopResources` creates a named event-loop group.
2. Both the server and outbound HttpClient are configured to use the same loops in the demo.
3. `ConnectionProvider` creates an outbound pool with a limit of 8 connections and a max pending queue of 16.
4. `HttpClient` uses that provider, adding connect timeout and response timeout.
5. `ReactorClientHttpConnector` attaches the HttpClient to WebClient.
6. The two requests call the same origin; the pool can reuse the connection if it remains valid.
7. `finally` stops the server, disposes the pool, and then disposes the event-loop group owned by the program.
8. `block()` is only in `main` of the demo to print synchronous output; do not use it in WebFlux handlers/services.

This example illustrates the API and resource ownership. Production Spring Boot applications usually prefer global resources or `ReactorResourceFactory` so Spring manages the lifecycle instead of manually disposing in business code.

## 19. Testing HttpClient Configuration

Tests should cover transport behavior and lifecycle, not just verifying that beans are created:

- Local server returning normal responses.
- Server slower than response timeout.
- Unreachable host/port to test connect timeout.
- Small pool with many concurrent requests to test pending acquire.
- Server closing idle connections to verify `maxIdleTime`/eviction.
- Valid, expired, or hostname-mismatched TLS certificates.
- Active proxy and proper handling of non-proxy hosts.
- Redirects to the same host and to a different host.
- HTTP/2 multiplexing if the application uses HTTP/2.
- Resource factory stopping resources when the ApplicationContext closes.
- Other clients continuing to work when one client is no longer used, if resources are shared.
- Metrics accurately reflecting active/idle/pending counts and timeouts.

Use a mock server or test containers to control response delays, connection closures, and TLS. Pool saturation tests need deliberate concurrency limits and timeouts; avoid relying on unstable scheduling timing.

Do not test only the happy path. Many production incidents come from full pool pending queues, stale idle connections, DNS changes, TLS rotation, or shutdown while requests are in flight.

## 20. Common Mistakes

1. **Creating HttpClient/ConnectionProvider per request.** Increases sockets, threads, and pools; create clients at startup and reuse them.
2. **Creating unnecessary multiple LoopResources.** Event loops should be shared per resource group with a clear lifecycle.
3. **Increasing maxConnections without bound.** Can overload upstreams and consume sockets/file descriptors; set quotas per system capacity.
4. **Leaving the pending queue unbounded.** Backlogs can consume memory and increase latency; set `pendingAcquireMaxCount`.
5. **Confusing pendingAcquireTimeout with connect timeout.** One waits on the pool; the other waits on TCP connect.
6. **Confusing responseTimeout with whole-operation timeout.** Configure a separate publisher deadline if an overall SLA is needed.
7. **Choosing maxIdleTime larger than the upstream's idle timeout.** Can borrow stale connections; aim for less than or equal to the server-side timeout.
8. **Not configuring eviction when pool cleanup is needed during low traffic.** Expired connections may only be detected on acquire/release without background eviction.
9. **Disposing global resources when one client stops.** Other clients/servers may lose functionality.
10. **Not disposing custom providers/loops.** Can keep threads and sockets alive after the module/context stops.
11. **Disposing shared resources too early.** In-flight requests or other clients will fail.
12. **Using a separate pool per tenant.** Easily fragments resources when there are many tenants; organize pools by upstream/policy.
13. **Treating HTTP/2 maxConnections as max request concurrency.** HTTP/2 multiplexes multiple streams over a connection.
14. **Blocking the event loop with block or JDBC.** Slows down all connections served by that thread.
15. **Disabling TLS verification to fix certificate errors.** Creates a security vulnerability; fix the trust chain/hostname.
16. **Not setting timeouts for TLS handshake or proxy.** One connection stage can hang longer than the request budget.
17. **Setting ReadTimeoutHandler too short for SSE.** Valid yet silent streams can be cut off.
18. **Not monitoring pending acquire metrics.** Pool saturation gets mistaken for a slow upstream or DNS failure.
19. **Enabling wiretap in production without controlling data.** Can log sensitive headers/bodies and increase CPU/I/O.
20. **Warming up with a request that has side effects.** Startup should not create unintended business transactions.
21. **Creating a new connector while forgetting resource ownership.** Identify which factory/provider/loops manage the lifecycle.
22. **Using a custom ReactorResourceFactory for one client while the server/other clients use another resource group.** To share custom resources, configure all related components with the same factory.
23. **Assuming disposeLater completes automatically without subscribing.** It is a publisher; at imperative shutdown, await completion or let Spring lifecycle manage it.
24. **Using defaults from Reactor Netty docs for a different version.** Spring Boot manages dependency versions; read the reference/Javadoc for the actual version in use.

## 21. Production Checklist

Before deploying, confirm:

- **Transport:** Is WebClient using Reactor Netty, Jetty, or the JDK connector?
- **Resource mode:** Global shared resources or a dedicated resource group?
- **Ownership:** Who creates and who closes ConnectionProvider/LoopResources?
- **Sharing:** Which clients/servers share providers and event loops?
- **Pool:** Are max connections, pending queue, acquire timeout, and idle/lifetime eviction based on load and quotas?
- **Timeout:** Are DNS, pool acquire, TCP connect, TLS handshake, proxy, response, and whole-operation deadlines separated?
- **TLS:** Are trust store, hostname verification, client certificates, and rotation configured properly?
- **Proxy/redirect:** Are credentials and host boundaries safe?
- **HTTP protocol:** HTTP/1.1 or HTTP/2; is concurrency calculated by connection or by stream?
- **Blocking:** Are event loops free of blocking/CPU-heavy code?
- **Warmup:** Is reducing first-request latency needed, and is readiness implemented properly?
- **Metrics:** Are active/idle/pending, acquire latency, connect/response timeouts, statuses, and request latency observed?
- **Shutdown:** Do in-flight requests have a grace period; are shared resources protected from disposal by the wrong owner?
- **Testing:** Have pool saturation, timeouts, TLS, proxies, stale connections, and context shutdown been tested?

**Key Takeaways:** `HttpClient` determines how Reactor Netty connects outbound; `ConnectionProvider` manages pools; `LoopResources` manages event loops; `ReactorResourceFactory` ties resources to Spring's lifecycle. Use global resources for most applications and share them across compatible clients/servers. Only create dedicated resources when justified isolation is needed. Set pool limits and per-stage timeouts, monitor pending/active metrics, and close resources from the proper owner when the application stops.

## References

- Spring Framework — [WebClient Configuration, Reactor Netty resources and timeouts](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html).
- Spring Framework — [ReactorResourceFactory Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/client/ReactorResourceFactory.html).
- Spring Framework — [ReactorClientHttpConnector Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/client/reactive/ReactorClientHttpConnector.html).
- Spring Boot — [Reactive Web Applications: shared server and client resources](https://docs.spring.io/spring-boot/reference/web/reactive.html).
- Project Reactor Netty — [HTTP Client: Connection Pool, Event Loops, TLS and Proxy](https://projectreactor.io/docs/netty/release/reference/http-client.html).
- Project Reactor Netty — [Timeout Configuration](https://projectreactor.io/docs/netty/release/reference/http-client.html#timeout-configuration).
