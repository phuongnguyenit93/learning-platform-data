# Timeouts, Connection Pools, TLS, and Resource Lifecycle of Synchronous HTTP Clients

## 1. Practical Problem and Objectives

In a Spring MVC application, batch job, or Java service, when calling a REST API via `RestClient` or `RestTemplate`, the caller typically **waits synchronously** until an HTTP response or error arrives. If the upstream is slow, this wait can hold a Java worker thread, occupy a connection in the outbound pool, build a pending queue, and trigger cascading timeouts. Even an API with simple business logic can exhaust worker threads, file descriptors, or sockets if limits are left unconfigured.

Four concerns must be addressed together:

1. **Timeouts:** how long does it take to acquire a connection from the pool, DNS/TCP connect, TLS handshake, send the request, and wait for the response? What time bound protects the overall HTTP call?
2. **Connection pool:** under what policy are connections created, leased, returned, reused, checked for staleness, and closed? How are total and per-route limits divided?
3. **TLS:** which certificates does the client trust, how is hostname verification performed, and when are truststores, keystores, and mTLS used? What should you do when `SSLHandshakeException` occurs?
4. **Resource lifecycle:** are RestClient/factory/pool created once or per request, who owns closing them, and when are idle connections and response streams cleaned up?

**Scope:** Java 17, Spring Framework 6.1/6.2, Spring Boot 3.3.x, Spring `RestClient` and `RestTemplate`, JDK `java.net.http.HttpClient`, Apache HttpClient 5.x. This is a **synchronous HTTP clients** lesson, not reactive WebClient. The complete example uses Spring Boot **3.3.13** / Java **17** and Apache HttpClient 5, with a mock HTTP upstream running on localhost without calling external Internet services.

### After Completing This Lesson You Should Be Able to Answer

- How does connect timeout differ from response timeout and connection lease wait?
- Why does a 700 ms response timeout **not** guarantee the entire call finishes before 700 ms?
- When a pool caps max 5 connections to an upstream, where does the sixth request go?
- Why does keep-alive reduce TCP/TLS handshakes, yet idle connections can also go stale?
- Does RestClient automatically guarantee the same pool/timeouts across all environments?
- How do Spring 6.1 and Spring 6.2 differ on the HttpComponents request factory?
- How should PKIX/hostname mismatches be resolved **without disabling TLS verification**?
- When a POST times out, can a retry create a duplicate record?
- Why does Java 17 JDK HttpClient lack a public `close()` like Java 21?
- How do you write JUnit tests verifying HTTP statuses vs transport timeouts and closing pools with proper lifecycle?

## 2. What Phases Does a Synchronous HTTP Call Have?

```text
Inbound MVC request / background job
                 |
                 v
       RestClient.get(...).retrieve().body(...)
                 |
          Caller thread waits
                 |
       ClientHttpRequestFactory
                 |
                 +--- [A] Pool lease / acquire connection
                 |         May have to wait if pool is full
                 |
                 +--- [B] DNS resolution (if not cached)
                 |
                 +--- [C] TCP connect (if not reused)
                 |
                 +--- [D] TLS handshake + certificate/hostname check
                 |         HTTPS only, typically skipped on reuse
                 |
                 +--- [E] Send HTTP headers/body
                 |
                 +--- [F] Wait for status/headers/body
                 |
                 +--- [G] Decode JSON, handle HTTP error status
                 |
                 +--- [H] Consume/close response, release pool resource
                 |
                 v
        Return DTO/ResponseEntity or exception
```

A request can skip [B]–[D] when a live connection is reused. With HTTP/2, multiple logical streams can share a single connection when client/transport and server support it; do not assume HTTP/2 across all synchronous HTTP clients.

**A connection is not a worker thread.** The Apache connection pool manages outbound sockets; the Tomcat worker pool manages inbound request execution. If 100 Tomcat workers all try to call one upstream whose Apache per-route limit is only 10, most of them may sit waiting to acquire. Increasing Tomcat maxThreads does not fix outbound pool saturation.

## 3. Classifying Timeouts: Right Layer, Right Meaning

| Name | Phase | Meaning |
| --- | --- | --- |
| Pool acquire / connection-request timeout | [A] | Max time waiting for a connection from the pool |
| DNS lookup timeout | [B] | Depends on resolver/OS/JVM/client; not always an independent setting |
| TCP connect timeout | [C] | Bounds establishing a new connection to host:port |
| TLS handshake timeout | [D] | Bounds TLS/ALPN session and certificate exchange; may be configured separately |
| Write/socket timeout | [E] | Waiting to write bytes; semantics vary by engine |
| Response timeout | [F] | Waiting for response per HTTP client, not automatically the entire call |
| Socket read inactivity timeout | [F] | Waiting for next data; a stream may span multiple intervals |
| Whole-call deadline | [A]–[H] | Overall business time budget; typically needs a dedicated policy |
| Idle timeout / connection TTL | After call | When the pool closes unused or expired sockets |
| Gateway/proxy timeout | Outside JVM | May return 502/504 even if client/remote has different policies |

### 3.1. Connect Timeout Bounds Only One Phase

Suppose TCP connects in 5 ms, and the server holds the request for 15 seconds before returning the body. If the client only sets a 1-second connect timeout, the caller can still wait a long time because the connect step already succeeded. You need timeouts for response/read and an **overall deadline** when business SLAs exist.

### 3.2. Lease Timeout Differs from Connect Timeout

If an Apache pool caps max 5 connections and 5 calls are busy, the sixth call can wait **in the pool before opening any new TCP socket**. If lease timeout is 200 ms and no connection returns in time, the call can fail without the upstream ever seeing the sixth request. Increasing TCP connect timeout will not help.

### 3.3. TLS Handshake Is Not Simply Part of Connect Timeout

In Spring Framework 6.1, `HttpComponentsClientHttpRequestFactory#setConnectTimeout` configures Apache RequestConfig's connection timeout, but the Javadoc warns it **does not cover SSL handshakes or HTTP CONNECT**; low-level socket/TLS config may be required. With JDK HttpClient, TLS/request timing follows different APIs and implementation semantics. Never say “connectTimeout always covers TLS” without verifying the engine/version.

### 3.4. Response Timeout Is Not a Total Wall-Clock Cap

A server may send headers and then stream the body in chunks, each arriving before the inactivity timeout while total download takes minutes. Response/socket timeouts have engine-specific semantics. If the business requires a 2-second SLA, enforce an end-to-end deadline and align timeout/cancellation/retry policies; `setResponseTimeout(2s)` alone does not guarantee all bytes are read within 2 seconds.

### 3.5. Timeouts May Not Stop Remote Side Effects

A client sends a POST creating an order. The server persists it to the database, but the response is lost in transit and the client hits a read timeout. The client **cannot infer the operation rolled back**. Uncontrolled POST retries create duplicate orders. You need idempotency keys, unique constraints, bounded retries, and clear business rules.

