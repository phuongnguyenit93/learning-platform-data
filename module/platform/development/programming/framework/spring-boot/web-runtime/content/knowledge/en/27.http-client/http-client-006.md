# Shared HTTP Connections, Connection Pools, and Client Resource Lifecycle in Spring Boot

## 1. Objectives

Spring Boot applications frequently make outbound HTTP calls to fetch product details, process payments, authenticate, look up prices, or contact internal services. An HTTP call is more than a `GET` followed by reading JSON: underneath lie **DNS, TCP, TLS, HTTP keep-alive, connection pools, connection wait queues, timeouts, I/O threads, and resources that must be closed**.

Creating a new HTTP client per request without cleaning up resources can cause:

- Repeated TCP/TLS handshakes, high latency and CPU usage, and many sockets stuck in `TIME_WAIT`.
- Fragmented connection pools exceeding socket and file descriptor limits, exhausting local or upstream resources.
- Leased connections never returning to the pool because response bodies/streams were not read, canceled, or closed properly.
- Rising pending acquires, requests queuing on the pool, and cascading timeouts under high load.
- Background threads, event loops, and idle connections left unclosed when the application or test context shuts down.
- User/token/cookie data from request A leaking to request B if a shared client holds **mutable request-specific state** improperly.

This lesson helps you:

1. Distinguish **sharing an HTTP client** from **sharing a single TCP connection**, and understand that connection reuse is enabled—not unconditionally guaranteed.
2. Choose Spring `RestClient`/`WebClient` and an HTTP transport suited for **blocking MVC** or **non-blocking WebFlux**.
3. Create **one application-scoped client and pool**, rather than creating a new pool in every method.
4. Configure pool limits, timeouts, eviction, and a shutdown mechanism with a **clear owner**.
5. Read/close response bodies properly to return or discard connections, and avoid blocking threads on an event loop.
6. Test against a **local HTTP server** and observe real pool behavior, distinguishing what tests prove from actual TCP socket reuse.

Primary scope: **Spring Boot 3.5.x, Spring Framework 6.2, Java 17+, Spring MVC, Apache HttpClient 5**. A standalone example with **WebClient/Reactor Netty** and notes on the JDK HTTP client are presented later. Spring Boot 4.x introduces reorganized auto-configuration and new customization APIs; do not copy Boot 3.5.x imports or configuration verbatim without checking the target version's docs.

> **Core rule:** keep the client/pool **long-lived at application scope**, while requests, sensitive headers, bodies, and response streams **belong strictly to the current call**.

## 2. Which Layers Does an HTTP Request Traverse?

Simplified diagram:

```text
Controller/Service in Spring Boot
           |
           | RestClient or WebClient (programming API)
           v
ClientHttpRequestFactory / ClientHttpConnector
           |
           | HTTP engine (Apache HC5, Reactor Netty, JDK HttpClient...)
           v
Connection manager / ConnectionProvider
   |          |           |
   | idle     | leased    | pending
   v          v           v
TCP/TLS socket(s)  <--- requests waiting for a connection
           |
           v
   API Gateway / Proxy / Upstream
           |
           v
      HTTP response
           |
           v
Consume/decode or cancel/close response body
           |
           v
Eligible connection -> returned to pool
Unsafe/closed connection -> discarded
```

**Distinguish three entities:**

- **HTTP client object** (`RestClient`, `WebClient`, Apache `CloseableHttpClient`, JDK `HttpClient`): configuration used to execute many requests. Many request specs can be created from a single client.
- **Connection pool/manager:** retains and leases physical connections per remote endpoint/route; controls active, idle, and waiting request counts.
- **HTTP request/response:** short-lived; bodies, headers, and data buffers must be consumed/closed/canceled properly. Never share a mutable request object across users.

**Sharing a client does not mean every request uses the exact same socket.** A client may open multiple connections due to concurrency, different host/port/proxy/TLS routes, keep-alive timeouts, server-initiated closes, HTTP/2 multiplexing, or pool policy. Conversely, sharing one pool **enables** reuse to avoid setup overhead whenever a suitable socket is available.

## 3. HTTP Keep-Alive, TCP Keepalive, Pooling, and HTTP/2 Differ

| Mechanism | Purpose | What it does not guarantee |
| --- | --- | --- |
| HTTP persistent connection / keep-alive | Lets multiple HTTP exchanges share one connection when protocol/peers allow | Does not keep sockets alive forever |
| Connection pool | Manages multiple connections and re-leases them to matching requests | Does not automatically prevent leaks or ensure load balancing |
| TCP `SO_KEEPALIVE` | OS-level TCP network probe when a socket sits idle for a long time | Does not replace HTTP timeouts or pool idle eviction |
| HTTP/1.1 | Typically one active request occupies a connection at a time (excluding rare pipelining) | No HTTP/2 multiplexing |
| HTTP/2 | Multiple streams on one connection up to peer limits | Does not mean always one connection; servers cap concurrent streams |
| TLS session resumption | Can reduce full handshake cost on new connections | Does not replace TCP connection reuse |

For instance, 100 **sequential** requests to the same host through one client may reuse very few connections; 100 **concurrent** requests to one host may need many connections under HTTP/1.1. With HTTP/2, multiple streams can share a socket, so never estimate pool size simply as active request count.

A **leased/active** connection is currently held by a request. An **idle/available** connection has been returned to the pool for another request to borrow. **Pending** is the count of requests waiting for a connection when limits are reached. Even after a controller appears finished, a connection may remain leased if a consumer has not finished reading the body or still holds a response stream.

## 4. Choosing an Application Client

| Option | API style | Transport & resource management | When appropriate |
| --- | --- | --- | --- |
| Spring `RestClient` | Imperative/blocking | Backed by `ClientHttpRequestFactory`; supports Apache HC5, JDK HttpClient, etc. | Spring MVC, synchronous code, virtual threads, or synchronous services |
| Spring `WebClient` | Reactive/non-blocking | Backed by `ClientHttpConnector`, commonly Reactor Netty | WebFlux, reactive processing, streaming/backpressure |
| `RestTemplate` | Imperative, legacy API | Also uses `ClientHttpRequestFactory` | Maintaining legacy code; consider `RestClient` for new projects |
| JDK `java.net.http.HttpClient` | Sync `send` and async `sendAsync` | JDK transport supporting connection reuse | When Spring abstractions are unneeded or JDK-only is desired |
| Apache HttpClient 5 directly | Classic/blocking or dedicated async stack | `PoolingHttpClientConnectionManager` and fine-grained settings | When low-level control, route pool metrics, and explicit timeouts are required |

Spring Boot provides **auto-configured `RestClient.Builder`/`WebClient.Builder`** with converters and customizers; inject the builder and **build the client once** in a long-lived bean. Builders are **mutable/stateful**; never mutate a shared builder concurrently across requests. Built clients are designed for concurrent use, whereas each request spec created from the client should be per-request.

**Do not confuse "Singleton Bean" with "Single JVM-wide Pool":** multiple `RestClient` instances can share one underlying `CloseableHttpClient` and pool, or two `RestClient` instances can each create separate Apache clients and therefore have **two separate pools**. What matters is **who actually owns the transport and pool**, not just the Spring bean names.

### 4.1. Anti-Pattern: Creating a Client on Every HTTP Request

