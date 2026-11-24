# Content Size Limits, Deadlines, and Sensitive Data in Logs

**Module:** Spring Framework – reactive  
**Parent Topic:** Security Integration  
**Objective:** Establish protection layers in Spring WebFlux against oversized payloads, long-running requests/responses, and credential/PII leaks in logs; accurately distinguish codec limits, HTTP body limits, multipart limits, network timeouts, and business deadlines.

## 1. Why Must These Three Limit Groups Work Together?

WebFlux does not dedicate one thread per request, yet it still consumes connections, buffers, CPU, memory, file descriptors, and disk space. Non-blocking I/O does not inherently prevent denial of service. Three common risks:

1. A client sends a body larger than decoder capacity, or streams unbounded data; the application aggregates via `collectList()`, `bodyToMono(byte[].class)`, or unbounded `DataBufferUtils.join`.
2. A client sends a request very slowly, an upstream fails to respond, or the pool saturates; the application retains subscriptions and resources longer than the SLA.
3. Failed requests are logged "for easier debugging" along with `Authorization`, cookies, tokenized URLs, error payloads, filenames, or personal information.

Sound configuration must address three things:

- **Byte budget:** limits at the gateway, HTTP parser, decoder, multipart, and each business route.
- **Time budget:** limits on pool wait, DNS, TCP, TLS, response wait, slow input, the entire business operation, and streaming idle time.
- **Information budget:** allowlisting selected metadata in logs instead of dumping user requests/responses.

A design containing only `spring.http.codecs.max-in-memory-size=64KB` does **not** mean every HTTP request over 64 KiB is blocked. That is a memory cap for codecs when buffering/aggregating data, not a byte ceiling for every body stream.

## 2. Defense Boundary Map

```text
Untrusted browser / partner
          |
          v
Gateway / WAF / reverse proxy
  - header/URI/body quotas
  - concurrent request and rate limits
  - idle and slow-client deadlines
          |
          v
Reactor Netty HTTP server
  - HTTP parser limits
  - socket and connection lifecycle
          |
          v
Spring WebFlux codecs + handler
  - maxInMemorySize
  - multipart memory/disk/parts limits
  - per-route byte counter
  - validation and timeout
          |
          v
Reactive business service
          |
          v
WebClient -> connection pool -> TLS -> upstream
  - acquire / connect / response timeout
  - response decode cap
          |
          v
Logs / metrics / traces
  - method, route pattern, status, duration
  - no secrets, raw body, raw query
```

Defense layers do not replace one another. The gateway blocks oversized requests before the JVM; codecs protect aggregation; routes enforce business quotas; deadlines release slow resources; logging policies keep sensitive data out of collectors and support systems.

| Limit | Unit | Purpose | Does Not Guarantee |
|---|---|---|---|
| Max header/request line | Bytes or chars per server | Blocks oversized headers and URLs | Body size |
| Max HTTP body | Bytes | Blocks payloads exceeding ceiling | Transmission duration |
| Codec `maxInMemorySize` | Buffered bytes | Blocks oversized decoder buffering | All raw streams |
| Multipart memory threshold | Bytes/part | Spills files from memory to disk | Max file upload size |
| Multipart `maxDiskUsagePerPart` | Bytes/part | Bounds temporary files | Total part count |
| Multipart `maxParts` | Part count | Blocks excessive fields/files | Individual file size |
| Pool acquire timeout | Duration | Avoids waiting indefinitely on pool | TCP connect |
| Connect/response timeout | Duration | Avoids hanging at network stages | Whole workflow |
| Reactor timeout | Duration | Publisher deadline or idle silence interval | Rolling back side effects |
| Log allowlist | Field names | Protects secrets/PII | Resource exhaustion |

## 3. Buffer Limits via WebFlux Codecs

WebFlux uses `HttpMessageReader`, `HttpMessageWriter`, and `DataBuffer`. Some decoders must buffer bytes to materialize a `String`, JSON DTO, form field, or complete structure. Many codecs default to around **256 KiB** for aggregated buffers.

When exceeded, a typical exception is:

```text
org.springframework.core.io.buffer.DataBufferLimitException:
Exceeded limit on max bytes to buffer
```

This is a protective mechanism, not an error to suppress by raising limits indefinitely.

### 3.1. Spring Boot 3.5 Properties

```properties
spring.http.codecs.max-in-memory-size=64KB
spring.http.codecs.log-request-details=false
```

In Spring Boot 3.5, `spring.http.codecs.max-in-memory-size` configures the byte limit when codecs buffer data on the WebFlux server and Boot auto-configured `WebClient`s. `log-request-details=false` avoids enabling detailed form/header logging in Boot-configured codecs.