### 3.6. Latency Budget Calculation Example

An inbound API has a 1,000 ms SLA; one illustrative allocation:

| Step | Example Budget |
| --- | ---: |
| Authentication/validation | 100 ms |
| Lease outbound connection | 100 ms |
| TCP/TLS if new connection needed | 200 ms |
| Wait upstream response | 450 ms |
| Encode/send inbound response, contingency | 150 ms |

This is not a benchmark: stages may overlap or spike abnormally; numbers must come from metrics. If downstream timeouts exceed the inbound SLA, requests will likely receive 504 from a gateway before the caller even sees the error.

## 4. RestClient, RestTemplate, and the Factory Actually Doing I/O

### 4.1. RestClient (Spring Framework 6.1+)

`RestClient` is a **synchronous** fluent API:

```java
RestClient client = RestClient.builder()
    .baseUrl("https://api.example.test")
    .build();

Product product = client.get()
    .uri("/products/{id}", 42L)
    .retrieve()
    .body(Product.class);
```

This is an illustrative snippet requiring a `Product` DTO and a real server. When `retrieve()` gets 4xx/5xx, Spring throws the corresponding `RestClientResponseException` subtype by default. On I/O failures, `ResourceAccessException` is typically raised with various root causes. On 204 No Content or an empty body, `body(Product.class)` can return null; avoid unboxing/deserializing as if an object always exists.

### 4.2. RestTemplate Is Also Synchronous

`RestTemplate` remains supported by Spring, though RestClient is nicer with its fluent style. Both use `ClientHttpRequestFactory` to perform I/O:

```java
RestTemplate template = new RestTemplate(requestFactory);
Product product = template.getForObject(
    "https://api.example.test/products/42", Product.class);
```

This is a snippet requiring `requestFactory` and `Product` to be configured. Migrating RestTemplate to RestClient **does not automatically** configure timeouts/pooling if the underlying request factory remains unmanaged.

### 4.3. Transport Factories

| Spring Factory | HTTP Engine | Meaning |
| --- | --- | --- |
| `JdkClientHttpRequestFactory` | Java `java.net.http.HttpClient` | Has connect/read timeout APIs, JDK-managed connections |
| `HttpComponentsClientHttpRequestFactory` | Apache HttpClient 5 | Explicit pool metrics/limits and lifecycle |
| `SimpleClientHttpRequestFactory` | Java `HttpURLConnection` | Simple, lacks explicit pool APIs like Apache |
| `JettyClientHttpRequestFactory` | Jetty HTTP client | Dedicated tuning |
| `ReactorNettyClientRequestFactory` | Reactor Netty | A request factory usable beneath the synchronous RestClient facade |

If no factory is set, selection depends on Spring Framework version, HTTP libraries on the classpath, and Spring Boot auto-configuration. **Do not** assume all environments share the same pool/timeout defaults. For production, configure an explicit request factory for easier review and testing.

### 4.4. Boot-Managed RestClient.Builder

Spring Boot creates a `RestClient.Builder` already configured with message converters, customizers, and observation hooks for the application environment. Inject the builder and build a consistent RestClient bean/service-scoped client with a fixed base URL and factory rather than calling `RestClient.create()` per request.

```java
@Service
class ExternalGateway {
    private final RestClient client;

    ExternalGateway(RestClient.Builder builder) {
        client = builder.baseUrl("https://api.example.test")
            .build();
    }
}
```

The builder is mutable; when sharing to build multiple target clients, use `clone()` or separate builder injections. Never mutate a builder concurrently during request processing.

## 5. JDK HttpClient on Java 17

Java 17 provides `java.net.http.HttpClient`. It supports internal pooling/reuse, redirects, SSLContext, and HTTP/2 negotiation per server. However, JDK 17 **lacks** standard public APIs equivalent to Apache's `setMaxConnPerRoute`/`getTotalStats` for fine-grained pool limits and inspection.

### 5.1. Integrating RestClient with the JDK Request Factory

```java
HttpClient jdk = HttpClient.newBuilder()
    .connectTimeout(Duration.ofSeconds(2))
    .followRedirects(HttpClient.Redirect.NEVER)
    .build();

JdkClientHttpRequestFactory factory =
    new JdkClientHttpRequestFactory(jdk);
factory.setReadTimeout(Duration.ofSeconds(3));

RestClient client = RestClient.builder()
    .requestFactory(factory)
    .baseUrl("https://api.example.test")
    .build();
```

This is a Java 17/Spring 6.1+ snippet requiring `java.net.http.HttpClient`, `Duration`, and Spring imports. The JDK request factory's read timeout maps to `HttpRequest.Builder.timeout` per Spring Javadoc. It is not identical to Apache's socket read timeout in every case.

### 5.2. Direct Java HttpClient

```java
HttpRequest request = HttpRequest.newBuilder()
    .uri(URI.create("https://api.example.test/data"))
    .timeout(Duration.ofSeconds(3))
    .GET()
    .build();

HttpResponse<String> response =
    jdk.send(request, HttpResponse.BodyHandlers.ofString());
```

`send` blocks the calling thread, while `sendAsync` returns a CompletableFuture with a different lifecycle. If using `BodyHandlers.ofInputStream()` or `ofLines()`, consume/close the stream properly; abandoning it early can prevent connection reuse and leak resources.

### 5.3. JDK 17 Lifecycle Differs from JDK 21

In **Java 17**, `java.net.http.HttpClient` does not yet have public `close()`/`shutdown()` methods and does not implement AutoCloseable as in **Java 21**. Do not write Java 17 code like `try (HttpClient c = ...)` or `c.close()`. Reuse one application instance rather than creating clients arbitrarily; if explicit pool lifecycle and metrics are required on Java 17, Apache HttpClient 5 is usually more convenient.

## 6. Apache HttpClient 5: Explicit Pool, Timeouts, and Lifecycle

Apache 5 classic synchronous client is commonly used beneath `HttpComponentsClientHttpRequestFactory`. Essential settings:

| API/Config | Purpose |
| --- | --- |
| `PoolingHttpClientConnectionManagerBuilder.setMaxConnTotal(n)` | Maximum connections across the entire pool |
| `setMaxConnPerRoute(n)` | Maximum connections to a single route |
| `ConnectionConfig.setConnectTimeout(...)` | TCP connect timeout |
| `ConnectionConfig.setSocketTimeout(...)` | Socket I/O timeout |
| `ConnectionConfig.setTimeToLive(...)` | Maximum connection lifetime |
| `ConnectionConfig.setValidateAfterInactivity(...)` | Check pooled connection for staleness after idle period |
| `RequestConfig.setConnectionRequestTimeout(...)` | Wait to acquire connection from manager |
| `RequestConfig.setResponseTimeout(...)` | Wait for response per Apache semantics |
| `HttpClientBuilder.evictIdleConnections(...)` | Evict idle connections |
| `evictExpiredConnections()` | Evict expired connections |
| `HttpClientBuilder.disableAutomaticRetries()` | Disable Apache-level retries to manage policy explicitly |

