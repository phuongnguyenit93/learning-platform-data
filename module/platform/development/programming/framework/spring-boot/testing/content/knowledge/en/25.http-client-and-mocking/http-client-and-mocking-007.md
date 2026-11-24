# Timeouts, Slow Responses, Disconnects, and Bounded Retries in HTTP Client Testing

A Spring Boot HTTP client may handle `200 OK` responses seamlessly yet fail severely when upstream is **slow**, **unresponsive**, **closes sockets**, or repeatedly returns `429/503`. A test that simply mocks a service's Java method to throw an exception **proves nothing** about timeout settings, network transport, actual outbound request counts, or the risk that the server already processed the request before the response was lost.

This lesson belongs to the **HTTP Client and Mocking** group and focuses on observing and testing four scenarios: **response delays**, **timeouts**, **disconnects**, and **bounded retries**. We distinguish HTTP status errors from I/O failures, pick the right mocking layer, design safe retries for GET vs. POST, verify `maxAttempts` limits, and manage backoff, deadlines, `Retry-After`, and idempotency. The runnable example uses **Java 17 + Spring Boot 3.5 + Spring Framework 6.2 + Spring Retry 2.0 + JUnit Jupiter** with `RestClient` and **JDK `HttpServer` on loopback**, requiring no Docker or internet access.

**Most critical takeaway:** a timeout or connection reset **does not prove upstream did not commit**. Never automatically replay payment or order-creation requests unless the API guarantees idempotency.

## 1. HTTP request lifecycle map

```text
HTTP CLIENT                                        HTTP SERVER
  |
  +---- DNS resolution -------> DNS resolver
  |      DNS failure / UnknownHost
  |
  +---- TCP connect ----------> listening port
  |      connect timeout / refused / route error
  |
  +---- TLS handshake -------> server (HTTPS)
  |      certificate / trust / handshake error
  |
  +---- HTTP request headers + body -------------->|
  |                                               +-- application processing
  |                                               +-- may have already committed DB
  |
  +<--- HTTP status + headers ---------------------| 200/400/429/503
  |
  +<--- HTTP response body ------------------------| may stall / cut off mid-stream
  |
  +---- Client decode / map response
```

| Symptom | What the client typically sees | Might the server have already processed it? | Test goal |
|---|---|---|---|
| Connect timeout | Cannot open TCP connection before deadline | Usually never reached that listener's HTTP handler | Connection dropped/route delayed; enforce connect timeout |
| Connection refused | Port closed or listener rejects | Usually no HTTP request reached that listener | Do not confuse with connect timeout |
| Slow response | Connection open; headers/body arrive late | May be processing or already committed | Short deadline fails, longer deadline passes |
| 503 | HTTP response `Service Unavailable` arrived | Might have partially processed | Retry GET exact count |
| 429 | HTTP response `Too Many Requests` arrived | API-dependent | Throttle/`Retry-After`/budget |
| 400/401/403/404 | HTTP response for request error | Business-dependent | Fail fast, never retry identical input |
| Disconnect before headers | EOF/reset/transport error | **Uncertain** | Propagate I/O exception, do not treat as 503 |
| Disconnect mid-body | Partial body/decoder exception | Often already processed | Never accept partial payload as success |
| Lost POST response | Timeout/EOF | **May have committed** | Idempotency/status lookup, never replay blindly |

In `RestClient.retrieve()`, HTTP 4xx/5xx responses default to `HttpClientErrorException` or `HttpServerErrorException`; I/O errors are normally wrapped by Spring in `ResourceAccessException`. The underlying `IOException` cause can vary across JDK `HttpClient`, Apache `HttpClient`, Reactor Netty, OS, and the exact moment the socket closed. Never assert literal messages such as `Connection reset by peer` across all tests.

## 2. Connect timeouts differ from response timeouts

### 2.1. Connect timeout

JDK 17 HTTP client example:

```java
HttpClient jdk = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(1))
        .version(HttpClient.Version.HTTP_1_1)
        .build();
```

