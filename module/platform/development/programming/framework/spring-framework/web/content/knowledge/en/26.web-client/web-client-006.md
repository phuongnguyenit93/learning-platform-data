# WebClient: Timeouts, Connection Pools, TLS, and Codec Memory Limits

## 1. The Big Picture

Spring WebFlux's `WebClient` is an asynchronous, non-blocking HTTP client. When using **Reactor Netty** as the HTTP connector (the common default with `spring-boot-starter-webflux`), a single request is governed by multiple layers:

```text
WebClient (Spring)
    │  encode request / decode response via HTTP message codecs
    ▼
ReactorClientHttpConnector
    ▼
Reactor Netty HttpClient
    ├── ConnectionProvider: reusable connections, max count, pending queue
    ├── DNS, TCP connect, proxy (if any)
    ├── TLS handshake + certificate/hostname verification (HTTPS)
    └── Send HTTP request → wait/read HTTP response
    ▼
Spring codecs: read/convert body → Mono<T> / Flux<T>
```

The four configuration groups in this lesson protect **four distinct resources/states**:

- **Timeouts:** prevent requests from hanging while waiting for a connection, TLS, response bytes, or exceeding overall bounds.
- **Connection pool:** bound connection counts and waiting requests, reducing repeated TCP/TLS setup overhead.
- **TLS:** encrypt transport and verify the server via certificate chain/hostname; optionally present client certificates for mTLS.
- **Codec `maxInMemorySize`:** bound memory buffered while decoding; prevent unbounded memory consumption from large responses.

The sample numbers below are **illustrative values for learning**. Derive production settings from SLOs, upstream characteristics, payload sizes, and load-test results rather than treating sample numbers as universal defaults.

## 2. Timeout Types: Understand Scope Before Configuring

| Type | Start/end and meaning | Typical configuration |
| --- | --- | --- |
| Waiting for a pool connection | Waits for an idle connection or capacity to open a new one; exceeding it fails acquisition | `ConnectionProvider.pendingAcquireTimeout(Duration)` |
| TCP connect | Waits for the TCP handshake to the remote address; does not cover the full HTTP response | `HttpClient.option(ChannelOption.CONNECT_TIMEOUT_MILLIS, ms)` |
| TLS handshake | Waits for the TLS handshake on HTTPS; independent of TCP connect timeout | `HttpClient.secure(ssl -> ssl.handshakeTimeout(...))` |
| HTTP response read | Bounds the idle gap **between network read operations** during a response, not a total transaction deadline | `HttpClient.responseTimeout(Duration)` |
| Optional Read/Write I/O | Monitors read/write inactivity via Netty handlers; scope can differ from `responseTimeout` | `ReadTimeoutHandler` / `WriteTimeoutHandler` |
| Total reactive pipeline | Cancels a `Mono`/`Flux` if the next signal does not arrive in time, depending on operator placement | `mono.timeout(Duration)`, or a multi-step deadline strategy |

**Important:** `responseTimeout(Duration)` in Reactor Netty describes the maximum gap between *network reads* while reading a response. A stream receiving small chunks continuously can run longer than this value without timing out. If business requirements demand "the entire call completes within 3 seconds," place an overall timeout on the publisher completing the whole request (and account for retries sharing one time budget). `CONNECT_TIMEOUT_MILLIS` does not bound DNS, pool acquisition, or response reading; depending on the environment, DNS/proxies also have their own timeouts.

Example creating a shared `HttpClient`:

```java
import java.time.Duration;
import io.netty.channel.ChannelOption;
import reactor.netty.http.client.HttpClient;

HttpClient httpClient = HttpClient.create()
    .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 3_000)
    .responseTimeout(Duration.ofSeconds(5));
```

Then attach it via Spring:

```java
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

WebClient webClient = WebClient.builder()
    .baseUrl("https://api.example.com")
    .clientConnector(new ReactorClientHttpConnector(httpClient))
    .build();

Mono<String> result = webClient.get()
    .uri("/health")
    .retrieve()
    .bodyToMono(String.class)
    .timeout(Duration.ofSeconds(8)); // Deadline for this publisher
```