### 6.1. Note on Spring 6.1 vs 6.2

Spring **6.1** `HttpComponentsClientHttpRequestFactory` provides `setConnectTimeout(Duration)` and `setConnectionRequestTimeout(Duration)` but **does not yet have `setReadTimeout(Duration)`**. Spring **6.2** added the readTimeout setter to the Apache factory. Thus on Spring Boot 3.3.x (Spring Framework 6.1.x), configuring response timeout via Apache 5's `RequestConfig.setResponseTimeout(...)` is the right approach. Meanwhile, `JdkClientHttpRequestFactory.setReadTimeout(Duration)` has existed since Spring 6.1.

Copying a Spring 6.2 blog post into Boot 3.3 and calling `factory.setReadTimeout(Duration...)` on the Apache factory will fail to compile. Differentiate by **actual class and Spring version**, not just similar method names.

### 6.2. Pool Total and Per-Route

If total=20 and per-route=5, one upstream can have at most 5 established/leased connections per route; subsequent HTTP requests queue to lease until timeout or a connection is returned. A “route” corresponds to scheme/host/port/proxy path, not URL paths like `/orders` vs `/customers`. Hence multiple API endpoints on the same host compete for the same per-route limit.

### 6.3. Pool Size Is Not Caller Concurrency

Tomcat may have 200 workers while the Apache outbound pool has 10. All 190 remaining workers can block waiting for a lease. Raising total connections can overload the remote service. Coordinate caller thread pools, semaphores/bulkheads, rate limits, and backend capacity.

### 6.4. Reused vs Stale Connections

While keep-alive remains valid, a connection that finished request A can serve request B without a new TCP/TLS handshake. If a load balancer closes an idle socket without the client knowing, reuse can fail. `validateAfterInactivity`, idle eviction, TTL, and controlled retries reduce stale reuse, though no setting eliminates every network race.

### 6.5. Why Must Bodies Be Closed?

Once the HTTP response body is consumed or the response is closed properly, the engine can return or discard the connection in a clean state. Holding a raw InputStream without closing it can keep the connection leased in the pool until timeout/GC/transport abort. `RestClient.retrieve().body(Dto.class)` normally manages standard decode lifecycles; `exchange` callbacks/custom streams and low-level Apache responses must obey close/consume contracts.

## 7. TLS: Trust, Hostname, and mTLS

### 7.1. HTTPS Requires Peer Authentication, Not Just Encryption

When connecting to `https://orders.example.test`, the TLS client must verify:

1. Does the server's certificate chain lead to a trusted trust anchor?
2. Is the certificate valid (not expired) and compliant with key usage/algorithm policies?
3. Does the SAN match the hostname in the URL **orders.example.test**?
4. Are TLS protocol/cipher/ALPN compatible?
5. If the server requires a client certificate (mTLS), does the client have a valid key/cert?

If a server sends a valid CA-signed certificate whose SAN only lists `payments.example.test`, the client must reject it for `orders.example.test`. **Trust chain and hostname verification complement each other**, neither replaces the other.

### 7.2. Truststore vs Keystore

| Artifact | Contents | When Used |
| --- | --- | --- |
| Truststore | CA certificates/trust anchors | Client verifies server |
| Client keystore | Private key + client certificate chain | Server requires mTLS |
| SSLContext | Key/trust managers + TLS settings | Client TLS configuration |
| Hostname verification | Compares URL host and certificate SAN | Prevents MITM spoofing |
| System trust | JDK root CA bundle/policy | Standard HTTPS |

Never accept an untrusted client-supplied `X-Client-Cert` header as proof of mTLS. If behind a gateway, trust boundaries and certificate forwarding must be tightly designed.

### 7.3. Custom Truststore in Java

Illustrative Java 17 example (not a standalone file):

```java
KeyStore trust = KeyStore.getInstance("PKCS12");
try (InputStream in = Files.newInputStream(
        Path.of("/secure/api-truststore.p12"))) {
    trust.load(in, password);
}

TrustManagerFactory tmf =
    TrustManagerFactory.getInstance(
        TrustManagerFactory.getDefaultAlgorithm());
tmf.init(trust);

SSLContext tls = SSLContext.getInstance("TLS");
tls.init(null, tmf.getTrustManagers(),
    new SecureRandom());

HttpClient httpsClient = HttpClient.newBuilder()
    .sslContext(tls)
    .connectTimeout(Duration.ofSeconds(2))
    .build();
```

Requires `KeyStore`, `InputStream`, `Files/Path`, `TrustManagerFactory`, `SSLContext`, `SecureRandom`, `HttpClient`, and `Duration` imports. `password` is a `char[]` loaded from secrets, never hardcoded. A custom truststore **replaces** system default roots; if both public and private CAs must be trusted, build an explicit composite trust policy. Never combine trust managers in a way that accepts all certificates.

### 7.4. mTLS Adds a Client Private Key

After loading the client keystore, initialize `KeyManagerFactory` and:

```java
SSLContext tls = SSLContext.getInstance("TLS");
tls.init(keyManagerFactory.getKeyManagers(),
    trustManagerFactory.getTrustManagers(),
    new SecureRandom());
```

This snippet is illustrative only; both stores must be loaded. mTLS authenticates the client certificate, while user/resource authorization remains separate. Plan certificate/key rotation and grace periods.

### 7.5. Never Fix SSL Errors with Trust-All

**Never use**:

- an empty `TrustManager.checkServerTrusted` method;
- `NoopHostnameVerifier.INSTANCE`;
- properties disabling hostname verification;
- trusting arbitrary untrusted self-signed certificates;
- plaintext HTTP to dodge certificate errors on credential-bearing traffic.

When encountering `PKIX path building failed` or `SSLHandshakeException`, investigate CA/intermediate chains, SANs, expiry, clock skew, protocols/ciphers, proxy TLS interception, and mTLS requirements. If the upstream uses a private CA, configure a valid truststore; **never bypass certificate validation**.

### 7.6. JVM Truststore System Properties and Apache Client

Some engines honor JSSE system trust properties when configured with `useSystemProperties()`. Never assume **every** Apache custom SSLContext automatically picks up `-Djavax.net.ssl.trustStore=...`. For multi-client/multi-tenant setups, configure per-client truststores rather than mutating global JVM trust state unintentionally.

### 7.7. TLS Handshakes and Pool Reuse

When a connection is reused, no new TLS handshake is needed per request. When idle eviction/TTL/remote close occurs, a new connection requires a handshake; p99 can differ significantly between cold starts and warm pools. HTTP/2 multiplexing, TLS session resumption, OCSP, and ALPN also affect connection cost. Benchmarks must cover both cases.

