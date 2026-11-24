# ClientHttpRequestFactory and Choosing the Underlying HTTP Library in Spring

## 1. Context: Same RestClient, Different Underlying HTTP Engines

In Java/Spring, a call to an external HTTP service can be written at a high level:

~~~java
Order order = restClient.get()
        .uri("/orders/{id}", 42)
        .retrieve()
        .body(Order.class);
~~~

This is a fragment assuming `RestClient restClient` and an `Order` class/record configured elsewhere. The snippet describes **what to call**: GET, URI template, convert JSON to DTO. But to actually send a request over TCP/TLS, Spring needs an **HTTP transport implementation**.

Technical stack:

~~~text
Business code
     |
     v
RestClient / RestTemplate              (synchronous HTTP API)
     |
     v
HttpMessageConverter + Interceptors   (JSON, headers, logging)
     |
     v
ClientHttpRequestFactory              (transport selection SPI)
     |
     +-- JdkClientHttpRequestFactory  --> java.net.http.HttpClient
     +-- HttpComponentsClientHttpRequestFactory --> Apache HttpClient 5
     +-- JettyClientHttpRequestFactory --> Jetty HttpClient
     +-- ReactorNettyClientRequestFactory --> Reactor Netty HttpClient
     +-- SimpleClientHttpRequestFactory --> HttpURLConnection
     |
     v
DNS -> connection acquire -> TCP -> TLS -> HTTP write/read -> response
~~~

**`ClientHttpRequestFactory` is Spring's abstraction for creating an executable HTTP request, not a factory for creating RestClient.** Swapping the factory can change connection pooling, HTTP versions, redirects/proxies, TLS, timeout types, performance, and error behavior without necessarily rewriting all business code.

### Learning Objectives

After this lesson, you will be able to:
1. Explain the `ClientHttpRequestFactory` interface and the roles of `ClientHttpRequest`/`ClientHttpResponse`.
2. Understand how `RestClient` and `RestTemplate` choose a request factory.
3. Compare `SimpleClientHttpRequestFactory`, `JdkClientHttpRequestFactory`, Apache HttpClient 5, Jetty, and Reactor Netty.
4. Select an HTTP transport suited to the workload: request rate, multiple hosts, pooling, HTTP/2, proxies, mTLS, TLS, and retry policies.
5. Configure timeouts at the **right layer**: connection acquisition, TCP connect, TLS handshake, response/read, overall deadline.
6. Understand the boundaries of Spring Framework **6.1** vs **6.2+**, avoiding copying APIs that do not yet exist.
7. Configure a `RestClient` bean with an explicit factory and Java 17.
8. Build a runnable demo with Spring Boot 3.3.5, a local server, and real HTTP JUnit tests.
9. Avoid resource leaks, thread starvation, SSRF, credential leakage, redirect surprises, and assuming immutable transport defaults.

Parent context: **synchronous HTTP clients**. `RestClient` debuted in Spring Framework 6.1. The examples below use **Java 17 + Spring Boot 3.3.5**, without applying newer Spring 7/Boot 4 APIs to the demo code.

## 2. What Does `ClientHttpRequestFactory` Actually Define?

In Spring Framework 6.1, the interface resides in package:

~~~java
org.springframework.http.client.ClientHttpRequestFactory
~~~

Core method:

~~~java
ClientHttpRequest createRequest(
        URI uri, HttpMethod httpMethod) throws IOException;
~~~

- `URI` identifies the destination and path to call.
- `HttpMethod` specifies GET/POST/PUT/PATCH/DELETE, etc.
- The result is a `ClientHttpRequest` whose headers/body can be prepared and then executed.
- `IOException` can arise when creating the request fails; errors during actual sending/reading typically surface later.
- `ClientHttpRequest.execute()` returns `ClientHttpResponse` once the request is sent and the response is available.

### 2.1. Low-Level Synchronous Flow

~~~text
factory.createRequest(uri, GET)
  -> request.getHeaders().setAccept(...)
  -> request.execute()                 [network may block]
  -> response.getStatusCode()
  -> response.getBody()                [I/O may block]
  -> close response/body resources
~~~

This is a conceptual description, not a recommendation to write business HTTP code using this low-level SPI. `RestClient`/`RestTemplate` normally manage headers, converters, error handling, and closing the response with the right lifecycle. When using `ClientHttpRequest` directly, the application must enforce closing `ClientHttpResponse`.

### 2.2. Does a Request Factory Make the HTTP Client Non-Blocking?

**No.** An underlying factory whose internal engine supports asynchronous I/O (such as Reactor Netty or JDK HttpClient) still serves a **synchronous request/response contract** when used through `RestClient`/`RestTemplate`. The thread calling `restClient.get()...retrieve()...body(...)` may block waiting for the result.

If running on a Spring WebFlux event-loop thread, **never** use `RestClient` directly in a handler assuming a Reactor Netty factory makes it non-blocking. For end-to-end non-blocking behavior, use reactive `WebClient` and return `Mono/Flux`, avoiding `block()`. If a legacy synchronous API must be called inside WebFlux, isolate it onto a bounded worker, and measure queue depth/timeouts.

### 2.3. Factories Differ from Message Converters

`HttpMessageConverter` converts Java objects ↔ HTTP payloads (Jackson JSON, String, form, etc.). It does not control connection pools or TLS protocols. `ClientHttpRequestFactory` controls how bytes are sent/received over HTTP. Changing the factory does not automatically change Jackson serializers, DTO versions, retry policies, or API error schemas.

## 3. ClientHttpRequestFactory Is the SPI, RestClient Is the Consumer API

### 3.1. `RestClient`

`RestClient` is Spring's **synchronous, fluent** HTTP client introduced in Spring 6.1:

~~~java
RestClient client = RestClient.builder()
        .baseUrl("https://service.example.test")
        .requestFactory(factory)
        .build();
~~~

`factory` is an injected or explicitly built `ClientHttpRequestFactory` bean. Operations:
- `get()`/`post()` select the method.
- `uri(...)` supports template variables.
- `header(...)`, `accept(...)`, `contentType(...)` add HTTP metadata.
- `body(...)` sends the body.
- `retrieve()` reads the response in the standard way with default status handling.
- `exchange(...)` gives custom raw response/status handling; you must manage errors/statuses yourself.

### 3.2. `RestTemplate`

`RestTemplate` still exists and is widely used in existing codebases:

~~~java
RestTemplate template = new RestTemplate(factory);

Order order = template.getForObject(
        "https://service.example.test/orders/{id}",
        Order.class, 42);
~~~

Both APIs can share **the same factory**. Migrating `RestTemplate` → `RestClient` does not force changing the HTTP engine at the same time; separating the two decisions reduces migration risk.

### 3.3. Do Not Confuse WebClient and ClientHttpConnector

`WebClient` (reactive) uses the `ClientHttpConnector` abstraction, such as `ReactorClientHttpConnector`, **not** `ClientHttpRequestFactory` as its primary extension point. `ReactorNettyClientRequestFactory` is an adapter for using Reactor Netty inside synchronous clients; it does not make RestClient's API reactive.

## 4. Available HTTP Backends in Spring 6.1