This is an illustrative snippet; add `import reactor.core.publisher.Mono` if used standalone and replace the server with a real endpoint. `timeout()` emits a reactive timeout error upon expiration and cancels the subscription; it **does not replace** transport-layer connect/pool/TLS/read settings. When multiple timeouts are configured, whichever limit is reached first determines the observed failure. Do not diagnose root causes solely from a top-level exception name; inspect the *cause chain* and metrics.

### Per-Request Timeouts and the Risk of Misusing ReadTimeoutHandler

`HttpClient.responseTimeout(...)` sets the default for requests on that `HttpClient`. Reactor Netty also supports overriding it at the `HttpClientRequest` level (in `doOnRequest`/`httpRequest` callbacks, where supported by the API/connector). This helps when most endpoints are fast while one streaming endpoint needs a longer read interval.

Some online examples use:

```java
HttpClient client = HttpClient.create()
    .doOnConnected(connection -> connection
        .addHandlerLast(new io.netty.handler.timeout.ReadTimeoutHandler(10))
        .addHandlerLast(new io.netty.handler.timeout.WriteTimeoutHandler(10)));
```

These two handlers monitor **channel** I/O inactivity (the arguments above are in seconds) and can affect pooled connection reuse and streaming traffic. If your goal is simply waiting for/reading HTTP responses, prefer Reactor Netty's `responseTimeout`; add raw I/O handlers only for specific requirements once you understand their lifecycle.

## 3. Connection Pools: Sharing, Bounding, and Reuse

Every new TCP/TLS handshake costs time, CPU, and sockets. A connection pool retains eligible connections after a response so subsequent requests can reuse them (respecting keep-alive and HTTP protocol rules). Reuse cuts down new connections, though a pool does not make an upstream server process faster.

Sample configuration:

```java
import java.time.Duration;
import reactor.netty.resources.ConnectionProvider;
import reactor.netty.http.client.HttpClient;

ConnectionProvider provider = ConnectionProvider.builder("partner-api-pool")
    .maxConnections(100)
    .pendingAcquireMaxCount(200)
    .pendingAcquireTimeout(Duration.ofSeconds(2))
    .maxIdleTime(Duration.ofSeconds(20))
    .maxLifeTime(Duration.ofMinutes(5))
    .evictInBackground(Duration.ofSeconds(30))
    .build();

HttpClient httpClient = HttpClient.create(provider)
    .responseTimeout(Duration.ofSeconds(5));
```

Explanation:

- `maxConnections(100)`: up to 100 active connections **per pool key** (e.g., remote authority/proxy depending on configuration); do not interpret this as strictly 100 total connections across the entire JVM for all hosts.
- `pendingAcquireMaxCount(200)`: maximum queued requests waiting for a connection when the pool is busy. This is an admission queue, not 200 extra connections.
- `pendingAcquireTimeout(2s)`: if no connection is acquired after 2 seconds, the request fails; this timeout is separate from TCP connect.
- `maxIdleTime(20s)`: connections idle too long become eligible for eviction. Choose appropriately, typically no longer than the server/load balancer's idle timeout.
- `maxLifeTime(5m)`: maximum lifetime of a connection before it should be retired from the pool. Does not mean an in-flight request is abruptly severed at that exact mark.
- `evictInBackground(30s)`: periodically sweeps eligible connections; if disabled, checks still occur on acquire/release depending on the implementation.

**Application-scoped pools:** typically create `WebClient`/`HttpClient`/`ConnectionProvider` as shared beans reused across requests instead of allocating a new pool per HTTP call.

```java
@Configuration
class PartnerClientConfig {
    @Bean(destroyMethod = "dispose")
    ConnectionProvider partnerPool() {
        return ConnectionProvider.builder("partner-api-pool")
            .maxConnections(100)
            .pendingAcquireMaxCount(200)
            .pendingAcquireTimeout(Duration.ofSeconds(2))
            .maxIdleTime(Duration.ofSeconds(20))
            .build();
    }

    @Bean
    WebClient partnerWebClient(ConnectionProvider partnerPool) {
        HttpClient http = HttpClient.create(partnerPool)
            .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 3_000)
            .responseTimeout(Duration.ofSeconds(5));
        return WebClient.builder()
            .baseUrl("https://api.example.com")
            .clientConnector(new ReactorClientHttpConnector(http))
            .build();
    }
}
```

