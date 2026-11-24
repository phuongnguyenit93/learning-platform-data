# Limiting Body Logging, Observability Cost, and Protecting Sensitive Data in Spring WebFlux

> **Module:** Spring Framework – reactive  
> **Parent Topic:** Observability and Debugging  
> **Focus:** designing logs, metrics, and traces sufficient for incident investigation without storing entire request/response bodies; controlling size, frequency, and cardinality; avoiding exposure of tokens, cookies, PII, payment data, and internal details; understanding `DataBuffer` lifecycle; integrating `WebFilter`, `WebClient` filters, and Micrometer Observation. The sample project uses Spring Boot 4.0.9, Java 17+, JUnit 5, and WebTestClient.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish logs, metrics, and traces, and choose the right signal for an operational question.
2. Log request/response metadata without reading the body.
3. Estimate CPU, memory, network, storage, and indexing costs of body logging.
4. Select which routes/operations are permitted to log bodies; enforce byte caps, sampling, TTL, and retention.
5. Build allowlisted safe projections instead of serializing entire DTOs or relying on regex to mask every secret.
6. Distinguish codec buffering limits from body logger limits.
7. Understand that a request body is a single-use stream; if an interceptor consumes the body, it must replay it and manage `DataBuffer` properly.
8. Use `WebFilter` to log method, route template, status, duration, request ID, and terminal signal.
9. Use `ExchangeFilterFunction` to observe WebClient without consuming the response body or logging sensitive URLs/queries/headers.
10. Use Spring Boot Actuator/Micrometer and control low-cardinality/high-cardinality tags.
11. Protect logs from secret leakage, PII, log injection, unauthorized access, and excessive retention.
12. Write tests proving projections exclude sensitive data, previews respect byte caps, and HTTP responses do not echo secrets.

**Core principle:** observability needs enough context to answer "which request, which route, when, what outcome, and where was it slow". It does not need to store a copy of every piece of data users send. Start with metadata and metrics; collect part of a body only with justification, a clear allowlist, a byte cap, and a short expiration window.

## 2. Three Pillars of Observability

Spring Boot organizes observability into three groups: logs, metrics, and traces.

| Signal | Answers the Question | Example |
| --- | --- | --- |
| Logs | What specific event happened? | `POST /api/orders` returned 422, duration 85 ms |
| Metrics | What are the system trends and magnitude? | p95 latency rising, 5xx rate 3% |
| Traces | Which services/dependencies did a request cross and where did it slow down? | Gateway 8 ms, catalog 20 ms, DB 210 ms |

Do not turn logs into metrics by emitting a log line per measurement. Do not use metrics to store individual request IDs or order IDs. Do not put raw bodies into traces just to inspect payloads later.

### 2.1. A Useful HTTP Log

An operational event usually only needs:
- Timestamp, severity, service, environment, and version.
- Request/correlation ID or trace ID.
- HTTP method and route template.
- Status/outcome and duration.
- Exception type or normalized error code.
- Body byte count if needed.
- Finite code-defined operation label.

Example:

~~~json
{
  "event": "http_request_completed",
  "requestId": "[a9c4e]",
  "method": "POST",
  "route": "/api/orders",
  "status": 202,
  "durationMs": 84,
  "outcome": "SUCCESS"
}
~~~

This log contains no raw path parameters, query strings, cookies, authorization headers, or bodies. Route templates collapse `/api/orders/1` and `/api/orders/2` into the same route.

### 2.2. Do Not Use Thread ID as a Correlation ID

WebFlux can process a single request across multiple threads. Thread names are not enough to stitch logs of the same request together. Spring provides a request-specific log ID and `ServerWebExchange.getLogPrefix()` to prefix logs. WebClient also has a log prefix on `ClientRequest`.

Use framework-managed request IDs/trace context rather than assuming a request always runs on one thread.

### 2.3. Operational Logs Differ from Audit Trails

| Type | Purpose | Example |
| --- | --- | --- |
| Operational log | Debugging and operations | Slow request, timeout, retry |
| Security event log | Detecting suspicious behavior | Access denied, login failure |
| Audit trail | Recording verifiable changes | Who approved a payment |
| Business event | Tracking business state | `order_created`, `payment_authorized` |

Do not use DEBUG logs as an audit trail. Auditing requires clear schemas, access controls, retention, integrity, and transactional semantics. If an audit record must persist atomically with a business transaction, consider a transactional outbox or an equivalent durable mechanism.

## 3. Cost of Full Body Logging

### 3.1. Estimating Volume

\[
\text{bytes/day} =
\text{requests/second}
\times \text{average logged bytes}
\times 86{,}400
\]

For example, 400 requests/second, with each request adding 1 KiB of body log:

\[
400 \times 1{,}024 \times 86{,}400
= 35{,}389{,}440{,}000
\]

That equals roughly **35.4 GB/day** of raw data, not counting response bodies, multiple replicas, metadata, indexes, replication, and backups.

### 3.2. Costs Are Not Just Disk

| Component | Why Cost Increases |
| --- | --- |
| CPU | JSON serialization, redaction, formatting, encoding, and compression |
| Heap/direct memory | Buffering bodies, copying byte arrays, appender queues |
| Event loop | Synchronous logging or serializing large payloads consumes processing time |
| Network | Shipping large logs from instances to collectors |
| Storage/index | Storage size and indexed field growth |
| Tracing backend | Large span attributes, excessive spans, and improper sampling |
| Cardinality | Dynamic tags spawning many time series |
| Personnel | Excessive payload noise obscuring important signals |

An async appender can reduce direct I/O on request threads, but typically has a bounded queue and a full-queue policy. Async logging does not make large payloads free; if producers outpace consumers, queues still fill or logs get dropped per policy.

### 3.3. Body Logging Expands the Leakage Surface

Request bodies can contain:
- Passwords, OTPs, recovery codes.
- Bearer/access/refresh tokens, API keys.
- Session IDs, cookies, CSRF tokens.
- Emails, phone numbers, addresses, or personal identifiers.
- Health information.
- Bank account numbers, payment cards, CVVs.
- Internal documents, prompts, customer content, or contract data.
- File uploads, binaries, and chat content.

