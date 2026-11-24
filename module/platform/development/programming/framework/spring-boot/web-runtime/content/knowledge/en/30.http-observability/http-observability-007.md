# Distinguishing Request Body Logging from Safe Metadata Observation

When a Spring Boot API returns HTTP 400 or 500 or runs slowly, developers are often tempted to log the entire request body to see what the client sent. That habit can accidentally build a second shadow datastore containing passwords, OTPs, bearer tokens, session cookies, email addresses, physical addresses, payment details, messages, documents, and sensitive records. Logs do not stay on the console: they typically flow through agents, centralized analytics systems, alerts, tickets, backups, and various operator accounts.

**Safe metadata observation** has a different purpose: it answers **what kind of request arrived, which endpoint it hit, what status it returned, how long it took, which error category occurred, and which trace it belongs to** without ever reading or storing the request content. For most HTTP monitoring tasks, metrics and metadata logs are far more useful than copying bodies.

This lesson belongs to **HTTP Observability**, focusing on **Spring Boot 3.x, Spring MVC/Servlet, Java 17+, Micrometer Observation, and Actuator**. The runnable example includes a `OncePerRequestFilter` logging method, route template, status, duration, and server-generated ID **without reading the body**. Automated tests verify that requests carrying fake emails, notes, and tokens never leak them into logs. Finally, the lesson covers WebFlux, async dispatches, reverse proxies, log access controls, and safe debugging workflows.

**Principle:** not collecting sensitive data in the first place is always better than collecting everything and trying to mask it with regexes afterward. Even metadata must be chosen via an allowlist rather than logging everything an HTTP request carries.

## 1. Learning Objectives

After this lesson, you will be able to:

- Distinguish request-body logging from HTTP access logs, application metadata logs, metrics, traces, and audit events.
- Classify request bodies, queries, URL paths, headers, and identify which fields may carry secrets or PII.
- Choose useful metadata fields: method, route pattern, status, latency, outcome, and a trusted correlation ID.
- Understand that `ContentCachingRequestWrapper` caches only bytes **already read**, neither reading bodies automatically nor performing redaction.
- Write a `OncePerRequestFilter` that generates a UUID, reads `HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE`, and cleans up MDC properly.
- Explain why `request.getRequestURI()` and `getQueryString()` are unsafe fallbacks for route labels.
- Configure `spring.mvc.log-request-details=false`, and inspect Tomcat access logs and proxy logs.
- Use Micrometer's `http.server.requests` to track HTTP error rates and latency with low-cardinality labels.
- Test with `MockMvc` + `OutputCaptureExtension` to prove fake secrets never appear in logs.
- Recognize differences with error/async dispatches, uploads, SSE, WebSockets, and WebFlux.
- Design incident investigation workflows that do not require collecting raw user payloads.

## 2. Body Logging and Metadata Logging Are Two Different Choices

An HTTP request:

```http
POST /api/orders?source=checkout HTTP/1.1
Host: shop.example.test
Content-Type: application/json
Authorization: Bearer <REDACTED>
Cookie: SESSION=<REDACTED>

{
  "sku": "BOOK-001",
  "quantity": 2,
  "contactEmail": "fake.user@example.test",
  "deliveryNote": "Example only"
}
```

**Body logging** writes the JSON or raw request bytes into text or binary logs. It captures unknown or future application fields, including secrets. **Metadata logging** records only an approved list of fields such as:

```text
http_request method=POST route=/api/orders status=200 durationMs=12 requestId=550e8400-e29b-41d4-a716-446655440000
```

The UUID and 12 ms above are dummy values; runtime generates different IDs and timings. This log links a request to a failure without exposing email addresses or delivery notes.

### 2.1. Classification Table

| Component | Example | Starting decision |
| --- | --- | --- |
| HTTP method | GET, POST, PUT | Generally safe to log once constrained to known values |
| Route template | `/api/orders/{id}` | Generally suitable for logs/metrics |
| Raw URI | `/api/orders/user@example.test` | Avoid; can expose identifiers |
| Query | `?token=...` | Do not log by default |
| Authorization/Cookie | Bearer token, session ID | Never log directly |
| Body | JSON, XML, form, multipart, binary | Do not log by default |
| Content-Length | Client-declared byte length | Log only if needed and aware of limitations |
| Content-Type | application/json | Reasonable if normalized; avoid arbitrary raw parameters |
| User-Agent/Referer | Client-supplied headers | Handle carefully; contains untrusted input |
| X-Forwarded-For/IP | Client/proxy address | Requires trust boundaries and privacy policy |
| Status | 200, 400, 500 | Generally safe to log |
| Latency | durationMs | Useful; must measure the right lifecycle |
| Request/trace ID | Server/gateway generated | Useful for correlation |
| Error category | VALIDATION_FAILED | Useful when bounded to an enum |

