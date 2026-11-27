# Safe Request and Response Logging in Spring Boot

When investigating an HTTP failure, request and response logs can help identify the route, status, latency, and cause of failure. However, if full headers or bodies are recorded, logs can end up holding access tokens, cookies, passwords, personal information, payment data, or private business content. Logs are also replicated across multiple systems and accessed by multiple teams; a single instance of over-logging can turn the log backend into an unintended store of sensitive data.

The lesson **Safe Request and Response Logging** belongs to the **Logging** chapter of the **SPRING_BOOT_OBSERVABILITY** module. The module guides setting up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing; covering context propagation, tags/cardinality, exporters, sampling, and signal correlation to investigate errors, latency, and application behavior in production environments.

After this lesson, you will be able to design an allowlist-based logging policy, remove or mask sensitive data, select useful metadata instead of logging payloads by default, understand where to instrument HTTP in Spring MVC/WebFlux, avoid exhausting streams when reading bodies, bound log sizes, correlate logs with traces, and test that prohibited data never leaks into logs.

## 1. Why Must Requests and Responses Be Logged Selectively?

HTTP requests and responses can carry many kinds of data:

| Component | Diagnostic value | Risk |
| --- | --- | --- |
| Method and route template | Identifies the operation type | Low if the route is normalized |
| Status code and duration | Error/latency analysis | Low |
| `Content-Type` and `Content-Length` | Identifies payload type/size | May reveal data type |
| `User-Agent` or client category | Client grouping | Can identify devices/users |
| `Authorization`, `Cookie`, `Set-Cookie` | Usually unnecessary to log | Contains credentials/sessions |
| Query parameters | Can aid debugging | Can contain emails, tokens, search terms |
| Request/response body | Can help reproduce failures | Can contain PII, secrets, financial data |
| Exception message | Helps understand errors | Can contain SQL, URLs, identifiers, or payloads |

Access logs usually need to answer: which endpoint received the request and with which method; what status resulted and how long it took; at which step the request was rejected, timed out, or failed; whether the event can be linked to a trace/span and service instance; and what minimal metadata suffices to reproduce the failure in a safe test environment.

Full bodies are unnecessary to answer most of these questions. **By default, do not log raw request/response bodies or full headers.** Collect only approved fields with a clear purpose, size limit, and retention window.

## 2. Threat Model: A Log Is a Copy of Data

Logs can flow from the application to stdout, agents, collectors, log platforms, archives, and analytics systems. Each hop may have different retention, access controls, and vendors.

```mermaid
flowchart LR
    A["HTTP request/response"]
    B["Application logging policy"]
    C["Sanitize / redact / limit"]
    D["Structured log event"]
    E["Agent / Collector"]
    F["Log backend"]
    G["Archive / analytics"]
    A --> B --> C --> D --> E --> F --> G
```

If sensitive data is written to stdout before redaction, masking it in a dashboard does not delete the data already sent to the collector or archive. Redaction should happen **before the log event leaves the application**, alongside secondary controls at the collector/backend when defense in depth is needed.

Risks go beyond data exposure:

- **Credential exposure:** tokens/cookies in logs can be replayed to access systems.
- **Privacy breach:** bodies can contain personal details, identifiers, addresses, or transaction histories.
- **Data retention mismatch:** logs outlive source data or what business policy permits.
- **Access expansion:** more people can read logs than can access the business system.
- **Injection/forgery:** newlines or delimiters in input can forge log entries if unencoded.
- **Cost and noise:** large, repetitive payloads inflate ingestion/storage and bury important events.

A logging policy must cover content, who has access, storage location, and retention duration.

## 3. Allowlist Is Better Than Denylist

There are two ways to choose data:

- **Denylist:** log everything, then try to strip known dangerous fields.
- **Allowlist:** log only fields explicitly identified as necessary and safe.

Requests can change schemas, new endpoints can introduce sensitive fields, or upstream services can send previously unseen headers. Denylists easily miss new fields. Allowlists restrict what is allowed to enter logs from the start.