## 8. Timeouts + Retries + Error Taxonomy

### 8.1. Error Classification

| Case | Typical Symptom | Response |
| --- | --- | --- |
| 404 | `HttpClientErrorException.NotFound` with `retrieve()` | Business not-found (if contract says so) |
| 429 | TooManyRequests | Rate limit/Retry-After/backoff |
| 503 | ServiceUnavailable | Service outage, circuit breaker |
| TCP connect refused | `ResourceAccessException` wrapping ConnectException | Host/port/listener/network |
| Connect timeout | ResourceAccessException/root timeout | Network path/DNS/firewall |
| Pool lease timeout | Apache request connection manager timeout | Check pool stats, active/pending |
| Response/socket timeout | I/O exception | Upstream latency, response policy |
| Bad certificate | `SSLHandshakeException`/PKIX | Chain, truststore, hostname |
| JSON decode error | Message conversion exception | DTO/schema/media type |
| 204 response | Body may be null | No-content API contract |
| Cross-host redirect | 3xx/redirect policy | Prevent SSRF/credential leak |

Specific exceptions vary by Spring/Apache/JDK version; log root causes safely and separate HTTP statuses (actually returned by remote) from I/O failures (potentially no HTTP response at all).

### 8.2. Retries Are Not a Simple On/Off Switch

- HTTP 400/401/403: typically do not retry.
- 404: retry only when eventual consistency is explicitly agreed.
- 429: slow down, honor `Retry-After` if present.
- 500/502/503/504: bounded retries allowed if idempotent and within deadline.
- TCP reset/timeout: unknown whether remote operation finished.
- POST create: use idempotency keys and server-side deduplication whenever retries are possible.

Also check Apache auto-retries, Spring Retry, gateway retries, and orchestration retries to avoid retry multiplication. In the lab, Apache automatic retries are disabled to keep tests predictable.

### 8.3. Circuit Breakers Differ from Timeouts

Timeouts cap how long one call waits; circuit breakers temporarily shed calls to a failing upstream; bulkheads bound concurrency; rate limiters pace throughput; retries can amplify traffic. They complement rather than replace one another. If a circuit breaker trips on 503 metrics, do not treat every exception (such as 404) as an unhealthy backend.

## 9. Resource Lifecycle: Who Closes the Client and When?

### 9.1. Never Instantiate a New HTTP Client Per Request

Anti-pattern:

```java
@GetMapping("/proxy")
Product wrong() {
    RestClient client = RestClient.builder()
        .baseUrl("https://api.example.test")
        .build();
    return client.get()
        .uri("/product").retrieve().body(Product.class);
}
```

Illustrative only, not standalone; continually creating clients/factories spawns transports/pools with no closing owner, forfeits reuse, and increases socket churn. Better: inject a singleton `RestClient` per upstream backed by a managed shared factory/pool.

### 9.2. Clear Ownership

With Apache:

```text
Spring ApplicationContext
  └── HttpComponentsClientHttpRequestFactory bean
        └── owns CloseableHttpClient
              └── owns PoolingHttpClientConnectionManager
                    └── socket connections + optional evictor thread

ApplicationContext shutdown
  └── factory.destroy()
        └── closes Apache client / manager / workers
```

Avoid declaring `CloseableHttpClient` both as a bean with a destroy callback and having the factory close it again without clear ownership. In the runnable example, **the factory is the sole owner**, constructing the Apache client inside its method and declaring `@Bean(destroyMethod="destroy")`.

### 9.3. Response Streaming and Raw Entities

If using a low-level Apache response:

```java
try (CloseableHttpResponse response =
        apache.execute(new HttpGet(url))) {
    // Read entity/body within scope.
}
```

This is a snippet needing imports and an initialized `apache` client. Never pass a raw InputStream out of `try` to read later, and never leave a response body unconsumed; if a response cannot be reused, the engine must be allowed to abort the connection rather than keeping it leased forever.

### 9.4. Graceful Shutdown and Active Calls

`server.shutdown=graceful` configures the **inbound** web server; it does not automatically drain outbound pools. Spring lifecycle must stop accepting new work, allow active calls a reasonable deadline, and then close pools. Pay attention to what happens if HTTP clients have in-flight requests when beans are destroyed; test shutdown/cancellation in integration tests.

### 9.5. Pool Eviction and Metrics

Idle eviction/TTL reduces stale sockets and idle resource consumption, though overly aggressive idle policies increase CPU/TLS handshakes. Monitor `leased`/`available`/`pending`/`max`, lease wait times, active caller threads, and upstream p95/p99. A pooled connection remaining leased could be a legitimate long call, not necessarily a leak.

## 10. Runnable Demo: Spring Boot 3.3.13, Java 17, Apache 5

The demo has **two modes** in the same Spring Boot fat JAR:

- `--mock-upstream` mode: runs JDK `com.sun.net.httpserver.HttpServer` on `127.0.0.1:9090`; endpoints `/fast`, `/slow`, `/missing`, `/unavailable`, `/echo`. No TLS since it is a localhost lab.
- Default mode: Spring MVC web app on port 8080, creates **one** explicit Apache HTTP client pool, and Spring RestClient calls the mock server synchronously.
- JUnit: starts the mock server on an ephemeral port instead of 9090 so tests do not depend on a specific port being free.

### 10.1. Directory Tree

```text
http-client-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/example/
    │   │   ├── HttpClientDemoApplication.java
    │   │   ├── Message.java
    │   │   ├── ClientConfiguration.java
    │   │   ├── UpstreamGateway.java
    │   │   ├── GatewayController.java
    │   │   └── MockUpstreamServer.java
    │   └── resources/application.properties
    └── test/java/example/
        └── UpstreamGatewayTest.java
```

### 10.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>http-client-demo</artifactId>
  <version>1.0.0</version>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.13</version>
    <relativePath/>
  </parent>
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

Dependency versions are managed by Spring Boot; do not override with arbitrary HttpClient 5 alphas/releases to avoid mismatches.

### 10.3. Message.java

```java
package example;
public record Message(String value) {}
```

Record acts as the JSON DTO for mock responses.

### 10.4. ClientConfiguration.java — Pool & Timeouts