**Metadata is not automatically 100% safe.** A URI can contain an email, a query string an API key, `Referer` a verification code, or an IP address personal data. Choose fields deliberately rather than logging everything outside the body.

### 2.2. A Commonly Misunderstood Case

Request:

```http
GET /users/alice@example.test/reset?token=abc HTTP/1.1
```

Even if a logger skips the body and prints only path/query, it still leaks the email and token. Replace it with route template `/users/{id}/reset`, `requestId`, and outcome code. Systems should also avoid placing secrets in URLs in the first place, since browser history, proxies, and access logs record them too.

## 3. Why Body Logging Is a Security and Operational Risk

### 3.1. Secrets and PII Appear in Many Forms

Payloads can hold passwords, OTPs, recovery codes, access tokens, API keys, payment cards, addresses, emails, phone numbers, health records, HR records, uploaded documents, and private messages. Even an innocent-looking field like `note` or `metadata` can contain sensitive user input that the filter author never anticipated.

Per the OWASP Logging Cheat Sheet, session identifiers, access tokens, passwords, sensitive personal data, encryption keys, and high-classification data **should generally never be written directly** to logs. Improper logging creates hard-to-purge copies across log aggregators, backups, and support tickets.

### 3.2. Log Injection

Client-controlled raw bodies or User-Agent headers can include newlines or control characters:

```text
note=ok
ERROR privileged.admin.event
```

Printed verbatim, log parsers may treat the second line as a separate forged entry, causing false alerts and misinterpretation. Prefer **not logging raw input**, and for permitted fields apply proper encoding/escaping, structured logging, and validation.

### 3.3. HTTP Correctness Bugs

A Servlet filter calling `request.getInputStream().readAllBytes()` before the controller can consume the request body. When `@RequestBody`/Jackson tries to read it, it hits EOF or a parse error. Holding full bodies in RAM to log them increases CPU, GC pressure, upload latency, and memory usage; large multipart uploads and streams make this far worse.

### 3.4. Truncation and Sampling Do Not Fix Privacy

Logging the first 1 KB of JSON can still capture a token or email. Logging only 1% of requests still leaks real user data for that 1%. Using `DEBUG` instead of `INFO` still writes data whenever debug is enabled, and log storage still requires access controls and retention management. The default must be **do not collect raw bodies**.

## 4. Forms of HTTP Observability

| Form | Data | Purpose | Notes |
| --- | --- | --- | --- |
| Tomcat/NGINX access log | Timestamp, request line, status, size, latency, IP | Traffic and gateway issues | Raw path/query may be sensitive |
| Application metadata log | Method, route, status, error category, requestId | Tracing request flow | Do not print DTOs/headers/bodies |
| Metrics | Counts, histograms, latency, status, route | Alerts, dashboards, SLOs | Avoid high-cardinality labels |
| Distributed trace | Spans, trace ID, dependency latency | Finding slow/failing hops | Never put secrets in span attributes |
| Audit event | Actor, action, resource type, outcome | Auditing business actions | Separate access controls and retention |
| Full request log | Raw HTTP request body | Special input debugging | High risk; avoid in production |

### 4.1. Access Logs Are Not Body Logs

Tomcat/NGINX access logs typically record request lines and statuses rather than bodies, though custom formats can accidentally log headers or bodies. `%r`, `$request_uri`, `$http_referer`, and `$http_user_agent` can carry queries, tokens, or attacker-controlled text. Avoid `$request_body`, `$http_authorization`, and `$http_cookie` in production unless explicitly designed and justified.

In Boot 3.3, `server.tomcat.accesslog.enabled` defaults to `false`. Disabling Tomcat access logs in the app does **not** disable NGINX, CDN, WAF, or API gateway logs.

### 4.2. Audit Events Are Not Request Dumps

To answer "who changed account permissions and what happened?", design an audit event containing the authenticated actor, action enum, outcome, timestamp, `requestId`, and resource type (plus subject ID when justified). Never store a raw POST body containing personal data and call it an audit log. Audit storage may require tamper-evidence, access auditing, and dedicated retention/deletion rules.

## 5. Selecting Metadata via Allowlist

A useful set of fields:

- `service`, `environment`: stable configuration values.
- `method`: `GET`/`POST`/`PUT`/`PATCH`/`DELETE`/`HEAD`/`OPTIONS`/`OTHER`.
- `route`: `/api/orders` or `/api/orders/{id}` matched by the framework.
- `status`: HTTP code, optionally paired with 2xx/4xx/5xx outcome.
- `durationMs`: measured via monotonic clock or Micrometer timer.
- `requestId`: UUID or ID issued by a trusted gateway.
- `traceId`/`spanId`: from Micrometer Tracing/OpenTelemetry if enabled.
- `errorCategory`: an approved enum, not a raw exception message.

