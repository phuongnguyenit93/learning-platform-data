# Timeouts and Retryer in Spring Cloud OpenFeign: Verifying Actual Default Behavior

## Objectives

When calling a service via OpenFeign, the important question is not only "what timeout should I set?", but also **is a failed call retried, who retries it, and which instance receives the retry?** Two applications sharing the exact same `@FeignClient` interface can still behave differently due to the Feign version, Spring Cloud OpenFeign configuration, selected HTTP client, and Spring Cloud LoadBalancer.

After this lesson, you will be able to:

- Distinguish `connectTimeout` and `readTimeout` from the overall time limit of a request.
- Explain the difference between `Retryer.Default` in **core Feign** and `Retryer.NEVER_RETRY` provided by **Spring Cloud OpenFeign** by default.
- Verify for yourself the actual number of requests reaching a server with a timeout test, instead of guessing from dependency names or client logs.
- Configure retries intentionally and recognize that Feign retries differ from Spring Cloud LoadBalancer retries.
- Choose policies for read vs. write operations to prevent duplicating side effects when connections fail.

**Context:** The `SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING` module focuses on inter-service communication using `service ID`, discovery, `ServiceInstance` selection, health checks, and client-side routing. OpenFeign is one of the HTTP clients that can participate in this flow. This lesson dives into timeouts and retries because they directly impact resilience, latency, and instance re-selection when failures happen.

## 1. Where Do Timeouts and Retries Sit in the Request Path?

```mermaid
sequenceDiagram
    participant App as Calling service
    participant Feign as OpenFeign
    participant LB as Spring Cloud LoadBalancer
    participant Target as ServiceInstance
    App->>Feign: Call interface method
    Note over Feign: Request.Options: connect/read timeout<br/>Retryer: handles RetryableException
    Feign->>LB: HTTP request by service ID (when using discovery)
    Note over LB: Picks instance; may have<br/>its own retry policy
    LB->>Target: Send HTTP request
    Target-->>LB: Response or error
    LB-->>Feign: Final result from LB layer
    Feign-->>App: Return value or exception
```

`connectTimeout` is the time spent waiting to establish a connection to the target. `readTimeout` is usually the time limit for waiting to read data from an established connection. Exact measurement depends on the underlying HTTP client (JDK, Apache HttpClient 5, or OkHttp if configured) and the type of network operation.

Some commonly misunderstood limits:

| Mechanism | What Does It Control? | What Does It Not Guarantee? |
| --- | --- | --- |
| `connectTimeout` | Waiting to open a TCP connection to the endpoint | Not a timeout for the entire call; DNS, pool acquisition, and TLS may have separate rules |
| `readTimeout` | Waiting to read data on the connection after sending the request | Not necessarily total response download time, especially for multi-chunk responses |
| Feign `Retryer` | Decides whether to retry when Feign receives `RetryableException` | Does not automatically retry every HTTP 4xx/5xx status |
| Spring Cloud LoadBalancer retry | May retry the HTTP operation and/or switch `ServiceInstance` depending on client, classpath, and config | Cannot be inferred solely from Feign's `Retryer` bean |
| Circuit breaker / time limiter | May bound or short-circuit calls at another layer when integrated | Does not replace defining timeouts and actual send counts |

For example, a method taking 2 seconds can exceed `readTimeout=500ms`; with 3 attempts, total latency can be far longer than 500 ms. **A per-attempt timeout is not a deadline for the entire business operation.**

## 2. Default Behavior: Distinguishing Core Feign from Spring Cloud OpenFeign

This is the easiest place to draw wrong conclusions:

1. **Core Feign** has a default `Retryer.Default`: it can retry upon receiving errors represented as `RetryableException`, such as certain transient I/O errors or errors marked retryable by `ErrorDecoder`.
2. **Spring Cloud OpenFeign** provides `Retryer.NEVER_RETRY` by default for its Feign clients. This policy **does not retry at the Feign layer** when encountering `RetryableException`. This is an intentional difference from core Feign.
3. Per-client configuration, custom `Retryer` beans, HTTP transport settings, or a retry mechanism at another layer can alter the final outcome.

Do not memorize a blanket rule like "on HTTP 500, Feign calls 3 times". With the default `ErrorDecoder`, **a regular 500/503 is not necessarily a `RetryableException`**. A `Retry-After` header or custom `ErrorDecoder` can change how errors are classified. Even when classified as retryable, `Retryer.NEVER_RETRY` still blocks retries at **the Feign layer**.