Logs can be shipped to collectors, dashboards, APMs, SIEMs, backups, and support environments. Every copy is another place to protect. A token written to logs may remain valid long after the request finishes.

## 4. Policy for Choosing What Data to Log

### 4.1. Metadata-Only Is the Default

For most routes, log only method, route template, status/outcome, duration, request ID/trace ID, exception type/error code, and code-defined operation label.

Do not log by default:
- `Authorization`, `Cookie`, `Set-Cookie`.
- Query strings that may contain tokens, emails, or personal data.
- Full URIs if paths include IDs or sensitive details.
- Raw request/response bodies.
- Raw exception messages that may contain URLs, SQL parameters, or credentials.

### 4.2. Allowlists Are Better Than Denylists

A denylist like "mask password, token, email" can miss new fields such as `clientSecret`, `refresh_token`, `privateKey`, `bankAccount`, or domain-specific fields.

An allowlist logs only approved fields:

~~~java
public record OrderLogProjection(
    int itemCount,
    long totalQuantity
) {}
~~~

This projection has no email, payment token, SKU, note, or raw order body. If `cardNumber` is later added to the DTO, the projection will not automatically log that new field.

### 4.3. Do Not Rely Solely on Regex to Redact JSON

Regexes can miss nested objects/arrays, differently cased field names, aliases such as `access_token`, encoded values, or tokens inside URLs/headers/free text.

If part of a payload must be kept, parse against a known schema, build a dedicated log DTO/projection, and serialize the projection. Never serialize an entire object and try to scrub secrets at the end.

### 4.4. Byte-Bounded Body Previews

Once you have a safe projection and genuinely need a preview:
- Enable only for allowlisted routes/operations.
- Accept only known media types and schemas.
- Enforce a small byte cap, such as 128–512 bytes.
- Mark `truncated=true` and record the original byte count.
- Never parse a truncated preview as complete JSON.
- Never log binary, multipart, file upload, SSE, NDJSON, or unbounded stream bodies.
- Use sampling and short expiration windows for debugging.

The byte cap must be measured in UTF-8 bytes, not just character count. A single Vietnamese character can take multiple bytes. The sample code in section 11 splits on UTF-8 boundaries and accepts only safe projections.

### 4.5. Do Not Enable Request-Details Logging Globally in Production

Spring WebFlux has an `enableLoggingRequestDetails(true)` option for codecs. DEBUG/TRACE can log more request details; form parameters and headers are masked by default, but configurations enabling full logging can expose data.

Do not use this global setting as a production body-logging solution. If temporary debugging is required, specify the logger, route, permitted data, shutoff time, and collector/APM policy.

## 5. Bodies in WebFlux Are Streams

### 5.1. Request Bodies Are Consumed Once

In WebFlux, a request body is usually a `Flux<DataBuffer>`. When a codec/controller reads the body, buffers are consumed to decode DTOs. A filter that subscribes to or reads the body before the controller can leave the controller with no data.

~~~java
// Anti-pattern: creating a separate subscription and consuming the body.
exchange.getRequest().getBody().subscribe(buffer -> {
    // log raw buffer
});
return chain.filter(exchange);
~~~

This detaches a subscription from the filter chain, does not replay the body, and can cause data loss or buffer leaks.

### 5.2. DataBuffer Can Be Pooled and Reference-Counted

On Netty, `DataBuffer` can wrap a pooled `ByteBuf`. Retained buffers must be released at the right time; buffers discarded due to filtering, cancellation, or error also need cleanup.

When reading buffers manually, you must understand:
- Who owns the buffer and when it is released.
- Whether `retain()` is needed.
- Whether buffer positions are modified.
- How downstream receives the data again.
- Whether errors/cancellations release unconsumed buffers.

Spring provides `DataBufferUtils` for joining, releasing, retaining, and manipulating byte streams. Even using the utility properly does not automatically solve request body replay.

### 5.3. If You Truly Must Capture a Body

A complete implementation typically must:
1. Check route, media type, content length, and policy before reading.
2. Aggregate with a byte limit; never join bodies unboundedly.
3. If the body exceeds the cap, skip capture per policy while ensuring the request is still processed properly.
4. Use `ServerHttpRequestDecorator` to replay data downstream.
5. Release original and retained buffers according to lifecycle.
6. Clean up on complete, error, and cancel.
7. Handle streaming bodies and resubscription cases.
8. Test body decoders, oversized requests, and pooled-buffer leaks.

This is error-prone infrastructure code. For business JSON, a simpler approach is usually logging a safe projection after the controller has decoded the DTO rather than intercepting raw bytes.

### 5.4. WebClient Filters Must Preserve the Response Body

`ExchangeFilterFunction` can observe request/response metadata. If a filter reads the `ClientResponse` body to log it without propagating/replaying the consumed body, downstream calls such as `bodyToMono()` will receive no data.

The metadata-only filter in this lesson does not subscribe to the body and therefore does not alter its lifecycle.

### 5.5. `maxInMemorySize` Is Not a Body Logger Cap

`maxInMemorySize` limits how much data codecs can buffer in certain decode/aggregate operations. It does not automatically limit byte arrays in custom loggers, appender queues, trace attributes, or body copies created by filters. Configure codec limits and logging byte caps as two separate controls.

## 6. Structured Logging and Preventing Log Injection

### 6.1. Use Fixed Message Templates

~~~java
log.warn(
    "request_rejected requestId={} route={} reasonCode={}",
    requestId, route, reasonCode);
~~~

Avoid direct string concatenation:

~~~java
// Avoid: user input may inject CR/LF into logs.
log.warn("Request failed: " + userInput);
~~~

Parameterized logging does not automatically eliminate log injection. If untrusted data must be logged, sanitize/encode control characters, use a standard JSON encoder, and cap field lengths.

### 6.2. Do Not Log Raw Exception Messages Unconditionally