```java
// ANTI-PATTERN — illustrative only, do not use in production:
@GetMapping("/catalog")
String catalog() {
    RestClient client = RestClient.create();
    return client.get()
            .uri("https://partner.example.org/catalog")
            .retrieve()
            .body(String.class);
}
```

This is a snippet (requiring a controller class and imports), and `RestClient.create()`'s implicit factory choice depends on framework/classpath; **do not claim every call necessarily opens a brand-new TCP socket**. Still, constructing a fresh client on a hot path makes lifecycle, config, and observability hard to manage, risks creating redundant transports/pools, and forfeits reuse opportunities. Move the client to a long-lived bean and create only new request specs inside the method.

### 4.2. Anti-Pattern: Closing the Client After Every Call

```java
// Do not do this with an application-wide shared transport:
try (CloseableHttpClient client = HttpClients.createDefault()) {
    // execute one request ...
}
```

`try-with-resources` is appropriate only when **intentionally creating a one-off transport**, not when pool reuse is desired. For a long-lived client, the **Spring ApplicationContext or owning bean** must close it **once on shutdown**, not after each request.

## 5. Pool Configuration: Separate Limits and Timeouts Clearly

A pool typically exposes the following settings:

| Parameter | Meaning | Symptom if misconfigured |
| --- | --- | --- |
| `maxTotal` / `maxConnections` | Total connections managed by the pool (exact scope varies by implementation) | Too small -> pending queues; too large -> socket/upstream overload |
| `maxPerRoute` | Per-route/per-host connection cap in Apache HC5 | One hot upstream exhausts the pool or stalls |
| `connectionRequestTimeout` / `pendingAcquireTimeout` | Max wait to **lease a connection from the pool** | Unbounded/missing -> long queueing and latency spikes |
| `connectTimeout` | Wait to establish a TCP connection | Unreachable upstream -> requests hang in connect |
| `responseTimeout` / `readTimeout` | Wait for response/data read per transport semantics | Slow upstream -> holds connections too long |
| `maxIdleTime` | Max time a connection stays idle in the pool | Stale sockets closed by server/LB |
| `maxLifeTime` / TTL | Max socket lifetime even when active | Reduces stale connections and balances connection age |
| `pendingAcquireMaxCount` | Max requests allowed to wait on the pool (Reactor Netty) | Unbounded queue -> memory/latency growth |
| eviction/validation | Cleans expired, broken, or idle connections | Old idle sockets accumulate or fail on reuse |
| concurrency / backpressure | Caps simultaneous outgoing requests | Large pool still overwhelms downstream |

**Three frequently confused timeouts:**

1. **Acquire timeout:** time spent waiting in the queue **before obtaining a connection**.
2. **Connect timeout:** time spent opening a new network connection.
3. **Response/read timeout:** time spent waiting for data after obtaining a connection, per library semantics.

**No single timeout is always the "end-to-end maximum duration"**. A business deadline may span DNS, acquire, connect, TLS, redirects, response body reading, retries, and processing. In Reactor, `timeout(Duration)` bounds the publisher per Reactive Streams semantics, but does not replace explicit network timeouts.

### 5.1. Estimating Pool Size Instead of Treating Defaults as SLAs

An initial heuristic based on Little's law:

```text
concurrent outbound requests ≈ throughput (req/s) × latency (s)
```

For example, 100 requests/s at 0.2 seconds average latency suggests roughly **20 concurrent requests** in steady state, before accounting for bursts, retries, tail latency, and multiplexing. An HTTP/1.1 pool to a specific host can start near the expected concurrency and then be measured; HTTP/2 multiplexes streams, so tune it differently.

- Per-host/route limits and total limits are distinct; calling three independent upstreams requires sizing for combined traffic.
- `maxConnections=500` is neither a throughput guarantee nor necessarily identical across Reactor Netty versions.
- Measure **active, idle, pending, pending wait, connect errors, TLS errors, and p95/p99 duration** before and after changes.
- Bound the wait queue; an overly long queue causes requests to expire their business deadline before ever borrowing a socket.
- Keep idle timeouts no significantly longer than the load balancer/upstream idle timeout to reduce reusing closed sockets.
- Never use unbounded retries to "fix" pool saturation; retries amplify load and trigger thundering herds.

## 6. Runnable Example: Spring Boot MVC + RestClient + Apache HttpClient 5

This example uses **Spring Boot 3.5.16** (an actual release on Maven Central), **Java 17**, Spring MVC, `RestClient`, and a shared Apache `CloseableHttpClient`. The pool is created **once**; **Spring calls `close()` when the ApplicationContext shuts down**.

**Version caveat:** Spring Boot 3.5.16 is the final OSS-supported patch in the 3.5.x line; it serves here **to reproduce a Spring Framework 6.2 example**. For new production projects, choose **an actively OSS-supported Spring Boot branch**, stay current on patches, and align imports/APIs with that version (such as Boot 4.1.x). Never ship an end-of-life release to production just because a tutorial used it.

The application provides:

- `GET /upstream/hello/{name}`: simulated upstream running in the same process so the demo runs locally without Internet access.
- `GET /demo/hello/{name}`: endpoint calling the upstream via the **shared RestClient bean** and returning JSON.
- `CloseableHttpClient` exclusively owning one `PoolingHttpClientConnectionManager`; no pool is created per request.
- An integration test starting a mock HTTP server on a **separate random port**, proving the outbound client sends real HTTP requests and receives responses independently of port 8080.

### 6.1. Project Structure

```text
shared-http-client-demo/
├─ pom.xml
└─ src/
   ├─ main/
   │  ├─ java/com/example/demo/
   │  │  ├─ SharedClientApplication.java
   │  │  ├─ OutboundClientConfiguration.java
   │  │  ├─ UpstreamGateway.java
   │  │  ├─ GatewayController.java
   │  │  └─ LocalUpstreamController.java
   │  └─ resources/application.properties
   └─ test/
      └─ java/com/example/demo/
         └─ SharedClientIntegrationTest.java
```

### 6.2. Maven Dependencies

**`pom.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>shared-http-client-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.apache.httpcomponents.client5</groupId>
            <artifactId>httpclient5</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
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
```

The Spring Boot BOM manages the compatible `httpclient5` version; do not pin an arbitrary Apache HC5 version manually. Requires Maven 3.6.3+ or Maven Wrapper and JDK 17+.

### 6.3. Application Properties

**`src/main/resources/application.properties`**

```properties
server.port=8080

# Local demo calls an endpoint inside the same application.
# Production uses an operator-permitted upstream HTTPS URL from config.
demo.upstream-base-url=http://127.0.0.1:8080
```

`demo.upstream-base-url` is **operator-controlled application configuration**, never read directly from a client query parameter; otherwise you introduce an SSRF vulnerability. In tests, this property is overridden with the random port of the test HTTP server.

### 6.4. Main Class

**`src/main/java/com/example/demo/SharedClientApplication.java`**

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SharedClientApplication {
    public static void main(String[] args) {
        SpringApplication.run(SharedClientApplication.class, args);
    }
}
```

### 6.5. Single Transport and Pool, Closed on Context Shutdown

**`src/main/java/com/example/demo/OutboundClientConfiguration.java`**

```java
package com.example.demo;