| Factory | Underlying HTTP Library | When Suitable | Points to Consider |
| --- | --- | --- | --- |
| `SimpleClientHttpRequestFactory` | `java.net.HttpURLConnection` | Demos, simple integrations, minimal dependencies | Legacy JDK API limits/quirks, status/error paths, features |
| `JdkClientHttpRequestFactory` | `java.net.http.HttpClient` (Java 11+) | Java 17, no third-party library needed, HTTP/2 if peer supports | Fewer pool knobs than Apache; JDK TLS/proxy/redirect semantics |
| `HttpComponentsClientHttpRequestFactory` | Apache HttpClient **5.x** | Pool tuning, enterprise proxies, high outbound volume, connection management | Requires adding Apache HttpClient 5, managing pooling/lifecycle/timeouts |
| `JettyClientHttpRequestFactory` | Jetty HttpClient | Teams standardized on Jetty, Jetty HTTP features | Extra dependencies, separate lifecycle, timeouts/proxy config |
| `ReactorNettyClientRequestFactory` | Reactor Netty HttpClient | Systems already using Reactor Netty wanting deliberate resource sharing | Client call API remains synchronous; event loops/pool ownership must be clear |
| `BufferingClientHttpRequestFactory` | Wrapper around another factory | Need to read request/response bodies multiple times | Buffers entire body in RAM; dangerous for large payloads |
| `InterceptingClientHttpRequestFactory` | Wrapper supporting interceptors | Headers, tracing, request hooks | Does not change transport; logging raw bodies carries risk |

Do not assume factories have completely identical behavior: TLS/proxy/redirect/HTTP protocols, exception wrapping, and connection reuse can differ. When switching transports, **run regression tests** against real downstreams and gateways.

### 4.1. `SimpleClientHttpRequestFactory`

The oldest adapter, using `HttpURLConnection`:

~~~java
SimpleClientHttpRequestFactory f =
        new SimpleClientHttpRequestFactory();
f.setConnectTimeout(Duration.ofSeconds(2));
f.setReadTimeout(Duration.ofSeconds(5));
~~~

This is a Java fragment (imports are in the official documentation). Simple, but do not pick it merely thinking all other backends are needlessly complex. In some environments, `HttpURLConnection` has awkward behavior when accessing error response statuses; the Spring reference recommends trying another factory if issues arise.

**Spring 6.1:** `setBufferRequestBody(boolean)` and `setOutputStreaming(boolean)` on Simple factory were deprecated/marked for removal because request bodies are **no longer buffered under that option**. Do not copy old articles advising `setBufferRequestBody(false)` as a mandatory optimization; check the Javadoc for your exact version.

### 4.2. `JdkClientHttpRequestFactory`

Based on the JDK's `java.net.http.HttpClient`:

~~~java
HttpClient httpClient = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(2))
        .followRedirects(HttpClient.Redirect.NEVER)
        .version(HttpClient.Version.HTTP_1_1)
        .build();

JdkClientHttpRequestFactory f =
        new JdkClientHttpRequestFactory(httpClient);
f.setReadTimeout(Duration.ofSeconds(3));
~~~

Advantages:
- Built into Java 17, no Apache/Jetty dependency required.
- HTTP/1.1 or HTTP/2 negotiation depending on `HttpClient.Version` and server support.
- Reusing the client across requests lets the JDK manage connections and executors per its implementation.
- Provides standard JDK APIs for proxy, authenticator, and SSLContext/SSLParameters configuration.

**This does not mean JDK HttpClient offers the same level of tuning** for per-route/max-total pools or lease timeouts as Apache HttpClient 5. If you need to cap outbound concurrency, you can still use semaphores/bulkheads/application limits, though they are not equivalent to tuning internal pool knobs.

### 4.3. `HttpComponentsClientHttpRequestFactory`

Based on **Apache HttpClient 5.1+** via `org.apache.httpcomponents.client5:httpclient5`, not Apache HttpClient 4.x/`org.apache.http.client.HttpClient`.

~~~java
HttpComponentsClientHttpRequestFactory f =
        new HttpComponentsClientHttpRequestFactory();
f.setConnectTimeout(Duration.ofSeconds(2));
f.setConnectionRequestTimeout(Duration.ofMillis(500));
~~~

This is a fragment. `setConnectionRequestTimeout` is critical when using a connection manager: it bounds how long to **wait to borrow a connection** from the pool. `setConnectTimeout` bounds the connect phase at the request configuration layer, though the Spring 6.1 Javadoc notes it **does not cover the entire TLS handshake/CONNECT proxy**; dedicated socket/TLS settings are required for strict timeouts.

**Version difference that causes compilation errors: Spring Framework 6.1 does not have `HttpComponentsClientHttpRequestFactory.setReadTimeout(...)`.** That API appeared in newer releases like Spring 6.2. With Boot 3.3.5/Framework 6.1, use Apache's `RequestConfig.setResponseTimeout(...)` via the underlying HttpClient configuration.

### 4.4. `JettyClientHttpRequestFactory`

Uses Jetty's HTTP client:

~~~java
JettyClientHttpRequestFactory f =
        new JettyClientHttpRequestFactory();
~~~

This fragment does not handle lifecycle, dependencies, or transport configuration. Appropriate when a system already uses Jetty client features, not as the default choice for every new app. Instantiating multiple independent Jetty clients can spawn multiple worker/executor resources. Check the 6.1 API, share a factory/client bean, and close cleanly on shutdown.

### 4.5. `ReactorNettyClientRequestFactory`

Uses Reactor Netty inside the synchronous framework interface. Requires the matching Reactor Netty dependency/runtime. Suitable when the ecosystem already relies on Reactor Netty, provided you understand:
- Networking resources involve event loops and connection pools.
- RestClient calls **remain blocking for the caller**.
- Resource reuse and HTTP client lifecycle require planning if the app creates multiple factories.
- Do not add the WebFlux starter to a Spring MVC app solely to select a transport; the dependency graph can affect Boot's web application type or auto-configuration. Pick the reactor-netty dependency/Boot platform intentionally.

## 5. How Does Spring RestClient Pick a Default Factory?

### 5.1. Do Not Rely on Assuming HttpURLConnection Is Always the Default

Spring Framework 6.1 documentation for `RestClient.Builder.requestFactory(...)` explains that when no factory is specified, the framework checks for Apache/Jetty clients on the classpath; if the JDK HTTP client is available, it uses the JDK client; only lastly does it fall back to simple.

**Depending on the application and setup**, Spring Boot may also participate in auto-detection via the auto-configured builder, and the classpath determines the selection. Adding an HTTP library via a transitive dependency can silently change the default backend without changing a single line of HTTP call code.

Therefore, for services requiring specific timeout/pooling/TLS behavior:
- Pass an explicit `requestFactory(factory)` when you want to guarantee the transport type.
- Do not infer from 200 responses that the connection policy did not change.
- Inspect the dependency tree before and after adding starters/libraries.
- Write timeout/redirect/proxy integration tests and monitor connection pools in staging.

### 5.2. Boot 3.3 Differs from Newer Boot Versions

Spring Boot 3.3 provides `RestClient.Builder` and `RestTemplateBuilder` auto-configurations. “Current” Spring Boot docs or Boot 3.4+/4.x may change builder packages/imports, property names, or how HTTP clients are selected. **Do not copy `spring.http.clients.imperative.factory` or Spring Boot 4 builder imports into a Boot 3.3.5 app without checking versions.**