Exception messages can include full URLs/queries, SQL statements/parameters, usernames/emails, internal paths, or headers/credentials attached by SDKs.

In request summaries, exception type and error code are usually sufficient. Full stack traces can be written to a more restricted sink when justified. Never send stack traces to clients.

### 6.3. Correlation IDs and Session Correlation

- Use server- or tracing-framework-managed request IDs/trace IDs.
- If accepting `X-Request-ID` from clients, validate length/characters and reject CR/LF.
- Never use raw session IDs as correlation keys.
- If session correlation is needed, consider HMAC/hashing with managed keys and rotation.
- Never promote trace IDs, request IDs, user IDs, or order IDs into metric tags.

## 7. Limiting Metrics and Traces Costs

### 7.1. Cardinality

A metric is distinguished by its tag combinations. For example:
- 6 HTTP methods.
- 30 route templates.
- 6 status groups.
- 4 regions.

The theoretical number of combinations is \(6 \times 30 \times 6 \times 4 = 4{,}320\) time series. Adding 100,000 user IDs can multiply cardinality dramatically and exhaust monitoring backend RAM, CPU, storage, and query time.

### 7.2. Low Cardinality and High Cardinality

Spring Boot/Micrometer distinguishes:
- **Low cardinality:** finite value sets such as method, route template, outcome, status group.
- **High cardinality:** nearly unbounded values such as user ID, order ID, or request ID.

In Micrometer Observation, low-cardinality key-values are added to metrics and traces; high-cardinality key-values are added only to traces. That does not mean all high-cardinality data is safe in traces: privacy, access control, retention, and trace cost still require governance.

### 7.3. Never Use These Values as Metric Tags

- Full URLs or query strings.
- Raw paths containing order/customer IDs.
- Emails, usernames, phone numbers.
- Request/trace/session IDs.
- Search terms, prompts, or body content.
- Exception messages.
- Arbitrary header values.
- Tokens or secrets.

Use URI templates like `/api/orders/{id}` instead of `/api/orders/839174`. Use status/outcome instead of exception messages. Use finite, code-defined operation names.

### 7.4. Spring Boot HTTP Observations

Spring Boot automatically instruments WebFlux server requests with `http.server.requests`. WebClient is instrumented when built from Spring Boot's auto-configured `WebClient.Builder`; the default metric is `http.client.requests`.

Avoid adding a manual timer on the same request just to record duration again, unless measuring a distinct, clearly named boundary. Duplicate instrumentation can cause dashboards to double-count.

### 7.5. Tracing Sampling

A trace can carry many spans, tags, and events. If 100% of traffic creates traces in a high-RPS system, costs grow rapidly.

Common policies:
- Sample steady success traffic at a low rate.
- Keep a higher rate for errors/high-latency requests via tail sampling if the collector supports it.
- Never record sensitive bodies/headers in span attributes.
- Cap span event counts and attribute lengths.
- Keep trace IDs to correlate with logs rather than copying raw payloads into traces.

Sampling does not replace mandatory security event logging; security/audit events must follow their own policy.

## 8. Sampling, Rate Limiting, and Retention

### 8.1. A Sample Operational Policy

| Route/Traffic | Metadata | Body Preview |
| --- | --- | --- |
| Health/readiness | Metrics are usually sufficient | No |
| Standard CRUD | Yes, at an appropriate level | No |
| Login/token/credential | Selective security events | No |
| Payment/PII/health | Minimal metadata + controlled audit | No |
| Upload/multipart/binary | Byte count, duration, outcome | No |
| SSE/NDJSON/WebSocket | Connect/disconnect, duration, error, event count | Do not aggregate |
| Allowlisted debug routes | Yes, sampled | Safe projection with byte cap |

### 8.2. Sample Before Reading Bodies

If you read and serialize a body before deciding to drop the log, the memory/CPU cost has already been paid. Decide sampling and route allowlists before capture.

Do not sample mandatory audit/security events. For high-volume success traffic, sample metadata by rate; for repeated errors, rate-limit logs by fingerprint while keeping counters/metrics intact.

### 8.3. Retention and Access Control

- Separate retention for operational logs, security logs, audits, and traces.
- Restrict reading sensitive logs to authorized personnel only.
- Use TLS when shipping logs over untrusted networks.
- Encrypt storage/backups.
- Audit access to sensitive logs.
- Purge debug dumps, exports, and backups upon expiration per policy.
- Enforce access control on dashboards, query APIs, exports, and backups.

## 9. Logging Metadata in WebFlux with `WebFilter`

A `WebFilter` can observe the request lifecycle without reading the body. For example, logging request ID, method, route template, status, terminal signal, and duration.

~~~java
package com.example.observability;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.HandlerMapping;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

@Component
@Order(Ordered.LOWEST_PRECEDENCE)
public class RequestSummaryWebFilter implements WebFilter {

    private static final Logger log =
        LoggerFactory.getLogger(RequestSummaryWebFilter.class);

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        long startedAt = System.nanoTime();
        String requestId = exchange.getLogPrefix();
        String method = exchange.getRequest().getMethod().name();

        return chain.filter(exchange)
            .doOnError(error ->
                log.warn(
                    "http_request_failed requestId={} method={} exceptionType={}",
                    requestId,
                    method,
                    error.getClass().getSimpleName()))
            .doFinally(signal -> {
                String route = exchange.getAttribute(
                    HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE);

                if (route == null) {
                    route = "unmatched";
                }

                var status = exchange.getResponse().getStatusCode();
                String statusValue =
                    status == null ? "unset" : Integer.toString(status.value());

                long durationMs =
                    (System.nanoTime() - startedAt) / 1_000_000;

                log.info(
                    "http_request_completed requestId={} method={} route={} status={} signal={} durationMs={}",
                    requestId,
                    method,
                    route,
                    statusValue,
                    signal.name(),
                    durationMs);
            });
    }
}
~~~