This snippet requires `java.net.http.HttpClient` and `java.time.Duration`. Connect timeout applies when **establishing a new connection**, not as a deadline for total server processing time. If a connection pool reuses an existing socket, no new TCP connect happens per request.

Do not use an **unlistening localhost port** to prove connect timeout: the OS usually returns `Connection refused` instantaneously. Producing a reliable connect timeout requires Toxiproxy or controlled fault injection (dropped SYN, stalled proxy, network namespace); public or unroutable IPs may also fail immediately depending on CI networking.

### 2.2. Read/response/request timeout

Spring Framework 6.2 supports the JDK request factory:

```java
JdkClientHttpRequestFactory factory =
        new JdkClientHttpRequestFactory(jdk);
factory.setReadTimeout(Duration.ofMillis(150));
```

Javadocs tie `setReadTimeout(Duration)` to `java.net.http.HttpRequest.Builder.timeout(Duration)`. With the JDK backend, this is the HTTP request's **request timeout**—not identical to socket idle timeouts across every transport. Apache/Jetty/Reactor each define distinct connect, response, idle, and pool-acquire deadlines.

Response timeout tests should use a **real HTTP server that accepts the request and intentionally stalls**: e.g., the stub waits 900 ms while the client deadline is 150 ms. If a test merely Mockito-mocks a gateway method to throw `SocketTimeoutException`, you tested **business handling**, not that HTTP transport is configured for 150 ms.

**Never assert `elapsed == 150ms`.** CI schedulers, JVM warmup, CPU load, and connection setup shift wall-clock timings. The stronger assertion is that the client rejects a 200 response delayed past the deadline and throws a transport timeout instead.

### 2.3. Total request budget

Consider 3 attempts, max 800 ms each, backoff 100 ms / 200 ms:

```text
Worst-case for attempts + delays alone:
3 × 800ms + 100ms + 200ms = 2700ms
```

That excludes connection pool queuing, DNS, proxies, serialization, and other work. A 1-second business SLA can be breached even when every HTTP attempt obeys an 800 ms timeout. Production needs an **end-to-end deadline**, max attempts, max elapsed time, and a rule not to retry when insufficient budget remains.

## 3. MockRestServiceServer, WireMock, MockWebServer, or a real HTTP server?

| Tool | Crosses network socket? | What it proves |
|---|---|---|
| Mockito mock of gateway method | No | Service branches, simple error classification |
| `MockRestServiceServer` | Does not cross real TCP | Method/path/headers/body/status mapping with `RestClient`/`RestTemplate` |
| WireMock on dynamic port | **Yes** | HTTP faults, delays, resets, request journal |
| OkHttp `MockWebServer` | **Yes** | Queued replies, `SocketPolicy`, recorded requests |
| JDK `HttpServer` | **Yes** | Response statuses, delays, abrupt closes over HTTP loopback |
| Toxiproxy | Network proxy | Drops, latency, bandwidth caps, disconnects at network layer |
| Testcontainers | Real backend container | Realistic configuration, though slower startup |

Spring Framework docs emphasize that a mock web server listening over real HTTP is the right choice for subtle differences between underlying HTTP clients. `MockRestServiceServer` is great for HTTP request contracts, yet uses a fake request factory that **never checks TCP timeouts or TLS handshakes**.

The example below uses **JDK `HttpServer`**: it runs with just JDK 17 + Spring dependencies, binds port 0 to avoid conflicts, and supports scripted response queues, delays, and closes. For advanced faults such as truncated chunks, TLS, or half-open sockets, use WireMock/MockWebServer or a network fault proxy as needed.

## 4. Retries must classify statuses and request semantics