import java.time.Duration;

import org.apache.hc.client5.http.config.ConnectionConfig;
import org.apache.hc.client5.http.impl.classic.CloseableHttpClient;
import org.apache.hc.client5.http.impl.classic.HttpClients;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManager;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManagerBuilder;
import org.apache.hc.core5.util.TimeValue;
import org.apache.hc.core5.util.Timeout;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.HttpComponentsClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration
public class OutboundClientConfiguration {

    @Bean(destroyMethod = "close")
    CloseableHttpClient sharedApacheHttpClient() {
        ConnectionConfig connectionConfig = ConnectionConfig.custom()
            .setConnectTimeout(Timeout.ofSeconds(2))
            .setSocketTimeout(Timeout.ofSeconds(5))
            .setTimeToLive(TimeValue.ofMinutes(2))
            .build();

        PoolingHttpClientConnectionManager manager =
            PoolingHttpClientConnectionManagerBuilder.create()
                .setMaxConnTotal(24)
                .setMaxConnPerRoute(8)
                .setDefaultConnectionConfig(connectionConfig)
                .build();

        // The client owns the manager; when client.close() runs, the pool
        // and its associated client resources are also released.
        return HttpClients.custom()
            .setConnectionManager(manager)
            .evictExpiredConnections()
            .build();
    }

    @Bean
    RestClient sharedRestClient(
            RestClient.Builder builder,
            CloseableHttpClient sharedApacheHttpClient,
            @Value("${demo.upstream-base-url}") String upstreamBaseUrl) {

        var factory = new HttpComponentsClientHttpRequestFactory(
            sharedApacheHttpClient
        );

        // Timeout waiting to lease a connection from the pool.
        factory.setConnectionRequestTimeout(Duration.ofSeconds(2));
        // Response timeout per Apache/Spring request factory semantics.
        factory.setReadTimeout(Duration.ofSeconds(5));

        return builder
            .requestFactory(factory)
            .baseUrl(upstreamBaseUrl)
            .build();
    }
}
```

**Understanding ownership carefully:**

1. Spring instantiates the `CloseableHttpClient` bean **once** (default singleton). This method constructs **one `PoolingHttpClientConnectionManager`** and hands management to the Apache client.
2. By default, `HttpClients.custom().setConnectionManager(manager)` does **not** mark the connection manager as shared across unrelated Apache clients. In this model, **the Apache client owns the manager**.
3. `@Bean(destroyMethod="close")` instructs Spring to call `CloseableHttpClient.close()` when the bean is destroyed with `ApplicationContext`; never call `close()` inside service methods.
4. `evictExpiredConnections()` runs background eviction managed by the Apache client; when the client closes, the associated task must also shut down. Avoid keeping unused application contexts alive indefinitely in tests.
5. `RestClient.Builder` is provided by Spring Boot with converters and customizers. We explicitly supply `HttpComponentsClientHttpRequestFactory` so `RestClient` definitely uses our Apache client/pool rather than relying purely on classpath auto-detection order.
6. The built `RestClient` is safe for use across threads; **never** mutate the same builder between HTTP requests.
7. Here, the factory is **not** a separate destroy-owning bean, so responsibility for closing the Apache client sits in **a single bean**. Avoid registering a second destroy hook calling `close` twice on the same transport.
8. `24` total connections and `8` per route are **illustrative values**, not universal recommendations. Measure concurrency, latency, and upstream limits.
9. `ConnectionConfig.setConnectTimeout` sets the TCP connect timeout; `setSocketTimeout` affects socket I/O; `setReadTimeout` on the Spring 6.2 factory configures request response timeout; `setConnectionRequestTimeout` bounds waiting to lease from the pool. None of these alone represents an overall end-to-end SLA.
10. We do not bake a shared user access token or cookie into default headers on a singleton. Per-user/per-request values must be attached to **individual requests** safely.

**Why not expose `PoolingHttpClientConnectionManager` as a second bean?** To avoid creating two owners that both close the same pool. If you want to expose the manager to read `getTotalStats()`, design ownership explicitly: let the manager bean live at application scope, pass `setConnectionManagerShared(true)` to the Apache client, and ensure the manager bean is destroyed **after** the client; or wrap both in one owning bean. Never let the Apache client close the manager while Spring also closes it independently without clear lifecycle ordering.

### 6.6. Service Reusing RestClient and Creating a New Request Spec Each Call

**`src/main/java/com/example/demo/UpstreamGateway.java`**

```java
package com.example.demo;

import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class UpstreamGateway {

    private final RestClient client;

    public UpstreamGateway(RestClient sharedRestClient) {
        this.client = sharedRestClient;
    }

    public Greeting hello(String name) {
        return client.get()
            .uri("/upstream/hello/{name}", name)
            .retrieve()
            .body(Greeting.class);
    }

    public record Greeting(String message) {}
}
```

Calling `hello("An")` invokes `client.get()`, which creates a **new request spec**. `RestClient` and the underlying pool are the reused objects—not HTTP response bodies or request state.

`retrieve().body(Greeting.class)` reads/decodes the response within the request lifecycle via Spring message converters. For 4xx/5xx codes, `retrieve()` raises an exception by default; never treat an upstream 404 as 200 or swallow errors and return fake data. In production, map upstream errors to your service's error contract intentionally, log safely, and avoid exposing internal URLs or tokens.

### 6.7. Controller Calling Upstream via the Shared Client

**`src/main/java/com/example/demo/GatewayController.java`**

```java
package com.example.demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GatewayController {

    private final UpstreamGateway gateway;

    public GatewayController(UpstreamGateway gateway) {
        this.gateway = gateway;
    }

    @GetMapping("/demo/hello/{name}")
    public UpstreamGateway.Greeting hello(@PathVariable String name) {
        return gateway.hello(name);
    }
}
```

Because this is Spring MVC, the request thread **can block** inside `RestClient`; that matches this programming model as long as thread pools and timeouts are sized properly. On a **WebFlux/Netty event loop**, **never** call blocking `RestClient` on the event loop; use `WebClient`/non-blocking pipelines or bounded offloading.

### 6.8. Local Simulated Upstream, for Practice Only

**`src/main/java/com/example/demo/LocalUpstreamController.java`**

```java
package com.example.demo;

import java.util.Set;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class LocalUpstreamController {

    private static final Set<String> KNOWN_NAMES = Set.of("An", "Binh");

    @GetMapping("/upstream/hello/{name}")
    public UpstreamGateway.Greeting hello(@PathVariable String name) {
        if (!KNOWN_NAMES.contains(name)) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }
        return new UpstreamGateway.Greeting("Hello " + name);
    }
}
```

In the demo, `/demo/hello/An` sends an HTTP call to `127.0.0.1:8080/upstream/hello/An` and reads back JSON. Both endpoints live in one application solely so the example runs **without external upstreams**. Production uses separate services at securely configured URLs with proper network/access controls.

Never copy this **HTTP self-call** pattern to replace in-process Java calls in production: it adds extra sockets, pool waits, serialization, and deadlock/starvation risk when request concurrency is bounded. In real systems, clients call **remote services**; the local self-call is strictly a transport exercise.

### 6.9. Run the Application and Inspect Results

In the directory with `pom.xml`:

```bash
java -version
mvn spring-boot:run
```

Or `./mvnw spring-boot:run` if using the Maven Wrapper (Windows: `mvnw.cmd spring-boot:run`). With `server.port=8080`, ensure the port is free.

In another terminal:

```bash
curl -i http://127.0.0.1:8080/upstream/hello/An
curl -i http://127.0.0.1:8080/demo/hello/An
curl -i http://127.0.0.1:8080/demo/hello/Binh
```

Expected **successful responses** have status 200 and JSON field `message` equal to `"Hello An"`, `"Hello An"`, and `"Hello Binh"`, respectively. Do not assume fixed header order or JSON formatting. The second request may reuse a pooled connection if the socket remains eligible; this exercise **makes no unconditional claim** because HTTP requests do not guarantee TCP reuse.

Try sending multiple sequential requests:

```bash
for n in 1 2 3 4 5; do
  curl -s http://127.0.0.1:8080/demo/hello/An
  echo