```java
package example;

import org.apache.hc.client5.http.config.ConnectionConfig;
import org.apache.hc.client5.http.config.RequestConfig;
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
public class ClientConfiguration {

    @Bean(destroyMethod = "destroy")
    public HttpComponentsClientHttpRequestFactory pooledRequestFactory() {
        ConnectionConfig connection = ConnectionConfig.custom()
            .setConnectTimeout(Timeout.ofSeconds(1))
            .setSocketTimeout(Timeout.ofSeconds(2))
            .setTimeToLive(TimeValue.ofMinutes(3))
            .setValidateAfterInactivity(TimeValue.ofSeconds(5))
            .build();

        PoolingHttpClientConnectionManager manager =
            PoolingHttpClientConnectionManagerBuilder.create()
                .setMaxConnTotal(20)
                .setMaxConnPerRoute(5)
                .setDefaultConnectionConfig(connection)
                .build();

        RequestConfig perRequest = RequestConfig.custom()
            .setConnectionRequestTimeout(
                Timeout.ofMilliseconds(300))
            .setResponseTimeout(Timeout.ofMilliseconds(700))
            .build();

        CloseableHttpClient apache = HttpClients.custom()
            .setConnectionManager(manager)
            .setDefaultRequestConfig(perRequest)
            .evictExpiredConnections()
            .evictIdleConnections(TimeValue.ofSeconds(30))
            .disableAutomaticRetries()
            .build();

        return new HttpComponentsClientHttpRequestFactory(apache);
    }

    @Bean
    public RestClient upstreamRestClient(
            RestClient.Builder builder,
            HttpComponentsClientHttpRequestFactory pooledRequestFactory,
            @Value("${demo.upstream-base-url}") String baseUrl) {
        return builder
            .requestFactory(pooledRequestFactory)
            .baseUrl(baseUrl)
            .build();
    }
}
```

Key points:

- `setMaxConnTotal(20)` and `setMaxConnPerRoute(5)` cap connections; these are **lab numbers**, not production defaults.
- `ConnectionConfig.setConnectTimeout` differs from `RequestConfig.setConnectionRequestTimeout`.
- `RequestConfig.setResponseTimeout` exists in Apache 5 and works with Spring Framework 6.1.
- `setSocketTimeout` applies low-level socket I/O; do not treat response timeout as a total deadline.
- `evictIdleConnections`/`evictExpiredConnections` require proper client lifecycle.
- The factory creates and **owns** `CloseableHttpClient`; `destroy()` closes the underlying client. Do not register a separate Apache client Spring Bean that gets closed twice.
- `disableAutomaticRetries()` enables a **single** clear retry policy in the app layer if needed later.
- Never copy 300/700ms thresholds to production without measuring traffic/demand and upstream p99.

### 10.5. UpstreamGateway.java

```java
package example;

import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class UpstreamGateway {
    private final RestClient client;

    public UpstreamGateway(RestClient upstreamRestClient) {
        this.client = upstreamRestClient;
    }

    public Message fast() {
        return client.get()
            .uri("/fast")
            .retrieve()
            .body(Message.class);
    }

    public Message slow(long ms) {
        return client.get()
            .uri(builder -> builder.path("/slow")
                .queryParam("ms", ms).build())
            .retrieve()
            .body(Message.class);
    }

    public Message echo(String requestId) {
        return client.get()
            .uri("/echo")
            .header("X-Request-Id", requestId)
            .retrieve()
            .body(Message.class);
    }

    public void missing() {
        client.get().uri("/missing")
            .retrieve().toBodilessEntity();
    }

    public void unavailable() {
        client.get().uri("/unavailable")
            .retrieve().toBodilessEntity();
    }
}
```

All methods above are **synchronous**. `retrieve().toBodilessEntity()` still checks HTTP statuses; 404/503 throw default exceptions. Never catch all errors into null because that conflates transport errors with empty business results.

### 10.6. GatewayController.java

```java
package example;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.client.HttpServerErrorException;
import org.springframework.web.client.ResourceAccessException;

@RestController
@RequestMapping("/demo")
public class GatewayController {
    private final UpstreamGateway gateway;

    public GatewayController(UpstreamGateway gateway) {
        this.gateway = gateway;
    }

    @GetMapping("/fast")
    public Message fast() {
        return gateway.fast();
    }

    @GetMapping("/slow")
    public Message slow(@RequestParam(defaultValue = "50") long ms) {
        if (ms < 0 || ms > 5000) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "ms out of range");
        }
        return gateway.slow(ms);
    }

    @GetMapping("/safe-status")
    public ResponseEntity<String> safeStatus() {
        try {
            gateway.unavailable();
            return ResponseEntity.ok("upstream-ok");
        } catch (HttpServerErrorException.ServiceUnavailable ex) {
            return ResponseEntity.status(HttpStatus.BAD_GATEWAY)
                .body("upstream-unavailable");
        } catch (ResourceAccessException ex) {
            return ResponseEntity.status(HttpStatus.GATEWAY_TIMEOUT)
                .body("upstream-IO-failed");
        }
    }
}
```

The demo's mapping of upstream 503 to inbound 502 is an API policy choice, not a rule that all 503s must become 502. Mapping ResourceAccessException to 504 is also a simplification; connection refused may be 502/503. In production, distinguish root causes and use a consistent error schema without exposing hostnames/secrets in exception details.

### 10.7. MockUpstreamServer.java

```java
package example;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

public final class MockUpstreamServer implements AutoCloseable {
    private final HttpServer server;
    private final ExecutorService executor;

    private MockUpstreamServer(
            HttpServer server, ExecutorService executor) {
        this.server = server;
        this.executor = executor;
    }

    public static MockUpstreamServer start(int port)
            throws IOException {
        HttpServer server = HttpServer.create(
            new InetSocketAddress("127.0.0.1", port), 0);
        ExecutorService workers = Executors.newCachedThreadPool();
        server.setExecutor(workers);

        server.createContext("/fast", exchange ->
            respond(exchange, 200, "{\"value\":\"fast\"}"));

        server.createContext("/slow", exchange -> {
            long ms = parseSleep(exchange.getRequestURI()
                .getRawQuery());
            try {
                Thread.sleep(ms);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                exchange.close();
                return;
            }
            respond(exchange, 200, "{\"value\":\"slow\"}");
        });

        server.createContext("/missing", exchange ->
            respond(exchange, 404, "{\"error\":\"missing\"}"));

        server.createContext("/unavailable", exchange ->
            respond(exchange, 503,
                "{\"error\":\"unavailable\"}"));

        server.createContext("/echo", exchange -> {
            String candidate = exchange.getRequestHeaders()
                .getFirst("X-Request-Id");
            String safe = candidate != null &&
                candidate.matches("[A-Za-z0-9._-]{1,64}")
                    ? candidate : "invalid";
            respond(exchange, 200,
                "{\"value\":\"" + safe + "\"}");
        });

        server.start();
        return new MockUpstreamServer(server, workers);
    }

    private static long parseSleep(String query) {
        if (query == null) return 0L;
        for (String part : query.split("&")) {
            if (part.startsWith("ms=")) {
                try {
                    long ms = Long.parseLong(part.substring(3));
                    return Math.max(0, Math.min(ms, 5000));
                } catch (NumberFormatException ignored) {
                    return 0L;
                }
            }
        }
        return 0L;
    }

    private static void respond(
            HttpExchange exchange, int status, String json)
            throws IOException {
        byte[] bytes = json.getBytes(StandardCharsets.UTF_8);
        try (exchange) {
            exchange.getResponseHeaders().add(
                "Content-Type", "application/json; charset=UTF-8");
            exchange.sendResponseHeaders(status, bytes.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(bytes);
            }
        }
    }

    public int port() {
        return server.getAddress().getPort();
    }

    @Override
    public void close() {
        server.stop(0);
        executor.shutdownNow();
    }

    public static void main(String[] args) throws Exception {
        try (MockUpstreamServer mock = start(9090)) {
            System.out.println(
                "Mock upstream: http://127.0.0.1:9090");
            new CountDownLatch(1).await();
        }
    }
}
```

