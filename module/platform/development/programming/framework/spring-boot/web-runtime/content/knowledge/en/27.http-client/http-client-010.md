# Bounding Response Size, Releasing Bodies, and Handling Target Service Errors

> **Scope:** Spring Boot web-runtime, topic **HTTP client**. This lesson uses **Java 17+, Spring Boot 3.3.x, and Spring Framework 6.1.x** to explain how an application calls a target HTTP service without buffering unbounded responses in memory, leaking `DataBuffer`s/connections, or forwarding raw upstream errors to callers. The example runs on Spring MVC/Tomcat while using `WebClient` for outbound I/O, and contrasts `RestClient` and `RestTemplate`.

## 1. Key Learning Outcomes

After this lesson, you will be able to:

1. Distinguish **wire response size**, **decoded body size**, **codec aggregation limit**, **streaming total-byte limit**, and **connection/concurrency budgets**.
2. Explain why `bodyToMono(String.class)`, `bodyToMono(byte[].class)`, and large JSON objects/lists typically buffer data, whereas `Flux<DataBuffer>` processes chunks incrementally.
3. Configure `WebClient` codec `maxInMemorySize` and understand exactly when `DataBufferLimitException` occurs—without mistaking this limit for a total stream size cap.
4. Use `retrieve()` or `exchangeToMono()` to branch on HTTP statuses, consume or release bodies, and map errors to the current API's contract.
5. Release pooled `DataBuffer` instances under proper ownership—even on limit violations, cancellation/discard, or timeouts—without double-releasing.
6. Count actual received bytes to cap the total body regardless of whether `Content-Length` is declared, missing, or altered by compression.
7. Return `HTTP 502`/503/504 or domain statuses instead of echoing upstream error HTML, stack traces, access tokens, or internal details.
8. Understand the differences between `RestClient` (blocking) and `WebClient` (reactive) regarding stream handling, response closing, timeouts, threads, and connection pools.
9. Test small 200 responses, oversized bodies, 503 responses with sensitive bodies, chunked responses, timeouts, redirects, client cancellations, and concurrent connections.

## 2. Model of an Application Calling a Target HTTP Service

Suppose a shop API needs product data from a catalog service:

~~~text
Browser / client A
       |
       | GET /api/product
       v
Spring Boot API (service A)
       |
       | outbound HTTP GET
       v
Catalog service (B)
       |
       +----> 200 / small JSON
       |
       +----> 200 / unexpectedly huge body
       |
       +----> 404, 429, 500, 503 + error page
       |
       +----> timeout / reset / TLS error
       |
       v
Service A handles body, status, resources, deadline
       |
       v
Public HTTP response with safe schema and errors
~~~

If B unexpectedly returns 800 MiB of HTML instead of 4 KiB of JSON, code calling `bodyToMono(String.class)` risks holding massive data in RAM without a codec limit; code calling `bodyToFlux(DataBuffer.class)` may keep memory bounded yet read an endless stream without a **total-byte cap**. If B returns 503 containing a raw database connection string, logging or returning `responseBody` leaks secrets even though internal traffic used TLS.

**Design principle:** every outbound call needs an explicit contract for content type, total byte size, duration, retries, concurrency, status mapping, memory, and response body ownership.

## 3. Resource Limits Are Not Interchangeable

| Limit | Controls | Does not guarantee |
|---|---|---|
| HTTP `Content-Length` | Body size **declared** by the server; useful for fast rejection | Not always present; does not replace a byte counter or reflect decoded size |
| `spring.codec.max-in-memory-size` | Aggregation buffer cap for certain WebClient/WebFlux codecs | Not a total byte cap for every `Flux<DataBuffer>` stream |
| `WebClient.Builder.codecs(...maxInMemorySize...)` | Codec buffer limit on a specific `WebClient` | Does not automatically stop unbounded streaming chunks |
| Total bytes counted | Actual decoded bytes passing through client operators | Does not bound wire bytes, time, redirects, or JSON parser CPU by itself |
| Connect/read/overall timeouts | Time and connection wait budgets | Does not stop a huge response that arrives quickly |
| Connection pool, bulkhead | Simultaneous calls/streams allowed | Does not bound the byte size of a single call |
| Content-Type/schema constraints | Expected content format | Does not replace byte caps, validation, or output sanitization |
| Compressed/decoded ratio | Guards against decompression bombs | Does not limit concurrent requests |

For example, 200 concurrent requests each decoding an 8 MiB response into a `byte[]` consume **1,600 MiB** just for one payload copy per request—before counting copies, JSON objects, buffer pools, and GC. Streaming in 8 KiB or 64 KiB chunks and releasing them slashes memory retention, though you still must measure pooled native/direct memory and queues under concurrency.

### `Content-Length` Is Not the Sole Source of Truth

A response may use `Transfer-Encoding: chunked` with no `Content-Length`, or HTTP/2 framing differs from HTTP/1.1. With gzip/br compression, encoded wire bytes can be far smaller than decompressed bytes. Reverse proxies can also transform bodies and headers. Therefore:

1. Read `Content-Length` as a **fast-reject hint** when present and trustworthy in context.
2. Always enforce a **byte counter** where content is processed if the contract demands a hard cap.
3. With auto-decompression enabled, enforce the limit on **decoded** payloads; add wire quotas at the connector/proxy if needed.
4. Never pre-allocate an array sized by a huge peer-declared `Content-Length`.

## 4. Common Spring HTTP Clients

| Client | I/O model | Suitable API | Risks |
|---|---|---|---|
| `RestClient` (Spring 6.1+) | Synchronous/blocking | `retrieve()` for small bodies; `exchange((req, resp) -> ...)` for status/stream control | Pins threads on slow networks; buffering huge bodies |
| `RestTemplate` | Synchronous/blocking | `execute` with `ResponseExtractor` for streaming | Default `ErrorHandler`, response body lifecycle, thread budgets |
| `WebClient` | Reactive; non-blocking when connector supports it | `retrieve`, `exchangeToMono`, `bodyToFlux(DataBuffer.class)` | Uncapped aggregation, pooled buffer leaks, blocking on event loop |
| `@HttpExchange` proxy | Interface abstraction | Adapter using `RestClient`/`WebClient` | Adds no byte cap/timeout by itself: depends on underlying client |
| JDK `HttpClient` | Sync/async Java API | `BodyHandlers.ofInputStream()` | Must handle streams, closing, and limits per contract |