| Status / error | Typical policy | Caveats to check |
|---|---|---|
| 200/201/204 | Success, no retry | Validate response contract |
| 400/422 | Never retry identical input | Payload must be fixed |
| 401/403 | Never retry infinitely | Credential refresh follows separate policy |
| 404 | No retry by default | May retry only under explicit eventual-consistency contract |
| 408 | May retry **idempotent** operations | Outcome uncertain |
| 409 | Never retry blindly | CAS/optimistic conflict may require read-modify-write |
| 425 | Check replay safety | TLS early-data |
| 429 | Bounded retry + `Retry-After` | Quota may be exhausted |
| 500/502/503/504 | Often short retry on idempotent reads | Not all 5xx are transient |
| Connect/response timeout | Conditional retry | Never retry permanent TLS/DNS failures |
| Socket EOF/reset | Conditional retry | Upstream may have committed |
| JSON decode/schema error | Normally no retry | Contract mismatch |
| Payment/order POST | No retry by default | Retry only if server provides idempotency/dedup |

**Never write an unbounded `while (true) { retry(); }` loop for failing upstreams.** A retry policy requires max attempts, eligible failures, backoff, budget, operation safety, idempotency, and clear error reporting when exhausted.

### Attempts vs. retries

```text
maxAttempts = 3
  Attempt 1 --> 503
  Retry   1 --> Attempt 2 --> 503
  Retry   2 --> Attempt 3 --> 200
  STOP: success

If Attempt 3 is still 503 --> STOP: failure.
No Attempt 4.
```

Spring Retry `RetryTemplate.builder().maxAttempts(3)` means **3 total calls** (1 initial + 2 retries)—not "3 retries in addition to the initial call." Exhaustion tests script **503, 503, 503, 200**, then assert the fourth 200 response was never consumed.

### Exponential backoff and jitter

```java
RetryTemplate policy = RetryTemplate.builder()
        .maxAttempts(3)
        .exponentialBackoff(100L, 2.0, 1000L, true)
        .retryOn(HttpServerErrorException.class)
        .build();
```

This is a snippet requiring Spring Retry imports. Backoff prevents retry storms when many callers hit 503 simultaneously, while jitter spreads out retry timing. The runnable example below uses **`noBackoff()` strictly for JUnit speed** to verify attempt counts cleanly—not as a production recommendation.

## 5. Test matrix before writing code

| Scenario | Stub response | Evidence to assert |
|---|---|---|
| GET 200 | 200 | Correct body, exactly 1 request |
| Recovery | 503, 503, 200 | 3 requests, eventual success |
| Retry exhaustion | 503, 503, 503, 200 | Throws after 3; 4th response stays unconsumed |
| Client error | 400, 200 | 1 request, fail-fast |
| Not found | 404, 200 | 1 request, fail-fast |
| Rate limit | 429, 200 | 2 requests under demo policy |
| Slow within deadline | Delay 100 ms, deadline 2 s | 200 and 1 request |
| Slow past deadline | Delay 900 ms, deadline 150 ms | Transport exception, 200 never accepted |
| Disconnect before headers | Close exchange | `ResourceAccessException`, no HTTP status |
| Non-idempotent POST | 503, 200 | 1 request, **no automatic retry** |
| Server commits POST then response drops | State + disconnect | Unknown outcome; requires ID/status lookup |
| 429 `Retry-After` > deadline | Header + throttle | Never sleeps indefinitely / fails per policy |

Do not rigidly assert `socketRequests == retryAttempts` in disconnect cases: some HTTP clients (including JDK `HttpClient`) perform **transparent transport-layer retries** on certain connection failures. Separate wire-level HTTP transmissions, `RetryTemplate` application attempts, and server-side business side effects.

## 6. Complete Java 17 + Spring Boot 3.5 + JUnit Jupiter example

The example builds `PartnerClient` with Spring `RestClient`:
- `GET /rate` uses `RetryTemplate` with max 3 attempts on 5xx/429/network I/O.
- `POST /orders` **uses no retry** because no idempotency contract is established.
- The client uses JDK `HttpClient` with a connect timeout and JDK request factory with a request deadline.
- Tests run a local JDK HTTP server on a dynamic port with a response queue and request counter.
- Tests are completely offline; `@AfterEach` shuts down both server and executor.

### 6.1. Structure

```text
http-client-fault-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/http/
    │   ├── HttpDemoApplication.java
    │   └── PartnerClient.java
    └── test/java/com/example/http/
        └── PartnerClientTest.java
```

### 6.2. Maven POM