| Field | Policy |
| --- | --- |
| HTTP method | Log |
| Route template | Log |
| Status code | Log |
| Duration | Log |
| `Content-Type` | Log if needed |
| `Content-Length` | Log as a bucket or bounded measurement |
| Trace ID / Span ID | Log via correlation integration |
| `Authorization` / `Proxy-Authorization` | Drop completely |
| `Cookie` / `Set-Cookie` | Drop completely |
| Password / secret / API key | Drop completely |
| Query parameters | Do not log by default; allowlist per key only |
| Body | Do not log by default |
| Exception | Log error type and classification code; check message/stack per policy |

Do not rely on a single generic regex to mask every kind of data inside a raw body. JSON, multipart, XML, URL-encoded forms, and binary payloads have different structures; a sanitizer can misunderstand encoding or nested fields. It is better not to log the body at all or to log only a purpose-built DTO containing permitted fields.

## 4. Useful Metadata Instead of Payloads

An access log event can use a small, stable schema:

```json
{
  "event": "http.server.request.completed",
  "service.name": "checkout-service",
  "http.request.method": "POST",
  "http.route": "/checkout",
  "http.response.status_code": 201,
  "event.duration_ms": 84,
  "network.protocol.name": "http",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "spanId": "00f067aa0ba902b7"
}
```

This is an illustrative log event, not a mandatory schema for every backend. Fields should share consistent names across services and contain no raw user input.

Useful metadata typically includes service name/version and environment; HTTP method, route template, and status code; duration or latency bucket; normalized error category; trace ID/span ID from the logging integration; and request/response size as a metric or bucket if needed.

Avoid logging raw URLs. URLs can carry sensitive query strings or dynamic identifiers. Prefer a route template like `/orders/{orderId}` instead of a URL containing a concrete order ID or query string.

## 5. Masking Sensitive Data: Drop First, Partially Mask Only with Reason

| Technique | Example | When to use |
| --- | --- | --- |
| **Drop field** | Completely omit `Authorization` | Credentials/secrets |
| **Mask** | Replace email with intentionally masked value | Only when the business genuinely needs partial recognition |
| **Normalize** | Convert channel to `web`/`mobile`/`partner` | Low-cardinality grouping |
| **Hash/tokenize** | Use a managed pseudonymous identifier | Only with a threat model, key management, and valid linking need |
| **Bucket** | Body size: 0–1 KB, 1–10 KB | Size analysis while avoiding overly granular values |

Masking does not make data anonymous. A partially masked email can still identify a user when combined with other data. Hashing does not guarantee anonymity either if the value space is small or guessable. Never use homemade hashing as a substitute for a data protection policy.

For credentials, the right choice is usually **not logging them at all**. Do not log prefixes/suffixes of bearer tokens for debugging; log a normalized authentication code or verification outcome instead.

## 6. Why Shouldn't You Log All Headers?

| Header | Default policy |
| --- | --- |
| `Authorization` | Drop |
| `Proxy-Authorization` | Drop |
| `Cookie` | Drop |
| `Set-Cookie` | Drop |
| `X-Api-Key` | Drop |
| `X-Forwarded-For` | Log only if needed and allowed by policy; can be identifying data |
| `User-Agent` | Log only if needed; consider normalizing to client family |
| `Content-Type` | Safe to log |
| `Content-Length` | Safe to log as a measurement |
| `Traceparent` | Let tracing instrumentation handle it; logging raw header is usually unnecessary |

Do not grab all request headers and simply delete four known keys. Choose a few permitted headers and normalize them. For forwarding headers, trust values only from proxies/gateways inside the trust boundary; Internet clients can spoof these headers.

Do not log all response headers because `Set-Cookie`, authentication challenges, redirect URLs, or vendor-specific metadata can contain information that should not be stored.

## 7. Do Not Log Raw Bodies by Default

Request bodies can contain credentials, payment data, identifying information, message contents, or uploaded files. Response bodies can echo that same data back. Logging bodies usually introduces greater risk than diagnostic value.

Instead of logging the body, log normalized outcomes:

```java
log.info(
    "checkout request completed: channel={}, itemCount={}, outcome={}",
    safeChannel,
    itemCount,
    outcome
);
```

This example assumes the three variables are validated/normalized and permitted by policy. Never pass a raw DTO or request object to the logger and rely on `toString()` to decide what data appears.

### Controlled Body Debugging Cases

Some integration incidents may require inspecting payloads. When genuinely necessary:

1. Prefer staging or test environments with synthetic data.
2. Enable only for a specific endpoint and a limited time window.
3. Enforce a very small size cap.
4. Parse only supported content types; reject binaries, multipart, or streams that cannot be safely sanitized.
5. Use an allowlist schema; drop unknown or unparseable fields.
6. Redact prior to logging and test against prohibited payloads.
7. Control who can read the logs and their retention.
8. Have a quick kill switch and record who enabled debug mode.

If any step cannot be guaranteed, do not log the body. Never build a global filter that logs every request/response body in production.

## 8. Spring MVC: Filters, Interceptors, and Request Wrappers

In the Spring MVC/Servlet stack, common places to log access metadata are:

- **Servlet Filter:** wraps the request/response at the servlet layer, well-suited for measuring duration and logging general metadata.
- **HandlerInterceptor:** knows the selected handler/controller and can obtain framework-level route mappings.
- **Controller/service logging:** suited for logging normalized business events, not raw request objects.
- **Micrometer Observation/HTTP instrumentation:** often already produces metrics/tracing for server requests; leverage it rather than duplicating instrumentation.

A minimal metadata filter:

```java
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import org.springframework.web.filter.OncePerRequestFilter;

public final class SafeHttpAccessFilter extends OncePerRequestFilter {
    private static final org.slf4j.Logger log =
        org.slf4j.LoggerFactory.getLogger(SafeHttpAccessFilter.class);

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {
        long started = System.nanoTime();
        try {
            chain.doFilter(request, response);
        } finally {
            long durationMs =
                (System.nanoTime() - started) / 1_000_000;

            String method = safeMethod(request.getMethod());
            String route = safeRoute(request);
            int status = response.getStatus();

            log.info(
                "http request completed method={} route={} status={} durationMs={}",
                method, route, status, durationMs
            );
        }
    }

    private static String safeMethod(String method) {
        return switch (method) {
            case "GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD" ->
                method;
            default -> "OTHER";
        };
    }

    private static String safeRoute(HttpServletRequest request) {
        Object pattern = request.getAttribute(
            "org.springframework.web.servlet.HandlerMapping.bestMatchingPattern"
        );
        return pattern instanceof String value ? value : "unmatched";
    }
}
```

This is an illustrative Servlet/MVC example, and the route attribute must be verified against how the application registers the filter. Filter ordering relative to `DispatcherServlet` and exception handling affects the observed status/route. In applications that already have access logging or observation instrumentation, avoid emitting a duplicate event for every request without good reason.

If the filter runs before handler mapping, the route attribute may not exist yet; log a stable placeholder such as `unmatched` or extract the route at an appropriate layer after mapping completes. Never fall back to the raw URI containing path variables.

## 9. Response Wrappers and the Risks of Reading Bodies

A response body is usually a write-once stream. To read the body for logging, code must wrap the response, cache bytes, and copy them back to the client. This is error-prone:

- Failing to copy all bytes leaves clients with empty or truncated responses.
- Memory usage spikes on large payloads.
- Streaming, SSE, file downloads, or response compression breaks.
- Data is logged before sanitizers run.
- When an exception occurs, the wrapper fails to flush or logs the wrong status.

Request bodies are also normally read-once input streams. A logging filter that consumes the stream before the controller leaves the controller with empty input. Content-caching wrappers have limits; they do not guarantee the full body was read or is safe to log.

**Do not wrap and cache every body just to log it.** If a specific use case truly requires the body, use a framework-supported wrapper, cap size and content types, handle streaming/exceptions properly, and log only a sanitized schema. For uploads/downloads/SSE, log only metadata such as content length, media type, status, and duration.

## 10. Spring WebFlux: Bodies Are Reactive Streams