Spring Boot can run a **Spring MVC/Tomcat server** alongside a **WebClient/Reactor Netty outbound client**. Having both `spring-boot-starter-web` and `spring-boot-starter-webflux` does not turn the server into WebFlux by default; Boot typically prefers Servlet MVC when both are present. A pure WebFlux app must avoid calling blocking `RestClient` on the event loop.

## 5. What Does `maxInMemorySize` Actually Limit?

`WebClient` uses `HttpMessageReader` and `Decoder` implementations to convert responses into Java objects. Many decoders default to roughly **256 KiB** for a single buffered/aggregated item (depending on version and codec). In Spring Boot 3.3, you can configure the global property for Boot-configured codecs:

~~~properties
spring.codec.max-in-memory-size=256KB
~~~

Or configure it per client:

~~~java
// Configuration snippet inside a Spring @Bean, not a standalone file.
WebClient webClient = WebClient.builder()
    .baseUrl("https://catalog.example.test")
    .codecs(configurer -> configurer.defaultCodecs()
        .maxInMemorySize(64 * 1024))
    .build();
~~~

With:

~~~java
Mono<String> body = webClient.get()
    .uri("/document")
    .retrieve()
    .bodyToMono(String.class);
~~~

Spring must decode/aggregate into a single `String`. Exceeding the buffer limit throws `org.springframework.core.io.buffer.DataBufferLimitException`. This is a **guard against unbounded in-memory aggregation**, not a reason to raise the limit to 1 GiB just for 1 GiB payloads. Switch the contract to pagination or streaming when sizes exceed budget.

By contrast:

~~~java
Flux<DataBuffer> parts = webClient.get()
    .uri("/download")
    .retrieve()
    .bodyToFlux(DataBuffer.class);
~~~

each `DataBuffer` is one chunk of bytes. Total transferred bytes can far exceed `maxInMemorySize` when no operator aggregates them. The application itself must enforce the **total byte limit**. Even `Flux<MyDto>` decoding many JSON objects can buffer up to the limit per individual object, so never assume every `Flux` type is immune to aggregation limits.

## 6. `retrieve()` vs. `exchangeToMono()`

### 6.1. `retrieve()`: Convenient for Small Responses with a Clear Schema

~~~java
Mono<Item> item = webClient.get()
    .uri("/items/{id}", 42)
    .retrieve()
    .bodyToMono(Item.class);
~~~

This is a **snippet** requiring an `Item` class and `WebClient`. `retrieve()` handles many 4xx/5xx responses by emitting `WebClientResponseException` or subclasses by default. For custom mapping, use `onStatus(...)`:

~~~java
Mono<Item> item = webClient.get()
    .uri("/items/{id}", 42)
    .retrieve()
    .onStatus(status -> status.value() == 404,
        response -> response.releaseBody()
            .then(Mono.error(
                new ItemMissingException())))
    .bodyToMono(Item.class);
~~~

Here `ItemMissingException` is application-defined. There is no need to buffer an entire upstream error page if unused. If you must read an error code from the body, enforce a **small byte cap**, validate the schema, and avoid logging or exposing unauthorized details.

### 6.2. `exchangeToMono()`: Full Control Over How the Response Is Used

~~~java
Mono<String> content = webClient.get()
    .uri("/data")
    .exchangeToMono(response -> {
        if (!response.statusCode().is2xxSuccessful()) {
            return response.releaseBody()
                .then(Mono.error(
                    new IllegalStateException(
                        "Upstream not available")));
        }
        return response.bodyToMono(String.class);
    });
~~~

`exchangeToMono` and `exchangeToFlux` let you inspect status and headers before deciding to decode, release, or stream the body. Once the callback's returned publisher completes, Spring checks and releases any unconsumed body. **Never** retain `ClientResponse` to decode after the callback publisher has completed. The legacy `exchange()` method should not be used as a default pattern because error branches easily forget to consume/release the body.

`ClientResponse.releaseBody()` is how you **consume and release unwanted content**, not an instant network erase. If an upstream sends an infinite or painfully slow error body, draining still takes time and bandwidth—enforce an overall deadline, network controls, and cancel/abort policies. Dropping keep-alive reuse on a connection with an unread body is sometimes preferable to pulling gigabytes of garbage just to keep the socket.

## 7. `DataBuffer` and Release Responsibility

On Reactor Netty, a `DataBuffer` can wrap a Netty `ByteBuf` backed by **pooled direct/native memory** with reference counting. Java garbage collection does not guarantee timely release of pooled buffers. When handling `Flux<DataBuffer>` directly:

- Receive a buffer and read/process it: **release it exactly once** once done with the data.
- Hand the buffer off to a writer/HTTP response: clarify who **owns** and will release it—never double-release.
- Buffers discarded by operators on cancel/error: register `doOnDiscard(DataBuffer.class, DataBufferUtils::release)` at the appropriate place for operators supporting discard hooks.
- When `DataBufferUtils.write(Publisher<DataBuffer>, Path)` manages sources in a writer, check the exact overload contract. Overloads `write(..., OutputStream/Channel)` returning `Flux<DataBuffer>` **do not release** buffers automatically and require separate handling.
- With standard `retrieve().bodyToMono(String.class)`, the framework decoder manages buffers per contract; do not manually release buffers you never received.
- When a client request cancels, unread HTTP content can close the connection instead of reusing it; that is not necessarily a leak, though resource metrics must still be monitored.

### Bounded Byte-Counting Pattern

~~~java
// Pipeline snippet; "source" must be a Flux<DataBuffer>.
AtomicLong bytes = new AtomicLong();