In the demo, we use Boot's `RestClient.Builder` while **attaching an explicit JDK factory**, avoiding reliance on auto-detection. If using Boot 3.3's `RestTemplateBuilder`, the right package is `org.springframework.boot.web.client.RestTemplateBuilder`, not Boot 4's newer package.

## 6. What Makes an HTTP Backend Suitable?

No single HTTP client library is optimal for every application. Decide based on **actual requirements**:

| Requirement | Transport Selection Question |
| --- | --- |
| Ease of packaging | Does Java 17/JDK client already have enough features? |
| High outbound concurrency | Do you need max total, per-route pools, lease timeout, queue depth? |
| HTTP/2 | Do client/server/proxy negotiate HTTP/2 and fall back cleanly? |
| Enterprise proxies | Are there HTTP CONNECT proxies, custom auth, allowlists? |
| TLS/mTLS | Are client certificates, custom trust bundles, hostname verification needed? |
| Latency limits | Do timeouts cover connect, TLS, pool wait, first-byte/read, and overall deadline? |
| Redirects | Are redirects allowed? Is there risk of leaving trusted origins? |
| Large payloads | Is there true streaming upload/download without unbounded buffering? |
| Observability | Are active/idle/pending connections, TLS errors, status/latency metrics exposed? |
| Operations | Does the pool close cleanly, support keep-alive/idle eviction, and respect DNS rotation? |
| Dependencies | Are security patches, CVEs, compatibility, and BOM managed? |
| Team | Does existing debugging/tooling fit Apache, JDK, Jetty, or Reactor Netty? |

### 6.1. When Starting with JDK HttpClient Makes Sense

- Service has moderate outbound request volume.
- Java 17 is already the baseline.
- Complex connection manager tuning is unnecessary.
- Want to minimize third-party dependencies.
- Want explicit redirect policies and standard JDK SSL configuration.
- Integration tests prove TLS/proxy/timeouts are sufficient.

The JDK client does not mean “no pooling”—it has internal connection reuse, though pool controls differ from Apache. Never create a new `HttpClient` per request.

### 6.2. When Apache HttpClient 5 Is Worth Considering

- Many distinct downstream hosts and high concurrency.
- Need max total/per-route connections and connection lease timeouts.
- Need custom proxy route planners, authentication, or TLS/socket controls.
- Want to inspect pool saturation/eviction via Apache manager APIs.
- System is already standardized on HttpClient 5.

Switching to Apache does not increase throughput if the bottleneck is downstream 429s, a database, or server limits. Increasing total pool size must never exceed partner API rate limits.

### 6.3. When Spring MVC Makes More Sense Than WebFlux

If an application is primarily JDBC/JPA + sync RestClient, Spring MVC's blocking request model may fit well. Using WebFlux while wrapping almost every operation in boundedElastic adds complexity without guaranteed benefit. Pick the stack based on real dependencies and concurrency rather than framework hype.

## 7. Different Timeout Phases

A “3-second timeout” sounds simple, yet can correspond to distinct phases:

~~~text
time -->
[DNS lookup] [pool wait] [TCP connect] [TLS handshake]
                                  [send body] [wait response header]
                                             [read response body]
|------------------------- overall request deadline -------------|
~~~

| Timeout/Budget | Phase | Example Configuration |
| --- | --- | --- |
| Pool acquire / connection request | Waiting for a connection from the pool | Apache `setConnectionRequestTimeout` |
| Connect | TCP connection | JDK `HttpClient.Builder.connectTimeout` or Simple `setConnectTimeout` |
| TLS handshake | TLS negotiation | Client/socket-specific SSL settings |
| Response/read | Waiting for response/reading data | JDK factory `setReadTimeout`; Apache 5 `RequestConfig.responseTimeout` |
| Whole-call deadline | End-to-end operation | Policy outside HTTP factory, API-specific deadline/cancellation |
| Caller's deadline | How long caller is willing to wait | Request SLA/gateway timeout, thread budget |

**Do not arbitrarily add/subtract values and call them the total end-to-end SLA.** DNS lookup and TLS handshake can have their own semantics; JDK/Apache/Jetty are not completely identical.

### 7.1. Connect Timeout

When a downstream host fails to answer the TCP handshake, connect timeout prevents threads from hanging indefinitely. However:
- DNS lookup may use its own resolver mechanism.
- Connection reuse skips establishing a new TCP connection.
- TLS handshake is a separate phase.
- Proxy CONNECT can add an extra connection layer.

### 7.2. Connection Request Timeout in Apache

If a pool caps max 20 connections per route, the 21st request may have to wait. `setConnectionRequestTimeout(Duration.ofMillis(500))` bounds how long to wait **to borrow a connection from the pool**, which is not a network read timeout and does not make the server respond faster.

When an application has 100 server threads and an Apache pool of 10 connections:
- 10 requests can actively use connections.
- The remaining 90 threads may wait on pool acquire, occupying servlet workers.
- Without an acquire timeout and queue budget, a slow downstream wave causes server thread exhaustion.

Pools must be sized according to concurrency, latency, downstream quotas, and backpressure/admission control; blindly raising the limit to 1,000 connections is not better.

### 7.3. Response Timeout Differs from Overall Deadline

Apache `RequestConfig` has a response timeout. JDK factory `setReadTimeout` ties into the underlying `HttpRequest.Builder.timeout` per Spring Javadoc. These mechanisms do not necessarily mean a per-read-byte socket SO_TIMEOUT, and must be tested empirically against streaming/slow-body endpoints.

If a business deadline strictly requires 2 s, use a client supporting end-to-end timeouts/deadlines, operation-level cancellation, or pool/driver/proxy policies; verify DNS, connect, headers, and body rather than merely calling `setReadTimeout(2s)` and treating it as absolute.

### 7.4. Zero Is Not Always a “Safe Disabled Timeout”

Some APIs treat 0 as an infinite timeout; default timeouts may come from the JVM/system/client. An infinite deadline causes thread starvation when a downstream hangs. In production, always enforce approved time budgets, deadline propagation, and per-route circuit breakers/rate limits.

## 8. Connection Lifecycle and Pooling

### 8.1. Reuse a Long-Lived Client/Factory

**Never create a RestClient+HttpClient inside every request handler**:

~~~java
@GetMapping("/orders/{id}")
Order bad(@PathVariable long id) {
    HttpClient newHttpClient = HttpClient.newHttpClient();
    RestClient newRestClient = RestClient.builder()
            .requestFactory(
                    new JdkClientHttpRequestFactory(newHttpClient))
            .build();

    return newRestClient.get()
            .uri("https://trusted.example.test/orders/{id}", id)
            .retrieve()
            .body(Order.class);
}
~~~

This is an **anti-pattern**: continually allocating client resources reduces connection/executor reuse and complicates metrics and shutdown. The sample also lacks enclosing class/method context and is not standalone runnable.

Instead, inject a singleton `RestClient` (or typed Gateway) with a configured request factory. That does not mean one RestClient for all downstreams must share identical auth/timeouts; create **one RestClient bean per upstream service** when requirements differ.

### 8.2. Apache Pool Lifecycle