The mock uses Java 17's `com.sun.net.httpserver.HttpServer` from JDK module `jdk.httpserver`. `Thread.sleep` in the mock intentionally creates a slow response and is **not** a good pattern for production apps. Using `start(0)` lets tests acquire an ephemeral port to avoid conflicts across CI workers.

### 10.8. HttpClientDemoApplication.java

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HttpClientDemoApplication {
    public static void main(String[] args) throws Exception {
        if (args.length > 0 &&
                "--mock-upstream".equals(args[0])) {
            MockUpstreamServer.main(new String[0]);
            return;
        }
        SpringApplication.run(HttpClientDemoApplication.class, args);
    }
}
```

Mock mode **does not start the Spring application**; it only serves the upstream API on 9090. Normal mode starts the MVC app on 8080. These are two independent processes, avoiding HTTP self-calls that obscure thread contention.

### 10.9. application.properties

```properties
server.port=8080
demo.upstream-base-url=http://127.0.0.1:9090
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
```

Production must replace loopback HTTP with an allowlisted HTTPS host, trust config, and credential policies. Never expose a proxy endpoint accepting arbitrary URLs from clients and letting RestClient reach internal metadata endpoints (SSRF).

### 10.10. Build and Run

With JDK 17+ and Maven, from the directory containing `pom.xml`:

```bash
mvn clean package

# Terminal 1 - mock server
java -jar target/http-client-demo-1.0.0.jar --mock-upstream

# Terminal 2 - Spring MVC web server
java -jar target/http-client-demo-1.0.0.jar
```

Then run:

```bash
curl -i http://localhost:8080/demo/fast
curl -i "http://localhost:8080/demo/slow?ms=50"
curl -i http://localhost:8080/demo/safe-status
curl -i "http://localhost:8080/demo/slow?ms=-1"
```

Expected:

| Request | HTTP Result |
| --- | --- |
| `/demo/fast` | 200, JSON `{"value":"fast"}` |
| `/demo/slow?ms=50` | 200, JSON `{"value":"slow"}` |
| `/demo/safe-status` | 502, text `upstream-unavailable` |
| `/demo/slow?ms=-1` | 400, invalid query error |
| `/demo/slow?ms=1800` | May throw ResourceAccessException due to response timeout; inbound default error handling per Boot |

Do not assert unconfigured raw stacktraces/error JSON. The timeouts above are lab values and running under heavy OS/CI load may alter actual timings.

## 11. JUnit 5 Tests: HTTP Statuses, Timeouts, and Client Reuse

File `src/test/java/example/UpstreamGatewayTest.java`:

```java
package example;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.client.HttpComponentsClientHttpRequestFactory;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.HttpServerErrorException;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;

import static org.junit.jupiter.api.Assertions.*;

class UpstreamGatewayTest {
    private MockUpstreamServer mock;
    private HttpComponentsClientHttpRequestFactory factory;
    private UpstreamGateway gateway;

    @BeforeEach
    void startMock() throws Exception {
        mock = MockUpstreamServer.start(0);
        factory = new ClientConfiguration().pooledRequestFactory();
        RestClient client = RestClient.builder()
            .baseUrl("http://127.0.0.1:" + mock.port())
            .requestFactory(factory)
            .build();
        gateway = new UpstreamGateway(client);
    }

    @AfterEach
    void closeAll() throws Exception {
        if (factory != null) factory.destroy();
        if (mock != null) mock.close();
    }

    @Test
    void fastJsonIsDecoded() {
        Message result = gateway.fast();
        assertNotNull(result);
        assertEquals("fast", result.value());
    }

    @Test
    void sameClientCanBeUsedRepeatedly() {
        for (int i = 0; i < 5; i++) {
            assertEquals("fast", gateway.fast().value());
        }
    }

    @Test
    void shortDelayStillSucceeds() {
        assertEquals("slow", gateway.slow(10).value());
    }

    @Test
    void slowResponseTriggersTransportTimeout() {
        assertThrows(ResourceAccessException.class,
            () -> gateway.slow(1800));
    }

    @Test
    void http404IsNotAnIoTimeout() {
        assertThrows(HttpClientErrorException.NotFound.class,
            gateway::missing);
    }

    @Test
    void http503IsAStatusError() {
        assertThrows(
            HttpServerErrorException.ServiceUnavailable.class,
            gateway::unavailable);
    }

    @Test
    void safeHeaderReachesUpstream() {
        assertEquals("req-001",
            gateway.echo("req-001").value());
    }

    @Test
    void mockRejectsUnexpectedHeaderValue() {
        assertEquals("invalid",
            gateway.echo("unsafe whitespace").value());
    }
}
```

**8 JUnit methods** verify JSON decoding, reusing the same client object, slow response timeout, 404/503 statuses, and header forwarding. Tests use an ephemeral port and need no Internet. They **do not prove** a physical TCP connection was reused on every call; they prove the client/factory object is reused and request processing works across multiple calls. To test actual socket reuse, inspect remote socket/session/connection stats.

### 11.1. Testing Pool Acquisition Requires a Different Test

With the demo's 20/5 pool, two HTTP calls will not saturate pool leases. A proper test requires pool max=1, holding a slow response leasing the socket, making a second call wait past the lease timeout, and asserting the pending/acquire error. Calling `gateway.slow(1800)` alone tests **response timeout**, not acquisition timeout.

### 11.2. TLS Is Not Yet Tested

The mock server runs on `http://127.0.0.1`, without HTTPS. Thus the 8 tests **do not** validate PKIX, hostname, mTLS, or ALPN. TLS requires an HTTPS test environment with a valid local CA/cert, matching SAN hostname, and managed client truststore/keystore; also write negative tests for expired/untrusted/wrong-host certs. Never declare “TLS PASS” just because HTTP tests passed.

### 11.3. Code Is Written, Not Claimed as Executed

The `mvn test` and `mvn clean package` commands here are for the learner. Report Maven tests as PASS only after observing actual Maven output. If timeout tests are flaky under heavy CI load, adjust mock timings in test setup/test-specific request policies instead of removing timeout validation.