Some older docs use `spring.codec.max-in-memory-size`. **Do not pull properties from a different version** when running Boot 3.5; check the Common Application Properties for your exact version.

The limit above does not replace file quotas, does not bound an infinite event stream, and is not guaranteed to apply if code constructs `WebClient`/codecs manually while bypassing Boot customizers.

### 3.2. Server: Direct Configuration

```java
@Configuration(proxyBeanMethods = false)
class WebFluxCodecConfiguration implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {
        configurer.defaultCodecs()
                .maxInMemorySize(64 * 1024);
    }
}
```

This is a Spring snippet requiring imports. If you only want to customize codecs in a Boot app, do not add `@EnableWebFlux`: that annotation switches WebFlux configuration to Framework-managed mode and causes Boot's WebFlux auto-configuration to back off.

### 3.3. `WebClient`: Limiting Response Aggregation

```java
WebClient client = WebClient.builder()
        .codecs(codecs ->
                codecs.defaultCodecs()
                        .maxInMemorySize(64 * 1024))
        .build();
```

Cases like `bodyToMono(String.class)` or `bodyToMono(Dto.class)` aggregate data and therefore require limits. `bodyToFlux(DataBuffer.class)` streams bytes incrementally; in that case, the application is responsible for tracking total bytes and buffer ownership/release.

Never call `collectList()` on an unbounded event response and assume codecs will protect total heap; codec limits and operator aggregation operate at different layers.

## 4. Raw Body: Checking Total Bytes Actually Received

A handler:

```java
@PostMapping("/raw")
public Mono<Void> process(@RequestBody Flux<DataBuffer> data) {
    return doSomethingWithBytes(data);
}
```

receives a raw buffer stream. Without an aggregating decoder, total body size can vastly exceed `maxInMemorySize`. For small payloads, Spring provides:

```java
Mono<DataBuffer> bounded =
        DataBufferUtils.join(data, 128 * 1024);
```

`DataBufferUtils.join(source, maxByteCount)` joins buffers up to the byte limit. Exceeding it emits `DataBufferLimitException`; on error/cancel, accumulated buffers are released per the API contract. When receiving the **resulting buffer**, the caller must read and release it exactly once if it owns it.

Example reading a buffer after `join`:

```java
return DataBufferUtils.join(body, 128)
        .map(buffer -> {
            try {
                byte[] bytes =
                        new byte[buffer.readableByteCount()];
                buffer.read(bytes);
                return bytes.length;
            }
            finally {
                DataBufferUtils.release(buffer);
            }
        });
```

Use `join` only when the budget is small and aggregation is acceptable. For a 1 GiB file, stream to storage while counting bytes per buffer against a quota, cancel if exceeded, clean up incomplete files, and enforce a hard cap at the gateway. Never call unbounded `collectList()` or `join(source)` on untrusted input.

### 4.1. `Content-Length` Is Not Proof

`Content-Length` can reject requests that declare an oversized body upfront, but cannot serve as **the sole check**:

- HTTP/1.1 can use chunked transfer encoding.
- HTTP/2 and HTTP/3 use different framing mechanisms.
- Reverse proxies can alter transfer encoding.
- Clients or intermediaries can send untrusted declarations.
- Compressed payloads can expand drastically after decompression.

Limits must check actual bytes at the right layer before materializing DTOs/files. When reading archives or compressed content, enforce a separate **post-decompression** limit to prevent decompression/ZIP bombs.

### 4.2. Byte Count Differs from Character Count

UTF-8 does not encode every character in one byte. The letter `é` takes 2 UTF-8 bytes even though its Java `String` length is 1. Many emojis take 4 UTF-8 bytes and 2 UTF-16 code units.

Therefore, `String.length() <= 128` is not a check for `body <= 128 bytes`. Count bytes before decoding whenever quotas are specified in bytes.

## 5. Multipart: Memory, Disk, Headers, and Part Counts

For `multipart/form-data`, Spring Boot 3.5 provides:

```properties
spring.webflux.multipart.max-in-memory-size=64KB
spring.webflux.multipart.max-disk-usage-per-part=5MB
spring.webflux.multipart.max-parts=8
spring.webflux.multipart.max-headers-size=8KB
```

Meaning:

- `max-in-memory-size` caps memory for non-file parts; for file parts, it is the threshold before spilling content to a temporary file on disk.
- `max-disk-usage-per-part` limits disk usage per part written to disk.
- `max-parts` limits the number of parts in a request.
- `max-headers-size` limits memory for each part's header section.

**Wrong:** assuming `max-in-memory-size=64KB` rejects files larger than 64 KB. Files can spill to disk once past the threshold. Therefore, you must also configure disk quotas, file size limits, total request limits, part counts, and retention/cleanup.