Key points:
- The filter does not call `getBody()` and does not consume the request body.
- `getLogPrefix()` uses request-specific identity; it does not rely on thread ID.
- `BEST_MATCHING_PATTERN_ATTRIBUTE` provides the route template such as `/api/orders/{id}` once a handler is matched.
- Does not log full URIs, query strings, headers, cookies, or exception messages.
- `doFinally` logs `ON_COMPLETE`, `ON_ERROR`, or `CANCEL`; cancellation does not mean a successful response.
- Status may still be unset if an error occurs before response commit, so the example logs `unset`.

This filter does not replace `http.server.requests` metrics or tracing.

## 10. Logging Outbound Metadata with a WebClient Filter

An outbound filter can record an operation label, method, status, and duration. Attach a code-defined operation name instead of logging full URLs/queries.

~~~java
package com.example.observability;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.ExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
public class CatalogWebClientConfiguration {

    private static final Logger log =
        LoggerFactory.getLogger(CatalogWebClientConfiguration.class);

    @Bean
    WebClient catalogWebClient(WebClient.Builder builder) {
        ExchangeFilterFunction metadataLog = (request, next) -> {
            long startedAt = System.nanoTime();

            String operation = request.attribute("observability.operation")
                .map(Object::toString)
                .map(SafeLogValues::operation)
                .orElse("unclassified");

            return next.exchange(request)
                .doOnNext(response -> {
                    long durationMs =
                        (System.nanoTime() - startedAt) / 1_000_000;

                    log.info(
                        "outbound_http operation={} method={} status={} durationMs={}",
                        operation,
                        request.method().name(),
                        response.statusCode().value(),
                        durationMs);
                })
                .doOnError(error -> {
                    long durationMs =
                        (System.nanoTime() - startedAt) / 1_000_000;

                    log.warn(
                        "outbound_http_failed operation={} method={} exceptionType={} durationMs={}",
                        operation,
                        request.method().name(),
                        error.getClass().getSimpleName(),
                        durationMs);
                });
        };

        return builder.filter(metadataLog).build();
    }
}
~~~

When calling WebClient:

~~~java
return catalogWebClient.get()
    .uri("/items/{id}", id)
    .attribute("observability.operation", "catalog.item_lookup")
    .retrieve()
    .bodyToMono(ItemView.class);
~~~

Never log `request.url()` unconditionally. URLs can contain IDs, queries, user info, or tokens. This filter does not read the response body, so downstream `bodyToMono()` still consumes the body normally.

## 11. Safe Projections and Byte-Bounded Body Previews

### 11.1. Request DTOs Can Contain Secrets

~~~java
package com.example.observability;

import java.util.List;

public record CreateOrderRequest(
    String customerEmail,
    String paymentToken,
    List<LineItem> items,
    String customerNote
) {}

record LineItem(String sku, int quantity) {}
~~~

Never serialize the entire `CreateOrderRequest` into logs. Create a separate projection:

~~~java
package com.example.observability;

import java.util.List;
import java.util.Objects;

public record OrderLogProjection(
    int itemCount,
    long totalQuantity
) {
    public static OrderLogProjection from(
            CreateOrderRequest request) {

        List<LineItem> items =
            request.items() == null ? List.of() : request.items();

        long totalQuantity = items.stream()
            .filter(Objects::nonNull)
            .mapToLong(LineItem::quantity)
            .sum();

        return new OrderLogProjection(
            items.size(),
            totalQuantity);
    }
}
~~~

The projection contains no email, payment token, SKU, or note. If `cardNumber` is later added to the DTO, the projection will not automatically log the new field.

### 11.2. Utility to Cap Previews by UTF-8 Bytes

~~~java
package com.example.observability;

import java.nio.charset.StandardCharsets;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

public final class SafeBodyPreview {

    private SafeBodyPreview() {}

    public record Preview(
        String text,
        int originalBytes,
        boolean truncated
    ) {}

    public static Preview from(
            Object allowlistedProjection,
            ObjectMapper mapper,
            int maxBytes) throws JsonProcessingException {

        if (maxBytes < 1) {
            throw new IllegalArgumentException(
                "maxBytes must be positive");
        }

        // Pass only the allowlisted projection, never the raw DTO.
        byte[] json = mapper.writeValueAsBytes(allowlistedProjection);
        int end = Math.min(json.length, maxBytes);

        // Do not split inside a multi-byte UTF-8 character.
        while (end > 0
                && end < json.length
                && (json[end] & 0xC0) == 0x80) {
            end--;
        }

        String preview = new String(
            json, 0, end, StandardCharsets.UTF_8);

        return new Preview(
            preview,
            json.length,
            json.length > maxBytes);
    }
}
~~~

`Preview.text` can be an incomplete JSON prefix when truncated; treat it as a human-readable preview, not valid JSON to parse again. `originalBytes` is the projection size before truncation. Raw bodies must never be passed into this utility.

### 11.3. Safe Label for WebClient Operations

~~~java
package com.example.observability;

public final class SafeLogValues {

    private SafeLogValues() {}

    public static String operation(String raw) {
        if (raw == null || raw.isBlank()) {
            return "unclassified";
        }

        String safe = raw.replaceAll(
            "[^A-Za-z0-9_.-]", "_");

        return safe.substring(0, Math.min(60, safe.length()));
    }
}
~~~

In production, operation labels should be code-defined constants. This function is an extra safeguard if attributes originate elsewhere; it is not a raw user-input redaction mechanism.

## 12. Configuring Actuator and Micrometer

### 12.1. Dependencies

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

When creating WebClient, inject Spring Boot's configured `WebClient.Builder` to preserve default instrumentation. Creating a standalone `WebClient.create()` can bypass customizers/observations attached to the builder by Boot.

### 12.2. `application.properties`

~~~properties
spring.application.name=webflux-safe-observability

management.endpoints.web.exposure.include=health,info,metrics,prometheus
management.metrics.distribution.percentiles-histogram.http.server.requests=true

logging.level.com.example.observability=INFO
logging.level.org.springframework.web=INFO
~~~

Actuator endpoints must be protected with appropriate authentication and network policies; never expose metrics/prometheus publicly to the Internet without controls.

