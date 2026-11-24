# Configuring Connect, Read, and Connection Acquisition Timeouts in Spring Boot HTTP Clients

## 1. Three Different Timeouts, Three Different Failure Scenarios

A Spring Boot service calling another service's HTTP API can exhibit nearly identical symptoms: requests hang for several seconds, followed by `ResourceAccessException`, `WebClientRequestException`, `SocketTimeoutException`, or a pool timeout error. Simply seeing the word **timeout** and raising every setting to 60 seconds fails to identify whether the problem lies in the network, the partner server, or **your own application's connection pool**.

This lesson distinguishes three critical timeouts:

1. **Connection timeout (connect timeout):** maximum wait to establish a **new connection** to the peer, typically TCP connect. It is not the time spent waiting for the server to process a request after connecting.
2. **Read/response timeout:** wait for a **response or data read operation** after sending the request, with semantics varying by library. It is not automatically an end-to-end deadline for the entire call.
3. **Connection acquisition timeout (connection request/lease/pending acquire timeout):** wait to **borrow a connection from the connection pool** when none is immediately available and the pool is at capacity. This failure can occur even when the target server is healthy and no TCP connect was ever attempted.

Scope: **Spring Boot 3.3.x, Spring Framework 6.1.x, Java 17+**, covering the two main HTTP client styles: `RestClient`/`RestTemplate` (blocking) and `WebClient` (reactive). The runnable example uses **Spring Boot 3.3.13, Java 21, Apache HttpClient 5.x**; the WebFlux section uses the Reactor Netty generation compatible with Spring Boot 3.3. Newer versions change APIs and properties; always verify against your target version.

**Diagram of a pooled HTTP call:**

```text
RestClient / WebClient calls GET https://partner.example/api
       |
       +-- [1] Wait for pool to lease a connection
       |          -> timeout: connection-request / pending-acquire
       |
       +-- If no idle connection: DNS + TCP connect
       |          -> timeout: connect; DNS and TLS have separate boundaries
       |
       +-- TLS handshake if HTTPS + send HTTP request
       |
       +-- [2] Wait for response / read bytes
       |          -> timeout: read / response / socket
       |
       +-- Read/close response body and return connection to pool
       |
       +-- Application uses result, possibly with retry/circuit breaker
```

This diagram is a logical model. HTTP/2 multiplexes, proxies add intermediate connections, and protocol stacks vary in implementation. **Never conclude that `connectTimeout=2s` plus `readTimeout=4s` guarantees every call finishes within 6 seconds**: DNS, pool wait, TLS, request body upload, multiple reads, retries, redirects, scheduling, and other queues also contribute.

## 2. Timing Examples to See All Three Wait Points

Suppose a client has a connection pool capped at **2 connections per route**, and the downstream API takes around 3 seconds per request.

```text
t = 0.0s    Request A takes connection #1, server is processing
t = 0.1s    Request B takes connection #2, server is processing
t = 0.2s    Request C arrives; both connections are busy
t = 1.0s    Request C still has not leased a connection
t = 1.2s    Request C hits 1s acquisition timeout -> FAIL
t = 3.0s    Request A finishes and returns connection #1 to the pool
```

Request C **may never even have attempted a new TCP connection**, because the pool was already at capacity. Raising connect timeout or read timeout will not solve **having no free connection**. Examine request concurrency, how long downstream holds connections, pool limits, and lease timeout.

Another scenario:

```text
t = 0.0s   Pool grants a connection
t = 0.1s   TCP connect completes
t = 0.2s   HTTP request sent
t = 4.2s   Server has not emitted a response while response timeout is 3s
           -> FAIL in the response/read wait phase
```

When a client targets an IP that drops SYN packets or a firewall drops TCP packets, **connect timeout** is the primary suspect. If the server immediately replies with HTTP 503/429/500, that is a **valid HTTP response with an error status**, not a timeout; distinguish the two before deciding on retries.

## 3. Terminology Across Common Libraries

| Phase | Apache HttpClient 5 + Spring `RestClient` | Reactor Netty + Spring `WebClient` | Meaning |
| --- | --- | --- | --- |
| Waiting on pool | `RequestConfig.setConnectionRequestTimeout(...)` | `ConnectionProvider.pendingAcquireTimeout(...)` | Waiting to lease/acquire |
| Opening TCP connection | `ConnectionConfig.setConnectTimeout(...)` or matching API version | `ChannelOption.CONNECT_TIMEOUT_MILLIS` | Waiting for a new TCP connection |
| Waiting for response | `RequestConfig.setResponseTimeout(...)` | `HttpClient.responseTimeout(...)` | Detecting/bounding slow responses per HTTP client semantics |
| Socket read inactivity | `ConnectionConfig.setSocketTimeout(...)` | `ReadTimeoutHandler` when truly needed | Detecting silent read I/O per stack |
| Whole-call deadline | Add deadline at appropriate business/resilience layer | `Mono.timeout(Duration)` when wrapping the call | Covers all phases within the operation scope |
| Pool capacity | `setMaxConnTotal`, `setMaxConnPerRoute` | `maxConnections`, `pendingAcquireMaxCount` | Determines concurrent request capacity |

Apache's `setResponseTimeout` and Reactor Netty's `responseTimeout` **do not have identical semantics**, and neither equals a business deadline. Apache's `responseTimeout` is not necessarily a wall-clock cap for an entire streaming response or retries; Reactor Netty enforces `responseTimeout` during HTTP response handling. Do not treat them as interchangeable purely by name.

Also, never confuse Apache's `connectionRequestTimeout` with an **HTTP request timeout**. "Connection request" means **requesting a connection from the pool**, not the maximum time for the server to process an HTTP request.

## 4. Visualizing the Connection Pool Before Tuning Timeouts

A pool retains open HTTP connections for reuse; opening fresh TCP/TLS connections for every request is expensive. In Apache HttpClient 5 classic, `PoolingHttpClientConnectionManager` enforces limits **across the whole pool** and **per route**; routes can vary by target host, proxy, and TLS config.

States to distinguish:

- **Available/idle:** free connection ready to be leased immediately if alive and matching the route.
- **Leased/active:** connection currently assigned to a request and held until the response is consumed/closed.
- **Pending:** request waiting for the pool to grant a connection.
- **Max total/per route:** configured caps; one hot endpoint can hit its per-route limit even while the total pool has room for other routes.