Additional upload checks: client-supplied filenames are untrusted; normalize paths and assign server-generated filenames. Verify magic bytes/content format rather than trusting `Content-Type` or file extensions alone. Consider malware scanning and per-tenant quotas.

### 5.1. Streaming with `PartEvent`

Spring WebFlux can process multipart streams via `@RequestBody Flux<PartEvent>`. `FormPartEvent` and `FilePartEvent` carry each part/segment, with `PartEvent.isLast()` marking the end of a part.

Conceptual example:

```java
Flux<PartEvent> events = incomingPartEvents;
return events.windowUntil(PartEvent::isLast)
        .concatMap(window -> handleOnePart(window));
```

`incomingPartEvents` and `handleOnePart` are illustrative abstractions, not a standalone program. When using `PartEvent`, every buffer must be consumed or released, including skipped parts. Hard caps on total bytes and part counts must still be enforced at the appropriate layer.

## 6. Upstream Responses Also Need Limits

A `WebClient` calling an external API can receive a huge or never-ending response:

```java
Mono<String> page = webClient.get()
        .uri("/reports/export")
        .retrieve()
        .bodyToMono(String.class);
```

If the body is too large, codecs throw `DataBufferLimitException`. Do not fix this by setting a massive default `maxInMemorySize` for all clients.

Alternatives:

- Small JSON objects: `bodyToMono(Dto.class)` with an explicit codec cap.
- Large lists: pagination or cursors.
- NDJSON/SSE: `bodyToFlux(T.class)`, processing per item with bounded concurrency.
- Large files: stream `Flux<DataBuffer>` with a byte counter, size cap, and buffer ownership management.
- Error responses: read error codes with a tight cap; never log raw upstream error bodies.

Limiting **responses** is just as important as limiting inbound requests. Partners can send malformed payloads, huge HTML proxy error pages, or files exceeding contracts.

## 7. Do Not Confuse Size Limits with Rate Limits

A 1 KB body is small, yet 100,000 requests/second can still take down a service. Combine:

- Rate limiting per principal/API key/tenant.
- Maximum concurrent connections/requests.
- Bounded queues and pool acquire timeouts.
- Total daily/tenant upload quotas.
- CPU protection for parsers/decompression.
- Circuit breakers or bulkheads for upstream calls.
- Dedicated authentication, authorization, and audit policies.

IP-based rate limiting can be insufficient behind NAT/proxies; `X-Forwarded-For` is trustworthy only when the proxy chain is explicitly configured as trusted. Never treat arbitrary client-provided headers as verified identity.

## 8. Distinguishing Timeouts by Stage

An outbound `WebClient` request can spend time in many places:

```text
subscribe
   |
   +-- DNS lookup
   +-- pool acquire
   +-- TCP connect
   +-- TLS handshake / proxy
   +-- send request
   +-- wait/read response
   +-- decode body
   +-- transform business result
   |
   v
complete / error / cancel
```

| Timeout | Protects | Config Example |
|---|---|---|
| DNS query | Resolver | Netty resolver `queryTimeout` |
| Pending acquire | Connection pool wait | `pendingAcquireTimeout` |
| TCP connect | Socket establishment | `CONNECT_TIMEOUT_MILLIS` |
| TLS handshake | SSL/TLS negotiation | `handshakeTimeout` |
| Proxy connect | Proxy tunnel setup | `connectTimeoutMillis` |
| Response read | Waiting/reading response data | `HttpClient.responseTimeout` |
| Whole operation | Business publisher | Reactor `timeout(Duration)` |
| Inbound slow request | Client sending request too slowly | Gateway/HTTP-server read/idle policy |
| Long-lived stream | Acceptable silence interval | Streaming idle/heartbeat policy |

Pool and transport example:

```java
ConnectionProvider pool =
        ConnectionProvider.builder("partner")
                .maxConnections(40)
                .pendingAcquireMaxCount(80)
                .pendingAcquireTimeout(Duration.ofSeconds(2))
                .build();

HttpClient netty = HttpClient.create(pool)
        .option(
                ChannelOption.CONNECT_TIMEOUT_MILLIS,
                2_000)
        .responseTimeout(Duration.ofSeconds(3));
```

This is an illustrative snippet requiring Reactor Netty/Netty imports. A custom `ConnectionProvider` must be disposed according to the application lifecycle; never create a new provider per request.

### 8.1. Reactor Timeout: `Mono` vs. `Flux` Differences

```java
Mono<Result> result = client.get()
        .uri("/result/{id}", id)
        .retrieve()
        .bodyToMono(Result.class)
        .timeout(Duration.ofSeconds(5));
```