WebFlux processes bodies as reactive `DataBuffer` streams. Reading or subscribing to the body a second time for logging can consume the stream, cause data loss, trigger reference-count errors, or alter backpressure.

Principles:

- Do not manually subscribe a second time just to log the body.
- Do not collect all `DataBuffer`s into a byte array for every request.
- Never block the event loop waiting to read a payload.
- Prefer `WebFilter`/Observation metadata and logging at the service layer using normalized DTOs.
- If payloads must be inspected in a test environment, cap size/content types, manage `DataBuffer` lifecycle, and test cancellation/error/backpressure.

Reactive body logging requires thorough understanding of publisher lifecycles. A log filter observing safe metadata is usually far more valuable than trying to duplicate stream bodies.

## 11. Size Limits, Encoding, and Log Injection

Even allowlisted fields need bounds. A header with a valid name can still contain hundreds of kilobytes, and user-agent or error strings can hold control characters.

| Property | How to control |
| --- | --- |
| Field length | Cap character/byte count |
| Body size | Do not log by default; if a use case exists, enforce a low hard limit |
| Character encoding | Normalize UTF-8 and handle malformed encodings |
| Newlines/control chars | Encode/escape before writing text logs |
| Nested JSON | Extract only allowlisted fields, limit depth |
| Binary/multipart | Do not log payload |
| Truncation | Record a `truncated` flag and byte count; never pretend the payload is complete |

Do not concatenate raw input directly into a log line that allows line breaks. Use a structured logger and reliable serializer; still enforce field size limits to prevent log forging or ingestion abuse.

## 12. Structured Logging and Correlation

Structured logging saves events as typed fields, enabling queries without parsing free-form text messages. Example:

```json
{
  "event": "http.server.request.completed",
  "http.request.method": "POST",
  "http.route": "/checkout",
  "http.response.status_code": 201,
  "event.duration_ms": 84,
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "spanId": "00f067aa0ba902b7"
}
```

Trace ID and span ID connect a log event to a distributed trace when tracing context is kept in the logging scope. With Logback, a text pattern can reference MDC fields:

```text
%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level trace=%X{traceId:-} span=%X{spanId:-} %logger - %msg%n
```

MDC is normally bound to `ThreadLocal`. When a task switches threads or crosses an executor/reactive boundary, ensure context is propagated and cleaned up properly; otherwise logs can miss IDs or carry IDs from a previous request. Use supported Spring/Micrometer integrations and test with real executors.

Do not put trace IDs into metric tags for dashboard linking because cardinality is very high. Metrics detect trends; traces show sampled request paths; logs reveal detailed events. All three can connect through trace context without logging sensitive payloads.

## 13. Exception Logging: Avoid Re-Logging Everything Across Layers

An exception can get logged in a filter, controller advice, service, and global handler. If every layer logs the same stack trace, one failure emits duplicate events, driving up costs and obscuring root cause.

Choose one place responsible for final error logging, such as a global exception handler or task boundary. Inner layers can add context selectively or rethrow without repeating the entire stack at each layer.

Example response handler logging normalized metadata:

```java
@ExceptionHandler(IllegalArgumentException.class)
ResponseEntity<ErrorResponse> handleBadRequest(
        IllegalArgumentException ex) {
    log.warn("request rejected category=validation");
    return ResponseEntity.badRequest()
        .body(new ErrorResponse("INVALID_REQUEST"));
}
```

This example intentionally omits the exception message and request body. If a stack trace is needed for unexpected errors, restrict it to one boundary, classify the error, and inspect messages/causes for potential secrets. Avoid returning internal exception messages to clients.

## 14. Retention, Access Control, and Environments

A logging policy is incomplete if it only states which fields are recorded. You must define:

- Which log events are permitted to be stored in development, staging, and production?
- Who is allowed to view logs containing correlation fields?
- Do logs contain identifying or transactional data; if so, what is the legal/policy basis and retention?
- Does the collector apply secondary redaction/filtering?
- Can data be deleted or access-restricted if accidental logging is discovered?
- Does debug logging automatically turn off after a time limit?

