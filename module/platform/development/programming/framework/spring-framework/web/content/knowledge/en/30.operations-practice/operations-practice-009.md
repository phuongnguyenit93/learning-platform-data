# Calling External Services Practice: HTTP Clients, Timeouts, and Error Handling

## 1. Goal: calling external services in a controlled way

In a Spring Framework application, an HTTP endpoint often has to call another system: inventory, pricing, payment, identity, shipping, or a partner API. Successfully calling a URL is only step one. In production, connections can fail during DNS/TCP/TLS, upstream can return 4xx/5xx, servers can return invalid payloads, networks can stall unexpectedly, or clients can cancel requests. If every case is swallowed with `catch (Exception)` returning `null`, callers cannot tell out-of-stock apart from a temporary upstream outage or a programming bug.

Practice goals:

1. Know how to choose between **`RestClient`**, **`WebClient`**, legacy `RestTemplate`, and HTTP Service Clients.
2. Set **connect timeouts, read/response timeouts, and end-to-end deadlines** from SLAs instead of arbitrary guesses.
3. Classify **HTTP status errors**, **transport/network failures**, **decode errors**, **timeouts**, and **business responses**.
4. Decide when to retry and when retrying can duplicate business actions.
5. Design a service-calling client adapter that maps errors to your service/API contract while protecting secrets and observability.
6. Run a Java 17+ program that starts a local HTTP server, calls it with Spring `RestClient`, and observes three scenarios: **200, 404, and a slow response triggering read timeout**.

**Reference versions:** Java 17+, Spring Framework 6.1.x, Spring Boot 3.3.x. `RestClient` was introduced in Spring Framework 6.1. The complete example uses Java SE + the `spring-web` module and a local JDK HTTP server; no Docker, database, or public API is required.

## 2. Choosing an HTTP client API that fits your execution model

| Client | Model and API | Use when | Notes |
| --- | --- | --- | --- |
| **`RestClient`** | Fluent, synchronous; `get().uri(...).retrieve().body(...)` | Spring MVC services, synchronous batches, imperative apps | Executes I/O on method call, holding the request thread until response |
| **`WebClient`** | Reactive; `Mono<T>`/`Flux<T>` | Spring WebFlux, streaming, async composition, high concurrent I/O | Publisher usually runs on subscribe; avoid `block()` on the event loop |
| **`RestTemplate`** | Legacy synchronous API | Existing projects maintaining older integrations | Spring now recommends `RestClient` for new synchronous APIs |
| **HTTP Service Client** | Java interface `@GetExchange`/`@PostExchange` + proxy | Modeling partner APIs via contract interfaces | Still requires choosing `RestClientAdapter`/`WebClientAdapter` and configuring transport/timeouts underneath |

Choose according to your real runtime environment. A Spring MVC controller making a few outbound REST calls usually does not need a full reactive rewrite just to make HTTP calls. Conversely, in WebFlux, blocking Netty event-loop threads with `RestClient` or `WebClient.block()` degrades throughput and can be rejected by Reactor.

**An HTTP client is not a single TCP connection.** `RestClient`/`WebClient` can reuse transports, connection pools, and thread resources depending on the underlying library. Declare and reuse clients as beans; never construct a new client, TLS context, or pool per incoming request.

### Two invocation styles

```java
// Synchronous fragment inside a method with an existing RestClient inventoryClient:
String body = inventoryClient.get()
        .uri("/items/{id}", 42)
        .retrieve()
        .body(String.class);
```

```java
// Reactive fragment inside a method with an existing WebClient inventoryWebClient:
Mono<String> bodyPublisher = inventoryWebClient.get()
        .uri("/items/{id}", 42)
        .retrieve()
        .bodyToMono(String.class);
```

With `RestClient`, the calling thread blocks until a response or exception arrives. With `WebClient`, `Mono` describes a pipeline and executes upon subscription. Both convert many **4xx/5xx** statuses into exceptions by default under `retrieve()`, rather than returning `null`. Neither is forced to use the same underlying connector.

## 3. Understanding the full journey of an HTTP call

A call is more than server business-logic time:

```text
Incoming request
      │
      ▼
Application service / outbound adapter
      │
      ├─ URI resolve + DNS
      ├─ Wait for connection from pool (if pooled)
      ├─ TCP connect
      ├─ TLS handshake (HTTPS)
      ├─ Send request headers and body
      ├─ Wait for response headers
      ├─ Read response body (may stream for a long time)
      └─ Decode JSON / map DTO
      │
      ▼
Success or a specific error class
```

Error classes:

| Stage | Failure scenario | Symptoms |
| --- | --- | --- |
| URI/input creation | Invalid URL, missing URI variable, illegal characters | May fail immediately on the client side |
| DNS / TCP | Unresolvable host, connection refused, network unreachable | Typically an I/O/transport exception, **no HTTP status** |
| TLS | Untrusted certificate, hostname mismatch, handshake error | SSL/transport exception; never disable TLS verification |
| Pool | Pool exhausted, pending acquire timeout | Depends on engine/pool, no response received |
| Reading response | Read/response timeout, connection reset, EOF | Transport exception |
| Server returned response | 400, 401, 403, 404, 409, 429, 500, 503… | **Actual HTTP status**; body/headers can be informative |
| Decoding | Bad JSON/fields, incompatible content type, oversized body | Codec/message conversion exception |
| Business | HTTP 200 while JSON indicates out-of-stock, denied, invalid state | Transport-valid response; requires understanding domain semantics |

**Do not equate HTTP 503 with connect timeout:** 503 means an HTTP response was received from a server/proxy; a connect timeout happens before any valid response exists. The two require different logging and retry handling.

**Do not equate upstream HTTP 404 with public HTTP 404:** inventory returning 404 means the SKU is absent from inventory; your public API might return 404, 422, or another business outcome depending on the use case. Never pass downstream statuses straight out automatically.

## 4. Timeouts: defining each timer

Timeouts must be budgeted around the request's SLA, not a blanket "5 seconds for everything."

| Timeout type | What it bounds | Example |
| --- | --- | --- |
| **Connect timeout** | Time to establish TCP connection to endpoint | 300 ms |
| **Pool acquire timeout** | Time waiting to borrow a pooled connection | 200 ms |
| **Read timeout** | Wait time on socket read operations, typically waiting for the next chunk of data | 900 ms |
| **Response timeout** | HTTP-engine timeout awaiting/receiving response per engine semantics | 1 s |
| **Write timeout** | Time writing request body/socket, if supported by engine | 1 s |
| **End-to-end deadline** | Total use-case budget, including network calls, processing, and retries | 2 s |

**Read timeout does not equal total request timeout.** For example, a stream sending one byte at a time faster than the read timeout can stay open for minutes. Likewise, setting only a connect timeout does not stop a server from accepting the connection and hanging before sending a body.

Timers also depend on the HTTP engine and version. DNS resolution is not always covered by connect timeout; TLS handshakes, proxies, and pending acquire can have separate limits. To enforce a **total cap**, set a deadline at the application/async pipeline level or via a lifecycle-wide client mechanism, and propagate **remaining budget** to downstream calls where possible.

### Example budget and retry count

Suppose a public endpoint has a 2-second SLO. Assume controller/serialization takes ~250 ms and other work takes ~150 ms, leaving ~1.6 seconds for the inventory call. If each outbound attempt allows a 1.5-second response timeout and automatically retries **twice more**, you risk holding the request far longer than the budget.

A better strategy:

- Define a **total deadline** for the call chain from the incoming request.
- Configure transport connect and read/response timeouts so resources never hang.
- Cap retry attempts and total retry duration; use a remaining-time budget.
- Stop retrying once the deadline expires or the client cancels the request.
- Fall back only when business semantics allow (e.g., cached informational data, never faking "success" for money or inventory reservations).

**No single timeout profile fits every upstream.** A payment service has different requirements than an image metadata service; configure per dependency group, endpoint, payload size, and resilience profile.

## 5. RestClient: configuring request factory and timeouts

In Spring Framework 6.1, `RestClient` is built via `RestClient.builder()`, `RestClient.create()`, or a Spring Boot-provided `RestClient.Builder`. Specific timeouts live on **`ClientHttpRequestFactory`** (the underlying HTTP library); there is no single engine-agnostic `RestClient.timeout(...)` method.

Accessible example: using `SimpleClientHttpRequestFactory` backed by JDK `HttpURLConnection`:

```java
import java.time.Duration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

SimpleClientHttpRequestFactory requestFactory =
        new SimpleClientHttpRequestFactory();
requestFactory.setConnectTimeout(Duration.ofMillis(300));
requestFactory.setReadTimeout(Duration.ofMillis(900));

RestClient client = RestClient.builder()
        .baseUrl("https://inventory.example.org")
        .requestFactory(requestFactory)
        .defaultHeader("X-Client-Name", "catalog-api")
        .build();
```

This is a **configuration fragment**; the example URL is not runnable as-is. Both `setConnectTimeout` and `setReadTimeout` accept `Duration` overloads in Spring 6.1. `0` on URLConnection timeouts can signify infinite timeout; never pass 0 thinking it means "do not wait."

Depending on your stack, the client might use Apache HttpComponents, JDK `HttpClient`, Jetty, or Reactor Netty (WebClient), each with distinct APIs for timeouts, pooling, and TLS. **Never copy `SimpleClientHttpRequestFactory` settings blindly across engines.** Inspect your dependency tree and which native HTTP engine is actually active.

### Using the Spring Boot-managed builder

In a Spring Boot application, inject the builder instead of creating an isolated client that skips common customizations:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration
class OutboundHttpConfiguration {