Mono<Long> total = source
    .<Long>handle((buffer, sink) -> {
        try {
            int n = buffer.readableByteCount();
            if (n > 4096L - bytes.get()) {
                sink.error(new IllegalStateException(
                    "Too large"));
            } else {
                sink.next(bytes.addAndGet(n));
            }
        } finally {
            DataBufferUtils.release(buffer);
        }
    })
    .doOnDiscard(DataBuffer.class,
            DataBufferUtils::release)
    .then(Mono.fromSupplier(bytes::get));
~~~

Every `DataBuffer` entering the callback is released in `finally`, even when exceeding the limit. If an operator discards buffers prior to the callback on cancellation, the discard hook cleans them up. `handle` emits `Long` and **never** forwards an already-released buffer. In real code, never log raw exceptions carrying secrets; translate errors into sanitized public responses and increment metrics for oversized rejections.

**Anti-pattern:**

~~~java
// Never use for large payloads.
webClient.get().uri("/archive")
    .retrieve()
    .bodyToFlux(DataBuffer.class)
    .collectList();
~~~

`collectList()` retains every buffer object in memory and provides no automatic total byte limit. Likewise, unbounded `DataBufferUtils.join()` can aggregate huge amounts of memory. Compute sums/checksums incrementally chunk-by-chunk, or stream to a temp file/object store through ownership-clear APIs.

## 8. Mapping Errors from the Target Service

An upstream status should not automatically be forwarded verbatim: service A owns its own public client contract.

| Situation at B | Choice for A | Explanation |
|---|---|---|
| 2xx + valid body | 200/201/204 per A's contract | Still verify byte size and Content-Type/schema |
| 404 | 404 if same resource contract; otherwise 502 | Avoid exposing internal resource existence inappropriately |
| 400 | 400 if A's caller truly sent invalid input; otherwise 502 | May indicate a bug in A→B request construction |
| 401/403 | 401/403 only if reflecting caller permissions; otherwise 502/503 | Never return internal authentication details |
| 409 | 409 on real domain conflict | Stable public details, never raw upstream JSON |
| 429 | 429 or 503, with sensible backoff policy | Prevent synchronized retries; inspect `Retry-After` |
| 500/502/503 | 502 or 503 | Never forward raw stack traces/SQL/HTML from B |
| Connect/DNS/TLS failure | 502 or 503 | Never disable TLS certificate verification for convenience |
| Overall timeout | 504 if gateway-like; or 503 per contract | Enforce deadline; never retry infinitely |
| Oversized 2xx response | **HTTP 502**/appropriate domain error | 413 normally applies to an oversized **request**, not a downstream response |
| Client A cancels request | Cancel outbound publisher/cleanup | Not always an opportunity to write an HTTP error body |

Suppose B responds:

~~~http
HTTP/1.1 503 Service Unavailable
Content-Type: text/plain

INTERNAL_DB_HOST=db.private; token=topsecret
~~~

A must never expose `INTERNAL_DB_HOST` or `token` in the body, custom headers, public logs, or response exception messages. Return a stable public error code and fixed message, optionally with a correlation ID. In controlled server-side logs, record **service label, route template, status, latency, exception type, and requestId** with redaction—never raw `Authorization`, `Cookie`, or response bodies.

## 9. Timeouts and Retries Do Not Replace a Body Cap

There are multiple timeout layers:

- **Connect timeout**: waiting for TCP connection establishment.
- **TLS handshake timeout**: peer verification and TLS negotiation.
- **Response/read timeout**: waiting for response or network reads, with connector-specific semantics.
- **Pending acquire timeout**: waiting to borrow a connection from the pool.
- **Whole-operation deadline**: max total time for DNS/connect/TLS/request/body/processing at the application layer.

A 3-second timeout will not stop a 400 MiB payload transferred in 1 second. Conversely, a 20-byte body can still pin a connection if the upstream drips bytes slowly. Combine **byte caps + deadlines + concurrency caps**.

Illustrative Reactor Netty configuration:

~~~java
// Requires imports reactor.netty.http.client.HttpClient,
// io.netty.channel.ChannelOption,
// org.springframework.http.client.reactive.ReactorClientHttpConnector,
// java.time.Duration.
HttpClient http = HttpClient.create()
    .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 2000)
    .responseTimeout(Duration.ofSeconds(3));

WebClient client = WebClient.builder()
    .clientConnector(new ReactorClientHttpConnector(http))
    .build();
~~~

Connector `responseTimeout` differs from `Mono.timeout` covering the entire reactive operation. When retries/backoff are enabled, fit all attempts inside the **total deadline budget**.

**Retry policy:**

- Retry only classified transient failures eligible under your contract (e.g., idempotent GET hitting 503/connection reset), with **max attempts**, exponential backoff, and jitter.
- Never retry `DataBufferLimitException` or oversized-response errors: repeating the same request usually yields the same oversized payload.
- Never retry 400/401/403 or TLS verification failures as if they were transient network glitches.
- Retry mutating POST/PUT requests only with explicit idempotency guarantees or domain protocol support.
- If the gateway, service A, and service mesh all retry, outbound call counts can multiply and crush B.
- Bulkheads and circuit breakers contain failure propagation; they do not replace size caps.

## 10. Runnable Example: Spring Boot 3.3 Java 17 + WebClient

The lab runs **one process** with two groups of endpoints:

~~~text
curl --> Spring MVC/Tomcat :8080
            |
            +-- /target/small  : fake B returns "hello"
            +-- /target/large  : fake B returns 128 KiB of "A"
            +-- /target/error  : fake B returns 503 + internal marker
            |
            +-- /proxy/text/{mode}
            |      WebClient -> fake B -> decode String (32 KiB cap)
            |
            +-- /proxy/count/{mode}
                   WebClient -> fake B -> DataBuffer byte counter (4 KiB cap)
~~~

Fake B runs in the same app **solely to run standalone on a laptop**. Production uses B's hostname across a separate network with proper auth/TLS, and never builds an open proxy from user-supplied URLs.

### 10.1. Project Structure

~~~text
outbound-limit-lab/
  pom.xml
  src/main/java/example/limits/OutboundLimitApplication.java
  src/main/resources/application.properties