This is an illustrative configuration requiring imports for `org.springframework.context.annotation.*`, `WebClient`, `HttpClient`, `ConnectionProvider`, `ChannelOption`, `ReactorClientHttpConnector`, and `Duration`. In Spring Boot, you can inject the Boot auto-configured builder to retain application customizers; remember to attach the connector before calling `build()`.

**Lifecycle:** dispose only pools **that you created and own** upon application shutdown; never dispose after each request. By default, Spring WebClient with Reactor Netty uses shared global resources; do not accidentally shut down global resources belonging to other components. When configuring custom resources in a container capable of in-place restarts, manage resources via Spring beans/`ReactorResourceFactory` to prevent thread/connection leaks.

### Pool Saturation and Diagnosis

If 100 concurrent requests use a pool with `maxConnections=10`, only 10 connections can serve simultaneously (simplifying for HTTP/1.1); the rest wait and may hit acquire timeouts or queue limits. Sizing the pool too large can overload the upstream, sockets, file descriptors, or ephemeral ports. If response bodies are not read/cancelled properly, connections can also stay leased too long.

Monitor at minimum: active/idle/pending connections per pool, acquire latency, acquire timeouts, connect/TLS timeouts, response latency, and error rates; use Reactor Netty metrics with Micrometer/Actuator if integrated. Tune **together with** caller concurrency bounds, rate limits, and upstream capacity. Do not enable an unbounded pending queue to mask a bottleneck; it inflates latency and causes cascading timeouts for users.

## 4. TLS: Secure HTTPS Connections and Related Timeouts

For `https://...` URLs, TLS provides encryption and server authentication. Normal configurations should use trusted anchors and verify both the certificate chain and hostname; never disable certificate verification just to "make it work." For endpoints requiring mutual TLS (mTLS), the client must also present an issued client certificate/private key.

Sample `HttpClient` for HTTPS with handshake timeout:

```java
import java.time.Duration;
import reactor.netty.http.Http11SslContextSpec;
import reactor.netty.http.client.HttpClient;

HttpClient httpsHttpClient = HttpClient.create()
    .secure(ssl -> ssl
        .sslContext(Http11SslContextSpec.forClient())
        .handshakeTimeout(Duration.ofSeconds(8)))
    .responseTimeout(Duration.ofSeconds(5));

WebClient httpsWebClient = WebClient.builder()
    .baseUrl("https://api.example.com")
    .clientConnector(new ReactorClientHttpConnector(httpsHttpClient))
    .build();
```

The `WebClient` part requires the imports shown in section 2. `Http11SslContextSpec` explicitly configures TLS for HTTP/1.1; HTTP/2/ALPN setups use the corresponding protocol-compatible spec. TLS configuration should only be applied to HTTPS endpoints. Connectors/versions differ in defaults; examples in this lesson target **Spring Framework 6.x + Reactor Netty 1.1.x**.

### Trust Store, Custom CA, mTLS

- **Public CAs:** in most standard HTTPS scenarios, prefer the default trust configuration supplied by the client/JDK/Netty, avoiding unnecessary manual certificate management.
- **Internal CA/self-signed test CA:** install the trusted CA into an appropriate runtime trust store, or pass a custom trust manager in a controlled way. The certificate must match the URL's hostname/SAN. Do not mistake an "unknown CA" error for a timeout.
- **mTLS:** additionally configure a valid client certificate and private key in the SSL context while still validating the server certificate. Protect secrets/passwords/keys; avoid placing private keys in source code, logs, or public Docker images.
- **TLS handshake timeout:** bounds only the handshake phase, not connect or response timeouts. If the server rejects the TLS version/cipher or presents an invalid cert, raising the timeout usually will not help.
- **Never use** `InsecureTrustManagerFactory.INSTANCE` or disable hostname verification in real environments; doing so leaves HTTPS vulnerable to target spoofing.

When encountering `SSLHandshakeException`/`SSLException`, check for expired/unknown CAs, missing intermediate certificates, SAN/hostname mismatches, protocol/cipher incompatibilities, server requests for a client certificate, or handshake timeouts. Enable TLS debugging selectively in test environments; never enable wiretap/body logging containing secrets in production.