In addition, documentation or examples for standalone `feign-core` cannot serve as proof of defaults in a Spring Cloud application. Nor should you treat one library version's timeout numbers as a guarantee for all versions: **read your active configuration and verify against your project's actual dependencies and HTTP client**. Popular Feign versions default `Request.Options` to roughly 10 seconds for connect and 60 seconds for read, yet an application may have overridden them or chosen a different transport.

## 3. Configuring Timeouts for a Feign Client

Suppose `order-service` calls `stock-service` to read stock. Basic interface:

```java
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;

@FeignClient(name = "stock-service")
public interface StockClient {
    @GetMapping("/stocks/{sku}")
    StockResponse getStock(@PathVariable("sku") String sku);
}

public record StockResponse(String sku, int available) {}
```

When Spring Cloud LoadBalancer and a corresponding service discovery mechanism are present, `stock-service` is used to discover/select instances. An illustrative configuration in `application.yml`:

```yaml
spring:
  cloud:
    openfeign:
      client:
        config:
          stock-service:
            connectTimeout: 500
            readTimeout: 1500
            loggerLevel: BASIC
```

`connectTimeout` and `readTimeout` here are in **milliseconds**. These are **explicitly configured** values, not guessed defaults. In practice, choose them based on observed latency, SLOs, network conditions, allowed attempts, and upstream request time limits.

You can set shared defaults under `spring.cloud.openfeign.client.config.default` and override by client name. Properties configuration can take precedence over Java configuration depending on the mechanism and Spring Cloud OpenFeign version; in supported versions, `spring.cloud.openfeign.client.default-to-properties` affects precedence. Inspect effective values rather than looking at a single `@Bean`.

To test Feign behavior in isolation, you can supply a direct URL:

```java
@FeignClient(name = "stock-service", url = "${stock.service.url}")
public interface StockClient {
    @GetMapping("/stocks/{sku}")
    String getStock(@PathVariable("sku") String sku);
}
```

With a fixed `url`, calls go straight to that URL: this test helps isolate Feign's retries from LoadBalancer instance selection. In a discovery-backed environment, omit `url` to use `service ID` and test the LoadBalancer layer as well.

## 4. Verify Defaults Yourself Instead of Guessing: Testing a Slow Request

### Hypothesis to Test

With Spring Cloud OpenFeign and no custom `Retryer` configured, if an endpoint holds the connection open and responds slower than `readTimeout`, then:

- The caller receives an exception related to read timeout.
- The server **receives only one HTTP request** sent by Feign; there is no default Feign retry.
- When changing retry policy, the request count may rise. If retries are enabled in LoadBalancer or a gateway, account for those layers separately.

### Integration Test Example Using the JDK's HTTP Server

The example below uses JUnit 5 and `@SpringBootTest`; it requires `spring-cloud-starter-openfeign` along with Spring Boot test dependencies. The HTTP stub uses the JDK's `com.sun.net.httpserver.HttpServer`, avoiding the need to install WireMock. Place the class in `src/test/java` of your Spring Boot application and ensure compatible Spring Boot/Spring Cloud versions.

```java
import com.sun.net.httpserver.HttpServer;
import feign.RetryableException;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.openfeign.EnableFeignClients;
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest(
    classes = TimeoutRetryBehaviorTest.TestApp.class,
    properties = {
        "spring.cloud.openfeign.client.config.stock-service.connectTimeout=300",
        "spring.cloud.openfeign.client.config.stock-service.readTimeout=200",
        "spring.cloud.loadbalancer.retry.enabled=false"
    }
)
class TimeoutRetryBehaviorTest {
    private static final AtomicInteger REQUESTS = new AtomicInteger();
    private static final HttpServer STUB = startStub();

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @EnableFeignClients(clients = StockClient.class)
    static class TestApp {}

    @FeignClient(name = "stock-service", url = "${stock.service.url}")
    public interface StockClient {
        @GetMapping("/stocks/{sku}")
        String getStock(@PathVariable("sku") String sku);
    }

    @Autowired
    StockClient client;

    @DynamicPropertySource
    static void setProperties(DynamicPropertyRegistry properties) {
        properties.add("stock.service.url",
            () -> "http://127.0.0.1:" + STUB.getAddress().getPort());
    }

    @Test
    void timeoutDoesNotCauseFeignRetryByDefault() {
        assertThrows(RetryableException.class,
            () -> client.getStock("SKU-1"));
        assertEquals(1, REQUESTS.get(),
            "Default OpenFeign Retryer must not resend the request");
    }

    @AfterAll
    static void stopStub() {
        STUB.stop(0);
    }

    private static HttpServer startStub() {
        try {
            HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
            server.createContext("/stocks", exchange -> {
                REQUESTS.incrementAndGet();
                try {
                    Thread.sleep(800); // Slower than readTimeout=200ms
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                }
                byte[] body = "ok".getBytes(StandardCharsets.UTF_8);
                try {
                    exchange.sendResponseHeaders(200, body.length);
                    try (var stream = exchange.getResponseBody()) {
                        stream.write(body);
                    }
                } catch (IOException clientDisconnected) {
                    // Client may close the connection after timeout.
                } finally {
                    exchange.close();
                }
            });
            server.start();
            return server;
        } catch (IOException error) {
            throw new IllegalStateException("Cannot start local HTTP stub", error);
        }
    }
}
```