## 12. Connection Pool Sizing and System Load

A commonly used quantitative relationship is Little's Law:

`in_flight ≈ requests_per_second × average_latency_seconds`

For example, an upstream receiving 100 calls/s averaging 0.2s has roughly **20 in-flight calls** in steady state. However, p99 spikes, retries, and bursts can push peak concurrency higher. Never pick 20 as a default maxConn if the backend only allows 8 concurrent requests; sizing must respect quotas.

### 12.1. Too Few Connections

Pending pool leases rise and caller threads wait even while the upstream is healthy. Inspect active/leased/pending metrics, backend response latency, and queues. Improve via traffic reduction, caching, concurrency limits, or increasing pool size **after** confirming downstream can handle it.

### 12.2. Too Many Connections

Instance count × maxConnPerRoute equals cluster-wide possible connections. For example, 20 JVMs × 100 per route = 2,000 potential sockets to the same host. Watch FD limits, SNAT ephemeral ports, TLS sessions, proxy/LB connection quotas, remote CPU, and rate limits.

### 12.3. Idle, TTL, and Stale

- **Idle:** duration a connection sits unused.
- **TTL:** maximum age of a connection.
- **Server keep-alive timeout:** server may close a pooled connection while idle.
- **Validate after inactivity:** reduces reusing stale sockets.
- **Evict idle/expired:** cleans up sockets, though it may increase connect/TLS overhead when re-established.

Tune idle eviction to match proxy/server behavior and monitor stale retry rates. Do not set everything to 0 or ultra-low just to “be safe”.

### 12.4. Pool Metrics and Thread Dumps

If worker threads are all blocked in `leaseConnection`, that differs from blocking in socket read. Thread dumps combined with Apache connection manager pool stats, Spring HTTP client metrics, and downstream server p99 distinguish the two. A leased connection is not automatically a leak: if the server streams long responses or the client downloads large data, the leased state may be valid.

## 13. Error Handling and Security in Production Systems

### 13.1. Network Failure vs HTTP Response

- HTTP 404/429/503: **an HTTP status was received** from the server/gateway.
- `ResourceAccessException`: the I/O layer may not have received an HTTP response; root cause can be timeout, refused, DNS, SSL, or pool acquisition.
- JSON parse/converter error: upstream body does not match DTO, even on status 200.
- Client cancellation/interruption: does not guarantee the remote operation rolled back.

The gateway/service layer should classify errors into business not-found, validation, transient, policy violation, and unexpected; never turn every exception into 404 or 504.

### 13.2. Retry Budget

Configure max attempts (e.g., 2), jitter, exponential backoff, deadlines, and circuit breakers. If the server returns `Retry-After`, honor it per contract. Avoid retry multiplication across Apache HttpClient, framework resilience libraries, reverse proxies, and message broker consumers. For POST/PUT/PATCH, determine idempotency by business/HTTP semantics; never retry blindly.

### 13.3. SSRF and Redirects

Never build requests from arbitrary client-supplied URLs; attackers can target localhost, metadata endpoints, or private networks. Use fixed base URLs, validate schemes/hosts/ports, and control DNS resolution, redirect hosts, and outbound egress policies. Disable following redirects when destinations must be restricted; if following redirects, strip sensitive headers on cross-origin hops.

### 13.4. Never Leak Secrets

Never log `Authorization`, client keystore passwords, private keys, full PII response bodies, or SSL debug traces containing sensitive data. For custom truststores/keystores, manage passwords via secrets management, filesystem permissions, and rotation. Never commit `.p12` files containing private keys or put real passwords in samples.

### 13.5. Synchronous HTTP Clients in Reactive Handlers

Never call blocking RestClient directly on WebFlux's Netty event loop. Use WebClient + reactive driver for end-to-end reactivity, or isolate blocking calls onto a bounded worker pool with explicit queue/timeout limits; `Mono.just(restClient.get()...)` still blocks **before** Mono assembly.

## 14. Symptom-Based Troubleshooting

| Symptom | Priority Diagnosis |
| --- | --- |
| 700ms timeout yet call takes over 1s | Lease/DNS/connect/TLS/response/body are distinct phases |
| 100 inbound requests, only 5 outbound active | Max per-route = 5, pending acquires |
| Timeout even though upstream sees no request | Lease/connection acquisition timeout |
| `Connection refused` | Listener/firewall/host:port, not HTTP 404 |
| `UnknownHostException` | DNS/resolver/network |
| `PKIX path building failed` | CA/cert chain/truststore |
| Hostname mismatch | URL host does not match certificate SAN |
| Local HTTPS works, production fails | Proxy, TLS version, truststore, cert rotation |
| POST times out yet two records created | Automatic retry/duplicate write |
| Pool leased count never drops | Slow response, unconsumed body, or resource leak |
| JVM fails to exit on app shutdown | Pool/client/evictor/executor not closed |
| JDK 17 compile error on HttpClient.close | Method does not exist on Java 17 |
| Spring 6.1 compile error on Apache setReadTimeout | Method was only added in 6.2 |
| Browser receives 504 while remote returned 200 | Gateway timeout fired before response arrived |
| Low CPU yet high p99 | Blocking waits/pool queue/downstream latency |
| Too many open files | Unbounded sockets/pools/FDs |
| TLS trust-all makes connection “work” | Security verification has been disabled |

## 15. Production Checklist

1. [ ] Know the actual HTTP engine/factory; do not rely on accidental defaults.
2. [ ] Specify maxConnTotal and maxConnPerRoute per downstream capacity.
3. [ ] Configure pool acquire timeout, connect timeout, response timeout, and whole-call deadline.
4. [ ] Account for DNS, proxy CONNECT, and TLS handshake separately in SLAs.
5. [ ] HTTP client/factory/pool are shared beans initialized once.
6. [ ] Connections have sensible TTL/idle eviction/stale validation.
7. [ ] Response bodies/low-level InputStreams are always consumed/closed properly.
8. [ ] Close/dispose pool/evictor cleanly on app shutdown.
9. [ ] Enforce bulkheads/rate limits on concurrent synchronous calls.
10. [ ] Clear retry policy, deadline, and idempotency keys for writes.
11. [ ] HTTP status errors are not confused with network transport exceptions.
12. [ ] TLS CA trust, SAN hostname verification, and mTLS (if required) are tested.
13. [ ] Never use trust-all, NoopHostnameVerifier, or disableHostnameVerification.
14. [ ] Secrets/truststores/keystores are stored and rotated securely.
15. [ ] Base URL/redirects/egress prevent SSRF.
16. [ ] Pool leased/pending/available and p95/p99 latency have metrics.
17. [ ] Cluster-wide connection budget accounts for instance count.
18. [ ] Test 404/429/503, timeouts, pool exhaustion, and untrusted/wrong-host certs.
19. [ ] Test graceful shutdown with active outbound calls.
20. [ ] When upgrading Java/Spring/Apache, check APIs and default semantics.
21. [ ] Never run blocking RestClient directly on the WebFlux event loop.
22. [ ] Benchmarks cover cold/warm connections and realistic TLS/proxies.