done
```

Note: each `curl` invocation here is a separate **inbound** client process, while the application still reuses the same `RestClient` and pool when calling upstream. To observe outbound connections, inspect metrics/instrumentation **on the application/upstream** side, not just curl's TCP sockets to port 8080.

## 7. Integration Testing Without Internet or Binding to Port 8080

With `spring-boot-starter-test`, we can use `MockMvc` for inbound MVC while spinning up a **real HTTP server on loopback** using JDK `com.sun.net.httpserver.HttpServer` to receive outbound HTTP from the Apache client.

Because the test server picks a random port, `@DynamicPropertySource` supplies `demo.upstream-base-url` before Spring constructs the `RestClient` bean. This test does **not** mock away the transport layer, so it verifies `RestClient`, the Apache engine, HTTP serialization, and decoding. Still, it **does not prove a specific socket was reused**, because the server might close keep-alive or the pool might open a new socket.

**`src/test/java/com/example/demo/SharedClientIntegrationTest.java`**

```java
package com.example.demo;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;

import com.sun.net.httpserver.HttpServer;
import org.apache.hc.client5.http.impl.classic.CloseableHttpClient;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.RestClient;

import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SharedClientIntegrationTest {

    private static final HttpServer STUB = startStub();

    @Autowired
    MockMvc mvc;

    @Autowired
    UpstreamGateway gateway;

    @Autowired
    RestClient sharedRestClient;

    @Autowired
    CloseableHttpClient sharedApacheHttpClient;

    @Autowired
    ApplicationContext context;

    private static HttpServer startStub() {
        try {
            HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0
            );

            server.createContext("/upstream/hello/", exchange -> {
                String path = exchange.getRequestURI().getPath();
                String name = path.substring(
                    "/upstream/hello/".length()
                );

                if (!name.equals("An") && !name.equals("Binh")) {
                    exchange.sendResponseHeaders(404, -1);
                    exchange.close();
                    return;
                }

                byte[] body = (
                    "{\"message\":\"Hello " + name + "\"}"
                ).getBytes(StandardCharsets.UTF_8);

                exchange.getResponseHeaders().set(
                    "Content-Type", "application/json"
                );
                exchange.sendResponseHeaders(200, body.length);
                try (var output = exchange.getResponseBody()) {
                    output.write(body);
                }
            });

            server.start();
            return server;
        } catch (IOException ex) {
            throw new IllegalStateException(
                "Could not start local HTTP test server", ex
            );
        }
    }

    @DynamicPropertySource
    static void upstreamEndpoint(DynamicPropertyRegistry registry) {
        registry.add(
            "demo.upstream-base-url",
            () -> "http://127.0.0.1:" + STUB.getAddress().getPort()
        );
    }

    @AfterAll
    static void stopStub() {
        STUB.stop(0);
    }

    @Test
    void gatewayFetchesDataViaRealHttpTransport() throws Exception {
        mvc.perform(get("/demo/hello/An"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("Hello An"));

        mvc.perform(get("/demo/hello/Binh"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("Hello Binh"));
    }

    @Test
    void transportAndRestClientAreSharedSpringBeans() {
        assertSame(
            sharedRestClient,
            context.getBean(RestClient.class)
        );
        assertSame(
            sharedApacheHttpClient,
            context.getBean(CloseableHttpClient.class)
        );
    }

    @Test
    void sequentialCallsCanReuseSameConfiguredPool() {
        for (int i = 0; i < 5; i++) {
            UpstreamGateway.Greeting result = gateway.hello("An");
            org.junit.jupiter.api.Assertions.assertEquals(
                "Hello An", result.message()
            );
        }
    }

    @Test
    void upstream404RemainsAnError() {
        assertThrows(
            HttpClientErrorException.NotFound.class,
            () -> gateway.hello("missing")
        );
    }
}
```

Run:

```bash
mvn test
```

With the right Maven dependencies and Java files above, **all four tests are expected to pass**. This reflects the intended design for learners to run themselves; **it is not a claim of having compiled or executed them in a live repository here**.

**Limitations to remember:**

- `transportAndRestClientAreSharedSpringBeans` proves Spring injects the **same `RestClient`/`CloseableHttpClient` instances**, not that request A and B shared the exact same TCP socket.
- The sequential test verifies multiple calls succeed over the same transport configuration; it avoids asserting an exact socket count because `HttpServer`/pools can close or reuse based on HTTP headers and versions.
- `HttpServer` runs outside the Spring context as a static test fixture and is stopped in `@AfterAll`. The Apache client bean belongs to the Spring context; Spring closes it via `destroyMethod` on context shutdown. **Never close the Apache client manually in `@AfterAll`**, because Spring Test may cache the application context across test classes.
- The stub server binds only to `127.0.0.1` on a random port and accepts no external network traffic.
- Do not use `MockRestServiceServer` to prove TCP pooling; a mock request factory checks HTTP semantics without executing real sockets or pools.
- The 404 test checks that `RestClient.retrieve()` preserves downstream errors meaningfully; production applications must map errors per clear policy rather than blindly echoing every upstream 404.

### 7.1. How Do You Verify Actual Connection Reuse?

**Do not infer reuse from two HTTP 200s.** If your goal is proving reuse, use tools that observe **connection identity**:

- Enable Apache or Reactor Netty pool metrics/instrumentation and monitor active/available/leased, acquisition, and creation rates.
- Capture TCP connections with authorized tools in a test environment (Wireshark/tcpdump, socket stats) and correlate local source ports, remote tuples, and connect events. Never treat a port printed inside HTML responses as reliable connection identity.
- Log connection IDs on a test upstream server or inspect access logs with a connection key, noting reverse proxies may terminate and re-originate TCP connections.
- Test under concurrent load and idle timeouts, not just five sequential calls. Pools legitimately open multiple sockets; "socket count = 1" is not a universal assertion across transports/protocols.
- Measure connection creation rates, pending waits, idle/leased ratios, and tail latency. Even with a proper pool, if the server sends `Connection: close`, sockets will not be retained for reuse.
- Benchmark with bounded concurrency and warm-up; isolate upstream CPU/load from TCP/TLS setup overhead. Never set an unbounded pool just for pretty localhost numbers.

## 8. Proper Lifecycle: Create Once, Reuse Often, Close Once

### 8.1. Lifecycle in Spring

```text
ApplicationContext startup
   |
   +--> create pool/connection manager
   +--> create HTTP engine
   +--> build RestClient/WebClient bean
   +--> inject into service(s)
                |
                v
       many parallel requests
       - create per-request spec
       - lease/multiplex connection
       - consume/cancel body properly
       - return/discard connection
                |
                v
Application shutdown
   |
   +--> stop accepting new requests (graceful shutdown if configured)
   +--> wait for in-flight work per policy
   +--> close/dispose transport and pool
   +--> stop owned eviction threads/event loops
```

Pitfalls to avoid:

1. **Per-request client creation:** redundant pools and idle sockets.
2. **Per-request client close:** breaks reuse and can abort other requests sharing the transport.
3. **Never closing owned resources:** when contexts/tests repeatedly start and stop in the same JVM, event loops, threads, and sockets accumulate.
4. **Double close or closing by the wrong owner:** two components both think they own the pool; shutting down one service kills HTTP for the entire app.
5. **Not draining response bodies:** leased connections or buffer allocators remain pinned longer than expected.
6. **Storing user data in singleton client default headers:** accidentally sends one user's token on another user's request.

### 8.2. Who Closes Resources in a Multi-Context App?

`@Bean(destroyMethod="close")` fits when the resource **belongs strictly to that ApplicationContext**. If a pool lives outside Spring (held in a static field or owned by a host/library), never let a child context dispose a shared pool still used by other contexts. This matters especially for:

- Spring MVC WARs deployed/redeployed in an application server.
- DevTools restarts or integration tests spinning up multiple contexts.
- Multiple `WebClient` instances sharing Reactor Netty global `HttpResources`.
- Multiple Spring apps sharing one JVM without isolated resources.

With Reactor Netty, **global resources must never be disposed arbitrarily by one service** while other clients or servers still use them. Clearly choose between **global managed resources** and **custom owned providers/event loops**, shutting down strictly at the owner's scope.

### 8.3. Graceful Shutdown and In-Flight Requests

Spring Boot supports graceful shutdown for the web server, yet **closing outbound clients too early** can sever outgoing calls that in-flight inbound requests are still awaiting. In production:

- Design readiness/termination sequences: stop admitting new traffic and allow in-flight work to finish within a grace period.
- Enforce finite timeouts: an infinite stream cannot block shutdown forever.
- When the deadline expires, cancel requests, cancel subscriptions, or close responses per transport API.
- Never instantiate a new HTTP client inside `@PreDestroy` just to "flush" a remaining queue during shutdown.
- If async background jobs or schedulers use the client, stop/await them before tearing down the transport they depend on.

Never treat "Spring calls `destroyMethod`, so all requests are guaranteed finished" as an absolute rule. Bean dependency ordering and graceful shutdown behavior must be verified in your deployment architecture.

## 9. WebClient + Reactor Netty: Sharing Event Loops and Connection Pools

Spring Boot can inject a configured `WebClient.Builder`, typically backed by Reactor Netty when `starter-webflux` is present. In **WebFlux**, prefer non-blocking `Mono`/`Flux` end-to-end instead of calling `.block()` on the Netty event loop.

### 9.1. Simple Approach: Using the Spring Boot–Managed Builder

```java
// Snippet: application includes spring-boot-starter-webflux.
@Service
public class PartnerService {
    private final WebClient client;

    public PartnerService(WebClient.Builder builder) {
        this.client = builder
            .baseUrl("https://partner.example.org")
            .build();
    }

    public Mono<String> getStatus() {
        return client.get()
            .uri("/status")
            .retrieve()
            .bodyToMono(String.class);
    }
}
```

This is a snippet (requiring imports for `Service`, `WebClient`, `Mono`), not a standalone class with a build file. `WebClient.Builder` can be injected by Boot as a prototype; configure and build it in the constructor, **never per service method call**.

With default Reactor Netty, clients can participate in **global `HttpResources`** containing event loops and pools. This is recommended to share a fixed resource budget for event-loop concurrency; Spring Boot manages resource lifecycle depending on stack/context. **Never** call `HttpResources.disposeLoopsAndConnections()` from an individual request or service, because every client sharing those global resources can stop working.

### 9.2. When You Need a Custom Pool with Explicit Ownership

The example below is **a separate WebFlux configuration variant**; do not mix it directly into the MVC/Apache project from Section 6 at the same time. Requires `spring-boot-starter-webflux` and Reactor Netty.

**`ReactiveOutboundConfiguration.java`**

```java
package com.example.reactive;

import java.time.Duration;

import io.netty.channel.ChannelOption;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;

@Configuration
public class ReactiveOutboundConfiguration {

    @Bean(destroyMethod = "dispose")
    ConnectionProvider partnerPool() {
        return ConnectionProvider.builder("partner-http")
            .maxConnections(40)
            .pendingAcquireMaxCount(100)
            .pendingAcquireTimeout(Duration.ofSeconds(2))
            .maxIdleTime(Duration.ofSeconds(25))
            .maxLifeTime(Duration.ofMinutes(2))
            .build();
    }

    @Bean
    WebClient partnerWebClient(
            WebClient.Builder builder,
            ConnectionProvider partnerPool) {

        HttpClient transport = HttpClient.create(partnerPool)
            .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 2000)
            .responseTimeout(Duration.ofSeconds(5));

        return builder
            .clientConnector(new ReactorClientHttpConnector(transport))
            .baseUrl("https://partner.example.org")
            .build();
    }
}
```

**Explanation:**

- `partnerPool` is an owned bean (owned by the Spring context) and disposed via `dispose()` when the context stops. `WebClient` does not create a new pool per request.
- `HttpClient.create(partnerPool)` uses the supplied pool. It may still rely on **default Reactor Netty event-loop resources**; **do not equate disposing the pool with disposing all global event loops**.
- `maxConnections(40)` and `pendingAcquireMaxCount(100)` bound pool concurrency and queue depth; these are only examples—measure real traffic.
- `pendingAcquireTimeout` differs from `CONNECT_TIMEOUT_MILLIS` and `responseTimeout`.
- `maxIdleTime` should be tuned alongside upstream/proxy idle timeouts.
- Customize the HTTP connector only when needed. Replacing the connector manually can bypass certain auto-configured integrations such as SSL bundles, observability, proxies, or customizers; verify against your Spring Boot version and overall config.
- **Never share this pool bean across two independent Spring contexts** and let both dispose the same resource.
- If graceful shutdown is needed for active connections, consult `ConnectionProvider.disposeLater(Duration)` and your Reactor Netty version's disposal semantics instead of immediate indiscriminate disposal.

**Never put a per-user authentication token into a singleton WebClient's default headers:**

```java
// ANTI-PATTERN: never store user A's token in a WebClient used for user B.
WebClient userAClient = builder
    .defaultHeader("Authorization", "Bearer token-of-user-A")
    .build();