Apache `CloseableHttpClient` and `PoolingHttpClientConnectionManager` must be closed/evicted by their owner. Spring's `HttpComponentsClientHttpRequestFactory` implements `DisposableBean` in 6.1 and can close the underlying client when the factory is destroyed; **do not accidentally let multiple factories co-own the same Apache client so each tries to close it unpredictably**.

If you build a manager/client separately to inject elsewhere, establish clear close ownership to avoid double-shutdown of shared pools. Never let an earlier test case close a singleton client that subsequent tests still need.

### 8.3. Keep-Alive and Idle Connections

Connection reuse cuts TCP/TLS setup overhead, with trade-offs:
- Servers/load balancers may close idle connections.
- DNS IP changes can interact with keep-alive.
- TLS certificate rotation and proxy config changes need testing.
- Pool stale-connection retries may occur; never auto-retry non-idempotent operations.
- Connection max lifetime/idle eviction must align with infrastructure.

### 8.4. One Factory Does Not Mean One Connection

A single singleton factory can manage many pooled connections. The resources to measure are **active/idle connections, pending acquires, and request latency**, not counting factory objects and assuming “there is only 1 TCP socket”.

## 9. HTTP Statuses, Network Errors, and RestClient

### 9.1. Network Failures Differ from HTTP 4xx/5xx

- **HTTP 404**: the server returned an HTTP response; this is an application/protocol response, not a TCP failure by default.
- **HTTP 503/429**: downstream signals overload/rate policy, possibly requiring backoff per Retry-After.
- **Connection refused/reset, DNS failure, TLS handshake failure**: no valid HTTP response received.
- **Read timeout**: client waited past its configured limit; not proof the server failed to apply a POST's side effect.

In `RestClient.retrieve()`, Spring maps HTTP error statuses (4xx/5xx) to the corresponding exception hierarchy by default. To apply a custom gateway/domain mapping, use `onStatus(...)` or `exchange(...)` and return your application's contract response—never catch Throwable and treat everything as 404.

### 9.2. Example Handling 404 in a Gateway

~~~java
public Optional<Order> maybeGet(URI uri) {
    try {
        Order order = restClient.get()
                .uri(uri)
                .retrieve()
                .body(Order.class);
        return Optional.ofNullable(order);
    } catch (HttpClientErrorException.NotFound notFound) {
        return Optional.empty();
    }
}
~~~

This is a method fragment inside a class with `RestClient restClient`; `HttpClientErrorException.NotFound` is in `org.springframework.web.client`. Catch only 404; never swallow 401/403/429/500, connect timeouts, JSON decode errors, or SSL errors into Optional.empty.

### 9.3. Closing Responses When Using Raw `exchange`

When using low-level `ClientHttpRequest.execute()`, close the response properly to return the pooled connection and prevent leaks. With `RestClient.exchange(...)`, the framework manages callback execution/closing per contract, but **never retain a raw InputStream/response body after the callback ends** expecting to read it later.

~~~java
int status = restClient.get()
        .uri(uri)
        .exchange((request, response) ->
                response.getStatusCode().value());
~~~

This fragment reads only the status and retains no reference to the response object outside the callback; unlike `retrieve()`, `exchange()` does not apply default status handlers in the same way, so you must interpret the status yourself.

## 10. Security When Choosing an HTTP Transport

### 10.1. SSRF (Server-Side Request Forgery)

Wrong:

~~~java
@GetMapping("/proxy")
String unsafe(@RequestParam String url) {
    return restClient.get()
            .uri(url)
            .retrieve()
            .body(String.class);
}
~~~

**Never** let users specify arbitrary URLs for the server to call directly without SSRF protections. Users could target loopback, cloud metadata IPs, internal control planes, DNS rebinding, or redirects to private destinations.

Better:
- Fixed base URL loaded from trusted server configuration.
- Path/ID encoded via URI templates.
- Allowlist schemes/hosts/ports and DNS/redirect policies if dynamic destinations are required.
- Network egress/firewall rules blocking unauthorized private/internal endpoints.
- Do not follow uncontrolled redirects to other origins.
- Test resolution and effective destinations, including IPv6, punycode, and redirects.

`RestClient` encoding a URI is not itself SSRF protection; encoding only handles syntax.

### 10.2. Never Disable TLS Verification

When configuring JDK/Apache/Jetty, keep CA trust validation and hostname verification enabled. “Trust-all SSLContext” or `NoopHostnameVerifier` snippets allow credentials to leak via MITM; never deploy them to production, even “temporarily to fix a handshake”. For mTLS, use client certificates/keystores or Spring Boot SSL bundles (per version) and test rotation/expiry.

### 10.3. Never Log Authorization or Raw Bodies

Interceptors/logging can observe headers and request/response bodies. Avoid:
- Logging `Authorization`, `Cookie`, `Set-Cookie`, API keys.
- Dumping raw request bodies containing passwords, cards, tokens, or PII.
- Using unbounded user IDs/URLs as metric labels.
- Keeping raw response bodies in memory too long for debugging.

Prefer logging method, trusted host, path template, status, elapsed time, byte size, and sanitized trace IDs.

### 10.4. Redirect Policy and Credentials

JDK `HttpClient.Redirect.NEVER` is an intentional default in the demo. Redirects can target a different host or change HTTP methods depending on status/client implementation. If enabling followRedirects:
- Validate trusted destinations and never leak Authorization across origins.
- Watch 301/302/303 vs 307/308 behavior for POST.
- Cap redirect hops and max response sizes.
- Never blindly retry side-effecting POSTs.

### 10.5. Proxy Authentication and Trust Boundaries

Enterprise proxies may require authentication, TLS interception, or mTLS. Use JDK/Apache APIs to configure proxies securely; never embed passwords into HTTP URIs or source code. Define proxy connect timeouts, CONNECT/TLS handshakes, and certificate trust chains.

## 11. Runnable Example: RestClient + Explicit JDK Factory

A small Spring Boot application containing:
- A **local HTTP endpoint** `GET /downstream/orders/{id}` returning order JSON or 404.
- A `ClientHttpRequestFactory` bean explicitly choosing **JdkClientHttpRequestFactory** and JDK `HttpClient`.
- A `RestClient` bean using that exact factory without relying on classpath auto-detection.
- An `OrderGateway` so business APIs do not depend on the transport implementation.
- `@SpringBootTest(webEnvironment=RANDOM_PORT)` starting a real HTTP server and tests using `@LocalServerPort` so the client calls the local test server.
- JUnit tests verifying 200/404, HTTP factory bean type, and URI/templates without needing the Internet.

**Because tests use a random port**, they do not rely on a hardcoded 8080 port. The demo runs with Java 17, compatible Gradle 8.x, and dependencies fetched from Maven Central. The files below omit Gradle wrapper scripts; generate the wrapper if your repository lacks one.

~~~text
http-factory-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/httpfactory/
    │   ├── HttpFactoryApplication.java
    │   ├── config/HttpClientConfig.java
    │   ├── domain/Order.java
    │   ├── gateway/OrderGateway.java
    │   └── web/DownstreamDemoController.java
    └── test/java/com/example/httpfactory/
        └── HttpFactoryIntegrationTest.java
~~~

### 11.1. Gradle