An HTTP call can **hold a connection well past receiving response headers** if code streams the body without reading/closing it completely. Pool starvation can therefore stem from **response body/resource leaks**, not solely from a slow server.

Increasing pool size is conditional: adding too many connections can overload the downstream, trigger TCP connect failures, and mask leaks or bad latency. Size limits to downstream capacity and measure **pending, leased, available, and latency percentiles**.

## 5. Spring Boot 3.3 Has No Single Global Property for Every HTTP Client

These properties govern the **inbound server receiving requests**, not outbound HTTP clients:

```properties
server.port=8080
server.tomcat.connection-timeout=20s
```

They do not replace timeouts on `RestClient`, `RestTemplate`, or `WebClient`. In **Spring Boot 3.3**, configuring outbound HTTP clients typically goes through builders, the underlying `ClientHttpRequestFactory`, or `ClientHttpConnector`.

Version warning: newer documentation introduces properties such as `spring.http.clients.connect-timeout` and newer builder APIs. **Do not assume they apply to Spring Boot 3.3.** In Boot 3.3, `RestTemplateBuilder` uses:

```java
new RestTemplateBuilder()
        .setConnectTimeout(Duration.ofSeconds(2))
        .setReadTimeout(Duration.ofSeconds(4));
```

This example sets **only two general timeouts and still depends on the active request factory**. It provides no pool lease timeout. `RestTemplateBuilder` is not a prebuilt `RestTemplate` bean; Boot supplies the builder and your app builds a client from it.

Spring Framework 6.1's `RestClient.Builder` does not expose `.connectTimeout(...)`/`.readTimeout(...)` directly as some newer Boot-level examples show. For Spring 6.1 `RestClient`, a clear approach is configuring a `ClientHttpRequestFactory` and passing it via `.requestFactory(...)`.

## 6. Pick the HTTP Engine Before Picking the API

`RestClient`, `RestTemplate`, and `WebClient` are **Spring-level APIs**. Timeouts are enforced by the request factory/connector and underlying HTTP library:

| Spring client | Possible underlying engines | Pool with tunable lease timeout? |
| --- | --- | --- |
| `RestClient` | Apache HttpClient 5, Jetty, JDK URLConnection, JDK HttpClient... by version/classpath | Yes, when choosing a pooled engine such as Apache |
| `RestTemplate` | `HttpComponentsClientHttpRequestFactory`, `SimpleClientHttpRequestFactory`, `JdkClientHttpRequestFactory`... | Depends on factory |
| `WebClient` | Reactor Netty, Jetty, JDK connector... | Yes, when using Reactor Netty provider/pool |