~~~

### 10.2. Complete `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>outbound-limit-lab</artifactId>
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
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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

`spring-boot-starter-web` provides the MVC/Tomcat server, while `spring-boot-starter-webflux` provides the `WebClient`/Reactor Netty client. In Boot 3.3 when both are present, Servlet MVC is the default web application type, so controllers can return `Mono` adapted asynchronously by Spring MVC without switching the server to Reactor Netty.

### 10.3. `application.properties`

~~~properties
server.port=8080

# Prevent Boot's default error page from exposing stacktrace/exception message:
server.error.include-message=never
server.error.include-stacktrace=never
server.error.include-exception=false
~~~

### 10.4. Complete Java File

Create `src/main/java/example/limits/OutboundLimitApplication.java`:

~~~java
package example.limits;

import java.time.Duration;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferLimitException;
import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientRequestException;

import reactor.core.publisher.Mono;

@SpringBootApplication
public class OutboundLimitApplication {

    public static void main(String[] args) {
        SpringApplication.run(OutboundLimitApplication.class, args);
    }

    @Configuration
    static class HttpClientConfiguration {

        @Bean
        WebClient destinationClient(WebClient.Builder builder) {
            return builder
                .baseUrl("http://localhost:8080")
                .codecs(c -> c.defaultCodecs()
                    .maxInMemorySize(32 * 1024))
                .build();
        }
    }

    @RestController
    static class FakeDestination {
        @GetMapping(value = "/target/{mode}",
                    produces = MediaType.TEXT_PLAIN_VALUE)
        ResponseEntity<String> target(@PathVariable String mode) {
            return switch (mode) {
                case "small" -> ResponseEntity.ok("hello");
                case "large" -> ResponseEntity.ok(
                        "A".repeat(128 * 1024));
                case "error" -> ResponseEntity
                        .status(HttpStatus.SERVICE_UNAVAILABLE)
                        .body("UPSTREAM_INTERNAL_ONLY=db.private");
                default -> ResponseEntity.notFound().build();
            };
        }
    }

    @RestController
    static class ProxyController {
        private static final long MAX_STREAM_BYTES = 4096L;
        private static final Duration TOTAL_DEADLINE =
                Duration.ofSeconds(5);

        private final WebClient client;

        ProxyController(WebClient destinationClient) {
            this.client = destinationClient;
        }

        @GetMapping("/proxy/text/{mode}")
        public Mono<ResponseEntity<?>> text(
                @PathVariable String mode) {
            if (!allowed(mode)) {
                return Mono.just(problem(HttpStatus.BAD_REQUEST,
                    "Invalid test mode."));
            }

            Mono<ResponseEntity<?>> request = client.get()
                .uri("/target/{mode}", mode)
                .exchangeToMono(response -> {
                    if (!response.statusCode().is2xxSuccessful()) {
                        int status = response.statusCode().value();
                        return response.releaseBody()
                            .then(Mono.<ResponseEntity<?>>error(
                                new RemoteFailure(status)));
                    }

                    // Aggregate String: codec cap is 32 KiB.
                    return response.bodyToMono(String.class)
                        .defaultIfEmpty("")
                        .<ResponseEntity<?>>map(body ->
                            ResponseEntity.ok(
                                Map.of("text", body)));
                });

            return guarded(request);
        }

        @GetMapping("/proxy/count/{mode}")
        public Mono<ResponseEntity<?>> count(
                @PathVariable String mode) {
            if (!allowed(mode)) {
                return Mono.just(problem(HttpStatus.BAD_REQUEST,
                    "Invalid test mode."));
            }

            Mono<ResponseEntity<?>> request = client.get()
                .uri("/target/{mode}", mode)
                .exchangeToMono(response -> {
                    if (!response.statusCode().is2xxSuccessful()) {
                        int status = response.statusCode().value();
                        return response.releaseBody()
                            .then(Mono.<ResponseEntity<?>>error(
                                new RemoteFailure(status)));
                    }

                    AtomicLong total = new AtomicLong();
                    return response.bodyToFlux(DataBuffer.class)
                        .<Long>handle((buffer, sink) -> {
                            try {
                                int n = buffer.readableByteCount();
                                if (n > MAX_STREAM_BYTES - total.get()) {
                                    sink.error(new ResponseTooLarge());
                                } else {
                                    sink.next(total.addAndGet(n));
                                }
                            } finally {
                                DataBufferUtils.release(buffer);
                            }
                        })
                        .doOnDiscard(DataBuffer.class,
                            DataBufferUtils::release)
                        .then(Mono.<ResponseEntity<?>>fromSupplier(
                            () -> ResponseEntity.ok(
                                Map.of("bytes", total.get()))));
                });

            return guarded(request);
        }

        private static boolean allowed(String mode) {
            // Mode allowlist instead of permitting arbitrary URLs.
            return Set.of("small", "large", "error")
                    .contains(mode);
        }

        private static Mono<ResponseEntity<?>> guarded(
                Mono<ResponseEntity<?>> request) {
            return request.timeout(TOTAL_DEADLINE)
                .onErrorResume(ResponseTooLarge.class, ignored ->
                    Mono.just(problem(HttpStatus.BAD_GATEWAY,
                        "Target service response exceeded limit.")))
                .onErrorResume(DataBufferLimitException.class,
                    ignored -> Mono.just(problem(
                        HttpStatus.BAD_GATEWAY,
                        "Target service response too large.")))
                .onErrorResume(RemoteFailure.class, failure ->
                    Mono.just(problem(
                        failure.status == 503
                            ? HttpStatus.SERVICE_UNAVAILABLE
                            : HttpStatus.BAD_GATEWAY,
                        "Target service unavailable.")))
                .onErrorResume(TimeoutException.class, ignored ->
                    Mono.just(problem(HttpStatus.GATEWAY_TIMEOUT,
                        "Target service responded too slowly.")))
                .onErrorResume(WebClientRequestException.class,
                    ignored -> Mono.just(problem(
                        HttpStatus.BAD_GATEWAY,
                        "Unable to connect to target service.")))
                .onErrorResume(Exception.class, ignored ->
                    Mono.just(problem(HttpStatus.BAD_GATEWAY,
                        "Unable to process target service response.")));
        }