    @Bean
    RestClient inventoryRestClient(RestClient.Builder builder) {
        SimpleClientHttpRequestFactory factory =
                new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(300);
        factory.setReadTimeout(900);

        return builder
                .baseUrl("https://inventory.example.org")
                .requestFactory(factory)
                .build();
    }
}
```

This is a Spring configuration fragment. Note that explicitly setting a request factory can swap out the Boot-selected transport, affecting pooling, metrics, or TLS defaults; verify after wiring with Boot customizers. Do not share a mutable `RestClient.Builder` as a singleton where upstream-specific headers leak across clients; Spring Boot typically provides a prototype-scoped builder.

Keep base URLs in environment-specific externalized configuration (e.g., validated `@ConfigurationProperties`). Hostnames, credentials, connect/read timeouts, and pool sizes should not be hardcoded constants copied across services.

## 6. RestClient: distinguishing 4xx/5xx from I/O errors

### 6.1 `retrieve()` and error statuses

With `RestClient`, `retrieve().body(Foo.class)` turns HTTP 4xx/5xx statuses into `RestClientResponseException` and specific subclasses like `HttpClientErrorException`/`HttpServerErrorException` by default. Because a response arrived, the exception carries **status**, and potentially **headers and response body**. Network failures throw different exceptions, commonly `ResourceAccessException`.

```java
import org.springframework.web.client.RestClientResponseException;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;

String result;

try {
    result = inventoryRestClient.get()
            .uri("/items/{id}", "SKU-42")
            .retrieve()
            .body(String.class);
} catch (RestClientResponseException responseError) {
    int code = responseError.getStatusCode().value();
    // The HTTP server/proxy actually returned this status code.
    // Mapping 404/429/503 must follow the dependency's semantics.
    throw responseError;
} catch (ResourceAccessException transportError) {
    // DNS, TCP, TLS, read timeout, or other I/O error.
    throw transportError;
}
```

**Fragment:** assumes `inventoryRestClient` is available. The `catch` blocks above illustrate error taxonomy only; production code should translate errors into domain/adapter exceptions with safe logging rather than propagating raw HTTP exceptions across every layer.

Never catch `Exception` and silently return `Optional.empty()`: that turns a network outage or JSON parse failure into "item does not exist." `Optional.empty` is only appropriate when the API contract explicitly defines HTTP 404 as absence.

### 6.2 Intentional handling with onStatus

If a service treats 404 as an expected outcome while 5xx must signal unavailability, you can write:

```java
import org.springframework.http.HttpStatusCode;
import org.springframework.web.client.RestClient;

// Fragment inside a method with an existing RestClient client.
String body = client.get()
        .uri("/inventory/{sku}", "ABC-1")
        .retrieve()
        .onStatus(HttpStatusCode::is5xxServerError,
                (request, response) -> {
                    throw new IllegalStateException(
                            "Inventory upstream failed: "
                            + response.getStatusCode());
                })
        .body(String.class);
```

`onStatus` here only customizes handling for 5xx. For 404, default `retrieve()` still throws; to map 404 to empty or a typed "not found," add matching status handling and choose an appropriate API. Avoid casually using `onStatus(s -> true, ...)` and swallowing the response body, which can break standard status handling.

When you need to read status, headers, and body without `retrieve()`'s default exceptions, consider RestClient's `exchange((request, response) -> ...)`. With `exchange()`, **status handlers are not applied automatically**; the caller must inspect status and consume/close the response per contract. Take care not to read the response stream twice or leave it unclosed.

### 6.3 Mapping errors to application language

Prefer an adapter rather than scattering `catch` blocks across controllers:

```text
HTTP controller
    → ProductService (use case)
      → InventoryGateway interface
        → HttpInventoryGateway (RestClient)
          → remote inventory API
```

`HttpInventoryGateway` can map 404 to `InventoryItemMissing`, 409 to `InventoryConflict`, 429/503 to `InventoryTemporarilyUnavailable`, and transport timeouts to `InventoryTimeout`. These exceptions represent the dependency abstraction so the service handles use cases without coupling to Spring HTTP client exceptions.

Whether the public API returns 502/503/504 or 404 depends on the **public contract**. 504 Gateway Timeout often fits when the service acts as a gateway and timed out waiting on upstream; 503 fits when a required dependency is unavailable; 502 fits invalid/bad upstream responses. There is no universal rule that timeouts must always map to 504 everywhere.

## 7. Retries: attempt caps, backoff, jitter, and idempotency

Retries can help with **transient** failures, yet easily amplify load and create duplicate records. Decisions must weigh operation type, error type, timeout budget, and idempotency.

| Scenario | Auto-retry? | Rationale |
| --- | --- | --- |
| Idempotent GET, transient connection refused | Yes, few attempts | Request likely never reached the server; monitor network errors |
| GET 503 or 429 | Yes, respecting `Retry-After` and budget | Upstream signals temporary unavailability/overload |
| GET 404 | Usually no | Not found per contract, not a transient error |
| POST creating order / charging payment | Never retry blindly | Server may have processed it and only the response was lost |
| POST with **server-supported durable** idempotency key | Allowed per policy | Server can deduplicate repeated calls |
| JSON decode error / schema mismatch | Usually no | Retrying will not fix a contract/schema mismatch |
| 401/403 | Usually no | Fix auth/permissions; do not spam retries |
| Timeout after request was sent | Only if semantics allow | Unknown whether the server already processed it |

### Design principles

- Start with **0 retries**; add retries only for errors proven transient and safe.
- Cap at 1–2 retries per SLA; use exponential backoff + jitter to avoid synchronized retry storms.
- Read and respect `Retry-After` when upstream returns 429/503 (seconds or HTTP-date); never retry past your budget.
- Keep per-attempt timeouts smaller than the total deadline; never sum them indefinitely.
- Separate errors **with an HTTP response** from **no response**: connect timeouts and read timeouts give very different certainty about whether upstream received the request.
- Circuit breakers and bulkheads curb cascading failures; retries are not the only tool.
- Preserve correlation IDs, idempotency keys, and trace context across attempts; log attempt counts without logging secrets.

**Dangerous business example:** `POST /payments` loses its response due to a network blip. The client sees a read timeout and retries; if the payment service does not support idempotency, the customer can be charged twice. A timeout never proves the first request was aborted.

### Retries in WebClient

`WebClient` uses Reactor for composition; fragment:

```java
import java.time.Duration;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