`settings.gradle`:

~~~groovy
rootProject.name = 'http-factory-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`spring-boot-starter-web` here only spins up a **Spring MVC/Tomcat HTTP test server**. That fits the **synchronous** `RestClient` completely; no WebFlux dependency is needed.

### 11.2. Main Application

`src/main/java/com/example/httpfactory/HttpFactoryApplication.java`:

~~~java
package com.example.httpfactory;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HttpFactoryApplication {
    public static void main(String[] args) {
        SpringApplication.run(HttpFactoryApplication.class, args);
    }
}
~~~

### 11.3. Order DTO

`src/main/java/com/example/httpfactory/domain/Order.java`:

~~~java
package com.example.httpfactory.domain;

public record Order(long id, String state) {}
~~~

Java 17 records are encoded/decoded to JSON by Spring Boot's default Jackson setup. `state` is a String to keep the example clear; production systems may use enums/validation per contract.

### 11.4. Explicitly Configured HTTP Factory

`src/main/java/com/example/httpfactory/config/HttpClientConfig.java`:

~~~java
package com.example.httpfactory.config;

import java.net.http.HttpClient;
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.ClientHttpRequestFactory;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration
public class HttpClientConfig {

    @Bean
    public ClientHttpRequestFactory orderRequestFactory() {
        HttpClient jdkClient = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(2))
                .followRedirects(HttpClient.Redirect.NEVER)
                .version(HttpClient.Version.HTTP_1_1)
                .build();

        JdkClientHttpRequestFactory factory =
                new JdkClientHttpRequestFactory(jdkClient);
        factory.setReadTimeout(Duration.ofSeconds(3));
        return factory;
    }

    @Bean
    public RestClient orderRestClient(
            RestClient.Builder builder,
            ClientHttpRequestFactory orderRequestFactory) {

        return builder
                .requestFactory(orderRequestFactory)
                .build();
    }
}
~~~

Explanation:
1. `@Bean ClientHttpRequestFactory` is a singleton in the Spring context.
2. The underlying HTTP engine is built from JDK 17's `java.net.http.HttpClient`.
3. Connect timeout 2 s and read/request timeout 3 s are **two separate knobs**, not a global 5-second SLA.
4. `Redirect.NEVER` prevents auto-following redirects in the demo; the app receives 3xx statuses or handles them per `RestClient` policy.
5. HTTP/1.1 is chosen for simple testing with embedded Tomcat. If trying HTTP/2, verify server/proxy/TLS support and run regression tests.
6. `RestClient.Builder` is provided by Boot; `requestFactory` is called explicitly to keep the transport consistent even if Apache/Jetty appear on the classpath.
7. Use a RestClient bean to reuse configuration/HTTP resources rather than creating one in every handler method.

**Note:** If a project has multiple `ClientHttpRequestFactory` beans, add `@Qualifier("orderRequestFactory")` at the injection point to avoid ambiguity. The demo has only one factory, so Spring injects it directly.

### 11.5. Gateway Wrapping the HTTP API

`src/main/java/com/example/httpfactory/gateway/OrderGateway.java`:

~~~java
package com.example.httpfactory.gateway;

import com.example.httpfactory.domain.Order;
import java.net.URI;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class OrderGateway {

    private final RestClient client;

    public OrderGateway(RestClient orderRestClient) {
        this.client = orderRestClient;
    }

    public Order fetch(URI trustedResourceUri) {
        return client.get()
                .uri(trustedResourceUri)
                .accept(MediaType.APPLICATION_JSON)
                .retrieve()
                .body(Order.class);
    }
}
~~~

The parameter name `trustedResourceUri` emphasizes **the value must come from application configuration or trusted code**, never a raw user-supplied `?url=...`. In the demo, tests build the URI from `localhost/random port` provided by the embedded server, so there is no public SSRF surface.

In production:
- Inject a configured trusted `baseUrl` into the Gateway and accept only business IDs.
- Use `uri("/orders/{id}", id)` to encode path variables.
- Define 404/401/429/5xx mappings, timeouts, and retries in the gateway/domain layer.
- Never treat `OrderGateway.fetch` as non-blocking: the calling thread waits for the response.

### 11.6. HTTP Server Endpoint for Transport Testing

`src/main/java/com/example/httpfactory/web/DownstreamDemoController.java`:

~~~java
package com.example.httpfactory.web;

import com.example.httpfactory.domain.Order;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/downstream/orders")
public class DownstreamDemoController {

    @GetMapping("/{id}")
    public ResponseEntity<Order> find(@PathVariable long id) {
        if (id == 1L) {
            return ResponseEntity.ok(new Order(1L, "CONFIRMED"));
        }
        return ResponseEntity.notFound().build();
    }
}
~~~

Local downstream server responses:
- `GET /downstream/orders/1` → 200 + JSON `{"id":1,"state":"CONFIRMED"}`.
- `GET /downstream/orders/999` → 404, no Order JSON.
- No database, authentication, or external service.

It is not a production design for an app to make HTTP calls to itself; **this is a convenient test fixture running over a real network stack** to exercise the request factory on loopback. Real applications call separate downstream services across domain/trust boundaries.

### 11.7. Integration Tests on a Local Port

`src/test/java/com/example/httpfactory/HttpFactoryIntegrationTest.java`:

~~~java
package com.example.httpfactory;

import com.example.httpfactory.domain.Order;
import com.example.httpfactory.gateway.OrderGateway;
import java.net.URI;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.client.ClientHttpRequestFactory;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.web.client.HttpClientErrorException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class HttpFactoryIntegrationTest {

    @LocalServerPort
    int port;

    @Autowired
    OrderGateway gateway;

    @Autowired
    ClientHttpRequestFactory factory;

    URI url(long id) {
        return URI.create(
                "http://127.0.0.1:" + port + "/downstream/orders/" + id);
    }

    @Test
    void usesExplicitJdkRequestFactory() {
        assertInstanceOf(JdkClientHttpRequestFactory.class, factory);
    }

    @Test
    void convertsResponseToOrderRecord() {
        Order result = gateway.fetch(url(1L));
        assertEquals(1L, result.id());
        assertEquals("CONFIRMED", result.state());
    }

    @Test
    void mapsHttp404ToRestClientException() {
        assertThrows(HttpClientErrorException.NotFound.class,
                () -> gateway.fetch(url(999L)));
    }
}
~~~

**What do the tests actually verify?**
- Test 1 confirms the request factory bean type matches the explicit configuration.
- Test 2 proves the JDK factory sends real HTTP, receives 200, and the JSON converter instantiates `Order`.
- Test 3 proves `RestClient.retrieve()` maps 404 by default to `HttpClientErrorException.NotFound` instead of returning a null Order.
- The server uses a random port to avoid conflicts with local services.
- No Internet or credentials needed; host is 127.0.0.1 from the test, never user input.
- Timeout, TLS/mTLS, proxy, connection pool saturation, and HTTP/2 tests are not yet included: add them per real deployment requirements.
- Tests do not measure QPS, p99 latency, or pooling efficiency.

### 11.8. Running the Project

In the directory with the appropriate Gradle wrapper:

~~~bash
./gradlew test
./gradlew bootRun
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat test
.\gradlew.bat bootRun
~~~