## 5. Codec Memory Limit: What Is `maxInMemorySize`?

`WebClient` uses HTTP message codecs to convert JSON, text, XML, etc., between byte streams and objects. Some decoders must buffer data in memory to parse a value/segment. By default per Spring documentation, the limit is typically **256 KiB (262,144 bytes)**. When exceeded, you may see:

```text
org.springframework.core.io.buffer.DataBufferLimitException:
Exceeded limit on max bytes to buffer
```

Raise the limit for a **specific WebClient**:

```java
WebClient client = WebClient.builder()
    .codecs(configurer ->
        configurer.defaultCodecs().maxInMemorySize(2 * 1024 * 1024))
    .build();
```

That value equals **2 MiB**, illustrating an endpoint returning a JSON object requiring more buffering than the default. Do not raise every client to hundreds of MiB when only one endpoint has large payloads; a high limit multiplied by concurrent requests puts pressure on heap/off-heap memory and GC.

**Common confusion:** `maxInMemorySize` is the buffering cap of the **applicable decoder/message reader**, not an application-wide memory quota, not a cap on total HTTP bytes transferred over the network, and not a defense against all forms of memory exhaustion. For NDJSON/SSE streams decoded item by item, the limit typically applies to the buffer needed for *one item/frame*; `collectList()` can still retain huge numbers of items in RAM. For `bodyToMono(String.class)` or large JSON objects, buffering the content is usually required and hits this limit.

When receiving large responses:

1. Check the **response format** and schema first: does a giant JSON object really need to be downloaded whole? Could the API switch to pagination, NDJSON, or streaming?
2. Size the limit according to business requirements and real payload sizes, including error bodies read as Strings by `onStatus`; do not blindly bump the max size just to "silence the error."
3. When downloading large files, consider streaming `Flux<DataBuffer>` into an appropriate file sink (e.g., `DataBufferUtils.write`), avoiding `bodyToMono(byte[].class)` or `collectList` of all buffers. Be careful with ownership/release when handling `DataBuffer` manually; framework decoders normally handle this.
4. Use pagination/backpressure/concurrency bounds to limit how many objects live simultaneously. Codec limits do not replace size caps at reverse proxies/gateways or API-contract total request/response limits.

Configuring the **client** does not automatically alter the **server's** codec limit. Spring MVC differs from Spring WebFlux across body-parsing layers; determine accurately which side threw `DataBufferLimitException`.

## 6. Localhost Runnable Java 17+ Example: Pool, Timeouts, and Codec Limit

This example creates a Reactor Netty HTTP server right inside `main`, so **no internet or external upstream is required** to run it. The client configures a pool, TCP connect timeout, response read timeout, and a 1 KiB codec limit. `/ok` returns a short response; `/large` returns 4 KiB of text and is expected to trigger `DataBufferLimitException` when decoded as a `String`.

Structure:

```text
webclient-resources-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/WebClientResourcesDemo.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'webclient-resources-demo'
```

**`build.gradle`** (Java 17+, Gradle 8.x)

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux:3.3.13'
}

application {
    mainClass = 'demo.WebClientResourcesDemo'
}
```

**`src/main/java/demo/WebClientResourcesDemo.java`**

```java
package demo;

import java.time.Duration;

import io.netty.channel.ChannelOption;
import org.springframework.core.io.buffer.DataBufferLimitException;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;
import reactor.netty.DisposableServer;
import reactor.netty.http.client.HttpClient;
import reactor.netty.http.server.HttpServer;
import reactor.netty.resources.ConnectionProvider;