// Method fragment: retry only idempotent GETs.
// isRetryable(Throwable) must be implemented per your own contract.
Mono<String> response = webClient.get()
        .uri("/catalog/{id}", 42)
        .retrieve()
        .bodyToMono(String.class)
        .retryWhen(Retry.backoff(2, Duration.ofMillis(100))
                .maxBackoff(Duration.ofMillis(500))
                .filter(this::isRetryable));
```

This is a fragment, not a standalone program: `webClient` and `isRetryable` are undefined here. `Retry.backoff(2, ...)` allows at most **two retries after the initial attempt**. Never filter with `throwable -> true`: that would retry validation and schema errors too. The retry operator takes effect only when the pipeline is subscribed. For a total deadline, consider pipeline-wide `timeout` and engine cancellation behavior.

## 8. WebClient: timeouts and reactive error handling

With Spring WebFlux, WebClient is the HTTP API layer; transport timeouts live on the connector/native engine. Reactor Netty is a common choice:

```java
import java.time.Duration;
import io.netty.channel.ChannelOption;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;

HttpClient httpClient = HttpClient.create()
        .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 300)
        .responseTimeout(Duration.ofSeconds(2));

WebClient client = WebClient.builder()
        .baseUrl("https://catalog.example.org")
        .clientConnector(new ReactorClientHttpConnector(httpClient))
        .build();
```

This fragment requires `spring-webflux` and `reactor-netty-http`. `CONNECT_TIMEOUT_MILLIS` is Netty's TCP connect timeout, while Reactor Netty's `responseTimeout` bounds response arrival per transport semantics. With a custom connection pool, also configure `pendingAcquireTimeout` and connection limits via `ConnectionProvider`; never build a pool per request.

**You can also set a publisher-level timeout:**

```java
Mono<String> mono = client.get()
        .uri("/catalog/{id}", 42)
        .retrieve()
        .bodyToMono(String.class)
        .timeout(Duration.ofSeconds(3));
```

`Mono.timeout` monitors the reactive publisher and emits a timeout signal if no matching item/signal arrives within the limit. It does not configure DNS/TCP/pool/socket timeouts by itself, nor does it act as a fixed total timeout on a long `Flux` stream if placed poorly. Set both transport settings and total deadlines deliberately.

### Handling status in WebClient

```java
import org.springframework.http.HttpStatusCode;
import org.springframework.web.reactive.function.client.WebClientResponseException;
import reactor.core.publisher.Mono;

// Fragment: returns Mono<String>, do not call block on the event loop.
Mono<String> content = client.get()
        .uri("/catalog/{id}", 42)
        .retrieve()
        .onStatus(HttpStatusCode::is5xxServerError,
                response -> Mono.error(new IllegalStateException(
                        "Upstream status: "
                        + response.statusCode().value())))
        .bodyToMono(String.class);
```

By default, `retrieve()` produces `WebClientResponseException` for 4xx/5xx responses unless overridden; connect/transport failures are wrapped in `WebClientRequestException`; decoder failures and Reactor `TimeoutException` must be handled separately. Inside `onStatus`, if a custom handler reads the body to build an error, read it once with size bounds and avoid retaining references after consumption.

**Avoid these mistakes:** calling `block()` on the WebFlux event loop, calling `subscribe()` manually in each controller request without managing errors, creating a new WebClient per item, using infinite `retry()`, or raising `maxInMemorySize` unbounded instead of streaming large bodies.

## 9. Standalone runnable example: Java 17 + RestClient + local HTTP server

The example below uses the JDK's `HttpServer` to simulate an upstream service, then calls it with Spring `RestClient`:

- `GET /inventory/ok`: returns 200, body `item-42`.
- `GET /inventory/missing`: returns 404, body `missing`.
- `GET /inventory/slow`: intentionally delays response beyond the client read timeout, triggering a transport timeout.

**No external Internet APIs are called when running the demo.** Gradle may need network access the first time to download Spring dependencies. The demo uses Spring Framework `spring-web` directly without `SpringApplication` or a Spring Boot server.

### 9.1 Directory structure

```text
http-client-practice/
├── build.gradle
└── src/main/java/demo/HttpClientPractice.java
```

Contents of `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')
    implementation 'org.springframework:spring-web'
}