### 12.3. Useful Meters

| Meter / Group | Question |
| --- | --- |
| `http.server.requests` | How long do inbound requests take, and what are their statuses/outcomes? |
| `http.client.requests` | Where are outbound WebClient calls slow or failing? |
| JVM memory/buffer pools | Is heap/direct memory growing? |
| Process CPU/file descriptors | Is the instance approaching resource limits? |
| Logback event metrics | Are log rates or error logs spiking? |
| Custom preview count | How many previews are logged/truncated? |

If custom metrics are needed, use bounded tags such as `operation`, `outcome`, `route`. Never use bodies, user IDs, order IDs, or request IDs as tags.

## 13. Sampling, Rate Limiting, and Retention

- Log metadata for all 5xx responses if operational policy requires it.
- Sample a small fraction of success traffic on high-volume routes.
- Keep mandatory security/audit events under their own policy; do not drop them due to trace sampling.
- Rate-limit logs by fingerprint when an error repeats continuously, while keeping metric counters to track total occurrences.
- Decide sampling before reading bodies; if you serialize a body first and then drop the log, memory/CPU cost has already occurred.
- Debug capture must have a route allowlist, byte cap, end time, and accountable owner.
- Separate retention for operational logs, security logs, audits, and traces.
- Allow only authorized personnel to read sensitive logs.
- Use TLS when transporting logs over untrusted networks; encrypt storage/backups.
- Audit access to sensitive logs.
- Delete debug dumps, exports, and backups upon expiration per policy.

## 14. Incident Investigation Scenario Without Raw Bodies

Suppose p99 for `POST /api/orders` jumps from 150 ms to 2 seconds:

1. Open the `http.server.requests` dashboard and filter by route `/api/orders` and status.
2. Identify the start time and deployment version.
3. Pick a representative trace for a slow request.
4. Inspect outbound/database spans to see which dependency took the time.
5. Use request ID/trace ID to look up structured logs for the same request.
6. Check error code, duration, operation label, and byte count.
7. If large payloads are suspected, compare request byte distributions or allowlisted `itemCount`/`totalQuantity`.
8. Only enable temporary capture for approved routes/test accounts if metadata is insufficient.
9. Remove/expire the capture after the investigation.

Traces and metrics show where things are slow; metadata logs tie requests to outcomes. Raw bodies usually do not explain why a database query took 1.8 seconds.

## 15. Runnable Project: Spring Boot 4.0.9 + Java 17+

The project demonstrates:
- `WebFilter` logging HTTP metadata.
- `WebClient` filter logging outbound metadata without reading the response body.
- Order request containing email/token/note, yet only logging the `itemCount` and `totalQuantity` projection.
- Safe preview capped at 128 bytes.
- Tests confirming projections exclude secrets, truncation respects byte boundaries, and the API does not echo sensitive fields.

This is an observability demo. It does not enable raw body logging and does not manually read `DataBuffer`.

### 15.1. Structure

~~~text
webflux-safe-observability/
├── pom.xml
├── src/main/resources/application.properties
├── src/main/java/com/example/observability/
│   ├── ObservabilityApplication.java
│   ├── RequestSummaryWebFilter.java
│   ├── CatalogWebClientConfiguration.java
│   ├── SafeLogValues.java
│   ├── SafeBodyPreview.java
│   ├── CreateOrderRequest.java
│   ├── OrderLogProjection.java
│   ├── OrderResponse.java
│   ├── OrderService.java
│   └── OrderController.java
└── src/test/java/com/example/observability/
    ├── SafeBodyPreviewTest.java
    └── OrderApiIntegrationTest.java
~~~

### 15.2. `pom.xml`

Spring Boot 4.0.9 and Java 17+; dependency versions are managed by the Boot parent.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.0.9</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>webflux-safe-observability</artifactId>
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
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-registry-prometheus</artifactId>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux-test</artifactId>
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
~~~

### 15.3. `ObservabilityApplication.java`

~~~java
package com.example.observability;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ObservabilityApplication {

    public static void main(String[] args) {
        SpringApplication.run(ObservabilityApplication.class, args);
    }
}
~~~

### 15.4. `RequestSummaryWebFilter.java`

~~~java
package com.example.observability;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.HandlerMapping;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

@Component
@Order(Ordered.LOWEST_PRECEDENCE)
public class RequestSummaryWebFilter implements WebFilter {

    private static final Logger log =
        LoggerFactory.getLogger(RequestSummaryWebFilter.class);

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        long startedAt = System.nanoTime();
        String requestId = exchange.getLogPrefix();
        String method = exchange.getRequest().getMethod().name();

        return chain.filter(exchange)
            .doOnError(error ->
                log.warn(
                    "http_request_failed requestId={} method={} exceptionType={}",
                    requestId,
                    method,
                    error.getClass().getSimpleName()))
            .doFinally(signal -> {
                String route = exchange.getAttribute(
                    HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE);

                if (route == null) {
                    route = "unmatched";
                }

                var status = exchange.getResponse().getStatusCode();
                String statusValue =
                    status == null ? "unset" : Integer.toString(status.value());

                long durationMs =
                    (System.nanoTime() - startedAt) / 1_000_000;

                log.info(
                    "http_request_completed requestId={} method={} route={} status={} signal={} durationMs={}",
                    requestId,
                    method,
                    route,
                    statusValue,
                    signal.name(),
                    durationMs);
            });
    }
}
~~~

### 15.5. `CatalogWebClientConfiguration.java`

~~~java
package com.example.observability;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.ExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
public class CatalogWebClientConfiguration {

    private static final Logger log =
        LoggerFactory.getLogger(CatalogWebClientConfiguration.class);