Never log raw `request.getRequestURI()`, `getQueryString()`, `getHeader("Authorization")`, `getHeader("Cookie")`, `getHeader("Referer")`, or `getParameterMap()` by default. Both `BindingResult` and DTO `toString()` can also print rejected values or PII.

### 5.1. Route Templates, Not Path Values

Controller:

```java
@GetMapping("/api/orders/{id}")
public Map<String, String> get(@PathVariable String id) {
    return Map.of("state", "demo");
}
```

This is a snippet from the full controller in the next section. For `GET /api/orders/customer-123?token=unsafe`, Spring MVC sets `HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE` to `/api/orders/{id}` once it selects the handler.

This attribute is **not guaranteed on every request**: requests blocked before MVC, 404s, error dispatches, or custom handler mappings may omit it. When absent, log `UNMATCHED`; never fall back to the raw URI or query string.

### 5.2. Cardinality

Metric labels must stay bounded: method, route template, status, service, outcome. Adding `requestId` or `userId` as a metric label creates nearly one time series per request, inflating metrics storage and risking identifier leaks. `requestId` belongs in logs and traces, **not** as a label on `http.server.requests`.

## 6. `ContentCachingRequestWrapper`: Understanding How It Actually Works

Spring Framework provides `org.springframework.web.util.ContentCachingRequestWrapper` for Servlet requests. The Spring 6.1 Javadoc clearly states:

1. The wrapper only **caches bytes already read downstream** from the input stream/reader.
2. It **does not read request content automatically** upon construction.
3. `getContentAsByteArray()` returns an empty array if nothing has read the stream yet.
4. The cache holds only bytes read up to the time of the call, which may be partial.
5. `contentCacheLimit` caps how many bytes are retained; it does not stop cached bytes from containing credentials.
6. Multipart, binary, and streaming payloads should never be logged as Strings.

**Anti-pattern reading the body before the controller:**

```java
// DO NOT USE: consumes the stream and can leak PII.
String rawBody = new String(
    request.getInputStream().readAllBytes(),
    StandardCharsets.UTF_8
);
log.info("payload={}", rawBody);
filterChain.doFilter(request, response);
```

This is an **unsafe snippet**, not a complete program. It can break `@RequestBody` because the body stream is already exhausted.

**Anti-pattern using a cache limit that still leaks payloads:**

```java
ContentCachingRequestWrapper wrapper =
        new ContentCachingRequestWrapper(request, 4096);

filterChain.doFilter(wrapper, response);

log.debug("payload={}",
    new String(wrapper.getContentAsByteArray(),
               StandardCharsets.UTF_8));
```

This remains an **anti-pattern**, even capped at 4096 bytes. Those first bytes can still carry access tokens, and the wrapper performs zero redaction. Never assume a byte cap or `DEBUG` level makes payload logging safe.

`ContentCachingResponseWrapper` serves a different purpose: wrapping/reading response bodies requires calling `copyBodyToResponse()` properly in the lifecycle; getting it wrong leaves clients receiving empty responses. Because this lesson has **no need to wrap bodies**, we avoid adding wrappers altogether.

### 6.1. Why Regex Redaction Is Unreliable

A denylist looking for `password` misses `pwd`, `session`, `otp`, newly added fields, nested JSON, XML, forms, Unicode escapes, gzip, binary data, and arbitrary text in `note`. Never dump raw payloads into a logger hoping log-collector regexes catch everything. When specific business facts are needed, parse against a schema, map into approved enums/buckets, and log the **outcome**, not the DTO.

## 7. Runnable Spring Boot Java 17+ Project: Metadata-Only Filter

The project exposes an API accepting JSON with fake email/note fields, a path-variable route, and a filter that never reads the input body. The demo uses **Spring Boot 3.3.x + Spring MVC Servlet**, running synchronously. No database or authentication is implemented; production must add proper security and validation.

### 7.1. Creating the Project

Generate a project with [Spring Initializr](https://start.spring.io/), choosing Gradle/Groovy, Java 17+, Spring Boot 3.3.x, and dependencies **Spring Web** and **Spring Boot Actuator**.

In the generated `build.gradle`, the dependencies block is:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

This is only the dependencies snippet, not the full Gradle file. Initializr generates the plugins, BOM/dependency management, repositories, and Gradle Wrapper.

Structure:

```text
src/
  main/
    java/demo/
      SafeHttpObservabilityApplication.java
      SafeRequestMetadataFilter.java
      OrderController.java
    resources/
      application.properties
  test/
    java/demo/
      SafeRequestMetadataFilterTest.java
```

### 7.2. SafeHttpObservabilityApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SafeHttpObservabilityApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                SafeHttpObservabilityApplication.class, args);
    }
}
```

Save at `src/main/java/demo/SafeHttpObservabilityApplication.java`. Package `demo` allows component scanning to discover the filter and controller.

### 7.3. SafeRequestMetadataFilter.java

```java
package demo;