application {
    mainClass = 'demo.HttpClientPractice'
}
```

The Spring Boot BOM keeps Spring Framework versions aligned. The project only needs `spring-web` for `RestClient` since the demo reads `text/plain` without JSON DTOs/Jackson. The HTTP server comes built into the JDK (`jdk.httpserver` module); this config runs on a standard classpath.

### 9.2 Full Java source

File `src/main/java/demo/HttpClientPractice.java`:

```java
package demo;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;

public final class HttpClientPractice {

    public static void main(String[] args) throws IOException {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/inventory", HttpClientPractice::serve);
        server.start();

        try {
            SimpleClientHttpRequestFactory transport =
                    new SimpleClientHttpRequestFactory();
            transport.setConnectTimeout(Duration.ofMillis(300));
            transport.setReadTimeout(Duration.ofMillis(150));

            RestClient client = RestClient.builder()
                    .baseUrl("http://127.0.0.1:"
                            + server.getAddress().getPort())
                    .requestFactory(transport)
                    .build();

            System.out.println("OK: " + fetch(client, "ok"));

            try {
                fetch(client, "missing");
                throw new AssertionError("Expected HTTP 404");
            } catch (RestClientResponseException error) {
                System.out.println("MISSING: HTTP "
                        + error.getStatusCode().value());
            }

            try {
                fetch(client, "slow");
                throw new AssertionError("Expected timeout");
            } catch (ResourceAccessException error) {
                System.out.println("SLOW: I/O failure (timeout expected)");
            }
        } finally {
            server.stop(0);
        }
    }

    private static String fetch(RestClient client, String item) {
        return client.get()
                .uri("/inventory/{id}", item)
                .retrieve()
                .body(String.class);
    }

    private static void serve(HttpExchange exchange) throws IOException {
        String path = exchange.getRequestURI().getPath();
        boolean slow = path.equals("/inventory/slow");
        int status = path.equals("/inventory/missing") ? 404 : 200;
        String body = path.equals("/inventory/ok")
                ? "item-42"
                : path.equals("/inventory/missing") ? "missing" : "too-late";

        if (slow) {
            try {
                Thread.sleep(1500);
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
            }
        }

        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        try {
            exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=utf-8");
            exchange.sendResponseHeaders(status, bytes.length);
            try (OutputStream output = exchange.getResponseBody()) {
                output.write(bytes);
            }
        } catch (IOException disconnected) {
            // Client timed out or disconnected before the server responded.
        } finally {
            exchange.close();
        }
    }
}
```

**This code is a complete program.** It starts the server on loopback using an OS-assigned ephemeral port, builds a `RestClient` with the request factory, and calls the three endpoints sequentially. `try/finally` ensures the local server stops. The example handles `text/plain` responses only; real apps add JSON converters, authentication, pooling, and observability.

### 9.3 Run command and output

Inside `http-client-practice`, with Gradle installed:

```bash
gradle run
```

If a Gradle Wrapper has been generated: macOS/Linux `./gradlew run`; Windows PowerShell `.\gradlew.bat run`. Note that the directory layout shown does not include a wrapper automatically: either install Gradle or generate a wrapper before running.

**Expected stdout lines under normal conditions**, excluding Gradle logs:

```text
OK: item-42
MISSING: HTTP 404
SLOW: I/O failure (timeout expected)
```

The slow case intentionally sleeps 1,500 ms while the client read timeout is 150 ms. If the runtime environment shifts dramatically and the slow request somehow succeeds without timing out, the program throws `AssertionError("Expected timeout")`, helping the exercise catch unapplied timeouts instead of silently passing. The `I/O failure` message in `catch` is a summary because `ResourceAccessException` covers multiple transport failures; in production tests, inspect the cause (e.g., `SocketTimeoutException`) to confirm it was specifically a timeout.

The 404 case differs from timeout: `retrieve()` received an HTTP response so the exception carries a status code, whereas slow failed before a valid response arrived. The `missing` body is not silently converted to `null` or an empty string.

### 9.4 Follow-up experiments

1. Increase `setReadTimeout` from 150 ms to 3,000 ms: `/inventory/slow` succeeds with `too-late`, and the example expecting a timeout throws `AssertionError`. That signals you to update test expectations if you deliberately changed the timeout.
2. Change `/inventory/missing` to return 200 + body `not-found`: the HTTP client sees **transport success**; the consumer must interpret the business response per contract rather than relying on HTTP 404.
3. Simulate the server returning 503: change the status in `serve` by path, catch `RestClientResponseException`, and observe code 503 in contrast to `ResourceAccessException` for timeouts.
4. Stop the server before calling: you may receive `ConnectException` wrapped in `ResourceAccessException`. Never confuse that with HTTP 503.
5. Test a URL with a DNS hostname or invalid HTTPS certificate in an isolated test environment to distinguish DNS/TLS failures; never disable hostname/certificate verification as a "quick fix."

This exercise cannot test pool acquire timeouts because `SimpleClientHttpRequestFactory` does not use a connection pool like Apache HttpClient or Reactor Netty. To test pooling, choose the corresponding engine and write a dedicated load test.

## 10. Realistic HTTP client testing: avoid mocking a single method call

Every HTTP client adapter should have **integration/contract tests** sending real HTTP requests to a local stub server, WireMock, MockWebServer, or a controlled test HTTP server. Mocking every Java `restClient.get()...retrieve()` call produces weak tests that miss broken serialization, URI encoding, timeouts, or status mapping.

### Minimum test matrix

| Test | Stubbed upstream | Expected adapter behavior |
| --- | --- | --- |
| Success | 200 + valid JSON/text | Parse DTO, return expected result |
| Not found | 404 + error body | Map error per business contract; do not retry infinitely |
| Validation/client error | 400/422 | Preserve appropriate error; do not treat as transient |
| Unauthorized | 401/403 | Never accidentally log credentials; refresh auth only per policy |
| Rate limit | 429 + `Retry-After` | Bounded retry within deadline or report unavailable |
| Dependency outage | 503 | Apply retry/circuit breaker per policy |
| Read timeout | Slow server or stalled socket | Fail within budget, never hang indefinitely |
| Connect failure | Unreachable/refused endpoint | Distinguish transport error from HTTP response |
| Invalid JSON | 200 response with malformed body | Decode error, never return fabricated data |
| Large payload | Response exceeding limits | Enforce safe memory/streaming policy |
| Retry POST | Server processes request then response drops | Guard against duplicates/idempotency if retrying |
| Cancellation | Caller cancels before response | Proper reactive cancellation/resource cleanup |

In services with multiple dependencies, measure per-call timing and total request budget. For timing tests, use controlled stubs and generous thresholds to avoid flakiness; never assert millisecond-exact timing on loaded CI runners.

### A useful unit test for error classification

You can unit test an exception classifier independently:

```java
import java.net.SocketTimeoutException;
import org.springframework.web.client.ResourceAccessException;