Never use real production data to test body logging in local/staging. Use synthetic fixtures, test tokens, and fake identifiers. Avoid leaving `DEBUG`/`TRACE` enabled system-wide for long periods; high log volume can drown out critical events and drive up costs.

## 15. Testing Safe Logging

Tests must verify both that **permitted data is present** and that **prohibited data does not appear**. Checking only that a log event was created is insufficient.

| Test | What to verify |
| --- | --- |
| Allowlist test | Only method, route template, status, duration, and approved fields are logged |
| Secret redaction test | `Authorization`, cookies, API keys, and passwords do not appear |
| PII test | Emails, phones, addresses, and prohibited body fields are excluded |
| Body-size test | Large payloads do not bloat logs unboundedly |
| Stream test | Request/response body reaches controller/client intact without consumption or mutation |
| Injection test | Newlines/control chars do not forge fake log entries |
| Error-path test | Exception is logged once at the right boundary |
| Correlation test | Trace ID/span ID match scope and do not leak to the next request |

### Metadata Normalization Test Example

```java
record SafeAccessEvent(
    String method,
    String route,
    int status,
    long durationMs
) {}

final class AccessEventFactory {
    SafeAccessEvent create(
            String method, String route, int status, long durationMs) {
        String safeMethod = switch (method) {
            case "GET", "POST", "PUT", "PATCH", "DELETE" -> method;
            default -> "OTHER";
        };
        String safeRoute = switch (route) {
            case "/checkout", "/health", "/orders/{id}" -> route;
            default -> "unmatched";
        };
        int safeStatus = status >= 100 && status <= 599 ? status : 500;
        long safeDuration = Math.max(0, Math.min(durationMs, 300_000));
        return new SafeAccessEvent(
            safeMethod, safeRoute, safeStatus, safeDuration);
    }
}
```

```java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class AccessEventFactoryTest {
    private final AccessEventFactory factory = new AccessEventFactory();

    @Test
    void doesNotCopyUntrustedPathOrMethod() {
        SafeAccessEvent event = factory.create(
            "CUSTOM-METHOD",
            "/orders/secret-id?token=abc",
            200,
            45
        );
        assertEquals("OTHER", event.method());
        assertEquals("unmatched", event.route());
        assertEquals(200, event.status());
        assertEquals(45, event.durationMs());
    }

    @Test
    void boundsDuration() {
        SafeAccessEvent event = factory.create(
            "GET", "/health", 200, Long.MAX_VALUE);
        assertEquals(300_000, event.durationMs());
    }
}
```

This tests the event factory, not a full integration test of a servlet filter or WebFlux. Add tests using `MockMvc`/`WebTestClient` to verify bodies still reach the controller/client intact, log output contains no sentinel secrets, and trace correlation is restored across async boundaries.

## 16. Common Pitfalls and How to Fix Them

| Symptom | Possible cause | What to check |
| --- | --- | --- |
| `Authorization` appears in logs | All headers logged or sanitizer runs too late | Allowlist before logging, test with sentinel token |
| Controller receives empty body | Filter already read request stream | Remove body logging or use a tested wrapper |
| Client receives empty response body | Response wrapper did not copy body back | Avoid arbitrary response caching; test full stream |
| File download/SSE slows down or breaks | Buffering the entire response | Log only metadata on streaming endpoints |
| Logs contain query tokens | Raw URL was logged | Use route template, strip query string |
| Email still appears after masking | Regex misunderstands schema/encoding | Do not log body; allowlist schema or drop field |
| Single request emits multiple stack traces | Multiple layers log the same exception | Choose one error boundary to own the event |
| Previous request's Trace ID appears | MDC/`ThreadLocal` not restored | Check scope and executor reuse |
| Sudden spike in log ingestion | Huge bodies/headers or broad debug level | Bound fields/size and time-limit debug levels |
| Forged log lines appear | Raw input contains newlines/control chars | Structured logging, encode, and cap length |
| Route logs contain user IDs | Raw URI logged instead of route template | Read mapped route pattern |
| Cannot correlate logs with traces | Missing logging integration or async context | Check MDC, bridge, and context propagation |