For a single-value `Mono`, `timeout` works well as a deadline to receive the result. However, `Flux.timeout(Duration)` normally limits **the silence interval between signals**, rather than guaranteeing total stream lifetime stays under a cap. A valid 24-hour SSE stream will keep running if heartbeats arrive regularly and no overall deadline exists.

Set dedicated time budgets for finite business requests, and separate idle/heartbeat policies for infinite streams. Never apply the same `timeout(3s)` to JSON APIs and server-sent events.

### 8.2. Timeouts and Cancellation

When downstream times out, it normally cancels the source. This releases sockets/connections/buffers, yet **does not guarantee** that external side effects already executed upstream are rolled back.

For `POST`/payment operations, design idempotency keys and careful retry policies. A connection timeout does not prove the upstream did not process the transaction. Never automatically retry every error on side-effecting requests.

### 8.3. Inbound Slow Clients

`WebClient.responseTimeout` does not protect the HTTP server against inbound clients trickling bytes very slowly. Configure header/body/idle read timeouts at the gateway and server transport, along with max concurrent connections and quotas.

Do not set read timeouts too short for legitimate uploads, nor leave connections hanging indefinitely. Tune policies per endpoint type and client network profiles, and measure actual timed-out requests.

## 9. HTTP Status Codes Should Reflect the Cause

| Scenario | Appropriate Status in Many APIs | Notes |
|---|---|---|
| Request body exceeds quota | `413 Content Too Large` | Map explicitly for consistency |
| Headers too large | `431 Request Header Fields Too Large` | May be blocked by proxy |
| URI too long | `414 URI Too Long` | Do not log raw URI |
| Invalid JSON/form | `400 Bad Request` | Do not turn every decode error into 413 |
| Rate limit exceeded | `429 Too Many Requests` | May include `Retry-After` |
| Gateway timeout calling upstream | `504 Gateway Timeout` | Not every service timeout is 504 |
| Server overloaded | `503 Service Unavailable` | May include `Retry-After` |
| Client disconnects | Response may no longer be writable | Clean up/cancel per lifecycle |

`DataBufferLimitException` does not automatically become HTTP 413 across every version and code path. If the API contract requires 413, handle the exception explicitly and write integration tests.

Client error messages should use short error codes without stack traces, SQL, request bodies, or upstream error payloads.

## 10. Threat Model for Logs

Logs, traces, and metrics may be exported to collectors, monitoring vendors, object storage, support tickets, and broadly accessible dashboards. A token written to logs can outlive the request session.

**Never log by default:**

- `Authorization`, `Proxy-Authorization`, `Cookie`, `Set-Cookie`, `X-API-Key`.
- Access/refresh tokens, passwords, OTPs, session IDs, private keys.
- Payment details, government IDs, emails, phone numbers, or PII without an explicit purpose.
- Request/response bodies or uploaded file contents.
- Raw query strings, full URIs, webhook secrets, signed URLs.
- Unsanitized upstream error bodies or exception messages.
- Arbitrary caller-supplied baggage/tracing metadata.
- User-supplied filenames, User-Agent, or Referer if they may contain private data.

Regexes like "mask `password=...`" cannot protect completely: a new field or new exception format can slip through. Designing an **allowlist**—logging only approved fields—is safer than logging everything and trying to redact afterward.

### 10.1. Metadata Safe to Log

For HTTP requests:

- Method: `GET`, `POST`, etc.
- Route **template**: `/api/orders/{id}`, not `/api/orders/8924`.
- Determined status or outcome.
- Processing duration in milliseconds.
- Service name, environment, instance ID.
- Correlation/trace ID generated by a trusted component.
- Standardized error category or error code.
- Byte count if purposeful and appropriately rounded/bounded.

Never use raw URIs, user IDs, or unique request IDs as high-cardinality **metric tags**. For traces, keep attributes allowlisted and never auto-attach bodies.

### 10.2. Request Detail Logging and Wiretap

Spring Boot 3.5:

```properties
spring.http.codecs.log-request-details=false
logging.level.org.springframework.web=INFO
logging.level.reactor.netty=INFO
```

At `DEBUG`/`TRACE` levels, request detail logging can print form data and headers if explicitly enabled. Disabling this flag does not guarantee custom filters, proxies, or APMs automatically protect data.

Reactor Netty includes wiretap for I/O debugging. Never enable it in production with sensitive data:

```java
HttpClient riskyDiagnosticClient =
        HttpClient.create().wiretap(true);
```

The snippet above only illustrates a risky configuration to recognize, **not** a production setting. Wiretap or network traces can expose headers/bodies. For debugging, use synthetic data, restricted access, and turn it off immediately afterward.

### 10.3. Exception Logs and Error Bodies

Dangerous:

```java
log.error("request failed headers={} response={}",
        headers, rawResponseBody);
```

Better:

```java
log.warn("upstream_failure service={} status={} code={}",
        "billing", upstreamStatus, normalizedErrorCode);
```

The variables are illustrative. `normalizedErrorCode` must come from an application allowlist, not a renamed raw exception message. If stack traces are needed for debugging, ensure exceptions never embed request payloads and restrict log access.

## 11. Correlation IDs and Reactor Context

Request IDs correlate events without logging bodies. However, logging raw attacker-supplied `X-Request-Id` values risks oversized strings, newlines, or log injection.

Validation example:

```java
static String safeRequestId(String value) {
    if (value != null
            && value.length() <= 64
            && value.matches("[A-Za-z0-9-]+")) {
        return value;
    }
    return UUID.randomUUID().toString();
}
```

This is an illustrative snippet. In production, prefer tracing/gateway IDs with a clear trust boundary. Never use a request ID as an authentication credential.

WebFlux runs multiple requests on event-loop threads and hops threads between operators. Hence `ThreadLocal`-based `MDC` does not automatically propagate per subscriber. Use Reactor Context, Micrometer Context Propagation, or version-appropriate OpenTelemetry integration. If bridging `MDC` manually, clean up on complete, error, and cancellation.

## 12. Example `WebFilter` Logging Metadata Only

```java
@Component
public class SafeAccessLogFilter implements WebFilter {

    private static final Logger log =
            LoggerFactory.getLogger(SafeAccessLogFilter.class);

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {
        long started = System.nanoTime();

        String method = exchange.getRequest()
                .getMethod().name();

        return chain.filter(exchange)
                .doFinally(signal -> {
                    Object pattern = exchange.getAttribute(
                            HandlerMapping
                                    .BEST_MATCHING_PATTERN_ATTRIBUTE);
                    String route = pattern == null
                            ? "unmatched" : pattern.toString();

                    HttpStatusCode status =
                            exchange.getResponse().getStatusCode();
                    String code = status == null
                            ? "unknown"
                            : Integer.toString(status.value());

                    long ms = (System.nanoTime() - started)
                            / 1_000_000;

                    log.info(
                            "method={} route={} status={} duration_ms={} signal={}",
                            method, route, code, ms, signal.name());
                });
    }
}
```

This is a Spring snippet requiring corresponding imports. The filter reads only the method, **route pattern**, and status/outcome; it never reads body, query, or headers. `HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE` may be `null` if no route matched.

The status at `doFinally` may not yet reflect the final status set by an outer error handler; therefore emit `"unknown"` when unset rather than assuming every error is 500. To capture final committed status, instrument at the proper server/gateway lifecycle layer.

## 13. Protecting Log Data After Writing

Operational safeguards:

1. Enforce least-privilege access control for reading logs/traces.
2. Encrypt in transit and at rest.
3. Limit retention; avoid keeping debug logs indefinitely.
4. Never copy production payloads into test/support workspaces.
5. Separate security audit logs from general application logs.
6. Maintain an incident response runbook for leaked tokens/PII.
7. Periodically scan log fields, proxy access logs, and APM attributes.
8. Restrict sampling of sensitive traces and sanitize at instrumentation layers.
9. Never enable Logbook/HTTP body recorders unconditionally.
10. Test log policies as part of security QA.

Sampling only reduces frequency; it **does not** make sensitive data safe.

## 14. Runnable Java 17+ Program: Hard Cap, Safe Logging, and Timeout

The project below uses **Spring Boot 3.5.16** and Java 17. Endpoint `POST /api/notes` accepts `text/plain` via `Flux<DataBuffer>`. The app blocks payloads over **128 bytes** using `DataBufferUtils.join(body, 128)` and returns HTTP 413. An outbound client configures a 64 KiB codec cap and Netty connect/response timeouts. The filter logs method, route template, status, and duration without logging bodies.

Integration tests send exactly 128 ASCII bytes, 129 bytes, and 65 `é` characters (130 UTF-8 bytes). The final test verifies `timeout` emits an error using virtual time.

### 14.1. Structure

```text
secure-webflux-limits/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/SecurityLimitApplication.java
    │   ├── java/demo/LimitedNotesController.java
    │   ├── java/demo/SafeAccessLogFilter.java
    │   ├── java/demo/OutboundClientConfiguration.java
    │   └── resources/application.properties
    └── test/
        └── java/demo/SecurityLimitTest.java
```

### 14.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>secure-webflux-limits</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
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

### 14.3. `application.properties`