import java.io.IOException;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.servlet.HandlerMapping;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 20)
public class SafeRequestMetadataFilter
        extends OncePerRequestFilter {

    private static final Logger log =
            LoggerFactory.getLogger(
                    SafeRequestMetadataFilter.class);

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        String requestId = UUID.randomUUID().toString();
        long startNanos = System.nanoTime();

        response.setHeader("X-Request-ID", requestId);

        try (MDC.MDCCloseable ignored =
                     MDC.putCloseable("requestId", requestId)) {
            try {
                chain.doFilter(request, response);
            } finally {
                long elapsed = System.nanoTime() - startNanos;
                long durationMs =
                        TimeUnit.NANOSECONDS.toMillis(elapsed);

                Object matched = request.getAttribute(
                    HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE);

                // Never fall back to raw URI.
                String route = matched instanceof String pattern
                        ? pattern : "UNMATCHED";

                String method = normalizeMethod(
                        request.getMethod());

                log.info(
                    "http_request method={} route={} " +
                    "status={} durationMs={} requestId={}",
                    method,
                    route,
                    response.getStatus(),
                    durationMs,
                    requestId);
            }
        }
    }

    private static String normalizeMethod(String method) {
        return switch (method) {
            case "GET", "POST", "PUT", "PATCH",
                 "DELETE", "HEAD", "OPTIONS" -> method;
            default -> "OTHER";
        };
    }
}
```

Save at `src/main/java/demo/SafeRequestMetadataFilter.java`.

**Explanation:**

- `@Component` lets Spring Boot register the Servlet filter automatically; do not register it a second time via `FilterRegistrationBean`.
- `OncePerRequestFilter` follows request dispatch semantics; it does **not** guarantee every async request runs only one dispatch.
- `UUID.randomUUID()` creates the request ID on the server. Do not trust raw client-provided `X-Request-ID` headers.
- `response.setHeader("X-Request-ID", requestId)` returns an ID customers can provide to support.
- `MDC.putCloseable` ensures `ThreadLocal` cleanup before the request thread is reused.
- `System.nanoTime()` measures monotonic duration instead of wall-clock time.
- `HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE` retrieves the matched MVC route template; when absent, falls back to `UNMATCHED`.
- `normalizeMethod` constrains HTTP methods to a fixed set, keeping unusual strings out of logs.
- `response.getStatus()` reflects status at the **end of the synchronous filter dispatch**, which may not be final if error/async dispatches occur afterward.
- **No line reads the body, cookies, `Authorization`, query string, or raw URI.** That property is verified by tests.

In production, if you only need latency/error metrics, you can omit a custom filter and rely on Micrometer auto-instrumentation. This filter is built to teach metadata logging and request IDs.

### 7.4. OrderController.java

```java
package demo;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class OrderController {

    public record PlaceOrderRequest(
            String sku,
            int quantity,
            String contactEmail,
            String deliveryNote) {
    }

    public record PlaceOrderResponse(String state) {
    }

    @PostMapping("/api/orders")
    public ResponseEntity<PlaceOrderResponse> create(
            @RequestBody PlaceOrderRequest body) {

        if (body.sku() == null || body.sku().isBlank()
                || body.quantity() <= 0) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "Invalid order request");
        }

        // Never log or echo email/note data.
        return ResponseEntity.ok(
                new PlaceOrderResponse("received"));
    }

    @GetMapping("/api/orders/{id}")
    public Map<String, String> get(
            @PathVariable("id") String id) {
        // Demo does not expose a specific user's order.
        return Map.of("state", "demo");
    }
}
```

Save at `src/main/java/demo/OrderController.java`. Jackson binds the Java record from JSON; `@RequestBody` reads the body normally because the filter did not consume it. Never add `log.info("body={}", body)` because the record's `toString()` prints all fields, including `contactEmail` and `deliveryNote`. `GET /api/orders/{id}` is only a sample route; production requires ownership/tenant checks and authentication.

### 7.5. application.properties

```properties
server.port=8080
server.address=127.0.0.1

# Spring MVC request details are off by default.
spring.mvc.log-request-details=false

# Disable separate Tomcat access log for this lab.
server.tomcat.accesslog.enabled=false

logging.level.org.springframework.web=INFO

# Metrics exposed only on localhost in this lab.
management.endpoints.web.exposure.include=health,metrics
management.endpoint.health.show-details=never