        private static ResponseEntity<?> problem(
                HttpStatus status, String message) {
            ProblemDetail body =
                    ProblemDetail.forStatusAndDetail(status, message);
            body.setTitle("Target service call failed");
            return ResponseEntity.status(status)
                    .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                    .cacheControl(CacheControl.noStore())
                    .body(body);
        }

        private static final class ResponseTooLarge
                extends RuntimeException {
        }

        private static final class RemoteFailure
                extends RuntimeException {
            final int status;

            RemoteFailure(int status) {
                super("remote status");
                this.status = status;
            }
        }
    }
}
~~~

### 10.5. How the Code Works

**WebClient bean:** the 32 KiB limit governs codec aggregation. Both the client builder and `WebClient` are safe to reuse across requests; never create a new `WebClient` per request. The base URL is hardcoded so the lab runs as one process; production must inject a **trusted** config value and never accept arbitrary URLs from users.

**Fake destination:** `small` returns `hello` (**5 ASCII bytes**); `large` returns 128 KiB of `'A'` to simulate a huge body; `error` returns 503 with an internal marker. Fake B in the same JVM deliberately allocates a 128 KiB string and does not represent an independent production service.

**text route:** uses `bodyToMono(String.class)` rather than streaming incrementally. `/proxy/text/large` exceeds the 32 KiB codec limit and is mapped to a public 502 error without holding the 128 KiB body as a single large `String`.

**count route:** uses `bodyToFlux(DataBuffer.class)` with a 4096-byte cap. `handle` inspects each buffer and its `finally` block releases every received buffer even when an error is raised. `doOnDiscard` cleans up buffers dropped by discard-capable operators prior to the callback. The terminal operator returns only the byte count without retaining body contents in a `List` or `String`.

**Error branch:** checks status before decoding. For non-2xx responses, it calls `releaseBody()` to discard error content and emits an exception carrying only the status code, never the response body. Public mapping emits a sanitized `ProblemDetail` with `no-store`; the `UPSTREAM_INTERNAL_ONLY` marker never leaves the proxy.

**Deadline:** `timeout(5s)` wraps the request publisher. Used for the lab; production adds per-phase timeouts, connection pool/concurrency limits, and retry budgets.

**Contract:** an oversized upstream response is a failure **of the target service**, so the example returns `502 Bad Gateway` instead of confusing it with `413 Content Too Large`, which applies to an API's **inbound request** body.

**Exception safety:** the final `onErrorResume` prevents raw library exceptions from leaking into public bodies. Production systems need structured internal error logs/traces with request IDs while avoiding logging tokens, PII, raw query URLs, or upstream stack traces.

## 11. Running and Verifying with curl

From the project root with Maven and JDK installed:

~~~bash
mvn spring-boot:run
~~~

Call:

~~~bash
curl -i http://localhost:8080/proxy/text/small
curl -i http://localhost:8080/proxy/count/small

curl -i http://localhost:8080/proxy/text/large
curl -i http://localhost:8080/proxy/count/large

curl -i http://localhost:8080/proxy/text/error
curl -i http://localhost:8080/proxy/count/error
curl -i http://localhost:8080/proxy/text/unknown
~~~

Expected:

| Endpoint | HTTP status | Meaningful body |
|---|---|---|
| `/proxy/text/small` | 200 | `{"text":"hello"}` |
| `/proxy/count/small` | 200 | `{"bytes":5}` |
| `/proxy/text/large` | 502 | ProblemDetail: response exceeded codec aggregation limit |
| `/proxy/count/large` | 502 | ProblemDetail: decoded bytes exceeded 4096 hard cap |
| `/proxy/text/error` | 503 | ProblemDetail: dependency unavailable, **without internal marker** |
| `/proxy/count/error` | 503 | Same |
| `/proxy/text/unknown` | 400 | Mode not in allowlist |

`Content-Type`, JSON field ordering, `Date`, and connection headers depend on the HTTP runtime; assert **status + semantics** rather than comparing raw bytes verbatim unless required.

**Verifying no error body leak:**

~~~bash
curl -s http://localhost:8080/proxy/text/error
~~~

Output **contains neither** `UPSTREAM_INTERNAL_ONLY` nor `db.private`. Calling `/target/error` directly as the simulator shows the marker; the proxy strips it out. Never expose this fake target service in production.

To test the exact 4096/4097-byte boundary, extend the fake destination in **a separate lab copy** with two text responses of exactly 4096 and 4097 ASCII characters, then call `/proxy/count/...` and verify 200 vs. 502. Never alter production settings just to run this boundary test.

## 12. `RestClient`: Streaming Blocking Responses

Spring Framework 6.1's `RestClient` offers a fluent API for synchronous HTTP I/O. For small bounded JSON, `retrieve().body(MyDto.class)` is simple. For files or untrusted bodies:

~~~java
// Anti-pattern for large responses; buffers entire body in RAM.
byte[] huge = restClient.get().uri("/archive")
    .retrieve().body(byte[].class);
~~~

Replace with `exchange(...)` reading the `InputStream` in chunks:

~~~java
// Snippet inside a method with RestClient client.
// Requires imports for InputStream, RestClient, and exceptions.
long bytes = client.get().uri("/archive")
    .exchange((request, response) -> {
        // exchange does not automatically run default retrieve status handlers.
        if (!response.getStatusCode().is2xxSuccessful()) {
            throw new IllegalStateException(
                "Upstream response failed");
        }

        long total = 0;
        byte[] block = new byte[8192];
        try (InputStream in = response.getBody()) {
            int n;
            while ((n = in.read(block)) != -1) {
                if (n == 0) {
                    continue;
                }
                if (n > 4L * 1024 * 1024 - total) {
                    throw new IllegalStateException(
                        "Response too large");
                }
                total += n;
            }
        }
        return total;
    });
~~~