File **`pom.xml`**:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>http-client-fault-demo</artifactId>
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
            <groupId>org.springframework.retry</groupId>
            <artifactId>spring-retry</artifactId>
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

The Spring Boot 3.5.0 BOM manages Spring Framework 6.2.x and Spring Retry 2.0.x. JDK `com.sun.net.httpserver.HttpServer` ships with Java 17 and works on the standard Maven classpath. If running with a custom module-path, ensure the `jdk.httpserver` module is resolved.

### 6.3. Spring Boot application class

File **`src/main/java/com/example/http/HttpDemoApplication.java`**:

```java
package com.example.http;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HttpDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(HttpDemoApplication.class, args);
    }
}
```

Tests do not need to boot an application context because the target is HTTP client behavior; constructing `PartnerClient` directly keeps URL, timeouts, and retry counts explicit per test. In a real app, register the client as a `@Bean` with `@ConfigurationProperties` and inject Boot's `RestClient.Builder` to inherit SSL/observability settings.

### 6.4. Defining PartnerClient

File **`src/main/java/com/example/http/PartnerClient.java`**:

```java
package com.example.http;

import java.net.http.HttpClient;
import java.time.Duration;

import org.springframework.http.MediaType;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.retry.support.RetryTemplate;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.HttpServerErrorException;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;

public final class PartnerClient {

    private final RestClient rest;
    private final RetryTemplate retry;

    public PartnerClient(
            String baseUrl,
            Duration connectTimeout,
            Duration requestTimeout,
            int maxAttempts) {

        HttpClient jdk = HttpClient.newBuilder()
                .connectTimeout(connectTimeout)
                .version(HttpClient.Version.HTTP_1_1)
                .build();

        JdkClientHttpRequestFactory factory =
                new JdkClientHttpRequestFactory(jdk);
        factory.setReadTimeout(requestTimeout);

        this.rest = RestClient.builder()
                .baseUrl(baseUrl)
                .requestFactory(factory)
                .build();

        // noBackoff is only so JUnit does not wait; production
        // requires bounded exponential backoff/jitter/Retry-After.
        this.retry = RetryTemplate.builder()
                .maxAttempts(maxAttempts)
                .noBackoff()
                .retryOn(error ->
                        error instanceof ResourceAccessException
                        || error instanceof HttpServerErrorException
                        || (error instanceof HttpClientErrorException ex
                                && ex.getStatusCode().value() == 429))
                .build();
    }

    public String getRate() {
        return retry.execute(context ->
                rest.get()
                        .uri("/rate")
                        .retrieve()
                        .body(String.class));
    }

    // Do not retry POST without an idempotency contract.
    public String createOrderWithoutRetry(String payload) {
        return rest.post()
                .uri("/orders")
                .contentType(MediaType.TEXT_PLAIN)
                .body(payload)
                .retrieve()
                .body(String.class);
    }
}
```

`RetryTemplate` is invoked explicitly here without requiring AOP/`@EnableRetry`. If you replace it with `@Retryable`, test **through the Spring AOP proxy bean**, because self-invocation bypasses advice. The predicate above applies only to GET: 5xx, 429, and `ResourceAccessException`. Production code must inspect root causes: permanent TLS/DNS errors must not be retried, and even GET can be unsafe if an upstream API violates HTTP semantics.

### 6.5. Real HTTP stub and 10 JUnit tests

File **`src/test/java/com/example/http/PartnerClientTest.java`**:

```java
package com.example.http;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.HttpServerErrorException;
import org.springframework.web.client.ResourceAccessException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class PartnerClientTest {

    private HttpServer server;
    private ExecutorService executor;
    private final Queue<Reply> replies = new ConcurrentLinkedQueue<>();
    private final AtomicInteger received = new AtomicInteger();
    private volatile boolean disconnectEveryRequest;

    private record Reply(int status, String body, long delayMillis) {
        static Reply status(int status, String body) {
            return new Reply(status, body, 0);
        }
        static Reply slow(long millis, String body) {
            return new Reply(200, body, millis);
        }
    }

    @BeforeEach
    void startStub() throws IOException {
        executor = Executors.newFixedThreadPool(4, task -> {
            Thread t = new Thread(task, "http-stub");
            t.setDaemon(true);
            return t;
        });
        server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/rate", this::respond);
        server.createContext("/orders", this::respond);
        server.setExecutor(executor);
        server.start();
    }

    @AfterEach
    void stopStub() {
        if (server != null) {
            server.stop(0);
        }
        if (executor != null) {
            executor.shutdownNow();
        }
    }

    private void respond(HttpExchange exchange) throws IOException {
        received.incrementAndGet();

        try {
            if (disconnectEveryRequest) {
                // Close before sending HTTP response headers.
                exchange.close();
                return;
            }

            Reply next = replies.poll();
            if (next == null) {
                next = Reply.status(503, "NO_STUB_RESPONSE");
            }

            if (next.delayMillis() > 0) {
                Thread.sleep(next.delayMillis());
            }

            byte[] bytes =
                    next.body().getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders()
                    .set("Content-Type", "text/plain; charset=utf-8");
            exchange.sendResponseHeaders(next.status(), bytes.length);

            try (OutputStream out = exchange.getResponseBody()) {
                out.write(bytes);
            }
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            exchange.close();
        } catch (IOException clientClosed) {
            // When the client times out before the response is written,
            // a broken pipe on the fake server is the expected fault.
            exchange.close();
        }
    }

    private void queue(Reply... values) {
        for (Reply reply : values) {
            replies.add(reply);
        }
    }

    private PartnerClient client(long deadlineMs, int attempts) {
        String base = "http://127.0.0.1:"
                + server.getAddress().getPort();
        return new PartnerClient(
                base,
                Duration.ofSeconds(1),
                Duration.ofMillis(deadlineMs),
                attempts);
    }

    @Test
    void successUsesOneRequest() {
        queue(Reply.status(200, "RATE-OK"));

        assertEquals("RATE-OK", client(2000, 3).getRate());
        assertEquals(1, received.get());
    }

    @Test
    void retry503TwiceThenSucceed() {
        queue(
                Reply.status(503, "busy1"),
                Reply.status(503, "busy2"),
                Reply.status(200, "RATE-READY"));

        assertEquals("RATE-READY", client(2000, 3).getRate());
        assertEquals(3, received.get());
    }

    @Test
    void retryLimitIsThreeNotFour() {
        queue(
                Reply.status(503, "busy1"),
                Reply.status(503, "busy2"),
                Reply.status(503, "busy3"),
                Reply.status(200, "SHOULD_NOT_RUN"));

        assertThrows(
                HttpServerErrorException.class,
                () -> client(2000, 3).getRate());

        assertEquals(3, received.get());
        assertEquals(1, replies.size());
    }

    @Test
    void status400FailsFast() {
        queue(
                Reply.status(400, "bad request"),
                Reply.status(200, "SHOULD_NOT_RUN"));

        assertThrows(
                HttpClientErrorException.BadRequest.class,
                () -> client(2000, 3).getRate());

        assertEquals(1, received.get());
    }

    @Test
    void status404FailsFast() {
        queue(
                Reply.status(404, "missing"),
                Reply.status(200, "SHOULD_NOT_RUN"));

        assertThrows(
                HttpClientErrorException.NotFound.class,
                () -> client(2000, 3).getRate());

        assertEquals(1, received.get());
    }

    @Test
    void status429Then200RetriesInDemo() {
        queue(
                Reply.status(429, "rate limited"),
                Reply.status(200, "RATE-OK"));

        assertEquals("RATE-OK", client(2000, 3).getRate());
        assertEquals(2, received.get());
    }

    @Test
    void slowButWithinDeadlineWorks() {
        queue(Reply.slow(100, "SLOW-OK"));

        assertEquals("SLOW-OK", client(2000, 1).getRate());
        assertEquals(1, received.get());
    }

    @Test
    void slowBeyondDeadlineFails() {
        queue(Reply.slow(900, "TOO-LATE"));

        assertThrows(
                ResourceAccessException.class,
                () -> client(150, 1).getRate());
        assertTrue(received.get() >= 1);
        // Never assert elapsed == 150ms on CI.
    }

    @Test
    void disconnectBeforeHeadersIsTransportFailure() {
        disconnectEveryRequest = true;

        assertThrows(
                ResourceAccessException.class,
                () -> client(2000, 1).getRate());
        assertTrue(received.get() >= 1);
        // The JDK client may retry at the wire layer below RetryTemplate.
    }

    @Test
    void unsafePostDoesNotRetry503() {
        queue(
                Reply.status(503, "busy"),
                Reply.status(200, "ORDER-CREATED"));

        assertThrows(
                HttpServerErrorException.class,
                () -> client(2000, 3)
                        .createOrderWithoutRetry("PAYMENT-REQUEST"));

        assertEquals(1, received.get());
        assertEquals(1, replies.size());
    }
}
```