Apache HttpClient 5 (distinct from HttpClient 4's `org.apache.http.*`) uses `org.apache.hc.client5.*` and `org.apache.hc.core5.*`. Reactor Netty uses `reactor.netty.*` and `io.netty.*`.

Specifically, `SimpleClientHttpRequestFactory` backed by `HttpURLConnection` has no **Apache-equivalent pool lease timeout API**; setting connect/read timeouts does not introduce a pool manager. Do not invent a property named `connectionRequestTimeout` expecting the framework to honor it.

Adding another library to the classpath can change which engine Boot auto-detects. When all three timeouts matter, **configure the engine/factory explicitly** and verify with tests.

## 7. Apache HttpClient 5 and Spring Framework 6.1: A Crucial Version Difference

In **Spring Framework 6.1**, `HttpComponentsClientHttpRequestFactory` provides:

```java
factory.setConnectTimeout(Duration.ofSeconds(2));
factory.setConnectionRequestTimeout(Duration.ofMillis(800));
```

However, the 6.1 factory API **does not have** `setReadTimeout(...)` seen in newer Spring Framework examples. If you copy:

```java
// Does not compile on Spring 6.1's HttpComponentsClientHttpRequestFactory:
factory.setReadTimeout(Duration.ofSeconds(4));
```

compilation fails with `cannot find symbol`. It is not a bean naming mistake or missing import: **that method literally does not exist in that version**.

To configure all timeouts cleanly and explicitly with Apache HttpClient 5 on Spring Boot 3.3, this lesson uses:

- `ConnectionConfig.custom().setConnectTimeout(...)`: time to establish a new connection.
- `ConnectionConfig.custom().setSocketTimeout(...)`: default socket I/O timeout.
- `RequestConfig.custom().setConnectionRequestTimeout(...)`: wait to lease a connection from the pool.
- `RequestConfig.custom().setResponseTimeout(...)`: wait for response at the HttpClient layer.
- `PoolingHttpClientConnectionManagerBuilder`: total/per-route limits and connection configuration.
- `HttpClients.custom()`: builds a `CloseableHttpClient` shared across callers.

This gives explicit engine control so you can see every timeout boundary clearly. If upgrading to Spring 6.2/Boot 3.4+, **re-check the API** before switching to newer factory setters or builder properties.

## 8. Runnable Spring Boot MVC Example with Three Apache HttpClient 5 Timeouts

This example uses **Java 21, Spring Boot 3.3.13**, and Gradle with Wrapper. It runs a local HTTP server and configures an outbound `RestClient` calling **back to the same local server** to simulate a downstream service. Self-calling is strictly for testing timeouts; production must use real downstream URLs and avoid infinite call loops.

Illustrative settings:

| Setting | Value |
| --- | --- |
| Total connection pool | Max 4 |
| Per-route connection pool | Max 1 |
| Pool lease wait | 800 ms |
| TCP connect | 2 seconds |
| Response wait | 3 seconds |
| Socket inactivity | 3 seconds |

### 8.1. `build.gradle`

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.apache.httpcomponents.client5:httpclient5'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot dependency management selects the compatible `httpclient5` version; do not pull in Apache HttpClient 4 because its classes/packages differ. If a project manages its own BOM, verify the Apache API for that version before compiling.

### 8.2. `src/main/java/com/example/httpclient/HttpClientApplication.java`

```java
package com.example.httpclient;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HttpClientApplication {
    public static void main(String[] args) {
        SpringApplication.run(HttpClientApplication.class, args);
    }
}
```

### 8.3. `src/main/java/com/example/httpclient/OutboundClientConfig.java`

```java
package com.example.httpclient;

import org.apache.hc.client5.http.config.ConnectionConfig;
import org.apache.hc.client5.http.config.RequestConfig;
import org.apache.hc.client5.http.impl.classic.CloseableHttpClient;
import org.apache.hc.client5.http.impl.classic.HttpClients;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManager;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManagerBuilder;
import org.apache.hc.core5.util.Timeout;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.HttpComponentsClientHttpRequestFactory;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestTemplate;

@Configuration(proxyBeanMethods = false)
public class OutboundClientConfig {

    @Bean(destroyMethod = "close")
    CloseableHttpClient outboundApacheClient() {
        ConnectionConfig connection = ConnectionConfig.custom()
                .setConnectTimeout(Timeout.ofSeconds(2))
                .setSocketTimeout(Timeout.ofSeconds(3))
                .build();

        PoolingHttpClientConnectionManager pool =
                PoolingHttpClientConnectionManagerBuilder.create()
                        .setMaxConnTotal(4)
                        .setMaxConnPerRoute(1)
                        .setDefaultConnectionConfig(connection)
                        .build();

        RequestConfig request = RequestConfig.custom()
                .setConnectionRequestTimeout(Timeout.ofMilliseconds(800))
                .setResponseTimeout(Timeout.ofSeconds(3))
                .build();

        return HttpClients.custom()
                .setConnectionManager(pool)
                .setDefaultRequestConfig(request)
                .build();
    }

    @Bean
    RestClient downstreamRestClient(
            RestClient.Builder builder,
            CloseableHttpClient outboundApacheClient,
            @Value("${demo.downstream.base-url}") String baseUrl) {

        HttpComponentsClientHttpRequestFactory factory =
                new HttpComponentsClientHttpRequestFactory(
                        outboundApacheClient);

        return builder
                .baseUrl(baseUrl)
                .requestFactory(factory)
                .build();
    }

    @Bean
    RestTemplate legacyRestTemplate(
            CloseableHttpClient outboundApacheClient) {
        return new RestTemplate(
                new HttpComponentsClientHttpRequestFactory(
                        outboundApacheClient));
    }
}
```

**Why each bean?**

- One `CloseableHttpClient` is shared by `RestClient` and `RestTemplate`, avoiding building a new pool per request.
- `PoolingHttpClientConnectionManager` sets a per-route limit of 1 so pool saturation is easy to reproduce in the lab. Production must choose realistic capacity, not 1.
- `RequestConfig` includes `setConnectionRequestTimeout(800ms)` and `setResponseTimeout(3s)`; they govern **two separate phases**.
- `ConnectionConfig` includes `setConnectTimeout(2s)` and `setSocketTimeout(3s)`; `socketTimeout` is an I/O-level bound and should not be treated as a total deadline.
- `@Bean(destroyMethod="close")` ensures Spring closes `CloseableHttpClient` and its owned connection manager when the context shuts down. Never instantiate a new `CloseableHttpClient` inside a handler method.
- The configuration keeps Spring Boot's prepared `RestClient.Builder` (converters, observability, customizers if present) and **replaces only the request factory** on the named client.

**Note:** Apache HttpClient 5 has changed older vs. newer APIs around connect timeout; use `ConnectionConfig` explicitly per Apache 5.3. Do not rely on `.setReadTimeout()` on Spring Framework 6.1's factory because that method does not exist.

### 8.4. `src/main/java/com/example/httpclient/SlowController.java`

```java
package com.example.httpclient;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class SlowController {

    @GetMapping("/slow")
    public String slow(@RequestParam(defaultValue = "0") long delayMs)
            throws InterruptedException {

        if (delayMs < 0 || delayMs > 12_000) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "delayMs is out of range");
        }

        Thread.sleep(delayMs);
        return "slow-ok";
    }
}
```

This is a **simulated slow server**, not production server code. `Thread.sleep` ties up a servlet thread for the delay duration; it is used in this bounded local demo to produce reproducible response delays.

### 8.5. `src/main/java/com/example/httpclient/ProxyController.java`

```java
package com.example.httpclient;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;

@RestController
public class ProxyController {
    private final RestClient client;

    public ProxyController(RestClient downstreamRestClient) {
        this.client = downstreamRestClient;
    }

    @GetMapping("/call")
    public String call(@RequestParam(defaultValue = "0") long delayMs) {
        return client.get()
                .uri(uriBuilder -> uriBuilder
                        .path("/slow")
                        .queryParam("delayMs", delayMs)
                        .build())
                .retrieve()
                .body(String.class);
    }
}
```

There is no `@ControllerAdvice` in this demo: when an outbound call times out, the exception becomes **HTTP 500** and is logged. That helps observe experiments, **not production error handling**. Real systems should map downstream errors appropriately (such as 502/503/504 per gateway policy), hide internal exceptions, and emit traces/metrics.

### 8.6. `src/main/resources/application.properties`

```properties
server.address=127.0.0.1
server.port=8080
demo.downstream.base-url=http://127.0.0.1:8080
```

Run from the project with Gradle Wrapper:

```bash
./gradlew bootRun
```

From another terminal:

```bash
curl -i "http://127.0.0.1:8080/call?delayMs=0"
curl -i "http://127.0.0.1:8080/call?delayMs=1000"
```

When the machine is not overloaded and no network errors occur, both responses return HTTP 200 with the **exact** body:

```text
slow-ok
```

If you send:

```bash
curl -i "http://127.0.0.1:8080/call?delayMs=5000"
```

`RestClient` is expected to hit the ~3-second response timeout and `/call` may return HTTP 500 in the demo; exact exception classes and log format depend on version and root cause. **Do not assert a fixed stdout line or exact millisecond** because OS scheduling and network timing vary.

## 9. Reproducing a Pool Wait Timeout Without Confusing It with Read Timeout

In this example, the Apache pool for the `/slow` route allows at most **1 connection**; while request A holds that connection, B must wait to lease it.

On Linux/macOS/Bash, test nearly concurrently:

```bash
curl -sS "http://127.0.0.1:8080/call?delayMs=2500" \
  -o /tmp/call-a.txt &

sleep 0.2

curl -i "http://127.0.0.1:8080/call?delayMs=0"
wait
```

Once A holds the connection and the server is still working, B can hit the **800ms connection acquisition timeout** before A completes. If scheduling or curl execution orders the two differently, outcomes can vary; deterministic testing requires synchronizing until A has actually leased the connection before dispatching B.

Inspect logs and pool state to confirm the failure is a **lease wait**, rather than guessing from B failing alone:

- Connection A was leased from the pool and not yet released.
- `available=0`, `leased=1`, `pending>=1` for the route while B waits.
- B's failure points to lease/connection request timeout, not TCP connect.
- Once A consumes the body and closes the response cleanly, the connection returns to the pool for reuse.

Raising `setConnectionRequestTimeout` to 5 seconds lets B wait for A and succeed, **at the cost of higher tail latency for B**. Raising `maxConnPerRoute` to 2 lets A and B run concurrently, assuming downstream has capacity. **Do not apply both changes blindly just to make the error vanish without checking throughput and queueing.**

Note that Windows PowerShell does not share Bash's `&`/`wait` semantics; use two terminals or controlled background jobs. Never run load tests against unauthorized production services.

## 10. RestTemplateBuilder: Simple Setup and Its Limits

In Spring Boot 3.3, the code below creates a `RestTemplate` with standard timeouts when supported by the selected request factory:

```java
import java.time.Duration;

import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.web.client.RestTemplate;

RestTemplate client = new RestTemplateBuilder()
        .setConnectTimeout(Duration.ofSeconds(2))
        .setReadTimeout(Duration.ofSeconds(4))
        .build();
```

This is an **illustrative snippet for setting timeouts on the builder**, not a standalone program: it requires Spring Boot dependencies and a bean/entrypoint using `client`. Inside Spring Boot, prefer **injecting the auto-configured `RestTemplateBuilder`** instead of `new RestTemplateBuilder()` to preserve customizers, SSL, converters, and observability.

**What is missing:** This builder has no explicit parameter for **pool lease timeout**. Without ensuring a pooled engine, there is no "connection acquisition timeout" to configure here. For this lesson's use case, configuring Apache explicitly as in Section 8 is clearer.

Version difference: in Boot 3.3, the methods are `setConnectTimeout` and `setReadTimeout`. Newer docs use `connectTimeout`/`readTimeout` and different auto-configured properties. **Do not mix versions** when studying or copying code.

If using `SimpleClientHttpRequestFactory`:

```java
import java.time.Duration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;

SimpleClientHttpRequestFactory simple =
        new SimpleClientHttpRequestFactory();
simple.setConnectTimeout(Duration.ofSeconds(2));
simple.setReadTimeout(Duration.ofSeconds(4));
```

`SimpleClientHttpRequestFactory` wraps JDK `HttpURLConnection`; it supports connect/read timeouts, **not an Apache-style pool leasing API**. Both snippets are **integration fragments**, not Java source files with a `main` method.

## 11. What Does Sharing a Request Factory Between `RestClient` and `RestTemplate` Mean?

Spring Framework 6.1's newer `RestClient` is a blocking fluent API; `RestTemplate` remains supported for legacy codebases. Both can share **the same Apache client/pool** when their factories point to the same `CloseableHttpClient`.

```text
RestClient        -> HttpComponentsClientHttpRequestFactory ----+
                                                               |
RestTemplate      -> HttpComponentsClientHttpRequestFactory ----+--> CloseableHttpClient
                                                                      |
                                                                      v
                                                       PoolingHttpClientConnectionManager
```

Sharing a pool manages total connections cleanly, while introducing **capacity contention across callers**. If API A turns slow and exhausts connections, API B sharing the same route/manager queues up; split pools per downstream or service tier when isolation is needed.

In Spring, register one `CloseableHttpClient` as a lifecycle-managed singleton bean and reuse it. Never create a new client per HTTP request or close `CloseableHttpClient` after each call when connection reuse is desired.

Ensure response bodies are read/closed. With `RestClient.retrieve().body(String.class)` on small responses, the framework consumes/closes the body cleanly. When using `exchange(...)` with `InputStream` or handling `ClientHttpResponse` directly, respect lifecycle and close resources; leaks leave **leased connections** trapped outside the pool.

## 12. WebClient + Reactor Netty: The Three Equivalent Timeouts

`WebClient` is Spring WebFlux's reactive API. When backed by **Reactor Netty**, pool wait and response timeouts use different APIs from Apache:

- `ConnectionProvider.pendingAcquireTimeout(Duration)` = wait time when no pooled connection is free.
- `ConnectionProvider.maxConnections(int)` and `pendingAcquireMaxCount(int)` = pool capacity and wait-queue depth.
- `HttpClient.option(ChannelOption.CONNECT_TIMEOUT_MILLIS, int)` = TCP connect timeout.
- `HttpClient.responseTimeout(Duration)` = response timeout.
- `Mono.timeout(Duration)` wrapping the call pipeline enforces a deadline from subscription to Mono completion; **it does not replace** phase-specific settings.

**Standalone WebClient configuration example** for a Spring Boot project with `spring-boot-starter-webflux`:

**`src/main/java/com/example/reactive/RemoteWebClientConfig.java`:**

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

@Configuration(proxyBeanMethods = false)
public class RemoteWebClientConfig {

    @Bean(destroyMethod = "dispose")
    ConnectionProvider remoteConnectionProvider() {
        return ConnectionProvider.builder("remote-service-pool")
                .maxConnections(30)
                .pendingAcquireMaxCount(60)
                .pendingAcquireTimeout(Duration.ofMillis(800))
                .maxIdleTime(Duration.ofSeconds(20))
                .build();
    }

    @Bean
    WebClient remoteWebClient(
            WebClient.Builder builder,
            ConnectionProvider remoteConnectionProvider) {

        HttpClient netty = HttpClient.create(remoteConnectionProvider)
                .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 2_000)
                .responseTimeout(Duration.ofSeconds(3));

        return builder
                .clientConnector(new ReactorClientHttpConnector(netty))
                .baseUrl("https://partner.example")
                .build();
    }
}
```

This is a **compilable configuration sample with matching dependencies**, not a complete app since it omits `@SpringBootApplication`, controllers, and a live endpoint. `partner.example` is a documentation placeholder; replace it with a real partner URL and valid TLS policy. Spring disposes the Reactor Netty `ConnectionProvider` on context shutdown via `dispose()`; never create a new pool per subscription.

Reactive call example:

```java
import java.time.Duration;
import reactor.core.publisher.Mono;