```

Each request/user token must be obtained from the **appropriate security context** and attached per request, enforcing tenant/permission boundaries. When using a shared **service-to-service** credential, design a dedicated token provider with refresh/rotation; never hardcode tokens in source code or leak them in logs.

### 9.3. Response Bodies and DataBuffers Must Be Managed Properly

With `WebClient`, the straightforward pattern is:

```java
Mono<Greeting> result = client.get()
    .uri("/upstream/hello/{name}", name)
    .retrieve()
    .bodyToMono(Greeting.class);
```

`retrieve().bodyToMono(...)` decodes and consumes the response normally. When using `exchangeToMono`/`exchangeToFlux`, **you must decide how the body is handled inside the callback**; modern Spring WebClient checks and **releases unconsumed bodies when the callback publisher completes** to prevent leaks. Never expect a response to remain decodable after the callback completes.

```java
Mono<String> result = client.get()
    .uri("/status")
    .exchangeToMono(response -> {
        if (response.statusCode().is2xxSuccessful()) {
            return response.bodyToMono(String.class);
        }
        return response.createError();
    });
```

This is a snippet missing the `client` variable. When working directly with `DataBuffer`, follow `DataBufferUtils` and ownership contracts, releasing pooled buffers when consumed or discarded; never cache `DataBuffer` instances indefinitely in singletons. When canceling a `Flux`, the pipeline must honor cancellation and free bodies/connections; test timeouts and circuit breakers for cancellation paths too.

**Never call `.block()` on a Netty event loop.** Blocking stalls threads serving many connections, spikes tail latency, and causes "pool starvation" that looks like a network failure. If a library forces blocking inside a reactive pipeline, offload it with a bounded scheduler and quota; keeping the chain non-blocking is strongly preferred whenever possible.

## 10. JDK `java.net.http.HttpClient`: Reuse and Java 17/21 Differences

The JDK provides its own HTTP client:

```java
// Java 17+ snippet — create once in configuration or service.
HttpClient httpClient = HttpClient.newBuilder()
    .connectTimeout(Duration.ofSeconds(2))
    .followRedirects(HttpClient.Redirect.NEVER)
    .build();