### 6.6. Analyzing the evidence from each test case

| Test | Evidence |
|---|---|
| `successUsesOneRequest` | 200 and right body; 1 request |
| `retry503TwiceThenSucceed` | 503, 503, 200 retried and eventually succeeded |
| `retryLimitIsThreeNotFour` | 3 attempts; 4th 200 response unconsumed |
| `status400FailsFast` | 400 does not retry the same input |
| `status404FailsFast` | 404 does not retry by default |
| `status429Then200RetriesInDemo` | 429 retries in demo policy (`Retry-After` not yet tested) |
| `slowButWithinDeadlineWorks` | Slower than usual yet succeeds within deadline |
| `slowBeyondDeadlineFails` | Request timeout surfaces as transport exception; late 200 rejected |
| `disconnectBeforeHeadersIsTransportFailure` | Socket closes before headers -> no HTTP status; app sees failure |
| `unsafePostDoesNotRetry503` | POST never fires a second time despite queued 200 |

For **HTTP statuses** 503/429, the counter measures exact network requests reaching the stub. For **disconnects**, JDK `HttpClient` can perform **transparent retries** on certain I/O/connection errors, so the test avoids asserting strictly 1 wire request even with `RetryTemplate.maxAttempts=1`. To prove business side-effect counts, measure on the server alongside application attempt counts.

Every test binds the server to `127.0.0.1` on OS-assigned port **0**, preventing port 8080 conflicts. `@AfterEach` shuts down the server and executor; handlers may be interrupted when clients time out. No internet calls occur and no third-party accounts are needed.

### 6.7. Run commands

Requires Java 17+, Maven, and permission to bind loopback HTTP:

```bash
mvn test
mvn -Dtest=PartnerClientTest test
```

With Maven Wrapper: `./mvnw test` or `mvnw.cmd test` on Windows. Expected: **10 JUnit tests**, with negative cases PASSING when `assertThrows` matches. There is no fixed business stdout; Maven Surefire/HTTP client logs vary by environment.

The example code was reviewed against Spring Boot 3.5 / Spring Framework 6.2 / Spring Retry 2.0, **not a claim that Maven ran while authoring this guide**. When adopting in practice, execute in CI with the exact JDK and HTTP transport used in production. If local runners use a custom module-path, ensure `jdk.httpserver` is resolved.

## 7. Retry-After, jitter, and overall deadlines

Rate-limit responses can include:

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 3
Content-Type: text/plain

rate limited
```

`Retry-After` may be integer seconds or an HTTP-date. Production clients must parse it safely, clamp its value, check **remaining business deadline**, and skip retries once budget is exhausted. If a caller has only 500 ms left and the server says wait 3 s, waiting 3 s violates the SLA. Add tests for invalid headers, huge values, past HTTP-dates, repeated 429s, concurrent callers, and exhausted rate-limit quotas.

**The demo uses `noBackoff()` and ignores `Retry-After`.** That keeps classifier/attempt tests fast; it is not a production retry policy. In production, use bounded exponential backoff + jitter, max elapsed time, and circuit breakers/bulkheads/rate limiters.

If service A retries 3 times into B and B retries 3 times into C, one user request can amplify into 9 calls to C. Never stack retries blindly across HTTP clients, services, gateways, and reactive operators. An end-to-end deadline and system-wide retry budget prevent retry storms.

## 8. Lost POST response: idempotency and unknown outcomes

Consider this timeline:

```text
Client                               Payment server
  |
  +--- POST /charges ----------------->|
  |                                   +-- COMMIT charge A
  X response connection closed       |
  |                                   |
  +--- RETRY POST (dangerous) ------->|
                                      +-- may COMMIT charge B