Mono<String> result = remoteWebClient.get()
        .uri("/api/health")
        .retrieve()
        .bodyToMono(String.class)
        .timeout(Duration.ofSeconds(6));
```

This snippet uses the injected `remoteWebClient` bean above and is **not a standalone Java program**. `timeout(6s)` bounds the `Mono<String>` pipeline (covering acquire/connect/response/body within the subscription), though exact error and cancellation behavior depend on the async transport. Never call `.block()` on a Reactor event loop; return `Mono`/`Flux` from reactive handlers.

**Special note:** if a project includes both `spring-boot-starter-web` and `spring-boot-starter-webflux`, Spring Boot usually selects **SERVLET** application type, yet `WebClient` remains usable as an outbound reactive client. That does not turn MVC controllers into a reactive server.

## 13. `responseTimeout`, `ReadTimeoutHandler`, and `Mono.timeout` Differ

In Reactor Netty, three "read-related" mechanisms exist:

| Mechanism | Where it applies | Key takeaway |
| --- | --- | --- |
| `HttpClient.responseTimeout(...)` | Reactor Netty HTTP response handling | Phase-specific; recommended when bounding response wait |
| Netty `ReadTimeoutHandler` | Channel-level I/O inactivity | Can affect other read operations if attached broadly; use only when needed |
| `Mono.timeout(...)` | Wrapped Reactor Publisher | Pipeline liveness/deadline, not purely TCP/response |

Spring Framework docs show:

```java
import io.netty.handler.timeout.ReadTimeoutHandler;
import io.netty.handler.timeout.WriteTimeoutHandler;