public class WebClientResourcesDemo {
    public static void main(String[] args) {
        DisposableServer server = HttpServer.create()
            .host("127.0.0.1")
            .port(0) // OS chooses an available port
            .route(routes -> routes
                .get("/ok", (request, response) ->
                    response.header("Content-Type", "text/plain; charset=UTF-8")
                        .sendString(Mono.just("OK")))
                .get("/large", (request, response) ->
                    response.header("Content-Type", "text/plain; charset=UTF-8")
                        .sendString(Mono.just("x".repeat(4096)))))
            .bindNow();

        ConnectionProvider pool = ConnectionProvider.builder("lesson-pool")
            .maxConnections(4)
            .pendingAcquireMaxCount(8)
            .pendingAcquireTimeout(Duration.ofSeconds(2))
            .maxIdleTime(Duration.ofSeconds(15))
            .maxLifeTime(Duration.ofMinutes(1))
            .build();

        try {
            HttpClient http = HttpClient.create(pool)
                .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 1_000)
                .responseTimeout(Duration.ofSeconds(2));

            WebClient client = WebClient.builder()
                .baseUrl("http://127.0.0.1:" + server.port())
                .clientConnector(new ReactorClientHttpConnector(http))
                .codecs(config -> config.defaultCodecs().maxInMemorySize(1024))
                .build();

            String result = client.get().uri("/ok")
                .retrieve()
                .bodyToMono(String.class)
                .block();
            System.out.println("ok: " + result);

            try {
                client.get().uri("/large")
                    .retrieve()
                    .bodyToMono(String.class)
                    .block();
                System.out.println("large: unexpected success");
            } catch (RuntimeException error) {
                if (!hasCause(error, DataBufferLimitException.class)) {
                    throw error;
                }
                System.out.println("large: DataBufferLimitException");
            }
        } finally {
            pool.disposeLater().block();
            server.disposeNow();
        }
    }

    private static boolean hasCause(Throwable error, Class<?> expectedType) {
        for (Throwable current = error; current != null;
             current = current.getCause()) {
            if (expectedType.isInstance(current)) {
                return true;
            }
        }
        return false;
    }
}
```

In the project directory, run with an installed Gradle or a generated Gradle Wrapper:

```bash
gradle run --quiet
```

**Lines printed by the program in a normal environment:**

```text
ok: OK
large: DataBufferLimitException
```

Extra library logs may appear depending on logger configuration. `port(0)` avoids port conflicts. `disposeNow()` stops the server; `disposeLater().block()` releases the pool created by this example. `block()` appears only in the CLI `main` to observe outputs; inside a WebFlux request handler, return `Mono`/`Flux` directly.

The example demonstrates timeout configuration; because localhost responds quickly, **it does not force a TCP connect timeout or response timeout**. To verify timeouts independently, use a test upstream with controllable latency, measure elapsed time, and distinguish error types. With a `/slow` endpoint emitting a body after a delay longer than `responseTimeout`, you can test response timeouts in an integration test without depending on the internet. TLS is not enabled on this `http://127.0.0.1` server; HTTPS configuration was covered in section 4.

## 7. Sizing Limits for Load and Business Needs

Suppose there are 200 concurrent requests to an external service, each with up to a 2 MiB response body:

- If the pool has only 20 connections, the rest may wait. `pendingAcquireTimeout` must align with the overall request deadline; if the overall deadline is 2 seconds while acquisition permits 10 seconds, the request may be cancelled before even reaching the HTTP stage.
- If a decoder can hold 2 MiB per response and many responses decode simultaneously, RAM usage scales with concurrency. A simple design reminder: 50 requests buffering up to 2 MiB each can create *roughly* 100 MiB of buffers in the worst case; in reality there is also object overhead, networking, and other buffers. This is **not** a total JVM RAM estimate.
- If the client streams content continuously, `responseTimeout=5s` is a read idle timeout; total completion time can exceed 5 seconds. Enforce overall bounds via publisher timeouts or business deadlines.
- Multiplying the pool size by 10 does not make the upstream stronger. Measure latency, throughput, and 429/503 rates, and bound request concurrency/retries.

A trial set of values only makes sense when paired with a documented traffic profile and upstream SLO. For an internal API typically responding under 500 ms, you might **start testing** with connect 2 s, acquire 1 s, read 3 s, total 5 s, and codec 1 MiB, then load-test to tune; do not treat those as recommended settings for streaming, file downloads, or high-latency cross-region calls.

## 8. Common Errors and Signal-Based Diagnosis