```

Requires imports `java.net.http.HttpClient` and `java.time.Duration`. The JDK HTTP client maintains internal connection/thread management and supports reuse; creating separate client instances **does not share a single pool**. Share one instance for the appropriate lifetime instead of calling `HttpClient.newHttpClient()` on every request.

**Key differences:**

- In **Java 17**, `java.net.http.HttpClient` **does not yet have** the `close()`/`shutdown()` APIs added in JDK 21. Do not write `try (HttpClient client = ...)` expecting it to compile on Java 17.
- Starting in **JDK 21**, `HttpClient` provides `close()`, `shutdown()`, `shutdownNow()`, and `awaitTermination()`. Close the client per ownership once no new requests will arrive; never close per request.
- When using `BodyHandlers.ofInputStream()`, read the stream to EOF or close it properly; never leave streams open indefinitely, or requests/shutdowns can hang.
- With `sendAsync`, account for cancellation and body completion. A `CompletableFuture` completing with a streaming response **does not mean the stream has been consumed**.
- The JDK client does not expose the exact same tuning knobs or pool metrics as Apache HC5 or Reactor Netty; do not expect an API like Apache's `maxConnTotal`.
- Spring's `JdkClientHttpRequestFactory` wraps JDK `HttpClient` under `RestClient`. Ownership and timeout configuration depend on the specific Spring and JDK versions.

## 11. Reading Response Bodies Properly So Connections Are Not Pinned

### 11.1. For RestClient

For most JSON calls:

```java
Greeting value = restClient.get()
    .uri("/upstream/hello/{name}", "An")
    .retrieve()
    .body(Greeting.class);
```

Spring handles the normal response lifecycle while decoding the body in `retrieve()`. There is no need to touch raw streams for small JSON payloads. If **streaming large files**, avoid buffering the entire body into a `byte[]` just to write it to disk afterward.

`RestClient.exchange(...)` grants direct access to the response. **Read/copy the body inside the callback**—never return a raw stream to use after the framework closes the response:

```java
// Snippet: path must be controlled server-side, never raw user input.
restClient.get()
    .uri("/export")
    .exchange((request, response) -> {
        if (!response.getStatusCode().is2xxSuccessful()) {
            throw new IllegalStateException(
                "Upstream export failed: " + response.getStatusCode()
            );
        }
        Files.copy(
            response.getBody(),
            Path.of("/tmp/downloaded-report.csv"),
            StandardCopyOption.REPLACE_EXISTING
        );
        return null;
    });
```

This snippet sits inside a Java method requiring imports for `Files`, `Path`, `StandardCopyOption`, filesystem permission checks, and `IOException` handling. For real files, use secure temp files, size limits, checksums/sanitization, cleanup, never use client-supplied filenames directly, and avoid overwriting other users' documents. Note that the `exchange` callback has its own status/error semantics and does not automatically apply `retrieve()` status handlers.

**Do not do this:**

```java
// ANTI-PATTERN: returning the stream past the response lifecycle.
InputStream body = restClient.get().uri("/large")
    .exchange((request, response) -> response.getBody());
// After the callback returns, the stream may already be closed/invalid.
```

If using Apache directly to obtain raw managed responses, use `try-with-resources`/response handlers per Apache's API so both the response and entity stream close even on exceptions. Avoid returning a status while leaving an unconsumed body when the adapter expects release.

### 11.2. For WebClient

`WebClient.retrieve().bodyToMono(...)` is normally safe for finite responses. For streaming data, use `bodyToFlux(...)` or `exchangeToFlux(...)`, and **subscribe/cancel** in line with business lifecycle. Without a subscriber, no HTTP request runs in the standard lazy reactive model; if subscribed and stopped early, cancel the subscription cleanly.

Bound the bytes decoded into memory: oversized payloads trigger `DataBufferLimitException` or heap/direct memory pressure; pool leaks are not the only failure mode. Separate decoding errors, timeouts, saturation, and cancellations in metrics and logs.

### 11.3. How Unconsumed Bodies Affect the Pool

A connection returns to the pool only when the transport knows the exchange has ended cleanly, remains reusable, and contains no unread bytes that could corrupt the next request. Depending on protocol/client, the transport may:

- Drain/read the remaining body and keep the socket.
- Close the socket and remove it from the pool if the body is canceled early.
- Keep the connection leased as long as the stream/raw response stays open.
- Refuse reuse when the server sends `Connection: close` or framing/TLS errors occur.

**Never assume "canceling immediately returns the connection to idle".** Canceling a long response stream may destroy the TCP socket to guarantee framing boundaries, or close one HTTP/2 stream while keeping the underlying HTTP/2 connection, depending on transport.

## 12. Bounded Connection Pools: Understanding Queuing and Cascading Timeouts

Suppose an Apache pool allows at most 8 connections for one route, while 30 concurrent HTTP/1.1 calls target that upstream:

```text
30 outbound calls
       |
       v
8 connections leased -> 8 calls active
22 calls waiting on pool (subject to queue limit)
       |
       +--> One call finishes and returns its connection
       |           -> next waiting call leases it
       |
       +--> Wait exceeds connectionRequestTimeout
                   -> timeout error acquiring connection