HttpClient configured = HttpClient.create()
        .doOnConnected(connection -> connection
                .addHandlerLast(new ReadTimeoutHandler(10))
                .addHandlerLast(new WriteTimeoutHandler(10)));
```

This is an **integration snippet**: it requires `reactor.netty.http.client.HttpClient` and `ReactorClientHttpConnector` when paired with `WebClient`. `ReadTimeoutHandler(10)` takes **seconds**, not 10 milliseconds. Channel-level read inactivity handlers can affect streaming/chunking and connection reuse depending on context.

In short: if the goal is preventing an HTTP response from hanging indefinitely, prefer `responseTimeout(...)`; when you need to **bound an entire call** (and have accounted for retries), add a business-layer deadline. Never "compensate" for missing pool acquire timeouts simply by increasing `responseTimeout`.

## 14. Default Values: Read Your Exact Version, Never Guess from Memory

Some libraries have very long defaults, while others leave certain timeouts unspecified. For example, Reactor Netty 1.1 documentation lists:

- `pendingAcquireTimeout`: default around **45 seconds**.
- `CONNECT_TIMEOUT_MILLIS`: default around **30 seconds**.
- `HttpClient.responseTimeout`: unspecified by default.
- `pendingAcquireMaxCount`: default around **2 × maxConnections**.

These values are **engine defaults in a specific documented version**, not Spring Boot SLA guarantees across all HTTP clients. Engines, client versions, and Spring Boot auto-configuration can change defaults; never rely on implicit defaults for production timeouts.

For Apache HttpClient 5.x, `RequestConfig`, `ConnectionConfig`, and the pooling manager each have their own defaults. Inspect the effective `RequestConfig`/`ConnectionConfig` and runtime pool limits. **Explicit configuration avoids guessing defaults**, while avoiding overly tight timeouts that cause flaky errors under load.

When consulting online docs, make sure you are viewing the version matching Spring Boot 3.3 / Spring Framework 6.1 / Apache HttpClient 5, not copying properties from Spring Boot 4.x.

## 15. HTTPS, DNS, and Proxies Add Extra Wait Phases

The three timeouts do not cover every network detail.

**DNS:** Before TCP connect, the hostname must resolve. In many clients/JVMs/resolvers, DNS latency is not strictly bounded by TCP connect timeout. If slow DNS is suspected, monitor lookup times in resolver metrics/logs and consider dedicated resolver timeouts.

**TLS handshake:** TCP connect completing does not mean TLS is done. Spring Framework 6.1's `HttpComponentsClientHttpRequestFactory` Javadoc notes that the factory's connect timeout setter **does not necessarily control the SSL handshake or HTTP CONNECT tunnel**; configure the socket/TLS layer accordingly. Never set a 2s connect timeout and assume every HTTPS handshake completes within 2s.

**HTTP proxy:** When routing through a forward proxy, connect timeout may apply to reaching the **proxy** rather than the final server. CONNECT tunneling, proxy auth, and proxy responses have separate timeouts and statuses. Diagnostics must distinguish URL, proxy hop, and connection route.

**Connection reuse:** Borrowing an idle TCP connection from the pool skips **opening a new TCP connection**, so connect timeout may not trigger on every call. Read/response timeouts remain vital if the server stops responding over a reused connection.

**Retries/redirects:** Every retry or followed redirect introduces fresh wait phases. A **per-attempt** timeout does not place an upper bound on multiple attempts combined.

## 16. Whole-Operation Deadline Differs from the Sum of Phase Timeouts

Suppose a reporting endpoint call has a total SLA of **5 seconds**. Configured values:

```text
pool acquisition <= 0.8s
connect          <= 2.0s
response         <= 3.0s
```

**You cannot add 0.8 + 2.0 + 3.0 = 5.8 seconds and claim the call always finishes within 5.8 seconds**, because DNS, TLS, body streaming, retries, and individual timeout semantics also play a role. Use an **end-to-end deadline** whenever the business flow has a strict budget.

A time-budgeting model:

```text
Inbound request deadline (e.g., 5s)
    |
    +--> auth/business logic 0.3s
    +--> outbound HTTP call <= 4.2s
    +--> serialization, logging, response 0.5s
```

In reactive code:

```java
Mono<String> body = webClient.get()
        .uri("/api/resource")
        .retrieve()
        .bodyToMono(String.class)
        .timeout(Duration.ofMillis(4_200));