`RestClient.exchange` passes request/response into the callback and manages response cleanup after the callback finishes; `retrieve()` status handlers **do not run automatically inside `exchange` callbacks**. Always check status before reading. The `InputStream` is valid **only inside the callback** and closed via `try-with-resources`. Closing/aborting an unread response may forfeit connection reuse—which is often the right trade-off rather than draining an endless error body.

This path is **blocking**: the calling thread waits on network reads. In MVC apps, size workers, pools, and timeouts accordingly. In WebFlux, never call sync `RestClient` directly on the Netty event loop; if an SDK forces blocking, offload to `Schedulers.boundedElastic()` with bounded queues/concurrency, noting that offloading does not add a byte cap automatically.

### `RestTemplate`

`RestTemplate` remains widely used and offers `execute(..., ResponseExtractor)` for streaming responses. Calling `getForObject(..., byte[].class)` on large bodies suffers the same memory issue. Remember that the default `ResponseErrorHandler` can throw on 4xx/5xx **before** the extractor runs; if customizing the handler, preserve resource lifecycle and limit error body reads.

In Spring 6.1+, `RestClient` fits new synchronous code, while `WebClient` fits reactive composition/streaming and non-blocking connectors. Do not rewrite working `RestTemplate` code solely for a new API name if timeouts, limits, monitoring, and tests are already solid.

## 13. Writing Large Responses to Disk: Ownership Matters

With `WebClient`, a clean pattern for downloading an archive is:

~~~text
GET upstream
  |
  | check status, Content-Type, optional declared length
  v
Flux<DataBuffer>
  |
  | count actual bytes; reject > MAX
  v
DataBufferUtils.write(..., tempPath)
  |
  | write complete -> verify size/checksum/format
  v
publish file / metadata; cleanup temp on error/cancel
~~~

Illustrative writer snippet:

~~~java
// Pseudocode, not a complete endpoint.
Mono<Void> write = DataBufferUtils.write(
    boundedDataBufferStream, temporaryPath);
~~~

With `DataBufferUtils.write(Publisher<DataBuffer>, Path)`, the writer manages received buffers per its API contract; do not release buffers **before** passing them to the writer. Overloads returning `Flux<DataBuffer>` that write to an `OutputStream` or `Channel` have a different contract: source buffers **are not automatically released** and the consumer must release them appropriately.

A real file download implementation must allocate temp files off the event loop if file I/O blocks, enforce a byte cap, check status before streaming, clean up on complete/error/cancel, block path traversal, enforce disk quotas, verify checksums/scan files, and publish the file only when complete. Java `Files.move` does not guarantee atomicity or durability across all filesystems by default.

## 14. Compression, Chunked Responses, and Parser Limits

A tiny gzipped response can expand enormously after decompression. `Content-Length` may reflect the encoded representation rather than decoded JSON. When decompression is enabled on the client/connector, know at which stage bytes are counted and apply **wire byte** limits alongside **decoded byte** limits if needed.

Edge cases:

- **Chunked HTTP/1.1**: no fixed `Content-Length`; rely on a byte counter.
- **HTTP/2**: DATA frames are managed by the transport; never infer total response size from a single header.
- **gzip/br**: decoded size can far exceed encoded length; guard against compression bombs and cap decode ratios for untrusted sources.
- **Large JSON arrays**: `bodyToMono(List.class)` buffers the entire list; switch to pagination or per-item streaming and bound item counts, nesting depth, and string lengths.
- **SSE/NDJSON**: streams can stay open indefinitely; enforce per-event caps, idle timeouts, and lifetime policies instead of assuming "streaming" means zero memory risk.
- **HTML error pages**: upstreams/gateways may return HTML instead of JSON. Never attempt to parse HTML as a domain DTO or log the entire page on parse failure.

A byte cap is only one layer: also account for parser CPU, schema/type validation, file extensions, object nesting, and per-request object counts.

## 15. Timeouts, Retries, Circuit Breakers, and Resource Budgets

**Connect timeout**, **TLS handshake timeout**, **response/read timeout**, **pending connection acquire timeout**, and **overall deadline** mean different things. A tiny response can hang for minutes if a dependency stalls, while a 100 MiB body can finish well before a timeout. Pair **time budgets** with **byte budgets**.

Advanced Reactor Netty example (snippet; requires proper imports):

~~~java
HttpClient netty = HttpClient.create()
    .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 2000)
    .responseTimeout(Duration.ofSeconds(3));

WebClient client = WebClient.builder()
    .clientConnector(new ReactorClientHttpConnector(netty))
    .build();
~~~

Connector `responseTimeout` applies at the connector/response-read layer per contract; `Mono.timeout` sets a deadline from publisher subscription. Never treat the two as equivalent.

Retries must be **bounded and selective**: an idempotent GET hitting a transient 503 can retry with exponential backoff, jitter, and a total deadline; HTTP 400/401/403 from bad requests, TLS certificate verification failures, or oversized responses **must not** retry the same payload endlessly. Mutating POST/PUT calls require idempotency keys or reconciliation models to prevent duplicate effects.

**Circuit breakers** stop calling consistently failing dependencies; **bulkheads** bound concurrency per downstream; **rate limiters** prevent overload; **timeouts + byte caps** prevent calls from pinning connections and memory. None of these controls replaces the others.

## 16. Redirects, SSRF, and Trust Boundaries

`WebClient`/`RestClient` run **server-side**, free from browser SOP/CORS. If a backend lets users pass an arbitrary URL and calls it:

~~~java
// Anti-pattern: user controls the network destination.
webClient.get().uri(userSuppliedUrl)
    .retrieve().bodyToMono(String.class);
~~~

the API can be exploited for **SSRF** against metadata endpoints, internal services, or hosts outside allowlists. A byte limit never stops the server from reaching a sensitive URL.

Load base URLs from trusted config/service discovery, accept only allowlisted paths/IDs, and encode URI parameters. If calling external user-provided URLs is strictly necessary, validate DNS/IP/host/scheme, restrict egress networking, cap redirects, and re-verify destinations after redirects and DNS resolution. Never forward `Authorization` or cookies across cross-host redirects.