With the server running on default port 8080, try:

~~~bash
curl -i 'http://localhost:8080/downstream/orders/1'
curl -i 'http://localhost:8080/downstream/orders/999'
~~~

Expected (200 response):

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":1,"state":"CONFIRMED"}
~~~

Expected 404 response:

~~~http
HTTP/1.1 404 Not Found
~~~

Headers such as Date, Content-Length, transfer-encoding, and charset may vary by server; tests assert status/JSON rather than byte-for-byte raw HTTP headers. The curl commands hit the server fixture directly, while JUnit verifies **RestClient calling this fixture via the JDK request factory**.

## 12. Apache HttpClient 5 Option When Connection Pooling Is Needed

This is **an alternative option**; do not place it directly alongside the JDK demo project in section 11 unless you intentionally switch configurations.

### 12.1. Adding the Right Generation Dependency

In Gradle (Spring Boot 3.3 manages the version via BOM):

~~~groovy
dependencies {
    implementation 'org.apache.httpcomponents.client5:httpclient5'
}
~~~

If the dependency tree already pulls in Apache HttpClient 4, **do not** attempt to inject `org.apache.http.client.HttpClient` into Spring 6's `HttpComponentsClientHttpRequestFactory`; that class requires Apache HttpClient **5.1+**.

### 12.2. Configuring Pool + Response Timeout for Spring 6.1

~~~java
import java.time.Duration;
import org.apache.hc.client5.http.config.RequestConfig;
import org.apache.hc.client5.http.impl.classic.CloseableHttpClient;
import org.apache.hc.client5.http.impl.classic.HttpClients;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManagerBuilder;
import org.apache.hc.core5.util.Timeout;
import org.springframework.http.client.ClientHttpRequestFactory;
import org.springframework.http.client.HttpComponentsClientHttpRequestFactory;

public final class ApacheFactoryExample {

    public static ClientHttpRequestFactory create() {
        var manager = PoolingHttpClientConnectionManagerBuilder.create()
                .setMaxConnTotal(60)
                .setMaxConnPerRoute(20)
                .build();

        RequestConfig requestConfig = RequestConfig.custom()
                .setConnectionRequestTimeout(Timeout.ofMilliseconds(500))
                .setResponseTimeout(Timeout.ofSeconds(3))
                .build();

        CloseableHttpClient client = HttpClients.custom()
                .setConnectionManager(manager)
                .setDefaultRequestConfig(requestConfig)
                .disableRedirectHandling()
                .build();

        HttpComponentsClientHttpRequestFactory factory =
                new HttpComponentsClientHttpRequestFactory(client);
        factory.setConnectTimeout(Duration.ofSeconds(2));
        return factory;
    }
}
~~~

This is a Java 17 class using Apache HttpClient 5 APIs compatible with Spring 6.1. To let Spring manage lifecycle, expose the factory as a `@Bean` and let the context destroy it; never create a new factory per HTTP request. If ownership is designed differently, ensure `CloseableHttpClient.close()` and the connection manager release exactly once.

**Why are there three distinct timeouts/limits?**
1. `MaxConnTotal(60)`: total pool connection cap (demo).
2. `MaxConnPerRoute(20)`: per-route cap.
3. `ConnectionRequestTimeout(500ms)`: wait time to borrow a connection.
4. `ResponseTimeout(3s)`: wait time for response per Apache config.
5. `ConnectTimeout(2s)`: TCP connect limit on the Spring factory.

The numbers above are **for demo**, not defaults or recommended production values. TCP connect/TLS handshake/proxy still need client-specific testing; Spring 6.1's `setConnectTimeout` has scoped coverage.

### 12.3. Why Not Use `factory.setReadTimeout`?

In **Spring Framework 6.1**, `HttpComponentsClientHttpRequestFactory` does not have that method. Calling:

~~~java
factory.setReadTimeout(Duration.ofSeconds(3));
~~~

is **incorrect** when `factory` has type `HttpComponentsClientHttpRequestFactory` on Framework 6.1. You must configure response timeout on Apache's `RequestConfig` as shown above. `JdkClientHttpRequestFactory` and `SimpleClientHttpRequestFactory` do have `setReadTimeout` in 6.1. Never assume from similar names that all request factories share identical setters.

### 12.4. Pool Sizing via Little's Law

Suppose a downstream takes 200 ms on average and needs 100 sustained calls/s. By Little's Law, average in-flight requests are roughly **100 × 0.2 = 20** (in steady state, before accounting for queues and tails). If per-route max is 10, requests will queue even if the server has plenty of worker threads.

However, a pool of 20 is **not a complete design**: p95/p99 response times, retries, bursts, tenant quotas, downstream max connections, and TLS overhead all require headroom and limits. Benchmark on real workloads and monitor pool pending/acquire waits rather than counting peak QPS alone.

## 13. RestTemplate Also Uses a Factory, Though the API Differs from RestClient

In Spring Boot 3.3, RestTemplate can be configured as:

~~~java
@Bean
RestTemplate customRestTemplate(
        ClientHttpRequestFactory factory) {

    return new RestTemplate(factory);
}
~~~

Or using Boot 3.3 `RestTemplateBuilder` to retain customizers/converters:

~~~java
@Bean
RestTemplate customRestTemplate(RestTemplateBuilder builder) {
    return builder
            .requestFactory(JdkClientHttpRequestFactory.class)
            .build();
}
~~~

These are fragments inside `@Configuration` with appropriate imports. Note `RestTemplateBuilder.requestFactory(Class<? extends ClientHttpRequestFactory>)` requires the factory to have a matching constructor; if a customized JDK `HttpClient` and specific timeouts are needed, use a supplier/function or an explicit factory bean.

**Do not replace the entire RestTemplateBuilder bean** if you want to keep Boot's active auto-configuration/customizers. When providing a custom builder, use Boot 3.3's `RestTemplateBuilderConfigurer` to preserve Boot defaults, or simply inject the Boot-provided builder.

### 13.1. RestTemplate → RestClient Migration

A practical strategy:
1. Inventory existing timeouts, proxies, TLS, redirects, default headers, interceptors, auth, and error mappings.
2. Keep the same factory/client backend while switching syntax to isolate risk.
3. Verify the contract with tests for 200/4xx/5xx, JSON, content types, and malformed bodies.
4. Check how `RestClient.retrieve()` default error mapping differs from legacy wrappers/custom ResponseErrorHandlers.
5. Only afterward swap the transport if justified: performance, pooling, TLS, HTTP/2, or proxies.
6. Measure latency/pools/retries in staging, using feature flags/gradual rollout for critical call paths.

### 13.2. Avoid Duplicating Configuration Across Clients

A `@Configuration` class can manage shared HTTP factory settings for multiple RestClients, but do not force every downstream to share the same trust store, connection pool, proxy, or retry budget. A payment API client and a public metadata API client likely need different security and timeout settings.

## 14. Interceptors, Request Initializers, and Request Factory Wrappers

### 14.1. Attaching Headers/Correlation in the Right Place

~~~java
RestClient client = RestClient.builder()
        .requestFactory(factory)
        .defaultHeader("X-App-Client", "catalog")
        .requestInterceptor((request, body, execution) -> {
            long started = System.nanoTime();
            try {
                return execution.execute(request, body);
            } finally {
                long nanos = System.nanoTime() - started;
                // Export metric with low-cardinality labels.
            }
        })
        .build();