    @Bean
    WebClient catalogWebClient(WebClient.Builder builder) {
        ExchangeFilterFunction metadataLog = (request, next) -> {
            long startedAt = System.nanoTime();

            String operation = request.attribute("observability.operation")
                .map(Object::toString)
                .map(SafeLogValues::operation)
                .orElse("unclassified");

            return next.exchange(request)
                .doOnNext(response -> {
                    long durationMs =
                        (System.nanoTime() - startedAt) / 1_000_000;

                    log.info(
                        "outbound_http operation={} method={} status={} durationMs={}",
                        operation,
                        request.method().name(),
                        response.statusCode().value(),
                        durationMs);
                })
                .doOnError(error -> {
                    long durationMs =
                        (System.nanoTime() - startedAt) / 1_000_000;

                    log.warn(
                        "outbound_http_failed operation={} method={} exceptionType={} durationMs={}",
                        operation,
                        request.method().name(),
                        error.getClass().getSimpleName(),
                        durationMs);
                });
        };

        return builder.filter(metadataLog).build();
    }
}
~~~

### 15.6. `SafeLogValues.java`

~~~java
package com.example.observability;

public final class SafeLogValues {

    private SafeLogValues() {}

    public static String operation(String raw) {
        if (raw == null || raw.isBlank()) {
            return "unclassified";
        }

        String safe = raw.replaceAll(
            "[^A-Za-z0-9_.-]", "_");

        return safe.substring(0, Math.min(60, safe.length()));
    }
}
~~~

### 15.7. `CreateOrderRequest.java`

~~~java
package com.example.observability;

import java.util.List;

public record CreateOrderRequest(
    String customerEmail,
    String paymentToken,
    List<LineItem> items,
    String customerNote
) {}

record LineItem(String sku, int quantity) {}
~~~

### 15.8. `OrderLogProjection.java`

~~~java
package com.example.observability;

import java.util.List;
import java.util.Objects;

public record OrderLogProjection(
    int itemCount,
    long totalQuantity
) {
    public static OrderLogProjection from(
            CreateOrderRequest request) {

        List<LineItem> items =
            request.items() == null ? List.of() : request.items();

        long totalQuantity = items.stream()
            .filter(Objects::nonNull)
            .mapToLong(LineItem::quantity)
            .sum();

        return new OrderLogProjection(
            items.size(),
            totalQuantity);
    }
}
~~~

### 15.9. `SafeBodyPreview.java`

~~~java
package com.example.observability;

import java.nio.charset.StandardCharsets;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

public final class SafeBodyPreview {

    private SafeBodyPreview() {}

    public record Preview(
        String text,
        int originalBytes,
        boolean truncated
    ) {}

    public static Preview from(
            Object allowlistedProjection,
            ObjectMapper mapper,
            int maxBytes) throws JsonProcessingException {

        if (maxBytes < 1) {
            throw new IllegalArgumentException(
                "maxBytes must be positive");
        }

        byte[] json = mapper.writeValueAsBytes(allowlistedProjection);
        int end = Math.min(json.length, maxBytes);

        while (end > 0
                && end < json.length
                && (json[end] & 0xC0) == 0x80) {
            end--;
        }

        String preview = new String(
            json, 0, end, StandardCharsets.UTF_8);

        return new Preview(
            preview,
            json.length,
            json.length > maxBytes);
    }
}
~~~

### 15.10. `OrderResponse.java`

~~~java
package com.example.observability;

public record OrderResponse(
    String id,
    int itemCount
) {}
~~~

### 15.11. `OrderService.java`

~~~java
package com.example.observability;

import java.util.UUID;

import com.fasterxml.jackson.databind.ObjectMapper;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;

@Service
public class OrderService {

    private static final Logger log =
        LoggerFactory.getLogger(OrderService.class);

    private final ObjectMapper objectMapper;

    public OrderService(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    public Mono<OrderResponse> create(
            CreateOrderRequest request,
            String requestId) {

        return Mono.fromCallable(() -> {
            OrderLogProjection projection =
                OrderLogProjection.from(request);

            SafeBodyPreview.Preview preview =
                SafeBodyPreview.from(
                    projection, objectMapper, 128);

            log.info(
                "order_body_summary requestId={} preview={} originalBytes={} truncated={}",
                requestId,
                preview.text(),
                preview.originalBytes(),
                preview.truncated());

            return new OrderResponse(
                UUID.randomUUID().toString(),
                projection.itemCount());
        });
    }
}
~~~

### 15.12. `OrderController.java`

~~~java
package com.example.observability;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderService service;

    public OrderController(OrderService service) {
        this.service = service;
    }

    @PostMapping
    public Mono<ResponseEntity<OrderResponse>> create(
            @RequestBody CreateOrderRequest request,
            ServerWebExchange exchange) {

        return service.create(request, exchange.getLogPrefix())
            .map(response ->
                ResponseEntity.status(HttpStatus.ACCEPTED)
                    .body(response));
    }
}
~~~

### 15.13. `SafeBodyPreviewTest.java`

~~~java
package com.example.observability;

import java.nio.charset.StandardCharsets;
import java.util.List;

import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SafeBodyPreviewTest {

    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void projectionExcludesSensitiveRequestFields()
            throws Exception {

        CreateOrderRequest request = new CreateOrderRequest(
            "alice@example.test",
            "secret-payment-token",
            List.of(new LineItem("PRIVATE-SKU", 2)),
            "confidential customer note");

        OrderLogProjection projection =
            OrderLogProjection.from(request);

        SafeBodyPreview.Preview preview =
            SafeBodyPreview.from(projection, mapper, 128);

        assertTrue(preview.text().contains("itemCount"));
        assertTrue(preview.text().contains("totalQuantity"));
        assertFalse(preview.text().contains("alice@example.test"));
        assertFalse(preview.text().contains("secret-payment-token"));
        assertFalse(preview.text().contains("PRIVATE-SKU"));
        assertFalse(preview.text().contains("confidential customer note"));
    }

    @Test
    void previewDoesNotExceedUtf8ByteLimit()
            throws Exception {

        record SafeProjection(String label) {}

        SafeProjection projection =
            new SafeProjection("x".repeat(500));

        SafeBodyPreview.Preview preview =
            SafeBodyPreview.from(projection, mapper, 64);

        assertTrue(preview.truncated());
        assertTrue(preview.originalBytes() > 64);
        assertTrue(
            preview.text().getBytes(StandardCharsets.UTF_8).length <= 64);
    }

    @Test
    void operationLabelCannotInjectNewLogLines() {
        String safe =
            SafeLogValues.operation("catalog.lookup\nERROR forged");

        assertFalse(safe.contains("\n"));
        assertFalse(safe.contains("\r"));
        assertTrue(safe.matches("[A-Za-z0-9_.-]+"));
    }
}
~~~