**Reading the result:** `readTimeout=200ms`, while the HTTP stub only begins sending its response after 800ms. In this isolated setup, Feign throws an I/O-related `RetryableException` and the `REQUESTS` counter must equal `1`. If your project uses a custom HTTP client, inspect the actual exception type before fixing class-level assertions; what matters here is **the number of requests that reached the server**.

When switching to `readTimeout=1200`, the server replies in time and the caller receives `"ok"`; that acts as a control check so you do not mistake a broken URL, annotation, or stub for a timeout.

Do not use an "unreachable" IP address to definitively prove `connectTimeout`: the OS may return `connection refused` immediately, DNS may fail before connecting, or firewalls may respond differently. To measure connect timeout accurately, use packet-blocking/network-shaping tools built for that purpose and measure elapsed wall time.

## 5. Explicitly Enabling Retryer and Re-Testing

When business requirements permit retries, configure a `Retryer` **specifically** for the Feign client:

```java
import feign.Retryer;
import org.springframework.context.annotation.Bean;

public class StockFeignRetryConfig {
    @Bean
    public Retryer stockRetryer() {
        // period=100ms, maxPeriod=300ms, maxAttempts=3 (including initial attempt)
        return new Retryer.Default(100, 300, 3);
    }
}
```

```java
@FeignClient(
    name = "stock-service",
    url = "${stock.service.url}",
    configuration = StockFeignRetryConfig.class
)
public interface StockClient {
    @GetMapping("/stocks/{sku}")
    String getStock(@PathVariable("sku") String sku);
}
```

`Retryer.Default(100, 300, 3)` allows at most **3 total attempts**, not "1 initial call + 3 retries". It triggers only when Feign actually receives a `RetryableException`; it does not mean every `500` response is resent.

Re-run the test in Section 4 with the new configuration: transient timeout failures can generate up to 3 hits on the server (plus cumulative wait time). Because the original test asserted exactly `1` request, update the assertion for the retry test case, reset the counter/server per case, and verify the final response too. Prevent `StockFeignRetryConfig` from being scanned as global configuration if you only want it applied to `stock-service`: place it outside regular component scan scope and reference it via `@FeignClient(configuration = ...)`.

You can also implement a custom `Retryer` to control backoff intervals, attempt counts, and error types. When doing so, make sure `clone()` instances of the retryer do not share attempt counters across independent requests.

## 6. Distinguishing Feign Retry from LoadBalancer Retry

In a `@FeignClient(name = "stock-service")` flow **without a fixed `url`**, Spring Cloud LoadBalancer can pick a `ServiceInstance` from discovery. When the corresponding retry dependencies and features are enabled, the LoadBalancer layer can retry against the same or another instance. Whether retries happen at this layer depends on **version, classpath, client type (blocking/reactive), and configuration**, so it cannot be deduced from `Retryer.NEVER_RETRY` alone.

Illustrative configuration when intentionally **disabling LoadBalancer retries during testing**:

```yaml
spring:
  cloud:
    loadbalancer:
      retry:
        enabled: false
```

When measuring in a real system:

1. Determine whether the client has a static `url` or calls via `service ID`; a static URL isolates Feign.
2. Check HTTP transport, Spring Cloud LoadBalancer, Spring Retry, and related configurations on the classpath.
3. Attach request IDs/correlation IDs, log attempt counts and instance names on the server, or use properly tagged metrics/tracing.
4. Test **Feign retry** and **LoadBalancer retry** separately, then test the whole system with both policies enabled.

If Feign attempts 3 times and an underlying layer retries multiple times per attempt, potential requests can **multiply**, sharply inflating timeouts and downstream load. Layers such as API gateways, service meshes, and reverse proxies must also be factored in.

## 7. Scenario Matrix to Observe

In the table, "default OpenFeign" assumes **no custom Retryer, no LoadBalancer/proxy retries, and calling via a static URL**.