```

Do not react by immediately bumping the pool from 8 to 800. First inspect:

- Is the upstream slow or are requests hanging?
- Are response bodies being read/closed properly?
- Are long-lived requests (SSE/streaming downloads) holding slots in the pool?
- Are retries/circuit-breakers amplifying traffic during upstream degradation?
- Are many app instances/replicas sharing the same upstream? Cluster-wide connections may exceed upstream quotas.
- Is HTTP/2 multiplexing enabled and supported at both ends?
- Do pool active/idle/pending metrics align with traffic observed in tracing?

During overload, consider **bulkheads/concurrency limits**, bounded queues, tailored timeouts, selective fallbacks, and circuit breakers. A connection pool protects sockets—it **does not replace** business quotas/rate limits and cannot fix a slow upstream by itself.

## 13. Observability: What Should You Measure?

### 13.1. Meaningful Metrics

| Group | Useful metrics | Analysis |
| --- | --- | --- |
| Pool | active/leased, idle/available, pending | Are we running out of connections or leaking releases? |
| Acquire | pending acquire duration and timeouts | Are requests waiting longer for the pool than upstream takes? |
| Network | DNS, connect, TLS handshake errors/duration | Bottleneck in network or DNS, not controllers |
| HTTP | client-side request counts, 2xx/4xx/5xx statuses | Upstream error rates and deployment regressions |
| Latency | p50/p95/p99 end-to-end, per route | Queueing time and tail latency |
| Lifecycle | pool count, background threads, sockets on shutdown | Leaks across redeploys or test contexts |
| Resilience | timeouts, retries, cancellations, circuit-open | Retry storms or hung body streams? |

Reactor Netty exposes metrics with prefixes such as:

```text
reactor.netty.connection.provider.total.connections
reactor.netty.connection.provider.active.connections
reactor.netty.connection.provider.idle.connections
reactor.netty.connection.provider.pending.connections
reactor.netty.connection.provider.pending.connections.time
```

These metrics require **enabling instrumentation/Micrometer dependencies** and appropriate tag config; do not assume every metric appears automatically just by adding Spring Boot Actuator. Watch tag cardinality when tagging by URLs containing IDs, tenants, or arbitrary hosts.

With Apache HC5, `PoolingHttpClientConnectionManager` offers `getTotalStats()` and `getStats(route)` for available/leased/pending/max counts. Because our demo leaves the manager owned by the Apache client, exposing metrics requires designing a resource-owning bean or instrumentation **that preserves lifecycle ownership**; never close the manager yourself to "reset metrics".

### 13.2. Quick Diagnostic Signals

| Symptom | Possible cause | Check first |
| --- | --- | --- |
| High latency, low CPU | Pending acquire, slow upstream | Pool pending + request duration + timeouts |
| Active stays high even after requests finish | Unclosed raw response/stream, long SSE | Body consumption/cancellation, leased connections |
| Sockets/`TIME_WAIT` spiking | Creating new clients/no reuse, server closes keep-alive | Bean lifecycle, connection creation rate, `Connection` headers |
| High memory/direct buffers | Excess clients/pools, unreleased `DataBuffer`, huge payloads | Allocators, heap/direct memory, streaming logic |
| 502/503 after idle periods | Stale connections closed by LB/server | `maxIdleTime`, validation, upstream idle timeout |
| Test suite slows down or hangs on exit | Unclosed contexts/clients/event-loops/background threads | `@Bean destroyMethod`, test resources, JDK async |
| 429/503 from upstream despite free pool slots | Upstream quota or overload | Retries, concurrency, rate limiting, and backoff |
| Fails only under load, fine locally | Pool too small or upstream tail latency | Controlled load test, p95/p99, pending queue |
| Pool behavior changed after Boot upgrade | Auto-detected transport or defaults changed | Dependency tree, configured request factory, runtime metrics |

## 14. Security When Using a Shared Client

### 14.1. Preventing Credential Leakage Between Requests

A singleton `RestClient`/`WebClient` safely shares **transport configuration**, while per-user data must be supplied per request:

```java
// Snippet: token retrieved and validated from a trusted source.
String result = client.get()
    .uri("/me")
    .headers(headers -> headers.setBearerAuth(tokenForThisRequest))
    .retrieve()
    .body(String.class);