## 16. Review Questions and Answers

**1.** Does TCP connect timeout guarantee a fast response?  
**Answer:** No; response/read timeout is a separate phase.

**2.** What is a lease timeout?  
**Answer:** Waiting for a connection from the pool, which can fail before any HTTP request hits the network.

**3.** How does pool total differ from per-route?  
**Answer:** Total caps all connections; per-route caps connections per target route.

**4.** Why should RestClient usually be reused?  
**Answer:** To reuse the request factory/pool and manage TLS/timeouts/lifecycle consistently.

**5.** Can RestTemplate use an Apache pool?  
**Answer:** Yes, via HttpComponentsClientHttpRequestFactory.

**6.** Does Spring 6.1 HttpComponents factory have setReadTimeout(Duration)?  
**Answer:** No; that API was added in Spring 6.2.

**7.** Does Spring 6.1 JdkClientHttpRequestFactory have setReadTimeout(Duration)?  
**Answer:** Yes.

**8.** Does Java 17 HttpClient have close() like Java 21?  
**Answer:** No; Java 21 added public lifecycle APIs.

**9.** How do connection idle and TTL differ?  
**Answer:** Idle measures unused time; TTL measures maximum age since creation.

**10.** What cost does HTTP keep-alive reduce?  
**Answer:** Creating new TCP/TLS connections via connection reuse.

**11.** How does an unclosed response stream affect the pool?  
**Answer:** The connection may remain leased/unusable.

**12.** Does 204 guarantee a non-null DTO body?  
**Answer:** No; 204 has no body.

**13.** How does HTTP 404 differ from TCP connection refused?  
**Answer:** 404 is an HTTP response; refused is a TCP failure.

**14.** Does a timeout after POST prove the server did not save the record?  
**Answer:** No; the server may have already committed.

**15.** Why are idempotency keys needed for POST retries?  
**Answer:** To prevent duplicate resources when a previous response was lost.

**16.** How should PKIX path building failed be fixed?  
**Answer:** Inspect CA/intermediates/truststore; never use trust-all.

**17.** What does hostname verification do?  
**Answer:** Verifies the certificate SAN matches the URL host.

**18.** Are truststore and client keystore the same?  
**Answer:** No; truststore verifies the server, while keystore private key authenticates the client/mTLS.

**19.** Does TLS mTLS automatically replace business authorization?  
**Answer:** No; identity/permission mapping is still required.

**20.** Is increasing pool size indefinitely good?  
**Answer:** No; it can overload upstreams and exhaust sockets/FDs.

**21.** Is a 700ms response timeout a 700ms total-call deadline?  
**Answer:** No; other stages and body semantics still apply.

**22.** Can a pool wait timeout occur even when the upstream is healthy?  
**Answer:** Yes, when all pooled connections are currently leased.

**23.** Why is Java 17 JDK HttpClient harder to control for pooling than Apache 5?  
**Answer:** It lacks equivalent public per-route pool limits, metrics, and close APIs.

**24.** During Spring Boot shutdown, is `server.shutdown=graceful` enough to close the Apache client cleanly?  
**Answer:** No; proper bean lifecycle/destroy of the outbound pool is needed.

**25.** What happens if a synchronous REST client is called on the WebFlux event loop?  
**Answer:** It can block the event loop and degrade concurrency; use WebClient or a bounded bridge.

**26.** Does testing `gateway.slow(1800)` with a 700ms response timeout prove the pool lease limit?  
**Answer:** No; that test only verifies the response timeout.

**27.** Can TLS handshakes affect p99 even when the request body is tiny?  
**Answer:** Yes, especially on cold connections and certificate negotiation.

**28.** When a client follows a redirect to another host, what must be watched?  
**Answer:** SSRF/Authorization header leakage and trust boundaries.

**29.** Should Apache HttpClient automatic retries always be enabled?  
**Answer:** No; consider idempotency, deadlines, and other retry layers.

**30.** What should you inspect first when leased=max and pending rises?  
**Answer:** Pool stats, upstream latency, body closures, and caller concurrency.

## 17. References

- [Spring Framework 6.1 — Rest Clients](https://docs.spring.io/spring-framework/reference/6.1/integration/rest-clients.html): RestClient/RestTemplate and transport adapters.
- [Spring 6.1 JdkClientHttpRequestFactory Javadoc](https://docs.spring.io/spring-framework/docs/6.1.19/javadoc-api/org/springframework/http/client/JdkClientHttpRequestFactory.html): read timeout and JDK bridge.
- [Spring 6.1 HttpComponentsClientHttpRequestFactory Javadoc](https://docs.spring.io/spring-framework/docs/6.1.19/javadoc-api/org/springframework/http/client/HttpComponentsClientHttpRequestFactory.html): connect/lease timeouts and lifecycle.
- [Spring 6.2 HttpComponentsClientHttpRequestFactory Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/http/client/HttpComponentsClientHttpRequestFactory.html): read timeout API added in 6.2.
- [Apache HttpClient 5.2 ConnectionConfig API](https://javadoc.io/static/org.apache.httpcomponents.client5/httpclient5/5.2.1/org/apache/hc/client5/http/config/ConnectionConfig.Builder.html): connect/socket timeout, TTL, idle validation.
- [Apache HttpClient 5 Pooling Manager API](https://hc.apache.org/components/httpcomponents-client-5.4.x/5.4.4/httpclient5/apidocs/org/apache/hc/client5/http/impl/io/PoolingHttpClientConnectionManagerBuilder.html): total/per-route pool limits.
- [Java 17 HttpClient API](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): send/sendAsync, connectTimeout, SSLContext.
- [Java 21 HttpClient API](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpClient.html): new public lifecycle methods.
- [Java 17 HttpExchange Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html): local test server lifecycle.
- [Spring Boot 3.3 — Calling REST Services](https://docs.spring.io/spring-boot/3.3/reference/io/rest-client.html): injected RestClient.Builder.
- [Java Secure Socket Extension](https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html): trust managers, key managers, TLS.
- [RFC 9110 HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): status, methods, idempotency.
- [RFC 8446 TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446): TLS handshake.

**Conclusion:** Synchronous HTTP clients are reliable only when **connect, lease, response, and whole-call deadlines are distinguished**, connection pools have explicit limits/metrics and lifecycle, TLS chains and hostnames are always verified, response streams are closed, and retries have idempotency. Choose a request factory for your **actual** Spring/JDK/Apache versions rather than copying non-existent methods or assuming every HTTP client shares identical pooling.