~~~

This is a fragment assuming `factory`. Interceptors wrap HTTP execution and can observe call duration. Never log request bodies by default; `body` in an interceptor can be a `byte[]` of the entire payload, creating memory/privacy risks.

### 14.2. BufferingClientHttpRequestFactory

Spring provides a wrapper:

~~~java
ClientHttpRequestFactory buffering =
        new BufferingClientHttpRequestFactory(factory);
~~~

It retains request/response streams in memory so they can be read multiple times when needed. **However, buffering every payload** is dangerous for large uploads/downloads and PII. Enable it only for bounded workloads, or avoid it altogether via metadata-only tracing. Do not assume Buffering factory solves body streaming or backpressure.

### 14.3. Propagate Trace IDs Without Trusting Raw Headers

If reading correlation IDs from inbound requests, validate format/length and sanitize before forwarding. Never forward a user's Authorization token to an arbitrary URL or redirect target; use domain-scoped service-to-service credentials/scopes. With Micrometer/OpenTelemetry, leverage built-in integrations and propagation policies rather than copying headers indiscriminately.

## 15. Large Request Bodies, Streaming, and Memory Pressure

### 15.1. Synchronous Does Not Always Mean Buffered

Spring 6.1 changed request body buffering across several factories. A `RestClient` call can stream bytes to the transport, yet:
- `HttpMessageConverter` may construct a byte[]/String before sending.
- Interceptors may receive the entire serialized `byte[]`.
- Buffering factory may buffer request/response bodies.
- The underlying HTTP client backend has its own buffering/flow control.
- `body(InputStream)` is not automatically a standard streaming API across all Spring converters.

If you need to stream a very large file:
1. Pick a factory backend that genuinely supports streaming.
2. Use a compatible body writer/input stream/resource API.
3. Never log/buffer the entire body.
4. Cap request/response bytes, timeouts, and disk/memory quotas.
5. Close resources even on error/cancellation.
6. Test with real file sizes and slow-responding servers.

### 15.2. Synchronous Response Streams Occupy Threads

Reading a multi-GB download with `RestClient` can hold the caller thread for the entire read duration. Do not confuse “streaming network bytes” with “non-blocking API”; connection pooling and worker threads still require sizing. If the need is fan-out or thousands of concurrent downloads, consider reactive WebClient or async JDK HttpClient with an appropriate architecture.

## 16. Diagnostics: Identifying the Actual Transport and Errors

### 16.1. Do Not Infer from the Dependency Tree That the Right Factory Is Used

The classpath is a clue, not proof; a client bean may explicitly override the default. Always:
- Inspect the `requestFactory` bean configuration of each RestClient.
- Log the factory class type **without secrets** at startup in debug environments.
- With Apache, monitor pool stats (leased, available, pending).
- With JDK, use application-level metrics/tracing and JDK HTTP client logs when needed (avoid logging bodies).
- Test real redirects/timeouts/proxies and TLS rather than only pinging HTTP 200.

### 16.2. Spring Exception Mapping

Exception layers include:
- `RestClientException`: Spring HTTP client abstraction.
- `RestClientResponseException`: carries HTTP error response/status/body.
- `ResourceAccessException`: typically I/O/transport errors.
- `HttpClientErrorException`, `HttpServerErrorException`: 4xx/5xx errors from `retrieve()`.
- Underlying `IOException`/`SocketTimeoutException`/TLS exceptions may sit in the cause chain.

Do not rely on exact exception messages across JDK versions. Error handling must classify **retryable vs non-retryable** based on HTTP method, status, idempotency, and network cause.

### 16.3. Timeouts and Retries Often Interact Badly

A retry policy with max 3 attempts, 2 s timeout per attempt, plus 1 s backoff can exceed a 3 s HTTP request SLA. You need:
- Overall deadlines and per-attempt limits.
- Retries only for transient failures and safe/idempotent HTTP methods.
- Exponential backoff + jitter; honor `Retry-After` when present.
- Circuit breakers, bulkheads, rate limiters.
- Budgets for caller threads and downstream request quotas.
- Correlation IDs/idempotency keys for POST commands.

A client timeout does not prove downstream failed to process the request before the connection broke. For side-effecting POSTs, retries require an idempotency contract or status reconciliation.

### 16.4. Watch 401/403 Statuses When Using Simple Factory

If switching from JDK/Apache to Simple factory produces unusual exceptions on `HttpURLConnection` error statuses, check the Spring reference notes on Simple implementation behavior. Never “fix” it by disabling HTTP error checks or returning a default 200; choose a suitable factory and add regression tests for error statuses.

## 17. Common Mistakes and Fixes

| Mistake / Misconception | Why It Is Wrong | Fix |
| --- | --- | --- |
| “RestClient always uses HttpURLConnection” | Backend is chosen by classpath/builder | Attach explicit `requestFactory` |
| “Reactor Netty factory makes RestClient non-blocking” | RestClient is a synchronous API | Use `WebClient` when reactive is needed |
| Copying Spring 6.2 Apache `setReadTimeout` to 6.1 | API does not exist yet | Apache 5 `RequestConfig.responseTimeout` |
| Using Apache HttpClient 4 with Spring 6 factory | Spring 6 requires 5.1+ | `httpclient5` and matching imports |
| Setting only connect timeout | Does not bound infinite read/pool waits | Layer timeouts by phase |
| Setting timeout 0 on all clients | May mean infinite | Set explicit budgets/deadlines |
| Creating HttpClient per HTTP request | Loses connection reuse, wastes resources | Reuse singleton beans |
| Max pool 500 for a downstream capped at 10 | Amplifies partner overload | Align quotas, admission control, pool sizing |
| Treating client 404 as socket failure | Status is an HTTP response, not a network error | Map 4xx/5xx separately |
| Catching RuntimeException and returning empty Order | Hides auth/timeout/5xx/bugs | Typed status/error policies |
| Enabling follow redirects for all URLs | SSRF/credential leak risk | Trusted destination checks |
| Disabling SSL hostname verification | MITM risk | Proper trust chain, mTLS/certs |
| Using user-supplied URLs directly | SSRF | Fixed base URL, allowlist + egress controls |
| Interceptor logging raw Authorization/bodies | Leaks secrets | Redaction/metadata-only tracing |
| Buffering all responses | Heap pressure | Cap payloads, avoid wrapper |
| Forgetting to close Apache manager/client | Socket/resource leaks | Bean lifecycle/close ownership |
| Multiple owners closing one factory bean | Double shutdown of shared resources | Clear single owner |
| Using RestClient on WebFlux Netty loop | Blocking calls stall event loop | WebClient or bounded worker |
| Only testing HTTP 200 on localhost | Misses real TLS/proxy/timeouts | Integration/load tests per contract |
| Using Boot 4 properties on Boot 3.3 | Version mismatch | Match API/docs to platform |
| Parsing error message strings to detect timeouts | Unstable messages | Inspect exception types/root causes |
| Auto-retrying POST after socket reset | Can duplicate side effects | Idempotency/reconciliation |

### Ordered Debugging