| Symptom | What to check first | Appropriate resolution |
| --- | --- | --- |
| Pool acquire timeout | Active/pending connections, queue length, response latency, number of clients/pools created | Reduce concurrency, reuse clients, tune pool, address slow upstream |
| TCP connect timeout | DNS, routing, firewall, address/port, proxy, server capacity | Check network path, set proper timeouts, bounded retry if safe |
| TLS handshake error/timeout | CA, SAN hostname, expired cert, mTLS, TLS versions, latency | Fix trust/cert/protocol; raise handshake timeout only when genuinely slow |
| `ReadTimeoutException` or response read timeout error | Did the server stop sending bytes? Streaming heartbeats? Proxy buffering? | Adjust read timeout and heartbeats; investigate upstream |
| `TimeoutException` from Reactor `timeout()` | Which pipeline is waiting? Is `timeout` before or after retry? | Design overall deadline; log stage and correlation ID |
| `DataBufferLimitException` | Which codec decoded, single large object vs. multi-item stream, payload size | Shrink payload, paginate/stream, raise `maxInMemorySize` selectively |
| OutOfMemoryError despite raising codec limit | High concurrency, `collectList`, large `byte[]`, Netty off-heap, memory leak | Bound concurrency/total bytes, stream, profile heap/direct memory |
| Intermittent keep-alive errors | Pool idle exceeds server/LB idle timeout, stale sockets, network resets | Configure max idle, eviction, check connection reuse |

At minimum, logs/traces should include the logical endpoint (without leaking sensitive data), correlation ID, pool/connect/response wait times, error type, HTTP status when a response arrived, and safe body size/type metrics. Never log credentials, access tokens, personal data, or raw TLS payloads.

**Anti-patterns to avoid:**

1. Using `Mono.timeout` and assuming transport TCP connect/pool timeouts are properly configured.
2. Increasing `maxConnections` and `pendingAcquireMaxCount` without bound to cure latency; this can overload the upstream.
3. Creating a new `ConnectionProvider` on every HTTP call, losing reuse and leaking resources.
4. Calling `block()` on the Netty event loop in WebFlux; non-blocking pipelines must compose with `map`/`flatMap` and return publishers.
5. Treating read timeout as the maximum total file download duration; streaming traffic needs separate deadline/idle policies.
6. Disabling certificate validation to bypass TLS errors; that is a security vulnerability, not timeout tuning.
7. Treating codec limits as a cap on total response/download size or total RAM; buffers and collections exist outside that scope.
8. `onErrorResume(error -> Mono.empty())` across all errors, hiding timeouts, certificate failures, HTTP 500s, and limit overflows from monitoring.
9. Retrying non-idempotent POST operations by default; enforce retry limits, backoff, idempotency keys where appropriate, and an overall deadline.
10. Setting ultra-short timeouts in environments with cold starts, TLS handshakes, DNS, or cross-region links without real measurements.

## 9. Self-Check Questions

1. **Max pool 10, 30 requests arrive simultaneously:** Will the remaining 20 necessarily fail with TCP connect timeout? → No; they may wait in the pool queue, bounded by `pendingAcquireMaxCount`/`pendingAcquireTimeout`, without entering TCP connect.
2. **A server sends one chunk every 2 seconds for 10 minutes, `responseTimeout=5s`:** Will it time out because the total is 10 minutes? → Not necessarily; read intervals stay under 5 seconds. Enforcing a total transaction cap requires a separate deadline.
3. **HTTPS reports "unable to find valid certification path":** Should you increase the handshake timeout? → No; check the CA chain/trust store, hostname, and potential mTLS requirements first.
4. **`bodyToMono(MyHugeDto.class)` hits `DataBufferLimitException` while `bodyToFlux(DataBuffer.class)` succeeds:** Does that mean RAM is always safe? → No; operators collecting buffers or high request concurrency can still exhaust memory.
5. **Continuous SSE stream:** Does setting a 2 MiB codec limit protect against 1 million events collected by `collectList()`? → No; process items incrementally and bound downstream retention.
6. **Why must self-created pools be disposed on application shutdown?** → Pools manage connections/resources; release them at lifecycle shutdown, not per request.

## 10. References

- Spring Framework, WebClient configuration (Reactor Netty, timeouts, codecs): https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html
- Spring Framework, Reactive Core — Limits/streaming/DataBuffer: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
- Reactor Netty, HTTP Client (connection pool, TLS, timeout): https://projectreactor.io/docs/netty/release/reference/http-client.html
- Reactor Netty Javadoc, `HttpClient.responseTimeout`: https://projectreactor.io/docs/netty/release/api/reactor/netty/http/client/HttpClient.html