```

With blocking `RestClient`, enforce application-level deadlines, cancellation, and resilience appropriately, while setting engine timeouts so threads never hang forever. **Never treat `CompletableFuture.orTimeout` as guaranteeing blocking socket I/O is canceled immediately**: it may complete the future exceptionally while the underlying network call keeps running unless proper cancellation/interruption is wired.

With three retries at 3s per attempt, total elapsed time can vastly exceed the SLA without a shared deadline. Use a retry budget, backoff with jitter, and an idempotency policy; never unconditionally retry side-effecting POST requests.

## 17. Choosing Timeouts from Latency and Dependency SLOs

No single "2s/3s/1s" recipe fits all services. An effective process:

1. Determine the **inbound request deadline** and the budget allocated to the outbound dependency.
2. Measure dependency latency across p50/p95/p99, regions, payload sizes, and concurrency.
3. Set response timeout high enough to meet the SLO without hanging too long during downstream outages, and not so low that it causes false timeouts.
4. Set connect timeout appropriately for LAN/WAN, DNS, proxy/TLS, and network quality; avoid arbitrarily huge values on fast internal APIs.
5. Set pool acquisition timeout short enough to **surface overload quickly**, avoiding long queues when capacity is exhausted.
6. Size `maxConnPerRoute/maxConnections/pendingAcquireMaxCount` to your concurrency budget, throughput, and downstream rate limits.
7. Test warm connections, cold starts, TLS rotation, proxy failover, packet loss, and long-tail responses.
8. Monitor timeout rates, retries, pool pending counts, and downstream health, adjusting based on evidence.

**Little’s Law (approximate model):** average concurrent requests \(L \approx \lambda W\), where \(\lambda\) is throughput in requests/sec and \(W\) is average processing time in seconds. For example, 100 requests/sec × 0.2 seconds ≈ 20 in-flight requests. This is a capacity hint, **not automatically the required pool size**: HTTP/2 multiplexing, bursts, other resources, and per-route contention all affect real sizing.

Making a wait queue huge does not create capacity; it piles up requests, spikes p99 latency, consumes memory, and triggers cascading failures.

## 18. Observing the Pool: available, leased, pending, max

In Apache HttpClient 5, the connection manager exposes pool statistics:

```java
// Illustrative code inside a class holding a reference to manager:
var stats = manager.getTotalStats();
System.out.println("leased=" + stats.getLeased());
System.out.println("pending=" + stats.getPending());
System.out.println("available=" + stats.getAvailable());
System.out.println("max=" + stats.getMax());
```

This snippet is **not standalone** because `manager` must be the live `PoolingHttpClientConnectionManager` serving real requests, not a fresh manager created solely to inspect stats. For production metrics, keep the connection manager as a shared bean or field and export stats via Micrometer/Actuator per policy.

For Reactor Netty, the connection pool emits metrics such as active/idle/pending connections when `metrics(true)` is enabled and a Micrometer recorder is configured:

```java
ConnectionProvider provider = ConnectionProvider.builder("orders-pool")
        .maxConnections(30)
        .pendingAcquireMaxCount(60)
        .pendingAcquireTimeout(Duration.ofMillis(800))
        .metrics(true)
        .build();
```

Exact metric names and tag labels depend on the Reactor Netty and Micrometer versions in use. Never expose internal Actuator endpoints to the public Internet just to debug timeouts.

**Metrics to graph:** connect timeout count, response timeout count, pool acquire timeout count, currently leased, pending queue length, remaining capacity, latency percentiles, throughput, retries, and downstream error rate. These metrics tell you whether failures come from **network connectivity**, **slow servers**, or **pool exhaustion**.

## 19. Reading Exceptions and Root Causes by Phase

| Signal/exception (illustrative) | Likely phase | Check next |
| --- | --- | --- |
| `ConnectTimeoutException` | TCP connection attempt took too long | Host/IP, firewall, network, connect timeout |
| `UnknownHostException` | DNS resolution | DNS, resolver, hostname; not always connect timeout |
| `Connection refused` | TCP peer refused / nothing listening | Host/port/service health, not a timeout |
| `SocketTimeoutException: Read timed out` | No response data arrived within read timeout | Slow response, idle stream, socket timeout |
| `java.net.http.HttpTimeoutException` | JDK client HTTP request timeout | JDK request timeout semantics and factory |
| Apache pool lease timeout / `ConnectionRequestTimeoutException` | Pool did not grant a connection in time | Leased/pending/per-route limits; response closing |
| `PoolAcquireTimeoutException` in Reactor Netty | Waited too long to acquire a pooled connection | Pool pending, max connections, event-loop load |
| `PoolAcquirePendingLimitException` | Pending acquire queue is full | `pendingAcquireMaxCount`, bursts, backpressure |
| `WebClientRequestException` | Outbound network/timeout error wrapper | Inspect `getCause()` and full cause chain |
| `ResourceAccessException` | `RestClient`/`RestTemplate` I/O wrapper | Inspect root cause; do not assume read vs. connect immediately |
| HTTP `429`, `502`, `503`, `504` | HTTP status returned by downstream/proxy/gateway | Headers, response body, gateway logs; timeout may be at another hop |

Exact exception class names vary across Apache HttpClient/Reactor Netty versions and code paths; never build business logic on brittle **exception message strings**. In Spring, many failures are wrapped in `RestClientException` or WebClient errors; read the cause chain to pinpoint the layer.

`HTTP 504 Gateway Timeout` is an **HTTP response generated by a gateway**, not automatically proof that your own HTTP client hit its local `readTimeout`. Separate gateway timeouts, upstream timeouts, and local client timeouts before tuning settings.

**How to build a timeline:** record `t0=outbound start`, connection acquire time, DNS/connect/TLS timings if available, first byte, and end of body; include trace IDs to correlate proxy and downstream logs. Never log secrets, `Authorization` headers, full response payloads, or sensitive addresses just for debugging.

## 20. Never "Fix" Pool Starvation by Raising Read Timeout

A common operational mistake:

```text
Leased connections = max
Available = 0
Pending queue grows continuously
Timeouts appear during pending acquire
```

Here, **read timeout is usually not the direct root cause**. Remediation steps:

- Find code failing to close `ClientHttpResponse`, `InputStream`, streaming bodies, or lacking cleanup on canceled requests.
- Check if rising downstream p99 latency is keeping connections leased too long.
- Compare `maxConnPerRoute` against traffic: a total pool of 100 with per-route cap 2 still throttles a hot service.
- Shed or bound in-flight requests using bulkheads, backpressure, or queue limits instead of growing the queue indefinitely.
- Increase pool size **only if** the downstream can handle it and load tests prove throughput improves.
- Set sensible acquisition timeouts to fail fast during overload while returning controlled HTTP errors and watching metrics.

If failures happen on **connections that sat idle for a long time**, stale connections closed by a load balancer are likely. Address this with `maxIdleTime`, `validateAfterInactivity`, keepalives, or eviction—not just connect/read timeouts.

## 21. Connection Lifetime, Idle Timeout, and Eviction Are Not the Three Main Timeouts

People often confuse these additional limits:

| Setting | Purpose |
| --- | --- |
| Pool `maxIdleTime` | Closes connections sitting idle too long |
| Pool `maxLifeTime` | Caps total connection age |
| Validation after inactivity | Checks whether an old connection is still healthy before re-leasing |
| TCP keepalive | Transport-level probe after long idle periods per OS/network policy |
| HTTP keep-alive | Reuses connections per HTTP protocol |
| Read/response timeout | Bounds waiting for reads/responses on a request |
| Acquisition timeout | Bounds how long a request waits **to borrow a connection** |

Reactor Netty example:

```java
ConnectionProvider provider = ConnectionProvider.builder("partner-pool")
        .maxConnections(40)
        .maxIdleTime(Duration.ofSeconds(25))
        .maxLifeTime(Duration.ofMinutes(3))
        .pendingAcquireTimeout(Duration.ofMillis(800))
        .build();