## 17. Real-World Scenario: Debugging a Payment Failure Without Logging Card Data

**Hypothetical scenario:** `payment-service` returns 502 when checkout calls the payment gateway. The development team needs to know the endpoint, status, latency, error type, and retry attempt. The request body holds the cardholder name, billing address, and payment token.

One way to handle it:

1. **Log HTTP metadata:** method, route template `/payments/authorize`, status, duration, and content type.
2. **Correlate traces:** record trace ID/span ID via tracing logging integration to locate the call's client/server spans.
3. **Normalize business context:** log the allowlisted payment provider name, attempt number, outcome category, and safe error code.
4. **Drop payloads:** never log raw bodies, tokens, authorization headers, cookies, or provider response bodies.
5. **Log error at boundary:** a single handler emits `payment.authorization.failed` with a normalized error category; lower layers do not re-log the same stack trace.
6. **Track retries:** a metrics counter tracks retry counts and a histogram measures duration; never use transaction ID as a metric label.
7. **Reproduce safely:** use test credentials and synthetic payloads in staging; enable time-limited debug logging only if extra data is required.

The log event can show that attempt 2 received 502 after 1.2 seconds, while the trace shows a slow dependency span. There is no need to store card numbers or payment tokens to diagnose the timeout.

## 18. Self-Check Exercises

**Exercise 1.** Why is an allowlist safer than logging all headers and denylisting a few keys?

*Hint:* New headers and unknown sensitive fields can appear at any time; an allowlist only lets pre-approved fields enter logs.

**Exercise 2.** A filter reads the request body to log it, and then the controller receives an empty body. What is the cause and fix?

*Hint:* The servlet input stream was consumed. Do not log bodies by default; if a use case exists, use a caching wrapper properly, cap size, and test that the controller receives intact content.

**Exercise 3.** Why should you avoid logging raw URLs?

*Hint:* Paths/queries can contain identifiers, tokens, or personal information. Use route templates and drop unapproved query parameters.

**Exercise 4.** A response uses Server-Sent Events. Should you cache the entire body to log it?

*Hint:* No. It is a long-lived stream; buffering can break backpressure/latency and consume lots of memory. Log metadata only.

**Exercise 5.** A log contains a partially masked email. Can that data be considered anonymous?

*Hint:* No. The field may still identify someone when combined with other data. Log it only with valid purpose and authorization.

**Exercise 6.** An exception is caught in a filter, service, and controller advice. How do you prevent duplicates?

*Hint:* Choose one error boundary to emit the final event/stack trace; other layers classify or rethrow without re-logging.

**Exercise 7.** How do you verify tokens never leak into logs?

*Hint:* Send a synthetic sentinel token in a test request, capture log output, and assert the sentinel never appears in application logger/collector tests.

**Exercise 8.** Why can trace IDs appear in logs yet never belong in metric tags?

*Hint:* Trace IDs are great for looking up requests in logs/traces, but every request generates a new ID, exploding metric cardinality.

## 19. Takeaways

- **Safe request/response logging starts with purpose and allowlists**, not logging everything and trying to mask known fields.
- By default, log only useful metadata such as method, route template, status, duration, and trace/span IDs; never log raw headers or bodies.
- **Drop credentials and secrets** such as `Authorization`, cookies, API keys, passwords, and payment tokens. Masking does not mean data is anonymous.
- In Spring MVC, filters/interceptors can log metadata, but you must understand handler mapping order and stream lifecycles; in WebFlux, avoid subscribing/consuming `DataBuffer` a second time.
- Never buffer entire request/response bodies for logging. Streaming, SSE, file transfers, and large payloads require special care.
- Use structured logs, cap sizes/encoding, encode control characters, and log exceptions at a single boundary to prevent injection and duplicate events.
- Correlate logs with traces via `traceId`/`spanId` and context propagation; never use trace IDs as metric labels.
- Test both that **permitted fields appear** and that **secrets/PII are absent**, including error paths, stream integrity, body size limits, and async context cleanup.