The second test uses a simulated safe projection with a long string to verify the byte cap. In production, projections must be allowlisted before calling the utility; a byte cap does not replace redaction.

### 15.14. `OrderApiIntegrationTest.java`

~~~java
package com.example.observability;

import java.time.Duration;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class OrderApiIntegrationTest {

    @Value("${local.server.port}")
    int port;

    private WebTestClient http() {
        return WebTestClient.bindToServer()
            .baseUrl("http://localhost:" + port)
            .responseTimeout(Duration.ofSeconds(5))
            .build();
    }

    @Test
    void createOrderReturnsSummaryWithoutEchoingSecrets() {
        CreateOrderRequest request = new CreateOrderRequest(
            "alice@example.test",
            "secret-payment-token",
            List.of(new LineItem("PRIVATE-SKU", 2)),
            "confidential customer note");

        http().post()
            .uri("/api/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(request)
            .exchange()
            .expectStatus().isAccepted()
            .expectHeader()
                .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
                .jsonPath("$.id").isNotEmpty()
                .jsonPath("$.itemCount").isEqualTo(1);
    }
}
~~~

The HTTP test verifies the response only returns the order ID and item count, without echoing the request DTO. `SafeBodyPreviewTest` tests the log projection; if backend logging output needs verification, add a test appender matching the project's logging framework.

### 15.15. Running the Project

Requires JDK 17+ and Maven:

~~~bash
java -version
mvn -version
mvn test
mvn spring-boot:run
~~~

Send a request:

~~~bash
curl -i -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{"customerEmail":"alice@example.test","paymentToken":"secret-payment-token","items":[{"sku":"PRIVATE-SKU","quantity":2}],"customerNote":"confidential customer note"}'
~~~

Illustrative response:

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json

{"id":"<generated-uuid>","itemCount":1}
~~~

Expected summary log contains only the projection:

~~~text
order_body_summary requestId=[...] preview={"itemCount":1,"totalQuantity":2} originalBytes=... truncated=false
~~~

Request IDs and UUIDs are generated dynamically; do not assert exact values in tests. The log does not contain email, payment token, SKU, or customer note.

Metrics can be inspected if Actuator endpoints are exposed and properly secured:

~~~bash
curl http://localhost:8080/actuator/metrics/http.server.requests
curl http://localhost:8080/actuator/metrics/logback.events
curl http://localhost:8080/actuator/prometheus
~~~

Meter names may be normalized differently when exported to Prometheus. `/actuator/metrics` uses Micrometer meter names prior to normalization.

## 16. Testing Logging Policy in Real Projects

| Test | What to Verify |
| --- | --- |
| Secret canary | Dummy token/password does not appear in log events |
| PII canary | Email/phone/address does not appear unless permitted |
| CR/LF injection | User input does not forge extra log lines |
| Byte cap | Preview does not exceed the limit |
| Oversized body | Request is still processed when not captured |
| Multipart/binary | Body is not stringified or aggregated |
| Streaming | SSE/NDJSON is not buffered into one huge body |
| Cancellation | Buffers/listeners are cleaned up when client disconnects |
| DataBuffer leak | No pooled buffer leaks after many requests |
| Route exclusion | Login/payment/upload routes have no body previews |
| Sampling | Log rate matches policy |
| Retention | Debug captures expire and exports are handled |
| Access | Unauthorized users cannot query/export sensitive logs |

You can use Logback `ListAppender` or a custom test appender to capture events and assert no canary strings are present. Do not inspect only console output because appenders/collectors may format and forward data differently.

## 17. Runbook When a Body or Secret Is Found in Logs

1. Identify the data type, route, time window, instances, and log destinations.
2. Disable capture on the exact logger/filter/agent and verify no new events arrive.
3. Determine whether credentials are still valid; rotate/revoke if necessary.
4. Restrict access to affected log indexes, exports, and backups.
5. Identify all copies: stdout, container runtime, local files, collectors, SIEM, APM, object storage, and backups.
6. Preserve necessary evidence per incident/legal policy; do not arbitrarily delete audit evidence.
7. Delete/redact copies per approved retention and incident response procedures.
8. Check for anomalous access to logs during the exposure window.
9. Add canary tests and policy checks in CI.
10. Document root cause, scope, remediation, and accountable owner.

If data was forwarded to third parties, evaluate per data processing agreements and organizational incident procedures. Deleting from a dashboard does not guarantee data is gone from indexes, replicas, or backups.

## 18. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Logging entire request DTOs | Exposes new fields or existing secrets | Build allowlisted projections |
| Redacting with regex alone | Misses nested/aliased/custom fields | Parse schema and allowlist |
| Truncating body and assuming it is safe | Secrets may sit at the beginning | Redact/allowlist first, truncate second |
| Subscribing to request body in WebFilter | Body consumed before controller | Do not read body in metadata filters |
| Joining DataBuffers unboundedly | Memory growth, potential OOM | Byte cap and route allowlist |
| Reading DataBuffers without releasing | Pooled memory leak | Manage retain/release/discard |
| Consuming WebClient response body in filter | Downstream bodyToMono gets no data | Propagate/replay body properly or log metadata only |
| Logging full URLs/queries | Exposes tokens/PII in URLs | Route templates and operation labels |
| Logging raw exception messages | Exposes SQL, hosts, credentials | Exception type/error code |
| Using thread name as request ID | Cannot correlate across thread switches | Request ID/trace context |
| Using userId/orderId as metric tags | Massive cardinality growth | Bounded route/operation/status |
| Writing bodies into trace spans | Trace backend stores sensitive payloads | Safe metadata only |
| Enabling TRACE/DEBUG globally | Huge log volume and data leakage | Scope logger, route, sampling, TTL |
| Redacting only in dashboards | Raw logs are already in the backend | Redact at the source |
| Async appender without queue policy | Uncontrolled queue fill or drop/block | Bounded queue, metrics, and severity policy |
| Keeping debug dumps indefinitely | Increased risk and cost | Time-bounded retention |
| Merging audit and operational logs | Loses semantics and breaks retention | Separate purpose and permissions |
| Not testing secret canaries | Regressions reach production | Unit/integration tests on log events |

## 19. Production Checklist

- [ ] Clear purpose defined for each type of log, metric, and trace.
- [ ] Metadata-only is the default for HTTP requests/responses.
- [ ] Passwords, tokens, cookies, session IDs, keys, and payment data are never logged.
- [ ] Full request/response DTOs are never serialized into logs.
- [ ] Body previews exist only on allowlisted routes and approved schemas.
- [ ] Projections strip secrets before serialization.
- [ ] Byte caps are measured in UTF-8 bytes; previews carry a truncated flag.
- [ ] Multipart, binary, SSE, NDJSON, or unbounded streams are never aggregated for logging.
- [ ] `enableLoggingRequestDetails(true)` is not enabled globally in production.
- [ ] WebFilters do not manually subscribe/consume request bodies.
- [ ] DataBuffers are properly released/retained/replayed when custom capture is used.
- [ ] WebClient filters do not consume response bodies needed downstream.
- [ ] Logs include request ID/trace ID, method, route template, status, and duration.
- [ ] Full URLs/queries or exception messages are not default log fields.
- [ ] Structured logging uses fixed templates and prevents CR/LF injection.
- [ ] Metrics use low-cardinality tags only.
- [ ] High-cardinality trace attributes also undergo privacy review.
- [ ] Spring Boot HTTP observations are not double-instrumented.
- [ ] Sampling does not drop mandatory security/audit events.
- [ ] Async logging queue, overflow, and dropped-event metrics are monitored.
- [ ] Log storage is encrypted, access-controlled, and retention-bounded.
- [ ] Tests cover secret canaries, PII canaries, truncation, route exclusion, and log injection.
- [ ] A runbook exists for when a secret is written to logs.
- [ ] Staging verification goes through the real collector/APM, not just local console output.

## 20. Hands-On Exercises

**Exercise 1 – Metadata filter.** Add `RequestSummaryWebFilter`, send 10 requests, and verify each event has request ID, method, route template, status, and duration.

**Exercise 2 – Route template.** Call `/api/orders/1`, `/api/orders/2`, `/api/orders/3`; verify logs/metrics use the same route template.

**Exercise 3 – Secret canary.** Send `paymentToken=CANARY_SECRET_123`; verify responses and log projections do not contain the canary string.

**Exercise 4 – Allowlist.** Add `customerPhone` to the request DTO; verify the projection does not automatically expose the new field.

**Exercise 5 – UTF-8 byte cap.** Create a safe projection with a long Vietnamese string; verify the preview does not split mid-character and never exceeds the cap.

**Exercise 6 – Log injection.** Send a field containing `\r\nERROR forged`; verify no forged log event is created.

**Exercise 7 – WebClient filter.** Attach operation `catalog.lookup`; verify outbound logs include method/status/duration and the response body still decodes properly.

**Exercise 8 – DataBuffer.** Build a request decorator in an isolated test; verify the body replays accurately and pooled buffers are released on complete/error/cancel.

**Exercise 9 – Cardinality.** Build a dashboard with `route`, `method`, `status`; compare series counts when adding a user ID tag. Do not deploy the user ID tag to production.

**Exercise 10 – Sampling.** Enable sampling for success metadata while retaining error/security events per policy; verify counters still reflect total traffic.

**Exercise 11 – Retention.** Create a simulated debug capture with a TTL, and verify it is no longer accessible via search/export after expiration.

**Exercise 12 – Incident drill.** Intentionally trigger a secret canary in test logs; practice disabling the logger, revoking the secret, finding copies, and writing remediation.

## 21. Official Documentation

1. Spring Boot 4.0 – Observability, Micrometer Observation, low/high cardinality, and context propagation: https://docs.spring.io/spring-boot/4.0/reference/actuator/observability.html
2. Spring Boot 4.0 – Metrics and WebFlux `http.server.requests` / WebClient `http.client.requests`: https://docs.spring.io/spring-boot/4.0/reference/actuator/metrics.html
3. Spring Framework 7.1 – WebFlux Reactive Core, log ID, sensitive logging, and DataBuffer: https://docs.spring.io/spring/reference/7.1/web/webflux/reactive-spring.html
4. Spring Framework – Data Buffers and Codecs, pooled buffer, release/retain, and `DataBufferUtils`: https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html
5. Spring Framework – WebClient filters and response body lifecycle: https://docs.spring.io/spring/reference/7.1/web/webflux-webclient/client-filter.html
6. Spring Framework – WebClient API and non-blocking behavior: https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html
7. OWASP Logging Cheat Sheet – data to exclude, structured logging, access control, retention, and log injection: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
8. OWASP Session Management Cheat Sheet – do not log raw session IDs: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
9. RFC 5424 – The Syslog Protocol: https://www.rfc-editor.org/rfc/rfc5424
10. Micrometer Observation – concepts and key-value cardinality: https://docs.micrometer.io/micrometer/reference/observation.html

**Final Self-Check:** Why does a body cap not replace redaction? Why should a WebFilter not subscribe directly to the request body? If a filter reads the `ClientResponse` body and does not replay it, what happens to downstream `bodyToMono()`? Why is a request ID suited for logs but unsuitable as a metric tag? When should you log `itemCount` instead of raw order JSON? If you can correlate a request across metadata, metrics, and traces without storing tokens, PII, or full bodies, you have designed WebFlux observability with sound cost and risk control.