```

This is a snippet; `tokenForThisRequest` must come from an auth/service layer, never unchecked from an inbound request. Never log tokens or include them in metrics. When user A and user B call concurrently, each request gets isolated headers/body—never share a single mutable `HttpHeaders` singleton across calls.

When an upstream uses a **shared service credential**, use a dedicated secure token provider/cache with refresh, expiry, and synchronization; never hardcode API keys in code or forward bearer tokens across unexpected cross-host redirects.

### 14.2. SSRF and Trusted Destinations

Never construct arbitrary outbound URLs from query parameters like this:

```java
// ANTI-PATTERN: client can force the server to call internal networks/metadata.
client.get().uri(userProvidedUrl).retrieve().body(String.class);
```

`baseUrl` should be an operator-controlled service URL; if business logic truly must fetch external URLs, enforce a **scheme/host/port allowlist**, restrict redirects and DNS rebinding, enforce egress firewalls, and block internal/metadata IP addresses. Connection pooling does not prevent SSRF; worse, a shared client could accidentally apply auth headers, proxies, or credentials to an untrusted route if misconfigured.

### 14.3. TLS, Proxies, and Cookie Stores

- Never disable certificate validation or hostname verification just to "get the connection pool working".
- When routing through a corporate HTTP proxy, configure proxy/CONNECT and truststores per infrastructure rules. Pools generally partition routes by proxy as well.
- Never use a shared cookie store across multiple users/tenants if cookies carry user identity; backend HTTP client cookies differ from browser session cookies.
- Never log sensitive payloads or `Authorization` headers via Reactor Netty wiretap/debug logging in production.
- Beware cross-origin redirects: a client can leak sensitive headers to an unintended destination if libraries/custom configs follow redirects blindly. Define explicit redirect policies and target allowlists.
- Keep-alive/pooled connections are not authentication sessions: every request still requires valid credentials and authorization.

## 15. Common Code Mistakes and Fixes

**Mistake 1 — `WebClient.create(...)` on every request.** Depending on transport it may reuse global Netty resources, yet recreating clients still breaks consistent config, testing, and instrumentation. Inject Boot's builder and build once in a constructor or bean.

**Mistake 2 — Mutating a shared stateful `RestClient.Builder` to set per-user tokens.** Builder mutations affect subsequent builds. Never call `builder.defaultHeader("Authorization", ...)` with per-request user tokens; set headers on each request.

**Mistake 3 — Using `CloseableHttpClient` in `try-with-resources` inside every service method.** Destroys pooling. Let the Spring context own long-lived transports.

**Mistake 4 — Disposing global Reactor Netty `HttpResources` from one component.** Breaks other WebClients/servers sharing those event loops and pools. Respect ownership.

**Mistake 5 — Calling `.block()` on the Netty event loop.** Causes deadlocks, starvation, and high latency; use reactive operators or bounded offloading.

**Mistake 6 — Ignoring response bodies or returning raw streams out of callbacks.** Connections/buffers stay leased or streams close prematurely. Consume/decode properly and close responses per contract.

**Mistake 7 — Setting huge pool sizes without load testing.** Increases upstream pressure, file descriptor usage, and connection storms; measure active/pending/tail latency and add bulkheads.

**Mistake 8 — Leaving out acquisition timeouts.** Pending queues grow unboundedly and requests blow their deadlines before reaching upstream; set acquire timeouts with bounded concurrency/queues.

**Mistake 9 — Using the same value for connect, acquire, and total request timeouts blindly.** Latency expectations break; measure each phase and enforce a separate end-to-end business deadline.

**Mistake 10 — Assuming one client object equals one connection.** One client manages many sockets, HTTP/2 multiplexes streams on a socket, and DNS/LB/proxies alter routing.

**Mistake 11 — Failing to close an owned Apache client on context shutdown.** Pool and eviction threads outlive redeploys; configure a bean destroy method and test lifecycle.

**Mistake 12 — Asserting HTTP 200 and claiming TCP reuse.** Observe connection identity or pool stats if reuse must be proven.

**Mistake 13 — Using `try (HttpClient client = ...)` on Java 17.** JDK `HttpClient` close APIs arrived in JDK 21; match your Java baseline.

**Mistake 14 — Letting long-lived streaming responses share a pool meant for short calls.** SSE, long polling, and huge downloads can monopolize slots; isolate pools/bulkheads or enforce appropriate limits per traffic class.

**Mistake 15 — Mismatched test lifecycles.** Manually closing a singleton transport in `@AfterAll` while Spring Test caches the application context causes subsequent tests to fail mysteriously. Let Spring own/close beans; tests should close only resources the test itself created directly.

## 16. Pre-Deployment HTTP Client Design Checklist

- [ ] Client objects are constructed and injected **once** per application/service lifetime, never per request.
- [ ] Underlying transports and connection pools have **one clear owner**, avoiding double-close or resource leaks.
- [ ] Architecture matches `RestClient` for blocking MVC or `WebClient` for reactive flows.
- [ ] Actual runtime-selected request factory/connector and dependency versions are verified.
- [ ] Pool enforces total/per-route caps, finite queues (where supported), and acquire/connect/response timeouts.
- [ ] TTL/idle eviction aligns with upstream and load-balancer keep-alive settings.
- [ ] Response bodies/streams are always consumed, closed, or canceled per contract; raw streams never escape callbacks.
- [ ] Pool sizing accounts for HTTP/2 multiplexing, proxy routes, and replica counts.
- [ ] Metrics track active/idle/pending, acquire latency, HTTP statuses, and timeouts with actionable alerts.
- [ ] TLS validation/hostname verification stay enabled; SSRF is blocked via allowlists and egress policies.
- [ ] Tokens/cookies/user headers are never held in mutable singleton state; per-request auth is isolated.
- [ ] Retries, backoff, and circuit breakers do not amplify load when pools or upstreams saturate.
- [ ] Tests exercise real HTTP against local stubs and load tests with bounded concurrency, not only mock factories.
- [ ] Graceful shutdown closes transports/pools only after handling in-flight work per policy.
- [ ] Spring Boot, Spring Framework, Apache, and Reactor Netty versions receive regular security patches.

## 17. Self-Check Questions

**1. Does creating a singleton `RestClient` bean mean the app uses only one TCP socket?**  
No. A singleton client can open/lease multiple TCP sockets in its pool depending on concurrency, routes, protocols, and upstreams.

**2. Why not create a `CloseableHttpClient` and close it after each `GET`?**  
It forfeits connection reuse and repeats TCP/TLS/thread/socket setup. Close resources when the owner (`ApplicationContext`) shuts down, not per request.

**3. How does `connectionRequestTimeout` differ from `connectTimeout`?**  
The first bounds waiting for the pool to lease a connection; the second bounds establishing a new network connection.

**4. When `pending` rises and `idle` is 0, is the pool definitely leaking?**  
Not necessarily. The upstream may simply be slow, concurrency may be too high, streaming may occupy connections, or bodies may not be released yet. Check active counts, response lifecycles, and latency.

**5. Does an HTTP 200 prove connection reuse?**  
No. You need pool metrics, connection IDs, or controlled network tracing.

**6. Does Spring Boot auto-configure `RestClient.Builder` and `WebClient.Builder`?**  
Yes, when matching dependencies are present; inject the builder and build the client once. Still, the selected underlying transport can depend on classpath, version, and customizations.

**7. When using Reactor Netty global resources, can a single service call `HttpResources.disposeLoopsAndConnections()` after a request?**  
No. Other clients or servers may rely on those global resources. Manage shutdown at the application/context owner level.

**8. Why must response bodies be fully read or canceled properly?**  
So the transport knows the exchange is complete and can return the connection to the pool or close the socket cleanly; leaving streams open keeps leased resources pinned.

**9. Should `@Bean(destroyMethod="close")` be put on an Apache HttpClient shared across multiple contexts in one JVM?**  
Only if that context truly owns the resource. If shared across contexts, use an external owner or precise lifecycle coordination.

**10. Why can blocking `RestClient` inside a WebFlux event loop stall the system?**  
Blocking I/O pins the event-loop thread, delaying many unrelated requests; use `WebClient` or bounded offloading.

**11. Can per-user auth credentials be stored as a default header on a singleton client?**  
No. Supply per-request headers/context to avoid leaking credentials across users and to respect token lifetimes.

**12. Should you always set `maxConnections` very high to boost throughput?**  
No. Base sizing on throughput × latency and load tests; upstream quotas, HTTP/2, queueing, retries, and resource budgets dictate safe thresholds.

**13. On JDK 17, can you call `HttpClient.close()`?**  
Not in the Java 17 API. Official shutdown/close methods on JDK `HttpClient` appeared in Java 21; do not confuse it with Apache `CloseableHttpClient`.

**14. The pool looks healthy, yet the API still gets `PrematureCloseException` after idle periods—what should you inspect?**  
Upstream/LB idle timeouts, stale sockets, remote closes, `maxIdleTime`/`maxLifeTime`/eviction, and retry policy—do not just increase `maxConnections`.

## 18. Official References

- Spring Boot 3.5 — *Calling REST Services* (`RestClient.Builder`/`WebClient.Builder`, client transport): https://docs.spring.io/spring-boot/3.5/reference/io/rest-client.html
- Spring Framework 6.2 — *REST Clients*: https://docs.spring.io/spring-framework/reference/6.2/integration/rest-clients.html
- Spring Framework — *WebClient Configuration and Resources*: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html
- Spring Framework — *WebClient Exchange*: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-exchange.html
- Spring Framework 6.2 — `HttpComponentsClientHttpRequestFactory`: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/http/client/HttpComponentsClientHttpRequestFactory.html
- Reactor Netty — *HTTP Client / Connection Pool / Disposing / Timeout Configuration*: https://projectreactor.io/docs/netty/release/reference/http-client.html
- Apache HttpComponents Client 5 — *Connection Management*: https://hc.apache.org/httpcomponents-client-5.5.x/current/tutorial/html/connmgmt.html
- JDK 21 — `java.net.http.HttpClient` API and `close/shutdown` lifecycle: https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpClient.html
- Spring Boot 3.5.16 release and OSS support note: https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/

**Conclusion:** A shared HTTP client is how you **reuse configuration and transport resources**; the connection pool bounds and leases physical connections; response bodies and request specs have their own short lifecycles. In Spring Boot, **build `RestClient`/`WebClient` once**, pick an appropriate transport, govern **max connections + pending queues + timeouts**, consume/cancel responses properly, close **pools/clients at the owner** on shutdown, and rely on metrics plus real HTTP tests to distinguish true connection reuse from a string of HTTP 200s.