| Server / Network Scenario | Expected Outcome with Default OpenFeign | What to Measure or Verify |
| --- | --- | --- |
| HTTP 200 before `readTimeout` | Success, 1 request | Response and server-side counter |
| Server holds connection, replies after `readTimeout` | Timeout exception, 1 request | Counter and client wait duration |
| Cannot connect to endpoint | Connection exception, no Feign-layer retry | Error logs; server request count may be 0 |
| Normal HTTP 500/503 | Throws HTTP exception, does not retry all 5xx by default | HTTP code, `ErrorDecoder`, and counter |
| `RetryableException` from I/O or `ErrorDecoder` | `NEVER_RETRY` fails immediately | Exception type and attempt count |
| Configured `Retryer.Default(..., 3)`; each attempt hits retryable error | Can attempt up to 3 times | Count attempts and backoff intervals |
| LoadBalancer retry enabled with discovery | Extra sends may occur outside Feign's layer | Count by service ID and instance |

Note: a `readTimeout` test does not verify handling for **every** HTTP error. For a 503 with `Retry-After`, `ErrorDecoder` or the transport can behave differently from a plain 503; test your application's specific conditions.

## 8. Aligning Retries with Business Semantics

Retries help survive transient failures, yet can re-send **an operation the server already processed**. A client timeout only proves **the client did not receive a result in time**; it does not assert the server never persisted data.

- **Read GET queries** generally suit bounded retries better, if downstream load and deadlines permit.
- **Write POSTs (orders, payments, balance updates)** require duplicate prevention such as `Idempotency-Key`, business locks, or transaction-status checks before retrying.
- **429/503** should only retry under an agreed policy with backoff/jitter and respect `Retry-After` where appropriate.
- **400/401/403/404** are rarely solved by retrying identically; address the root cause, permissions, or input data.
- **Persistent recoverable errors** still need bounded attempts, overall deadlines, load observation, and potentially circuit breakers.

A rough time-budgeting check sums each attempt's time plus backoffs and compares against the upstream request deadline. For instance: 3 attempts each able to wait up to 1.5 seconds on read, plus 0.1s and 0.3s backoff, already totals around **4.9 seconds** for reads and backoff alone—excluding connection setup, discovery, and other layers. This is an illustrative calculation, **not** a guaranteed execution cap.

## 9. Diagnostic Checklist When Results Differ from Expectations

| Symptom | First Things to Check |
| --- | --- |
| Thought timeout was set, yet requests still hang a long time | Is `spring.cloud.openfeign.client.config.<client-name>` spelled right? Which HTTP client is running? Are another layer's retries/backoffs active? |
| Seeing multiple requests despite `Retryer.NEVER_RETRY` | Are Spring Cloud LoadBalancer, gateway/mesh, upstream callers, or user actions resending? |
| No retry when server returns 500 | Was 500 converted into `RetryableException`? What `Retryer` is active? |
| Retries happen without switching instances | Static URL or discovery? What is LoadBalancer's same/next instance policy? |
| Behavior differs between local and staging | Compare dependency versions, `Request.Options`, client config, proxies, DNS, and network latency |
| A POST was recorded twice | Timeout likely occurred after server processing; check idempotency and transaction state |

Do not read Feign's `FULL` logs alone and infer how many requests the server received. Logs at each layer may reflect different attempt scopes; counting at the **actual endpoint** or cross-layer traces answers "how many times was it sent?".

## 10. Self-Practice

1. Re-run the test in Section 4 with `readTimeout` set to 100ms, 200ms, and 1200ms; record exceptions, measured duration, and `REQUESTS`.
2. Replace `Retryer.NEVER_RETRY` with `Retryer.Default(100, 300, 3)`; adjust assertions, count requests, and verify total attempts. Then test a plain HTTP 500 to confirm retries do not apply automatically to every 5xx.
3. Remove the static URL, register two instances of `stock-service` via your application's discovery mechanism, and observe which instances are selected on errors. Toggle `spring.cloud.loadbalancer.retry.enabled` to separate retry layers.
4. Propose a `timeout/retry` policy for `GET /stocks/{sku}` and `POST /orders`, explaining how to prevent duplicates and protect the overall deadline.

**Key takeaway:** When inspecting a Spring Cloud LoadBalancer + OpenFeign system, accurate answers about default behavior come from **the right layer and real measurements**: Spring Cloud OpenFeign defaults to `Retryer.NEVER_RETRY` at the Feign layer; timeouts are not overall deadlines; and retries from LoadBalancer or external infrastructure must be observed independently.