```properties
spring.application.name=secure-webflux-limits
server.port=8080

spring.http.codecs.max-in-memory-size=64KB
spring.http.codecs.log-request-details=false

spring.webflux.multipart.max-in-memory-size=64KB
spring.webflux.multipart.max-disk-usage-per-part=5MB
spring.webflux.multipart.max-parts=8
spring.webflux.multipart.max-headers-size=8KB

logging.level.org.springframework.web=INFO
logging.level.reactor.netty=INFO
```

Remember that the 128-byte endpoint limit is implemented in controller code; these properties only configure application-wide codec and multipart policies.

### 14.4. `SecurityLimitApplication.java`

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityLimitApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityLimitApplication.class, args);
    }
}
```

### 14.5. `LimitedNotesController.java`

```java
package demo;

import java.nio.charset.StandardCharsets;

import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferLimitException;
import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
public class LimitedNotesController {

    private static final int MAX_BYTES = 128;

    @PostMapping(
            path = "/api/notes",
            consumes = MediaType.TEXT_PLAIN_VALUE)
    public Mono<ResponseEntity<String>> upload(
            @RequestBody Flux<DataBuffer> body) {

        return DataBufferUtils.join(body, MAX_BYTES)
                .map(buffer -> {
                    try {
                        byte[] bytes =
                                new byte[buffer.readableByteCount()];

                        buffer.read(bytes);

                        String note = new String(
                                bytes, StandardCharsets.UTF_8);

                        if (note.isBlank()) {
                            return ResponseEntity.badRequest()
                                    .body("empty note");
                        }

                        // Do not log or echo back the note content.
                        return ResponseEntity.ok(
                                "bytes=" + bytes.length);
                    }
                    finally {
                        DataBufferUtils.release(buffer);
                    }
                })
                .switchIfEmpty(Mono.just(
                        ResponseEntity.badRequest()
                                .body("empty note")))
                .onErrorResume(
                        DataBufferLimitException.class,
                        e -> Mono.just(
                                ResponseEntity
                                        .status(HttpStatus.PAYLOAD_TOO_LARGE)
                                        .body("payload too large")));
    }
}
```

The code counts raw bytes via `DataBufferUtils.join` before decoding to a `String`, so 65 `é` characters equal 130 bytes and are rejected. `finally` releases the resulting buffer. `DataBufferUtils` handles cleaning up accumulated buffers if `join` fails due to error/cancel. The handler returns a safe message containing no body content.

This is a small-note limit example; real applications must add authentication, validation, anti-abuse controls, gateway quotas, and storage security. Never use `join` to buffer large uploads.

### 14.6. `SafeAccessLogFilter.java`

```java
package demo;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatusCode;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.HandlerMapping;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

@Component
public class SafeAccessLogFilter implements WebFilter {

    private static final Logger log =
            LoggerFactory.getLogger(SafeAccessLogFilter.class);

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {
        long started = System.nanoTime();
        String method =
                exchange.getRequest().getMethod().name();

        return chain.filter(exchange)
                .doFinally(signal -> {
                    Object pattern = exchange.getAttribute(
                            HandlerMapping
                                    .BEST_MATCHING_PATTERN_ATTRIBUTE);
                    String route = pattern == null
                            ? "unmatched"
                            : pattern.toString();

                    HttpStatusCode status =
                            exchange.getResponse().getStatusCode();

                    String code = status == null
                            ? "unknown"
                            : Integer.toString(status.value());

                    long ms = (System.nanoTime() - started)
                            / 1_000_000;

                    log.info(
                            "method={} route={} status={} duration_ms={} signal={}",
                            method, route, code, ms, signal.name());
                });
    }
}
```

The filter logs only the route pattern (not the raw URI), method, and metadata. If an exception handler outside the filter decides the status later, the status at `doFinally` may not be the final HTTP status; this is learning instrumentation, not a full replacement for gateway access logs. No request body, headers, or query string appear in this log message.

### 14.7. `OutboundClientConfiguration.java`

```java
package demo;

import java.time.Duration;

import io.netty.channel.ChannelOption;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.netty.http.client.HttpClient;

@Configuration(proxyBeanMethods = false)
public class OutboundClientConfiguration {

    @Bean
    WebClient partnerClient(WebClient.Builder builder) {
        HttpClient netty = HttpClient.create()
                .option(
                        ChannelOption.CONNECT_TIMEOUT_MILLIS,
                        2_000)
                .responseTimeout(Duration.ofSeconds(3));

        return builder
                .baseUrl("https://api.example.org")
                .clientConnector(
                        new ReactorClientHttpConnector(netty))
                .codecs(configurer ->
                        configurer.defaultCodecs()
                                .maxInMemorySize(64 * 1024))
                .build();
    }
}
```

`HttpClient.create()` uses shared Reactor Netty resources by default, avoiding custom pools needing separate disposal in the demo. This bean serves as a configuration example; tests do not contact external hosts. In production, if a dedicated pool is needed, create a `ConnectionProvider` managed by a lifecycle bean or `ReactorResourceFactory`.

### 14.8. `SecurityLimitTest.java`

```java
package demo;