class TimeoutClassifier {
    static boolean hasSocketTimeout(Throwable error) {
        for (Throwable current = error;
                current != null; current = current.getCause()) {
            if (current instanceof SocketTimeoutException) {
                return true;
            }
        }
        return false;
    }
}

// Example assertions (inside a JUnit test):
// assertTrue(TimeoutClassifier.hasSocketTimeout(
//       new ResourceAccessException("read",
//           new SocketTimeoutException("Read timed out"))));
```

This is an **illustrative fragment**, without full JUnit imports or test class wrapper. Note that not every timeout is a `SocketTimeoutException`: JDK HttpClient may use `HttpTimeoutException`, while Reactor `TimeoutException` or engine-specific exceptions appear at different layers. Production classifiers must cover the types used by their actual HTTP library.

## 11. Designing an outbound adapter and clear error contract

Never let HTTP controllers or business services handle Netty/JDK/Apache exception names in dozens of places. Separate them cleanly:

```text
CheckoutController (HTTP boundary)
       │
       ▼
CheckoutService (application use case)
       │
       ▼
PriceGateway (interface)
       │
       └────► HttpPriceGateway (RestClient)
                  ├─ parse PriceQuote DTO
                  ├─ upstream 404 → PriceNotFound
                  ├─ upstream 429/503 → PriceUnavailable
                  ├─ timeout → PriceTimeout
                  └─ invalid JSON → PriceProtocolError
```

Example interface:

```java
record PriceQuote(String sku, String currency, long cents) {}

interface PriceGateway {
    PriceQuote getPrice(String sku);
}
```

This fragment does not compile standalone without an implementation. The application service receives a `PriceGateway` via constructor, not `RestClient` directly. Inside `HttpPriceGateway`, map errors from the **upstream contract**, and keep timeouts, authentication, tracing, and retries at that same boundary.

Key mappings:

- 404 from a product registry may mean "SKU does not exist"; 404 from a misconfigured URL is a deployment bug and must not automatically be treated as a business outcome.
- 401/403 can mean expired credentials, service-account permission denial, or a policy change; never turn it into "product missing."
- 429/503 can be temporary; avoid returning a generic HTTP 500 for everything if the public API needs clear outage signals.
- Decode/contract mismatches should emit dedicated metrics and alerts; if 200 returns broken JSON, HTTP "succeeded" while the integration broke.
- Timeouts can leave state-changing commands in an unknown outcome; "unknown" requires reconciliation or idempotency keys.

### Example exception translation to ProblemDetail

In a public HTTP service, `@RestControllerAdvice` can map adapter exceptions to a standard payload:

```java
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
class DownstreamErrorAdvice {