```

Setting `maxIdleTime` at or below the idle timeout advertised by the partner's load balancer/server reduces "connection reset" errors when reusing old connections. Still, verify against real traffic; overly aggressive eviction increases TCP/TLS handshakes and CPU.

Do not equate raising `maxLifeTime` with giving an HTTP call more time. An actively leased connection is not necessarily torn down immediately upon hitting an idle/lifetime threshold; each pool implementation follows specific lifecycle rules.

## 22. HTTP/2, Streaming, and Long Polling Need Dedicated Settings

With classic HTTP/1.1, one connection typically handles one request at a time. With HTTP/2, a single TCP connection multiplexes many streams, so **TCP connection count does not equal concurrent HTTP requests**. Size pools, limits, and timeout semantics for the actual transport and protocol version.

**Server-Sent Events (SSE)/streaming:** a stream can run for minutes or hours while continuously sending chunks. Read inactivity timeout must exceed expected heartbeat intervals, and a 5s total deadline will kill a healthy stream. Use separate policies for streaming endpoints.

**Long polling:** a request intentionally waits longer than typical REST calls for server data. Set read/response timeouts above the server's long-poll duration plus network margin, and budget sufficient connection capacity. Never apply a single 2s read timeout uniformly if you have long polling or large downloads.

**Large uploads/downloads:** connect timeout differs from body-byte wait timeouts; HTTP clients can have separate write timeouts, `ReadTimeoutHandler`, retry policies, and streaming backpressure. Receiving many consecutive chunks each faster than the inactivity limit lets total transfer time exceed read timeout without error—another reason to understand **exact timeout semantics** instead of blindly adding numbers.

## 23. Controlled Experiments: Separating Slow Responses from Pool Contention

In the Section 8 Spring MVC example:

**Scenario A — Fast downstream**

```bash
curl -i "http://127.0.0.1:8080/call?delayMs=100"
```

Expect HTTP 200 and body `slow-ok`.

**Scenario B — Downstream slower than response timeout**

```bash
curl -i "http://127.0.0.1:8080/call?delayMs=5000"
```

Expect the outbound HTTP client to stop waiting after the configured limit; Spring wraps the exception and sample `/call` may return 500. Never treat the sample's 500 status as a production API contract.

**Scenario C — Pool saturation**

Send at least two concurrent `/call` requests with `maxConnPerRoute=1` and the first request's `delayMs` > `connectionRequestTimeout`; measure timing and inspect pool pending/leased counts. If B fails before any new outbound TCP connect occurs, it is a lease timeout.

**Scenario D — Failing TCP connect**

Use a host:port under **test-environment control** with a network rule intentionally dropping SYN packets (not a non-listening port on `127.0.0.1`, which normally causes immediate `Connection refused`). Measure TCP connect duration and error. Never probe random public IPs to "test connect timeout".

**Scenario E — Gateway timing out before the client**

If a load balancer sits between client and downstream, test the gateway returning HTTP 504 **before** the client's response timeout expires. Here the local client receives a normal 504; do not misdiagnose it as a local read timeout failure.

Perform all slow/load testing in dev/staging or authorized environments—never induce pool exhaustion against shared production systems.

## 24. Writing Real HTTP Tests Instead of Inspecting Bean Config Alone

Integration test example for the fast scenario, based on Section 8. The test invokes HTTP on a random port; because the sample project's `demo.downstream.base-url` is fixed at `localhost:8080`, **do not reuse that default property as-is with `RANDOM_PORT`** for `/call` self-calls.

A clean approach for this lesson is testing the simulated downstream `/slow` endpoint directly in `@SpringBootTest`:

**`src/test/java/com/example/httpclient/SlowControllerHttpTest.java`:**

```java
package com.example.httpclient;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class SlowControllerHttpTest {

    @Autowired
    TestRestTemplate client;

    @Test
    void slowEndpointReturnsExpectedBody() {
        ResponseEntity<String> response =
                client.getForEntity("/slow?delayMs=0", String.class);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody()).isEqualTo("slow-ok");
    }
}
```

Run:

```bash
./gradlew test
```

This test verifies the **simulated downstream** over a real HTTP server, not all three Apache client timeouts automatically. To test all three timeouts, spin up a **controlled server** and coordinate timing/pool state—such as JDK `HttpServer` on a random port or WireMock/MockWebServer synchronized with latches. Avoid brittle assertions like "exactly 800ms" because CI scheduling varies; use reasonable tolerances and assert exception types/causes and pool metrics.

A reliable pool-lease test holds **one connection leased** via an incomplete server response blocked on a `CountDownLatch`, dispatches a second request, and verifies an acquisition timeout occurs; a read-timeout test sends a single request to a server that accepts the connection but delays sending the first response byte.

## 25. Production Monitoring: Three Failure Modes Need Three Metric Labels

A useful dashboard separates three groups:

```text
client_connect_timeouts_total{downstream="inventory"}
client_response_timeouts_total{downstream="inventory"}
client_pool_acquire_timeouts_total{downstream="inventory"}

client_pool_leased{downstream="inventory"}
client_pool_pending{downstream="inventory"}
client_pool_available{downstream="inventory"}