import java.time.Duration;
import java.util.concurrent.TimeoutException;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class SecurityLimitTest {

    @Autowired
    WebTestClient client;

    @Test
    void permitsBodyAtExactByteLimit() {
        client.post()
                .uri("/api/notes")
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("A".repeat(128))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("bytes=128");
    }

    @Test
    void rejectsOneByteOverLimit() {
        client.post()
                .uri("/api/notes")
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("A".repeat(129))
                .exchange()
                .expectStatus().isEqualTo(413)
                .expectBody(String.class)
                .isEqualTo("payload too large");
    }

    @Test
    void unicodeIsMeasuredInUtf8Bytes() {
        client.post()
                .uri("/api/notes")
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("é".repeat(65))
                .exchange()
                .expectStatus().isEqualTo(413);
    }

    @Test
    void timeoutCanBeTestedWithVirtualTime() {
        StepVerifier.withVirtualTime(() ->
                        Mono.delay(Duration.ofSeconds(10))
                                .thenReturn("late")
                                .timeout(Duration.ofSeconds(1)))
                .thenAwait(Duration.ofSeconds(1))
                .expectError(TimeoutException.class)
                .verify();
    }
}
```

Run from the project directory, with JDK 17+ and Maven:

```bash
mvn test
```

**Expected outcome:** four tests PASS, Maven exit code 0. Test 1 confirms status 200 and body `bytes=128`. Tests 2 and 3 confirm status 413, where Test 3 distinguishes UTF-8 bytes from Java `String` length. Test 4 verifies `TimeoutException` with virtual time.

Build/startup logs, random ports, and test timings vary across environments; do not hardcode stdout expectations. Virtual time tests **do not replace** transport timeout tests: to test Netty connect/response timeouts, use a simulated slow server and test pool/DNS/network failures separately.

Start the application:

```bash
mvn spring-boot:run
```

Send a normal note:

```bash
curl -i -X POST "http://localhost:8080/api/notes" -H "Content-Type: text/plain" --data-binary "hello"
```

Expected HTTP status is 200, body:

```text
bytes=5
```

Never put real secrets on the command line; command history or process lists can capture sensitive commands and headers.

## 15. Verifying with Integration Tests and Chaos Tests

Beyond the four demo tests, verify real-world flows:

| Test | Objective |
|---|---|
| 0-byte request or blank note | 400 per contract |
| Request at exact max | Accepted with exact byte count |
| Request at max+1 | 413 |
| Multi-byte Unicode and emojis | Counts bytes rather than characters |
| Chunked input without `Content-Length` | Quota still enforced |
| Compressed input | Does not exceed budget post-decompression |
| Multi-file multipart | Disk quota and max parts |
| Client cancels mid-upload | Buffer/temp file cleanup |
| Oversized upstream response | Codec/streaming cap |
| Upstream slower than response timeout | Stops or errors per policy |
| Saturated connection pool | Pending acquire timeout |
| Very slow client transmission | Gateway/server read timeout |
| Logs with `Authorization`/cookies/body | No secrets present |
| Error body containing a token | Logs only normalized error code |
| Request ID containing newlines | Validated or replaced ID |
| Valid SSE with heartbeats | Not prematurely timed out |

For outbound `WebClient`, use a mock HTTP server/embedded Netty server to simulate slow, oversized, malformed, or dropped responses. Do not rely solely on a fake `ExchangeFunction` when testing TCP timeouts or pools.

For logging, use output capture or a test appender to assert that sample secrets never appear in application logs. Test error paths, `DEBUG`/`TRACE`, upstream exceptions, reverse proxies, and APMs.

## 16. Common Pitfalls

1. **Treating `maxInMemorySize` as a total request cap.** Raw streaming is not automatically bound by codec aggregation limits.
2. **Raising codec limits indefinitely.** Causes heap pressure and invites DoS.
3. **Counting `String.length()` instead of bytes.** Multi-byte UTF-8 breaks byte quotas.
4. **Trusting `Content-Length` alone.** Chunked encoding, proxies, or compressed bodies can differ.
5. **Treating multipart `max-in-memory-size` as max file size.** Files can spill onto disk.
6. **Omitting `max-parts`.** Requests with many fields/files exhaust resources.
7. **Omitting disk limits or temp file cleanup.** Can fill up the filesystem.
8. **Unbounded `join` on large bodies.** Causes memory spikes or `DataBuffer` leaks.
9. **Not releasing owned `DataBuffer`s.** Netty pooled buffers can leak.
10. **Releasing a `DataBuffer` twice.** Incorrect ownership causes errors.
11. **Using `responseTimeout` as a total deadline.** DNS/pool/connect/TLS are separate from response read.
12. **Setting short timeouts on SSE/streaming.** Heartbeats and idle policies must be distinct.
13. **Retrying `POST` after timeouts without idempotency.** Can cause duplicate side effects.
14. **Enabling wiretap in production.** Risks exposing HTTP bodies and credentials.
15. **Logging full headers.** Leaks `Authorization`/Cookie/API keys.
16. **Logging full URIs/queries.** Signed URLs, emails, or tokens may be in query strings.
17. **Logging raw exception messages.** Upstream exceptions may include URLs or bind values.
18. **Logging actual user IDs instead of route patterns.** Leaks data and creates high metric cardinality.
19. **Trusting raw `X-Request-Id`.** Log injection or unbounded strings.
20. **Unbridged `ThreadLocal` MDC.** Can mix requests in reactive chains.
21. **Using one policy for JSON, uploads, and SSE.** Each payload type has a different SLA.
22. **Leaving outbound responses unbounded.** Upstream data is also untrusted.
23. **Assuming `INFO` logging is safe by itself.** Proxies, APMs, or custom filters can still log bodies.
24. **Enabling sampling without masking secrets.** A sampled token is still a leaked token.
25. **Returning stack traces/SQL to clients.** Exposes internals and sensitive data.
26. **Returning 504 for every timeout.** 504 is mainly appropriate for gateway/upstream timeouts.
27. **Ignoring cancellation consequences.** Executed side effects may not roll back.
28. **Not monitoring pool queues/active connections.** Size caps do not resolve resource contention.
29. **Failing to test limit error paths.** May return wrong status codes or leak buffers on failure.
30. **Treating non-blocking as a security control.** Reactive I/O does not replace authentication or quotas.

## 17. Pre-Production Checklist

- Are header/request-line/body limits configured at the edge/gateway?
- Does codec `maxInMemorySize` fit JSON/form aggregation?
- Do raw bodies and streaming uploads have dedicated hard byte limits?
- Does multipart enforce memory/disk/part/header limits and cleanup?
- Are quotas measured in actual bytes rather than `String.length()` or `Content-Length`?
- Is there a post-decompression limit to prevent ZIP bombs?
- Are rate/concurrency quotas appropriate per user/tenant?
- Does `WebClient` have response decode caps, bounded pools, and connect/read timeouts?
- Are inbound slow-client timeouts separated from outbound upstream timeouts?
- Do `Mono`/`Flux` deadlines account for first-signal vs. inter-signal differences?
- Does cancellation clean up resources while side effects remain idempotent?
- Do logs include only method, route pattern, status, duration, and validated IDs?
- Are `Authorization`, cookies, bodies, queries, and exception payloads excluded from logs?
- Are `spring.http.codecs.log-request-details` and Netty wiretap set safely?
- Are metrics/tracing free of PII and high-cardinality user input?
- Are log retention, encryption, access control, and incident response defined?
- Do tests cover 128/129 bytes, Unicode, multipart, slow clients, errors, and logs?
- Are configuration properties verified for the exact Spring Boot/Netty version?

**Key Takeaway:** WebFlux security requires coordinating **content size**, **time limits**, and **log minimization**. `spring.http.codecs.max-in-memory-size` protects codec aggregation, not every request. Multipart needs memory/disk/max-parts limits; raw `DataBuffer` needs a hard byte cap and proper buffer release. Pool/connect/TLS/response timeouts differ from whole-publisher deadlines and do not protect against slow inbound clients. Safe logging relies on metadata allowlists, not logging everything and masking afterward. Verify with integration tests and real resource monitoring.

## References

- Spring Boot 3.5 — [Common Application Properties: HTTP codecs and multipart limits](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html).
- Spring Framework — [WebFlux Config: HTTP message codecs](https://docs.spring.io/spring-framework/reference/web/webflux/config.html).
- Spring Framework — [WebClient Configuration: maxInMemorySize](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html).
- Spring Framework — [DataBufferUtils.join with maxByteCount Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/core/io/buffer/DataBufferUtils.html).
- Spring Framework — [Multipart Content, PartEvent streaming](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/multipart-forms.html).
- Spring Framework — [Reactive Core, DataBuffer and codec limits](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html).
- Spring Boot — [Logging](https://docs.spring.io/spring-boot/3.5/reference/features/logging.html).
- Reactor Netty — [HTTP Client timeout configuration](https://projectreactor.io/docs/netty/release/reference/http-client.html).
- OWASP — [Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html).
- OWASP — [Input Validation Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html).