```

A client timeout does not mean charge A never happened. When an API supports **`Idempotency-Key`**, the client sends the exact same key across attempts:

```http
POST /charges HTTP/1.1
Idempotency-Key: order-9e4a
Content-Type: application/json

{"amountMinor":150000,"currency":"VND"}
```

This is an illustrative payload. The server must implement **real deduplication**, store the outcome/operation ID transactionally, and define policies for matching keys with differing payloads, key TTL, and concurrent requests sharing a key. Simply attaching a header does not create idempotency by itself.

### How to test a POST that committed before losing its response

1. The stub receives POST with key `K`.
2. The stub records state `charge[K] = done` and intentionally closes the socket before writing the response.
3. The client reports an unknown outcome rather than replaying automatically unless the contract permits it.
4. The client queries `GET /operations/K` or retries **with the same `K`** per the official API.
5. Assert the final charge count equals **1**, not merely Mockito's call-count verification.
6. Test duplicate keys, concurrent requests, and payload-mismatch policies.

The stub in section 6 only tests **disconnect before headers**—not backend payment deduplication. Never conclude from a passing disconnect test that charges cannot double-post. That belongs in a **dedicated stateful upstream/idempotency test**.

## 9. WebClient and @RestClientTest: different layers, different timeouts

### Reactive WebClient

```java
Mono<String> result = webClient.get()
        .uri("/rate")
        .retrieve()
        .bodyToMono(String.class)
        .timeout(Duration.ofSeconds(2))
        .retryWhen(Retry.backoff(2, Duration.ofMillis(100))
                .filter(error ->
                        error instanceof WebClientResponseException.ServiceUnavailable
                        || error instanceof java.util.concurrent.TimeoutException));