server.error.include-stacktrace=never
server.error.include-message=never
```

Save at `src/main/resources/application.properties`.

`spring.mvc.log-request-details=false` suppresses request headers/parameters in Spring MVC `DEBUG`/`TRACE` logs; it does **not** stop custom app loggers, third-party interceptors, NGINX/WAF/CDNs, or WireTap. `server.tomcat.accesslog.enabled=false` does not turn off proxy access logs.

`management.endpoints.web.exposure.include=health,metrics` is suitable only for a loopback-bound lab. In production, restrict management endpoints with network policies/authentication or keep them off public ingress.

### 7.6. Running

From the project root with the Gradle Wrapper:

```bash
./gradlew bootRun
```

PowerShell:

```powershell
.\gradlew.bat bootRun
```

Because Spring/Jakarta libraries are required, Java files cannot be compiled standalone with `javac OrderController.java` using the default classpath; use the Gradle Wrapper created by Initializr.

### 7.7. POST with Completely Synthetic Data

```bash
curl -i -X POST http://127.0.0.1:8080/api/orders \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer DEMO-NOT-A-REAL-TOKEN' \
  --data '{"sku":"BOOK-001","quantity":2,"contactEmail":"fake.user@example.test","deliveryNote":"SYNTHETIC-PRIVATE-NOTE"}'
```

Equivalent response:

```http
HTTP/1.1 200
X-Request-ID: <generated-uuid>
Content-Type: application/json

{"state":"received"}
```

This is an **illustrative format**; header ordering, reason phrase, and UUID vary. Equivalent metadata log:

```text
http_request method=POST route=/api/orders status=200 durationMs=8 requestId=550e8400-e29b-41d4-a716-446655440000
```

8 ms and the UUID are purely illustrative. The filter does **not** log `fake.user@example.test`, `SYNTHETIC-PRIVATE-NOTE`, or `DEMO-NOT-A-REAL-TOKEN`.

### 7.8. GET with Path Variable and Query

```bash
curl -i 'http://127.0.0.1:8080/api/orders/customer-123?token=DEMO-DO-NOT-LOG'
```

Controller body:

```json
{"state":"demo"}
```

Logs record `method=GET route=/api/orders/{id} status=200`, omitting `customer-123` and `DEMO-DO-NOT-LOG`. Even though the app skips the URI, browsers and proxies still see the URL; never pass real tokens in query parameters.

### 7.9. Windows PowerShell

Use `curl.exe`. For JSON quoting in PowerShell 5.1, you can store the fake payload in `order-demo.json` and send:

```powershell
curl.exe -i -X POST http://127.0.0.1:8080/api/orders -H "Content-Type: application/json" --data-binary "@order-demo.json"
```

Never put real secrets into sample files or shell history.

## 8. Automated Testing with MockMvc and CapturedOutput

`spring-boot-starter-test` provides Boot test utilities and `MockMvc`. Create `src/test/java/demo/SafeRequestMetadataFilterTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ExtendWith(OutputCaptureExtension.class)
class SafeRequestMetadataFilterTest {

    @Autowired
    MockMvc mvc;

    @Test
    void logsOnlyApprovedMetadata(CapturedOutput output)
            throws Exception {

        String body = """
            {
              "sku":"BOOK-001",
              "quantity":2,
              "contactEmail":"fake.user@example.test",
              "deliveryNote":"SYNTHETIC-PRIVATE-NOTE"
            }
            """;

        mvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .header(HttpHeaders.AUTHORIZATION,
                        "Bearer DEMO-NOT-A-REAL-TOKEN")
                .content(body))
            .andExpect(status().isOk())
            .andExpect(header().exists("X-Request-ID"));

        assertThat(output.getOut())
            .contains("http_request method=POST")
            .contains("route=/api/orders")
            .contains("status=200")
            .doesNotContain("fake.user@example.test")
            .doesNotContain("SYNTHETIC-PRIVATE-NOTE")
            .doesNotContain("DEMO-NOT-A-REAL-TOKEN");
    }

    @Test
    void routePatternHidesPathAndQuery(
            CapturedOutput output) throws Exception {

        mvc.perform(get(
                "/api/orders/customer-123?token=DEMO-QUERY-TOKEN"))
            .andExpect(status().isOk());

        assertThat(output.getOut())
            .contains("route=/api/orders/{id}")
            .doesNotContain("customer-123")
            .doesNotContain("DEMO-QUERY-TOKEN");
    }
}
```

Test 1 verifies the request body still deserializes to JSON, returns 200, emits `X-Request-ID`, and keeps synthetic sensitive strings out of logs. Test 2 verifies the path variable and query string stay out of logs. If another library turns on raw payload logging, these tests fail—catching the regression early.

**Limitations:** the tests capture app logs inside the test runtime only; they do not verify NGINX, WAF, CDN, access logs, or external APM agents outside the JVM. Audit staging/production separately.

Run:

```bash
./gradlew test
```

With Spring Boot 3.3.x and no raw-logging middleware, both tests are expected to pass. Exact Gradle output depends on version and console mode.

## 9. Micrometer Observation: Observing Performance Without Bodies

Spring Boot 3.3 Actuator integrates Micrometer for HTTP server requests, typically via meter:

```text
http.server.requests
```

Recorded metadata usually includes method, route/URI pattern, status/outcome, latency, and exception category per web stack and observation conventions. Prefer this metric over logging every single request when your goal is throughput, error rates, p95/p99 latency, or SLOs.

In the demo, `metrics` is exposed on loopback. After sending a few requests:

```bash
curl -sS http://127.0.0.1:8080/actuator/metrics