client_latency_seconds{downstream="inventory",outcome="success|error"}
```

These are **suggested metric names**, not claims that Spring Boot/Apache emit these exact names out of the box. When using Micrometer/Reactor Netty, verify your runtime version's metric names and map exception causes cleanly into categories.

When latency rises, diagnose in order:

1. Are timeouts happening **before** TCP connect? Check the pool.
2. Is the pool hitting per-route/total limits with a growing pending queue?
3. If the pool is healthy, is connect latency rising or DNS/TLS slowing down?
4. If connect is fast, is downstream first-byte latency/processing time rising?
5. Are retries amplifying concurrency or pinning connections longer?
6. Are circuit breakers/bulkheads rejecting calls during dependency overload?

Never log raw Authorization tokens, TLS secrets, query strings with private data, or response bodies in metrics. High-cardinality tags like `userId`/`requestId` do not belong in metric dimensions; keep trace IDs in controlled tracing/logging.

## 26. Common Configuration Mistakes and Misconceptions

**"Connect timeout is how long you wait for the HTTP response."** Wrong. It primarily bounds **opening a new TCP connection**; the server can take additional time to respond afterward.

**"Read timeout is the total request duration."** Not automatically true. Semantics vary by engine, chunked reads, response streaming, and retries.

**"Connection request timeout is the HTTP request timeout."** Wrong in Apache HttpClient: it bounds **waiting to borrow a connection from the pool**.

**"Just call `.setReadTimeout(...)` on Spring 6.1's `HttpComponentsClientHttpRequestFactory`."** That API **does not exist** on the 6.1 factory. Use Apache `RequestConfig.setResponseTimeout` and matching config classes.

**"`RestTemplateBuilder.setReadTimeout` always configures the pool lease timeout."** No. Lease timeout belongs to the request factory/pool manager separately.

**"Make the pool huge so timeouts stop."** No. That can overload the downstream, spike TCP/TLS pressure, and hide leaks.

**"`server.tomcat.connection-timeout` controls outbound `RestClient`."** No. That configures the inbound web server.

**"Every 504 error comes from the local HTTP client's read timeout."** No. A 504 can be returned as an HTTP status by an intermediate **gateway**.

**"`Connection refused` is a connect timeout."** No. Refused is an active rejection right away, whereas a timeout expires after waiting for establishment.

**"Running `WebClient` inside MVC makes it a reactive server."** No. You can use `WebClient` outbound inside a Servlet app.

**"`Mono.timeout` fixes any pool/network misconfiguration."** No. It bounds the pipeline, while resource acquisition and cancellation still require proper configuration.

**"Longer timeouts make the system more stable."** Not necessarily. Overly long timeouts keep request threads and pooled connections pinned longer, amplifying cascading failures.

## 27. Applied Checklist and Self-Check Questions

**Checklist:**

- Clearly identify your stack: `RestClient`, `RestTemplate`, or `WebClient`, and the underlying Apache/JDK/Reactor engine.
- Configure explicit values for **connect, response/read, and acquire** when using a pool.
- Enforce total/per-route pool limits, bounded pending queues, and client shutdown lifecycles.
- Keep blocking I/O off the Netty event loop.
- Handle errors by root cause and timeout phase—never depend on exception message strings.
- Define time budgets for the entire inbound request/call including retries and redirects.
- Export metrics/traces for pool pending, leased, connect latency, response latency, and timeout rates.
- Test slow servers, pool saturation, and controlled TLS/DNS/proxy failure scenarios.
- Distinguish inbound server settings from outbound client settings; verify exact API versions.
- Run staging tests to evaluate p95/p99 and throughput rather than relying on a single manual curl.

**Review questions:**

1. Requests A and B hold all pooled connections, and C cannot get one. Which timeout governs when C fails?
2. TCP connect takes 100ms, yet the server waits 10s before sending headers. Which timeout should you inspect?
3. Why can `maxConnTotal=100` with `maxConnPerRoute=2` still trigger pool acquire timeouts?
4. Distinguish `RequestConfig.setConnectionRequestTimeout` from `ConnectionConfig.setConnectTimeout`.
5. Why does the Spring Boot 3.3 example not call `.setReadTimeout()` on `HttpComponentsClientHttpRequestFactory`?
6. In Reactor Netty `WebClient`, which APIs set pending acquire timeout, connect timeout, and response timeout?
7. Why is an `HTTP 504` from a gateway not necessarily a client read-timeout exception?
8. When response bodies are not closed, how do `leased/pending/available` counts shift?
9. With three retries, why do per-attempt timeouts fail to guarantee a 5-second SLA?
10. Why cannot `Mono.timeout(Duration.ofSeconds(5))` replace pool capacity tuning?
11. For SSE or streaming downloads, why must read inactivity timeout and total deadline follow different rules than small REST requests?
12. When reproducing a connect timeout, why use a controlled test network environment instead of connecting to an unlistening localhost port?

**Takeaway:** an outbound HTTP call can **wait for a pooled connection**, **wait to establish a TCP connection**, and **wait for responses/byte reads**. All three phases must be configured and observed separately. In Spring Boot 3.3, configure timeouts on the **version-matched HTTP engine/factory/connector**, enforce business deadlines across the whole call when required, and bound pools/queueing to prevent cascading failures.

### References

- Spring Boot 3.3 — Calling REST Services, `RestClient`, `RestTemplate`, `WebClient`: https://docs.spring.io/spring-boot/3.3/reference/io/rest-client.html
- Spring Boot 3.3 — HTTP Client how-to: https://docs.spring.io/spring-boot/3.3/how-to/http-clients.html
- Spring Framework 6.1 — `HttpComponentsClientHttpRequestFactory`: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/http/client/HttpComponentsClientHttpRequestFactory.html
- Spring Framework 6.1 — `RestClient.Builder`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/client/RestClient.Builder.html
- Apache HttpClient 5.3 — `RequestConfig.Builder`: https://hc.apache.org/components/httpcomponents-client-5.3.x/5.3.1/httpclient5/apidocs/org/apache/hc/client5/http/config/RequestConfig.Builder.html
- Apache HttpClient 5.3 — `ConnectionConfig.Builder`: https://hc.apache.org/components/httpcomponents-client-5.3.x/5.3.1/httpclient5/apidocs/org/apache/hc/client5/http/config/ConnectionConfig.Builder.html
- Apache HttpClient 5.3 — Pooling Connection Manager builder: https://hc.apache.org/components/httpcomponents-client-5.3.x/5.3.1/httpclient5/apidocs/org/apache/hc/client5/http/impl/io/PoolingHttpClientConnectionManagerBuilder.html
- Reactor Netty — HTTP Client timeout and connection provider: https://projectreactor.io/docs/netty/release/reference/http-client.html
- Spring Framework — WebClient configuration and timeouts: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html
- Java 17 — Duration API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Duration.html