In the lab, `mode` allows only `small`, `large`, and `error`, preventing users from turning the app into an open proxy. When 302/307 HTTP redirects occur, auto-follow behavior depends on the connector; verify status/`Location` handling and auth forwarding per your exact client setup.

## 17. Preventing Information Leaks from Downstream Errors

When app A receives an error from B, these values **must never appear** in public responses:

- Raw exception class names, stack traces, SQL, or database hostnames/JDBC URLs.
- `Authorization`/Bearer tokens, JWTs, API keys, `Set-Cookie`, signed URLs, or session IDs.
- User/tenant identifiers outside A's API contract, PII, or request bodies.
- Internal service IPs, pod names, ports, filesystem paths, or debug/config dumps.
- Reverse-proxy 502/503 HTML error pages revealing deployment topology.

Return `ProblemDetail` with stable public `status`, `title`, and `detail`, optionally including a correlation ID. Public error bodies **are not a place to debug via `throwable.toString()`**. Internal logs/metrics still need diagnostic visibility, using allowlisted fields, secret redaction, access controls, and retention rules.

If B returns 401/403, do not blindly translate it into 401/403 for A's caller: it could be a **service-to-service token misconfiguration**, not an unauthenticated end user. If a response exceeds the size cap, `502 Bad Gateway` fits when A acts as a gateway calling B and B breaks the contract, rather than `413 Content Too Large` when A's inbound request was tiny.

## 18. Connection Pools and Cancellation

HTTP clients use keep-alive/HTTP2 pooling to reuse sockets. When response bodies are not consumed, released, or canceled properly, connections can stay pinned or lose eligibility for reuse.

- `retrieve().bodyToMono(...)` with normal consumption: framework manages decoding and lifecycle.
- `exchangeToMono(...)`: unconsumed bodies are released once the callback publisher completes.
- `ClientResponse.releaseBody()`: explicitly discards unwanted error content, though network draining may still occur.
- Custom `Flux<DataBuffer>` handling: release per ownership, using `doOnDiscard` for discard-enabled operators.
- Mid-stream timeout/cancel: may forfeit connection reuse; the connector must free native buffers and prevent pool leaks.
- `RestClient.exchange(...)`: consume `InputStream` strictly inside the callback—never return the stream after the response scope closes.
- Never call manual `subscribe()` inside controllers without managing `Disposable`/cancellation; return `Mono`/`Flux` so the framework owns the request lifecycle.

Monitor connection pool active/idle/pending acquire counts, pool timeouts, Netty direct memory, heap, GC, outstanding buffers, bytes/sec, and cancellations. If pending-acquire rises, investigate downstream latency and unconsumed bodies before blindly expanding pool sizes.

## 19. Testing Across Every Failure Axis

| Test | Evidence to verify |
|---|---|
| 200 small | Valid body, status 200, expected byte/char count |
| 200 body > codec cap | `DataBufferLimitException` mapped to public error; no OOM |
| 200 body > total stream cap | Counter rejects cleanly; pooled buffers cleaned up |
| Body == exact limit | Accepted if contract allows; limit+1 rejected |
| 503 with sensitive body marker | Public 503 hides marker, stack trace, and tokens |
| Chunked without `Content-Length` | Byte counter still enforces cap |
| High-ratio gzip | Enforces cap on decoded bytes and parsing |
| Timeout, slow chunk stream | Deadline/cancel fires; connections not held forever |
| Mid-stream connection reset | Proper error mapping; no buffer leaks |
| Bad TLS chain/SAN | Client fails cleanly; verification stays enabled |
| 429/`Retry-After` | No retry storm; bounded backoff verified |
| 100 concurrent requests | Heap/direct memory, pool, and latency stay stable |
| Proxy returns HTML 502 | Error HTML never echoed into public body |
| Unexpected URL input / internal redirect | SSRF prevented and egress policy enforced |
| Caller cancels request A | Outbound publisher cancels/cleans up; pool does not jam |

### Key Measurements

- **Categorized error rates**: HTTP 4xx/5xx, transport, timeout, parse, size-rejected.
- **Encoded/decoded response bytes** by route template; never put user IDs in metric labels.
- **Heap and native/direct memory**, pooled buffers, and GC pauses.
- **Active/idle/pending connections**, connect latency, response latency, and cancellations.
- **Retries per initial request**, total deadline vs. retry backoff, downstream requests/sec.
- **p95/p99** latency for API A and outbound HTTP B.

Passing one small happy-path request does not prove memory safety when B repeatedly returns multi-gigabyte 500 bodies or when many clients disconnect mid-stream. Run fault-injection and soak tests in a controlled environment.

## 20. Anti-Pattern Reference Table

| Mistake | Consequence | Better approach |
|---|---|---|
| `bodyToMono(byte[].class)` for multi-GB archives | Heap exhaustion / OOM | Stream to disk/SDK with hard byte cap |
| `collectList()` on a `DataBuffer` stream | Buffers every chunk in memory | Handle each buffer, release, add discard hook |
| Setting `maxInMemorySize` to 2 GiB | Weakens guard; OOM risk under concurrency | Limit aggregation; use streaming/pagination |
| Checking only `Content-Length` | Bypassed by missing header, chunking, compression | Count actual decoded bytes |
| Legacy `exchange()` ignoring response | Pool leaks / unreleased bodies | `retrieve` or `exchangeToMono`/`Flux` |
| Double `release()` | Reference count violation | Respect buffer ownership strictly |
| Unbounded draining of error bodies | Pins connections and saturates network | Bounded deadline / abort policy |
| Copying raw upstream errors to public body | Leaks internals, secrets, PII | Stable sanitized `ProblemDetail` |
| Mapping every error to 500 | Loses HTTP semantics and skews monitoring | Map 4xx/5xx/timeouts/size errors by domain |
| Unlimited retries on 502/503 | Cascading overload | Bounded retries, backoff, circuit breaker |
| Retrying oversized bodies | Repeats failure, wastes bandwidth | Fix contract, reject/paginate |
| `block()` on Netty event loop | Stalls reactive server | Return `Mono`/`Flux`; offload blocking SDKs |
| Passing raw user URLs | SSRF | Trusted fixed base URLs and egress allowlists |
| Escaping `InputStream` from `RestClient.exchange` | Response scope already closed | Read/close stream inside callback |
| Logging raw `Authorization`/error bodies | Leaks tokens and PII | Structured redacted logs |
| Testing only HTTP 200 | Misses error, cancel, and limit paths | Full integration test matrix |