```

This is a snippet, not a standalone Java file: it requires WebFlux/Reactor dependencies and a configured `webClient`. `Retry.backoff(2, ...)` means 2 **retries** after the initial attempt, totaling 3 subscriptions. Placing `.timeout()` before `.retryWhen()` caps each attempt; placing it after caps the whole pipeline. To test pure Reactor backoff logic, use `StepVerifier.withVirtualTime`, keeping in mind virtual time **does not control real TCP sockets**.

### @RestClientTest and MockRestServiceServer

`@RestClientTest` creates a client slice and `MockRestServiceServer` to verify method/path/headers/status/JSON mapping without opening sockets. It **does not verify HTTP transport timeouts** unless a test actually runs an external mock web server listener. With `RestClient.retrieve()`, the default 4xx/5xx status handler throws an exception; if you switch to `exchange((req, res) -> ...)`, `retrieve()`'s status handlers **do not run**, so you must check statuses manually. If forgotten, a 503 can be treated as success and `RetryTemplate` will never trigger.

When production uses Apache HttpClient, Jetty, JDK HttpClient, or Reactor Netty, run **network fault tests using the exact same factory**. Swapping dependencies can change the HTTP client Spring Boot auto-selects, altering timeout/reset semantics. Fake method mocks never catch that.

## 10. Diagnosing flaky tests and retry misconfigurations

| Symptom | Common cause | Fix |
|---|---|---|
| Timeout passes locally, fails on CI | Delay too close to deadline, CPU contention | Widen the margin and never assert exact milliseconds |
| Disconnect test sees > 1 wire request | Underlying JDK auto-retries connection errors | Separate app attempts from wire count |
| 503 retries 4 times despite max 3 | Off-by-one or nested retries | Queue 503, 503, 503, 200 and assert last reply remains |
| 401/400 retried repeatedly | Retrying all `RestClientException`s | Narrow predicate; fail fast on permanent 4xx |
| 429 retries immediately causing storm | Missing backoff/`Retry-After` | Rate limit, budget, bounded jitter |
| Client times out while order exists upstream | Response lost after COMMIT | Idempotency key + status reconciliation |
| `MockRestServiceServer` passes, socket test fails | Mock skips the network | Use loopback WireMock/`HttpServer`/MockWebServer |
| Test tries binding port 8080 | Port already in use | Bind port 0 and query actual port |
| Closed port labeled as connect timeout | `Connection refused` returns immediately | Use network drop/proxy fault injection |
| Simply raising timeout when server returns 503 | 503 is an HTTP status, not a duration | Check overload and retry classifier |
| Payment POST sent twice | Non-idempotent retry | Never replay without a dedup contract |
| One test breaks the following suite | Stub/executor never stopped | Clean up in `@AfterEach` |
| Changing HTTP library changes test exception | Different root cause/wrapping | Assert contract abstraction/cause, avoid brittle messages |
| Multiple service hops all retry | Request amplification | Define clear retry boundaries and total deadlines |

In production, logs/metrics should capture operation name, upstream alias, response status, error type, application attempt number, total duration, backoff decision, trace/correlation ID, and rate-limit signals. Never log `Authorization`, cookies, API keys, payment payloads, or PII. If the HTTP client logs raw headers at `DEBUG`/`TRACE`, apply redaction and limit CI artifact retention.

## 11. Pre-completion checklist

- [ ] Distinguished connect timeout, request timeout, response delay, and total deadline.
- [ ] Do not mistake connection refused for connect timeout.
- [ ] Network fault tests run through sockets/proxies when needed, not solely Mockito.
- [ ] Stub delays differ clearly from deadlines; no exact elapsed-time assertions.
- [ ] Includes tests for success and recovery from transient failures.
- [ ] Includes retry-cap tests confirming the fourth response **is never consumed** when `maxAttempts=3`.
- [ ] 400/404 fail fast and 429/5xx are classified per policy.
- [ ] Counts **total attempts** properly rather than extra retries.
- [ ] Production applies backoff + jitter, `Retry-After` where needed, and max elapsed time/deadline.
- [ ] GET/POST retry decisions reflect **real side-effect semantics**.
- [ ] Payment/order POSTs never retry blindly on unknown outcomes.
- [ ] When retrying POST, the real server enforces idempotency keys/dedup/status lookup.
- [ ] Does not equate application retries with wire requests when transport auto-retries.
- [ ] For `WebClient`, `timeout`/`retryWhen` placement matches the intended deadline.
- [ ] `MockRestServiceServer` covers client contracts; socket tests use a real listener.
- [ ] Stubs bind dynamic ports and shut down servers/threads after tests.
- [ ] Never calls production APIs from the suite; secrets stay out of logs.
- [ ] Tests run in CI with the real underlying HTTP library.
- [ ] States limits accurately: timeout/disconnect tests do not prove upstream rollback.

**Conclusion:** HTTP client testing must deliver clear evidence for **slow responses inside/outside deadlines, transport disconnects, HTTP statuses, and maximum attempt caps**. Retries must be bounded and restricted to safely replayable operations; a lost POST response is an **unknown outcome**, never a license to replay unconditionally.

### Official documentation

- [Spring Framework — Testing Client Applications](https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-client.html)
- [Spring Framework 6.2 — REST Clients](https://docs.spring.io/spring-framework/reference/6.2/integration/rest-clients.html)
- [JdkClientHttpRequestFactory 6.2 — Javadoc](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/http/client/JdkClientHttpRequestFactory.html)
- [Spring Retry — RetryTemplateBuilder API](https://docs.spring.io/spring-retry/docs/2.0.x/apidocs/spring.retry/org/springframework/retry/support/RetryTemplateBuilder.html)
- [Spring Boot 3.5 — Calling REST Services](https://docs.spring.io/spring-boot/3.5/reference/io/rest-client.html)
- [JDK 17 — HttpServer/HttpExchange](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html)
- [Reactor — Error Handling and Retry](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html)