curl -sS http://127.0.0.1:8080/actuator/metrics/http.server.requests

curl -sS 'http://127.0.0.1:8080/actuator/metrics/http.server.requests?tag=method:POST'
```

JSON measurements and available tags depend on runtime, registry, and request history. In production, restrict Actuator management endpoints with network policies/RBAC/mTLS or keep them off public ingress.

### 9.1. Low-Cardinality Tags

Use `method=POST`, `uri=/api/orders`, `status=200`, `service=order-api`, `outcome=SUCCESS`. Never attach `requestId`, email, `userId`, tokens, queries, or raw URIs as metric labels, as they explode time series.

### 9.2. Metrics vs. Traces vs. Logs

- Metrics: "how many requests are slow or failing?"
- Metadata logs: "what status/error category did this `requestId` receive?"
- Traces: "did the request spend time in the DB, downstream HTTP, or a specific service?"

Micrometer Tracing/OpenTelemetry propagates trace/span context; sampling may mean not every request produces a trace. Span attributes must also be controlled—never put raw bodies, tokens, or secrets into traces. Server-generated request IDs are distinct from session IDs and access tokens.

## 10. 400, 401, 403, and 500 Errors: Log Categories Instead of Raw Values

Common error categories:

| Category | Example | Sufficient log fields |
| --- | --- | --- |
| INVALID_JSON | JSON parse failure | route, status, requestId, category |
| VALIDATION_FAILED | `quantity<=0` | field name and constraint code, no `rejectedValue` |
| UNAUTHENTICATED | Missing credentials | route, HTTP 401, auth category |
| FORBIDDEN | Missing role/object permission | resource/action type, status |
| DEPENDENCY_TIMEOUT | DB or HTTP downstream timed out | dependency/span category, duration |
| INTERNAL_ERROR | Unclassified app bug | trace ID, controlled exception class |

Never blindly call `log.warn("errors={}", bindingResult.getAllErrors())`: rejected values can contain emails, passwords, or PII. Never log raw `exception.getMessage()` when parsers or libraries include JSON snippets or SQL parameters in error messages.

If a bug reproduces only with a specific input, construct a **synthetic fixture** in staging and describe the triggering condition. Never route real customer requests into production logs just to reproduce a bug.

### 10.1. `DTO.toString()` Is Also Body Logging

Java record `PlaceOrderRequest` generates a `toString()` printing all field values. Writing:

```java
log.info("request={}", body);
```

accidentally logs emails and notes even without calling a JSON serializer. This is an **anti-pattern**. Lombok `@ToString` and entity logging carry the exact same risk.

## 11. Async Servlets, Error Dispatches, and Streaming

`OncePerRequestFilter` runs per request dispatch, not necessarily across the entire lifetime of every logical request. With `DeferredResult`, `Callable`, `StreamingResponseBody`, or `SseEmitter`:

- The initial request thread may return before the response finishes.
- `isAsyncStarted(request)` can be `true`.
- An `ASYNC` dispatch can execute on a different thread.
- An `ERROR` dispatch can finalize status after the initial filter already logged.
- MDC from the initial request thread does not automatically propagate to executors.
- Enabling re-runs on async/error dispatches without lifecycle management risks logging twice.

Therefore, the demo filter's status and duration apply to **synchronous dispatch completion**. For production SLOs and long-lived connections, use Spring Boot HTTP Observations or properly scoped Servlet async listeners with cleanup. Never treat a 30-minute `SseEmitter` as a 5 ms request just because the initial filter returned early.

### 11.1. Exceptions Handled After the Filter

When a controller throws an unhandled exception, the container may trigger an error dispatch after the first `finally` block runs. In that case, the filter logs `status=200` while the browser receives 500. Do not assume the filter misread or the client misreported; inspect the dispatch lifecycle and rely on proper lifecycle-aware observability instrumentation.

### 11.2. MDC and Thread Pools

`MDC` is generally `ThreadLocal`-backed. Use `MDC.putCloseable`/`finally` so earlier requests never taint subsequent requests on reused threads. For `@Async`, `CompletableFuture`, or Reactor, use official context propagation, task decorators, or tracing rather than copying MDC manually without cleanup.

## 12. WebFlux: `WebFilter` and `DataBuffer` Differ from Servlets

Spring WebFlux uses `ServerWebExchange`/`WebFilter` with request bodies modeled as `Flux<DataBuffer>`. Servlet `OncePerRequestFilter` is **not** how you instrument reactive WebFlux.

If a `WebFilter` calls `.subscribe()` on `exchange.getRequest().getBody()` just to log:

- It can consume the stream before the controller reads it;
- Excess buffering causes memory pressure;
- Pooled Netty `DataBuffer`s require exact retain/release handling to avoid leaks or double-release crashes;
- Blocking decode/logging stalls the event loop;
- Reactor context and MDC behave differently from Servlet `ThreadLocal`.

**Prefer WebFlux HTTP Observation.** When payload processing is genuinely required, use request decorators with bounded memory, cancellation cleanup, and stream lifecycle tests—never do this merely for logging.

Multipart/file uploads, gzip/protobuf/binary payloads, and SSE/WebSocket messages also must not be logged as Strings. For SSE/WebSockets, monitor connection counts, event rates, close codes, and drops rather than logging per-user messages/events.

## 13. Multiple Layers Can Log Requests

```text
Client
  |
  v