    @ExceptionHandler(PriceTimeout.class)
    ProblemDetail timeout(PriceTimeout ex) {
        ProblemDetail result = ProblemDetail.forStatus(
                HttpStatus.GATEWAY_TIMEOUT);
        result.setTitle("Upstream timeout");
        result.setDetail("Pricing service did not respond in time");
        return result;
    }

    @ExceptionHandler(PriceUnavailable.class)
    ProblemDetail unavailable(PriceUnavailable ex) {
        ProblemDetail result = ProblemDetail.forStatus(
                HttpStatus.SERVICE_UNAVAILABLE);
        result.setTitle("Pricing unavailable");
        result.setDetail("Please retry later");
        return result;
    }
}
```

This is a **Spring fragment**; `PriceTimeout` and `PriceUnavailable` must be defined as domain/adapter exceptions, and it is not standalone-runnable. The detail text is controlled public copy—never expose internal hostnames, raw exception messages, stack traces, or tokens. You can attach an `errorCode` and trace ID for client diagnostics while keeping the payload compatible with your OpenAPI contract.

## 12. Operations: security, performance, and observability

### 12.1 Do not turn your HTTP client into an SSRF proxy

If an API accepts a URL or hostname from user input and calls it with `RestClient`/`WebClient`, it risks SSRF against metadata endpoints, localhost, private networks, or internal services. Use **preconfigured base URLs**, allowlist schemes/hosts/ports/IP ranges by policy, control redirects and DNS rebinding, and avoid logging URLs with credentials. Never attach service-account tokens/headers to untrusted dynamic hosts.

Over HTTPS, validate the certificate chain and hostname. Never enable "trust all certificates" or disable TLS validation to work around production connectivity issues. Proxies/firewalls and service meshes can alter timeouts, headers, and retries; know which layer owns retries to prevent retry multiplication.

### 12.2 Connection pooling, threads, and resources

A production HTTP client should generally use connection pooling. Tune these bounds:

- Total max connections and per-route/per-host limits.
- Pending acquire timeout, queue length, and connection max idle/lifetime.
- TLS reuse, DNS caching, and connection validation/eviction per engine.
- Clean lifecycle shutdown of pools, event loops, and client resources.
- Total concurrent inbound requests multiplied by outbound fan-out; avoid spawning excessive calls per request.

**Example:** if 300 concurrent requests each call 4 services at once, concurrent outbound operations can greatly exceed 300. Do not just raise pool limits infinitely to "fix timeouts"; track upstream capacity, apply concurrency limiters, and enforce bulkheads.

With Reactor Netty, event-loop and connection-pool resources are often shared; isolate a `ConnectionProvider` when a specific upstream needs isolation, and manage its lifecycle. With Apache HttpClient, the pool and `RequestConfig` have distinct timeouts whose parameters and behavior do not necessarily match JDK `HttpURLConnection`.

### 12.3 Observability and data security

Key metrics/traces to monitor:

| Metric | Question it answers |
| --- | --- |
| Outbound requests/sec by dependency and route template | Traffic to which upstream is climbing? |
| Latency p50/p95/p99, connect/read/total if available | Is the bottleneck in connect or response? |
| HTTP statuses 2xx/4xx/5xx and decode failures | Is upstream returning errors or incompatible payloads? |
| Timeout counts, connect errors, pool acquire waits | Are there transport or capacity bottlenecks? |
| Retry attempts, success after retry, circuit state | Are retries saving requests or amplifying an outage? |
| Concurrent requests, pool active/idle/pending | Are pool or upstream limits exceeded? |
| Tracing/correlation IDs across HTTP hops | Which system was slow for a specific request? |

Log **route templates**, dependency identifiers, statuses, latencies, trace IDs, and retry counts; never log raw `Authorization` headers, session cookies, payment payloads, tokens, URL queries with secrets, or full error response bodies. When inspecting bodies for debugging, enforce byte limits, masking, and access control. Never let a response-logging interceptor consume the body or prevent `DataBuffer` release.

### 12.4 Practical production checklist

1. Define outbound clients per dependency and reuse them as beans.
2. Give each dependency measured connect/read/response timeouts, concurrency limits, and circuit policies.
3. Never wait indefinitely; pass remaining deadline budget downstream where feasible.
4. Retry only transient failures aligned with idempotency, with max attempts, backoff, and jitter.
5. Translate transport/status/decode errors into clear business/gateway error types.
6. Verify JSON contracts, payload sizes, encodings, and response content types.
7. Add tests covering 200, 4xx, 5xx, timeouts, connect failures, malformed bodies, and duplicate POSTs.
8. Enforce proper TLS, protect credentials, block SSRF, and sanitize sensitive log data.
9. Provide legitimate fallback/resync mechanisms; never fake "success" responses to hide outages.
10. Monitor p95/p99 latency, rate limits, pool pressure, retries, and per-upstream alerts.

## 13. Common mistakes and fixes

| Mistake | Consequence | How to fix |
| --- | --- | --- |
| Leaving timeouts unconfigured | Threads/resources hang long when upstream stalls | Set transport timeouts + total deadline |
| Catching every `Exception` and returning `null` | "Missing data" masks outages/bugs | Classify status, I/O, decode, and business errors |
| Assuming upstream HTTP 404 = public HTTP 404 | Leaks topology and breaks business semantics | Map in adapter per dependency contract |
| Retrying every POST timeout | Creates duplicate orders/payments | Use idempotency keys, reconciliation, and retry bounds |
| Retrying immediately many times on 503 | Amplifies upstream outage | Use backoff+jitter, circuit breakers, and budgets |
| Setting only connect timeout | Server accepts connection then hangs while holding request | Add read/response timeouts + deadline |
| Treating `ReadTimeout` as total request duration | Continuous byte streams can drag on indefinitely | Enforce an appropriate total deadline |
| Recreating clients/pools per request | Connection churn and thread/resource leaks | Inject shared clients with managed lifecycles |
| Calling `block()` on the WebFlux event loop | Stalls the event loop and triggers Reactor errors | Compose reactively and return `Mono/Flux` |
| Logging full headers/bodies | Leaks tokens, PII, and bloats logs | Mask/limit and log only required metadata |
| Disabling TLS certificate validation | Loses server identity verification | Configure truststores/PKI properly |
| Testing only by mocking the fluent API chain | Misses broken URIs, timeouts, statuses, and serialization | Call a local stub HTTP server and assert contracts |
| Assuming HTTP client return means downstream finished business work | Ignores uncertain outcomes | Understand API semantics, confirmations, and idempotency |

## 14. Self-check questions and further practice

**Question 1.** A RestClient call to `/inventory` receives HTTP 503 after 20 ms. Is this a connect timeout?

**Answer:** No. An HTTP 503 response was received, so it is a status/protocol/service failure; a connect timeout happens before any response is received.

**Question 2.** A payment POST suffers a read timeout after the client sends JSON; can we retry immediately to ensure it doesn't fail?

**Answer:** No. The server may have already charged successfully and only the response was lost. Use an upstream-supported idempotency key or an inquiry/reconciliation mechanism.

**Question 3.** Why do we still need a total deadline when connect timeout and read timeout are already set?

**Answer:** They bound individual stages or I/O operations, not total end-to-end duration—especially with pool waits, DNS, TLS, retries, and streaming.

**Question 4.** Should every upstream 404 become a public 404?

**Answer:** No. Understand the dependency's contract and what missing data means. Public 404 is only right when the resource promised by the public API truly does not exist.

**Question 5.** Has `WebClient.get().retrieve().bodyToMono(String.class)` sent the request yet?

**Answer:** It is a publisher; the request is normally triggered upon subscription. In a WebFlux controller, return the publisher to the runtime rather than calling `block()`.

**Question 6.** Does `Retry.backoff(2, ...)` mean two total attempts or two retries?

**Answer:** At most two **retries**—one initial attempt plus up to two retry attempts, subject to the filter/policy.

**Question 7.** Why is `ResourceAccessException` not enough by itself to conclude "Read timed out"?

**Answer:** It can also stem from DNS, connection refused, TLS, reset/EOF, and other I/O errors. Inspect the cause or engine error code to classify accurately.

**Question 8.** After enlarging the pool, latency stays high and upstream returns 429; what is the sensible fix?

**Answer:** Reduce concurrency, honor rate limits/`Retry-After`, optimize fan-out, and add bulkheads/circuit breakers. Simply enlarging the pool can overload upstream further.

**Exercise 1:** Replace `/inventory/slow` on the local server with an endpoint streaming text chunks spaced slightly under the read timeout; observe why read timeout does not bound the entire stream. Add a total timeout in an appropriate pipeline to compare.

**Exercise 2:** Add an endpoint returning 429 and `Retry-After: 1`; write a retry policy for GET only that never retries 404 and respects the deadline. Count attempts using logs with a correlation ID.

**Exercise 3:** Use `@RestControllerAdvice` to return a safe ProblemDetail when inventory times out. Distinguish an upstream 503 response from connection failure and decode error; add HTTP integration tests for each case.

## Official references

- [Spring Framework — REST Clients, RestClient](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html)
- [Spring Framework — WebClient Configuration/Timeouts](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html)
- [Spring Framework — WebClient Error Handling](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html)
- [Spring Framework 6.1 — SimpleClientHttpRequestFactory](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/http/client/SimpleClientHttpRequestFactory.html)
- [Spring Framework 6.1 — RestClient Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/client/RestClient.html)
- [Spring Boot — REST Clients](https://docs.spring.io/spring-boot/reference/io/rest-client.html)
- [Project Reactor — Error Handling](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html)