## 21. Production Deployment Checklist

1. Define schema/`Content-Type`, maximum decoded body bytes, item counts, and pagination contracts.
2. Pick blocking `RestClient` or reactive `WebClient` based on thread/latency/workload fit, not trends.
3. Configure codec `maxInMemorySize` appropriately for calls that must aggregate.
4. Add a **total streaming byte cap** whenever consuming `DataBuffer` directly.
5. Distinguish compressed/encoded from decoded bytes and cap decode ratios if needed.
6. Set connect, TLS, read, and overall deadlines alongside connection pool budgets.
7. Retry only eligible failures with backoff, jitter, idempotency, and retry budgets.
8. Validate status/errors **before** trusting payloads; never echo raw upstream bodies.
9. Release/drain/cancel responses properly across success, error, and timeout paths.
10. Enforce network allowlists, redirect guards, SSRF prevention, and TLS verification.
11. Return a stable public error schema; keep internal logs redacted with correlation IDs.
12. Measure heap/native memory, pools, bytes, failures, and latency under concurrency.
13. Test proxy/gateway-generated error pages, not only controller responses.
14. For large files, use temp/object storage with quotas, cleanup, and checksums.
15. Run soak and cancellation tests before claiming response handling is leak-free.

**Rule to remember:** *Cap what codecs buffer in RAM, cap total streaming bytes, release every buffer/response under clear ownership, and never let target-service errors leak through your API.*

## 22. Review Questions

**1. Does `maxInMemorySize=256KB` mean a 10 MiB streaming response is automatically blocked?**  
Not automatically. It primarily bounds codec aggregation, while `Flux<DataBuffer>` can emit many chunks. You must count total bytes.

**2. Why is `Content-Length` insufficient?**  
The header may be missing, reflect encoded length, or be altered by proxies; total decoded bytes must still be enforced.

**3. Can `bodyToMono(String.class)` hold the entire response in memory?**  
Yes. A `String` must be decoded from the full body, requiring aggregation/buffering and falling under codec limits.

**4. What happens if `exchangeToMono` runs without reading the response body?**  
Spring handles unconsumed bodies once the callback publisher completes; still call `releaseBody` explicitly when discarding bodies and set timeouts.

**5. Does `releaseBody()` guarantee zero network cost?**  
No. It may drain/release remaining body bytes; deadlines and connection aborts may also be needed.

**6. When consuming `DataBuffer` directly, when should you release it?**  
Right after processing completes, provided ownership was not transferred to another writer. Never release twice.

**7. Why is `doOnDiscard` needed?**  
Some operators can drop buffers on errors or cancellation before the main callback runs, and pooled buffers must be returned to the pool.

**8. Does an upstream 503 force service A to return 503 to its caller?**  
Not necessarily. A maps errors per its contract and may return 502/503 without forwarding raw error bodies.

**9. When B returns an oversized response, should A always return 413?**  
No. 413 normally refers to an oversized inbound request; a gateway encountering an oversized downstream response typically returns 502.

**10. Does `RestClient.exchange` apply default `retrieve()` status handlers?**  
No. Inside an `exchange` callback, you inspect statuses and handle responses yourself.

**11. If `WebClient` is a reactive client, does a Spring MVC server automatically switch to Reactor Netty?**  
No. MVC/Tomcat can use `WebClient` outbound while remaining a Servlet server.

**12. Can you call blocking `RestClient` from the Netty event loop?**  
You should not. It holds the event-loop thread during I/O; offload or use `WebClient`.

**13. Why is retrying an oversized-body error unhelpful?**  
Because the same response still exceeds the cap, wasting bandwidth and adding load to B.

**14. Is it safe to forward A's cookies/tokens to a redirect URL returned by B?**  
Not by default. Validate destinations, redirects, and auth-header forwarding to prevent leaks and SSRF.

**15. When testing 100 concurrent requests, what should you monitor besides heap?**  
Netty native/direct memory, outstanding buffers, pool active/pending counts, threads/queues, errors, and cancellations.

**16. Why is logging raw upstream error payloads dangerous?**  
Payloads can contain database hosts, internal paths, secrets, or PII; logs are often shared and retained longer than intended.

## 23. Authoritative References

- [Spring Framework – WebClient configuration, maxInMemorySize](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html): configuring codecs on `WebClient`.
- [Spring Framework – WebClient exchangeToMono/Flux](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-exchange.html): handling status/body and releasing unconsumed responses.
- [Spring Framework – WebClient retrieve](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html): default 4xx/5xx handling and `onStatus`.
- [Spring Framework – Data Buffers and Codecs](https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html): reference counting, ownership, `release`, and `doOnDiscard`.
- [Spring Framework 6.1 – DataBufferUtils Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/core/io/buffer/DataBufferUtils.html): `release`, `join`, and `write` overloads.
- [Spring Framework – REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): `RestClient`, `RestTemplate`, `WebClient`, and `exchange` status handling.
- [Spring Boot 3.3 – Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): `spring.codec.max-in-memory-size` and HTTP settings.
- [Project Reactor – Error handling and retry](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html): `onErrorResume`, retry/backoff semantics.
- [Reactor Netty – HTTP Client](https://projectreactor.io/docs/netty/release/reference/http-client.html): timeouts, connection pools, and outbound HTTP.
- [OWASP – SSRF Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html): network allowlists and URL validation.
- [OWASP – Error Handling](https://cheatsheetseries.owasp.org/cheatsheets/Error_Handling_Cheat_Sheet.html): information disclosure and safe logging.