1. Confirm Java, Spring Boot, Spring Framework versions, and BOM.
2. Inspect the exact factory bean and underlying HTTP library dependency.
3. Verify RestClient/RestTemplate actually uses that factory without being overridden by another builder.
4. Check host/port, trusted URLs, DNS resolution, and proxy routes.
5. Verify connect, pool acquire, TLS, and response timeouts separately.
6. Test 2xx, 4xx, 5xx, and malformed JSON.
7. Under concurrency, measure threads, active/pending/idle connections, and queues.
8. Verify interceptors do not buffer/log credentials.
9. Verify response/stream/client lifecycles and resource cleanup.
10. Test staging rollouts with egress/TLS/proxy and fault injection.

## 18. Pre-Production Checklist

- [ ] Choose a factory based on workload/features/security, not merely defaults.
- [ ] Java/Spring/HTTP client dependency versions are compatible.
- [ ] Apache HttpClient is 5.x for Spring 6.x.
- [ ] Check Spring 6.1 vs 6.2 API differences, especially Apache setReadTimeout.
- [ ] RestClient/RestTemplate beans reuse factories and connection resources.
- [ ] Factory lifecycle/CloseableHttpClient ownership is clear.
- [ ] Connect, pool acquire, TLS, response/read, and overall deadlines are budgeted.
- [ ] No unintended 0/infinite timeouts.
- [ ] Pool limits align with downstream concurrency/rate limits.
- [ ] TLS trust/hostname verification is not disabled.
- [ ] Proxy/mTLS/redirect policies have been reviewed.
- [ ] User-supplied URLs are never called without SSRF defenses.
- [ ] Credentials are destination-scoped and never forwarded arbitrarily.
- [ ] Header/body logging is redacted, avoiding buffering large streams.
- [ ] Typed error handling for 401/403/404/429/5xx/transport failures.
- [ ] POST retries have idempotency or reconciliation.
- [ ] HTTP response resources are closed properly when using low-level APIs.
- [ ] Synchronous RestClient is never called on a reactive event loop.
- [ ] Real HTTP JUnit integration tests on random port.
- [ ] TLS/proxy/timeouts/redirects/pooling tested on matching infrastructure.
- [ ] Measure p95/p99, pool pending/acquire, exceptions, and outbound retries.
- [ ] Maintain transport config & dependency security patch policies.

### Self-Check Questions

**1.** Which layer does `ClientHttpRequestFactory` belong to?

**Answer:** Spring's abstraction for creating executable client HTTP requests, sitting beneath `RestClient`/`RestTemplate` and message conversion, and above the transport backend.

**2.** When migrating from RestTemplate to RestClient, must you change the HTTP library?

**Answer:** No. You can keep the same ClientHttpRequestFactory to separate API migration risk from transport migration risk.

**3.** Why is the JDK factory suitable for simple Java 17 services?

**Answer:** `java.net.http.HttpClient` is built in, supports connection reuse and SSL/proxy/redirect configuration, and avoids an Apache dependency when specialized pool tuning is unnecessary.

**4.** When is Apache HttpClient 5 advantageous?

**Answer:** When max total/per-route pooling, lease timeouts, proxy/TLS controls, and deep connection management are needed under high outbound load.

**5.** Does Spring 6.1 `HttpComponentsClientHttpRequestFactory` have `setReadTimeout`?

**Answer:** No. Configure `RequestConfig.setResponseTimeout` on the underlying Apache HttpClient 5; `setReadTimeout` on HttpComponents factory belongs to newer versions.

**6.** How does ConnectionRequestTimeout differ from ConnectTimeout?

**Answer:** ConnectionRequestTimeout bounds how long to wait to borrow a connection from the Apache pool; ConnectTimeout bounds establishing the TCP connection per client configuration.

**7.** Why is RestClient with ReactorNettyClientRequestFactory still blocking?

**Answer:** RestClient has a synchronous caller contract; the backend may use internal event loops, yet the caller still waits for the result.

**8.** When `RestClient.retrieve()` receives HTTP 404, does it necessarily return a null DTO?

**Answer:** No. By default 4xx/5xx raise an HTTP status exception; handle it via explicit mapping, status handlers, or `exchange`.

**9.** Should BufferingClientHttpRequestFactory be used on every outbound request?

**Answer:** No. It can buffer the entire payload in memory, risking OOM and exposing sensitive data if logged.

**10.** Why are redirects and user-supplied URLs dangerous in a server-side HTTP client?

**Answer:** They can lead to SSRF against internal/cloud metadata endpoints and leak credentials to external origins; fixed/allowlisted destinations, egress controls, and redirect policies are required.

## 19. Official Documentation

- [Spring Framework 6.1 — ClientHttpRequestFactory Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/http/client/ClientHttpRequestFactory.html): `createRequest(URI,HttpMethod)` interface and implementations.
- [Spring Framework 6.1 — JdkClientHttpRequestFactory](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/http/client/JdkClientHttpRequestFactory.html): constructors, `setReadTimeout`.
- [Spring Framework 6.1 — SimpleClientHttpRequestFactory](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/http/client/SimpleClientHttpRequestFactory.html): HttpURLConnection, connect/read timeouts, and buffering deprecation.
- [Spring Framework 6.1 — HttpComponentsClientHttpRequestFactory](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/http/client/HttpComponentsClientHttpRequestFactory.html): Apache HttpClient 5, connect/lease timeouts, and pooling.
- [Spring Framework 6.1 — JettyClientHttpRequestFactory](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/http/client/JettyClientHttpRequestFactory.html): Jetty HttpClient adapter.
- [Spring Framework 6.1 — ReactorNettyClientRequestFactory](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/http/client/ReactorNettyClientRequestFactory.html): Reactor Netty adapter for sync clients.
- [Spring Framework 6.1 — RestClient.Builder](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/client/RestClient.Builder.html): `requestFactory` and builder configuration.
- [Spring Framework 6.1 — REST Clients Reference](https://docs.spring.io/spring-framework/reference/6.1/integration/rest-clients.html): RestClient, RestTemplate, request factories, and selection.
- [Spring Boot 3.3 — Calling REST Services](https://docs.spring.io/spring-boot/3.3/reference/io/rest-client.html): RestClient.Builder, RestTemplateBuilder, and auto-configuration.
- [Apache HttpClient 5 — Classic Client](https://hc.apache.org/httpcomponents-client-5.4.x/current/httpclient5/apidocs/): connection manager, RequestConfig, response timeout.
- [JDK 17 — java.net.http.HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): HTTP/1.1/2, SSL, redirects, proxies, connection handling.
- [Spring Framework — HTTP Client Test Utilities](https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-client.html): MockRestServiceServer for mocking behavior; real-server integration tests complement transport coverage.
- [OWASP — SSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html): allowlists, DNS, redirects, and network restrictions.

**Takeaway:** `RestClient`/`RestTemplate` are synchronous APIs; `ClientHttpRequestFactory` chooses the HTTP backend. JDK HttpClient is a solid starting point on Java 17 when needs are simple; Apache HttpClient 5 fits when deep pool/timeout/proxy/TLS tuning is required. Never let the transport change silently via the classpath, never confuse sync with non-blocking, and always configure deadlines, lifecycle, credentials, SSRF policies, logging, and integration tests before deployment.