CDN/WAF           security events, request sampling
  |
  v
Load balancer     access logs
  |
  v
NGINX/Ingress    raw URI/headers if misconfigured
  |
  v
Spring Boot      filters, MVC, app logs
  |
  v
RestClient       outbound HTTP logging/wiretap
  |
  v
Log collector    stdout/file processing
  |
  v
Central logs     search, export, retention, backup
```

A safe filter inside the JVM **cannot erase** bodies or queries already logged by a WAF, proxy, or agent. Audit inbound and outbound HTTP logs, log levels, proxy access log formats, and APM instrumentation end-to-end.

`spring.mvc.log-request-details=false` restricts certain Spring MVC `DEBUG`/`TRACE` details, not custom loggers. `server.tomcat.accesslog.enabled=false` applies only to Tomcat access logs, not CDN/NGINX/WAF logs. In particular, exclude `$request_body`/`$http_authorization`/`$http_cookie` from NGINX log formats and avoid logging raw prepared SQL parameters in database diagnostics.

### 13.1. The Log Platform Is Also a Data Store

Enforce encryption in transit and at rest, RBAC, viewer/export auditing, retention limits, and deletion workflows. Simply hashing an email does not anonymize it: the input domain is guessable. If pseudonymization is needed, evaluate keyed HMAC with rotating keys and strict access policies instead of dumping user identities into every metric/log.

## 14. Special Debugging Without Turning On Full-Body Logging

When metadata alone is not enough, follow this workflow:

1. Formulate a concrete hypothesis: parse error, invalid enum, missing field, downstream timeout, or authorization failure?
2. Build a minimal synthetic request locally or in staging to reproduce.
3. Capture route, status, error category, allowlisted field name, `requestId`, and trace.
4. If an input attribute must be inspected, identify an approved schema field and emit a categorical bucket or validation code rather than the raw value.
5. Enable approved diagnostics narrowly—scoped in target, duration, and sample count—separate from the general log sink.
6. Cap payload size, skip multipart/binary, and test malformed input, nested JSON, Unicode escapes, and log injection.
7. Encrypt collected data, restrict viewer permissions, audit access, auto-expire feature flags, and purge per retention.
8. If a token or PII accidentally enters logs, handle it as a security/privacy incident, including restricting access and revoking secrets as needed.

Sampling or regex masking does not substitute for legal basis, internal policy, or risk assessment.

## 15. Common Pitfalls

| Symptom | Cause | Fix |
| --- | --- | --- |
| `@RequestBody` hits EOF | Filter read input stream before controller | Never consume the body just to log |
| `ContentCachingRequestWrapper` returns empty | Nothing read the body yet | Expected wrapper semantics |
| Cache holds only first 4 KB | Content cache limit | Do not assume it holds the full request; don't log it |
| Logs contain emails/tokens | `DTO.toString`, body, headers, or raw URI | Enforce metadata allowlist |
| Query tokens still in access logs | Proxy logs raw request line | Audit proxy access log policy |
| Metrics series count explodes | Labels include `requestId`/`userId`/raw path | Use low-cardinality tags |
| 404 shows `route=UNMATCHED` | MVC supplied no pattern | Fixed fallback; never raw path |
| Filter logs 200 while client gets 500 | Error dispatch happened after `finally` | Use lifecycle-aware observation |
| `requestId` mixed across requests | Missing MDC cleanup | `try`-with-resources/`finally` |
| Async tasks lack MDC | Thread context not propagated | Use tracing/context propagation |
| SSE latency looks tiny | Measured initial dispatch only | Use async completion/stream metrics |
| WAF still logs request body | App filter has no effect upstream | Audit WAF/request sampling |
| Logs show forged `ERROR` lines | Raw string newlines / log injection | Never log raw input; structured escaping |
| Multipart logging spikes heap | Buffering/copying file uploads | Metadata only; enforce upload limits |
| Debug masking misses new field | Regex denylist gaps | Schema allowlist + regression tests |
| Metrics exposed to Internet | Actuator open on public port | Private management/RBAC/network controls |

## 16. Review Exercises

**1.** Can `DEBUG` be enabled temporarily to log `POST /login` bodies?  
**Answer:** Not by default. Passwords still land in logs/backups; rely on status/category/trace and synthetic fixtures.

**2.** Is logging raw `/users/alice@example.test?token=abc` safe as long as the body isn't logged?  
**Answer:** No. The path and query contain email and token. Use route templates and omit queries.

**3.** Does `ContentCachingRequestWrapper` read the body automatically?  
**Answer:** No, it only caches bytes already read downstream; it may be empty or partial.

**4.** Does capping cache size at 1024 bytes prevent secret leaks?  
**Answer:** No. Secrets can appear in the opening bytes.

**5.** Why must `requestId` not be added as a Micrometer tag?  
**Answer:** Nearly unique UUIDs create high-cardinality time series.

**6.** Is `BEST_MATCHING_PATTERN_ATTRIBUTE` always present?  
**Answer:** No; when missing, use a fixed label rather than raw URI.

**7.** What advantage does `System.nanoTime()` have over `currentTimeMillis()` for latency?  
**Answer:** It is a monotonic clock suited for measuring elapsed intervals.

**8.** Why can a filter observe 200 while the browser receives 500?  
**Answer:** An error dispatch or status update may occur after the initial filter completes.

**9.** What risk comes from logging `BindingResult.getAllErrors()`?  
**Answer:** It can contain rejected values like passwords or emails; log only approved field names and constraint codes.

**10.** Does `spring.mvc.log-request-details=false` stop CDN logging?  
**Answer:** No. Spring MVC settings do not control CDN/WAF/NGINX logs.

**11.** Does `@Async` automatically propagate MDC to worker threads?  
**Answer:** No; explicit context propagation and cleanup are required.

**12.** When investigating a failure spanning multiple services, what should you prioritize?  
**Answer:** Request/trace IDs, route/status/error category, and distributed spans—not raw bodies.

## 17. Production Checklist

- [ ] Request/response bodies, `Authorization`, `Cookie`, session IDs, and credentials are never logged by default.
- [ ] Raw URLs/queries and client-supplied headers are never treated as safe metadata automatically.
- [ ] Only allowlisted method, route template, status, duration, error category, and correlation IDs are logged.
- [ ] Routes come from `HandlerMapping` patterns or framework conventions, falling back to a fixed label if missing.
- [ ] Filters never read input streams/readers solely for logging.
- [ ] `ContentCachingRequestWrapper` is never relied on for redaction or truncated body logging.
- [ ] `DTO.toString`, validation errors, and exception messages never print rejected values.
- [ ] Request IDs are generated/validated at trust boundaries rather than reusing raw tokens.
- [ ] MDC is cleaned up per lifecycle, and async/reactive contexts are instrumented explicitly.
- [ ] Micrometer metrics use low-cardinality route/method/status tags, never `userId` or `requestId`.
- [ ] `spring.mvc.log-request-details=false` and all `DEBUG`/`TRACE`/wiretap settings are reviewed.
- [ ] Tomcat/NGINX/CDN/WAF access logs and outbound HTTP client logs are audited.
- [ ] Unit tests send synthetic data and assert bodies, tokens, path variables, and queries stay out of logs.
- [ ] Actuator and log platforms enforce RBAC, network restrictions, encryption, auditing, and retention.
- [ ] Exceptional debugging follows a narrow, time-bounded workflow using synthetic data.
- [ ] A security incident process exists in case tokens or PII ever leak into logs.

## 18. References

1. [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
2. [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
3. [Spring Framework 6.1 — ContentCachingRequestWrapper Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/util/ContentCachingRequestWrapper.html)
4. [Spring Framework 6.1 — OncePerRequestFilter Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html)
5. [Spring Framework 6.1 — HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/servlet/HandlerMapping.html)
6. [Spring Framework — Observability Support](https://docs.spring.io/spring-framework/reference/integration/observability.html)
7. [Spring Boot 3.3 — Actuator Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html)
8. [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/)
9. [Spring Boot 3.3 — Embedded Web Server Access Logging](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html)
10. [Micrometer — Observation Concepts](https://docs.micrometer.io/micrometer/reference/observation/introduction.html)
11. [OpenTelemetry — HTTP Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/http/)
12. [Spring Framework — MVC Async Requests](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html)

**Conclusion:** logging more does not automatically improve observability. **Method, route template, status, latency, request/trace ID, and controlled error categories** answer most operational questions. Avoiding **reading and writing bodies by default**, while governing raw URLs, headers, and proxy layers, keeps your application observable without building a second sensitive-data store.