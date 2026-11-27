# Masking Request Bodies in Spring Boot Observability

## 1. Objectives and Context

Request bodies often contain business data that developers want to inspect when debugging: registration details, shipping addresses, payment payloads, tokens, or user-submitted data. Recording entire bodies into application logs, traces, or APM can turn telemetry into a copy of sensitive data that spreads across multiple systems and persists longer than the original data.

**Masking request bodies** is the process of removing or replacing sensitive fields before the body is written to logs/telemetry. The goal is to retain enough structure and metadata to investigate requests while avoiding storing secrets or unnecessary personal information.

This lesson belongs to the **Security and Privacy** chapter of the **SPRING_BOOT_OBSERVABILITY** module. The module guides you through setting up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing; learning context propagation, tags/cardinality, exporters, sampling, and signal correlation to investigate errors, latency, and application behavior in production environments.

After this lesson, you will be able to:
1. Identify the paths by which request bodies leak into logs, traces, and APM.
2. Classify sensitive fields by content type and schema.
3. Design safe-by-default allowlists and redaction policies.
4. Understand the limitations of `ContentCachingRequestWrapper` and request body buffering.
5. Handle streaming, multipart, and binary payloads without breaking requests.
6. Prevent body leakage through exceptions, debug logs, and observability agents.
7. Test masking across every telemetry sink using sentinel values.

**Baseline:** Spring Boot 3.5.x, Java 17+, Spring MVC/Servlet or WebFlux. Logging filter examples focus on the Servlet stack; WebFlux has its own `DataBuffer`/reactive lifecycle.

## 2. Why Should You Not Log Entire Request Bodies?

Bodies can contain:
- Passwords, access tokens, refresh tokens, API keys, and session secrets.
- Emails, phone numbers, addresses, dates of birth, and identifying information.
- Payment details, account numbers, or transaction data.
- Health records, HR data, or legal data.
- Uploaded files, images, documents, or free-form user input.
- Unclassified internal data.

The risk does not live solely in log files. Bodies can appear in:

| Source | Example |
| --- | --- |
| Servlet filter/interceptor | Logging request/response payloads |
| API gateway/reverse proxy | Request capture or debug traces |
| APM agent | HTTP body capture and span attributes |
| Exception handler | Logging DTOs or request bodies on validation failures |
| Validation/debug code | Printing entire objects or binding errors |
| Audit pipeline | Copying request payloads into audit events |
| Test/support tooling | Wire logs, mock server recordings, support bundles |

Disabling one application logger does not guarantee other agents, gateways, or sidecars stop capturing. You must inspect the entire telemetry path.

## 3. Principle: Do Not Log Bodies Unless Necessary

Prefer logging safe metadata instead of payloads:
- HTTP method, route template, and status.
- Content-Type and Content-Length if available.
- Request duration and outcome.
- Correlation ID/`traceId` per policy.
- Operation name and validation error category.
- A few allowlisted and schema-redacted fields if genuinely needed.

If payload debugging is necessary, use synthetic/anonymized data or a controlled environment. Never enable global body logging in production just to reproduce a bug.

## 4. Designing a Redaction Policy

The policy should be **allowlist-based**: only fields classified as safe are retained. Unknown fields, new schemas, or unsupported content types must be redacted completely or have the body omitted.

Example JSON policy:

| Field | Handling | Reason |
| --- | --- | --- |
| `password` | `[REDACTED]` | Secret |
| `accessToken` / `refreshToken` | `[REDACTED]` | Credential |
| `email` | `[REDACTED]` or omit field | PII |
| `phone` | `[REDACTED]` | PII |
| `cardNumber` | `[REDACTED]` | Payment data |
| `amount` | Keep if approved | Business value |
| `currency` | Keep if approved | Finite enum |
| `requestType` | Keep if allowlisted | Operation metadata |
| Unknown field | Redact or omit whole body | Unclassified schema |

Do not rely on field names alone to decide safety. `metadata`, `value`, `data`, `notes`, or nested fields can contain secrets/PII. Policies must be endpoint/schema-aware with recursive traversal.

### 4.1. Before and After Body Example

Incoming request body:

```json
{
  "requestType": "CREATE_ORDER",
  "email": "alice@example.test",
  "password": "SECRET_SENTINEL_91",
  "cardNumber": "4111111111111111",
  "amount": 125000,
  "currency": "VND"
}
```

Body permitted to be logged after redaction:

```json
{
  "requestType": "CREATE_ORDER",
  "email": "[REDACTED]",
  "password": "[REDACTED]",
  "cardNumber": "[REDACTED]",
  "amount": 125000,
  "currency": "VND"
}
```

This is an illustrative example. Retaining `amount`/`currency` must also be approved by your organization's data policy; transaction values can be sensitive data in certain domains.

## 5. Servlet Stack: ContentCachingRequestWrapper

In Spring MVC, `ContentCachingRequestWrapper` can cache bytes as downstream code reads the request body so a filter can read them afterward. The wrapper does not eagerly read the entire body upon creation and does not perform redaction itself.

Example filter that logs only metadata, not the raw body:

```java
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;
import java.io.IOException;

@Component
public class RequestMetadataLoggingFilter extends OncePerRequestFilter {
    private static final Logger log =
            LoggerFactory.getLogger(RequestMetadataLoggingFilter.class);

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain) throws ServletException, IOException {
        long started = System.nanoTime();
        try {
            filterChain.doFilter(request, response);
        } finally {
            long durationMs = (System.nanoTime() - started) / 1_000_000;
            log.info("HTTP request completed method={} uri={} status={} durationMs={}",
                    request.getMethod(),
                    request.getRequestURI(),
                    response.getStatus(),
                    durationMs);
        }
    }
}
```

The example above still needs the URI normalized into a route template if the path contains identifiers. Do not log query strings by default, since query parameters can also contain secrets or PII.

### 5.1. When to Use ContentCachingRequestWrapper?

Use it only when there is a valid use case to inspect the body after the application has read it. A few caveats:
- The cache limit must be bounded to prevent memory exhaustion.
- Bodies not yet read downstream may not appear completely in the cache.
- Multipart/file uploads should not be copied into memory for logging.
- The wrapper does not parse JSON or mask fields.
- Never log cached bytes directly; decode and redact per schema if genuinely needed.
- Be careful with charsets, binary content, malformed payloads, and oversized requests.

If you need to read the body before downstream processing, you need a wrapper that properly supports stream replay. Reading `InputStream` in a filter without replacing/replaying it can cause the controller to receive an empty body.

## 6. Bounded JSON Redaction Example

If policy permits logging certain JSON requests, you can parse into a JSON tree, redact according to an approved allowlist/denylist, and then serialize the processed version. Example with Jackson:

```java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.util.Set;

public final class RequestBodyRedactor {
    private static final Set<String> SENSITIVE_FIELDS = Set.of(
            "password", "accessToken", "refreshToken",
            "email", "phone", "cardNumber"
    );

    private final ObjectMapper mapper;

    public RequestBodyRedactor(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    public String redact(String json) {
        try {
            JsonNode root = mapper.readTree(json);
            redactNode(root);
            return mapper.writeValueAsString(root);
        } catch (Exception ex) {
            return "[BODY_OMITTED:UNPARSEABLE_OR_UNSUPPORTED]";
        }
    }

    private void redactNode(JsonNode node) {
        if (node instanceof ObjectNode object) {
            object.fieldNames().forEachRemaining(name -> {
                if (SENSITIVE_FIELDS.contains(name)) {
                    object.put(name, "[REDACTED]");
                } else {
                    redactNode(object.get(name));
                }
            });
        } else if (node.isArray()) {
            node.forEach(this::redactNode);
        }
    }
}
```

This is a starter example, not a complete production redactor. It only handles JSON objects/arrays and a static field list; you must add policies for nested schemas, field aliases, case normalization, polymorphic payloads, and unknown fields. On parse failure, the example omits the entire body instead of logging raw input.

Do not invoke the redactor automatically on every request. Activate it only for allowlisted endpoints/content types, enforce size limits, and evaluate the cost of extra parsing.

## 7. Content Types, Multipart, and Binary

Not every request body is JSON:

| Content-Type | Logging Policy |
| --- | --- |
| `application/json` | Log only the version redacted per approved schema |
| `application/x-www-form-urlencoded` | Redact each field; omit tokens/passwords by default |
| `multipart/form-data` | Never log file bytes; log only approved metadata |
| `application/octet-stream` | Omit body |
| `image/*`, `audio/*`, `video/*` | Omit body; do not encode into text logs |
| `text/plain` | Omit by default or apply explicit limits/allowlists |
| `application/*+json` | Process only when schema/content type is supported |

Multipart filenames can also contain personal information or user-controlled paths. Log only file size, media type, or file count if needed and approved; do not log filenames/paths by default.

## 8. Response Bodies and Exception Leakage

Response bodies can also contain access tokens, reset links, personal data, or downstream-returned content. If a filter logs both requests and responses, enforce separate policies for both directions.

Validation exceptions can contain rejected values. For example, binding errors sometimes retain the input object/value; never serialize entire `BindingResult` objects or DTOs into logs. Log only controlled field names and error codes, not rejected values.

Never log entire request objects in controllers/services via `toString()`. Generated `toString()` methods can include all fields, nested objects, or secrets.

APM agents, gateway wiretaps, and HTTP client/server debug logging can also capture payloads. Inspect body-capture settings and disable or redact at the source before sending to exporters.

## 9. WebFlux and Streaming Bodies

WebFlux uses reactive streams and `DataBuffer`. Consuming a body for logging can affect backpressure, memory, and buffer lifecycles.

Principles:
- Do not subscribe an extra time just to log the body.
- Do not aggregate large streams into a single byte array just to log them.
- Never block the event loop to parse/redact payloads.
- If manually reading `DataBuffer`, follow ownership/release semantics strictly to avoid leaks.
- For streaming requests, log metadata and event summaries rather than full contents.
- Context/trace propagation must remain intact across scheduler hops.

On the reactive stack, prefer `WebFilter`/`ExchangeFilterFunction` or instrumentation that natively understands body semantics. Never copy the Servlet `ContentCachingRequestWrapper` pattern into WebFlux.

## 10. Buffer Size, Performance, and Denial of Service

Body logging can double memory usage: one copy for request processing and one copy cached/serialized for logging. With large payloads or high concurrency, this can create heap pressure, GC pauses, and DoS vectors.

Design requirements:
- Cap the maximum body bytes inspected.
- Never cache file uploads or streaming payloads.
- Enforce timeouts and size limits at the server/container.
- Avoid parsing the same JSON multiple times unnecessarily.
- Sampling applies only to already-redacted data and must never justify recording secrets.
- Measure filter/redactor overhead via load testing.

If the limit is exceeded, omit the entire body or record a marker like `BODY_OMITTED_TOO_LARGE`; never arbitrarily truncate JSON and log a partial slice that might still contain a secret.

## 11. Testing Masking with Sentinel Values

Use recognizable synthetic values to test for leaks:
- Email: `mask-user-731@example.test`.
- Token: `BODY_SECRET_SENTINEL_42`.
- Phone: `+84981234567`.
- Card-like test value: `4111111111111111` (test data only).

Test matrix:
1. Valid JSON with nested sensitive fields: raw values do not appear in logs.
2. Malformed JSON: body is omitted without falling back to raw logging.
3. JSON exceeding size limit: body is omitted and marker is recorded.
4. Form-urlencoded: passwords/tokens are redacted.
5. Multipart: file bytes and filenames are not logged.
6. Binary/streaming: body is neither consumed nor buffered for logging.
7. Validation error: rejected values do not appear in exception logs.
8. Response body: tokens/reset links do not appear.
9. APM/exporters/gateways: sentinels do not appear in any sink.
10. Concurrent requests: wrappers/caches/contexts never mix bodies across requests.

Example assertion:

```java
assertThat(capturedTelemetry)
        .doesNotContain("mask-user-731@example.test")
        .doesNotContain("BODY_SECRET_SENTINEL_42")
        .doesNotContain("+84981234567")
        .doesNotContain("4111111111111111");
```

Checking only one appender is insufficient if the application also has a stdout collector, tracing exporter, APM agent, or gateway logging.

## 12. Troubleshooting

| Symptom | Possible Cause | Remediation |
| --- | --- | --- |
| Logs still show passwords after enabling filter | Another agent/gateway/appender captures the body | Inspect the entire telemetry path |
| Controller receives empty body | Filter consumed `InputStream` without replaying | Use a proper replay wrapper or avoid reading beforehand |
| Cached body is empty | Downstream hasn't read body yet or wrapper order is wrong | Check filter order and lifecycle |
| Heap grows after enabling body logging | Caching large bodies or high concurrency | Cap bytes, skip uploads/streaming |
| Nested JSON field not masked | Redactor handles root only or incomplete schema | Recursive traversal and test nested payloads |
| JSON parse error exposes raw body | Fallback logs raw input | Fail closed: omit body when parsing is unsupported |
| Multipart log contains filename | File metadata unclassified | Drop filename/path, keep only allowlisted metadata |
| WebFlux `DataBuffer` leak | Custom filter fails to release buffers properly | Follow buffer ownership/lifecycle rules |
| Validation log exposes rejected value | Logging entire `BindingResult`/DTO | Log only safe field/error codes |
| Response token appears in traces | Response body capture in APM/client | Disable body capture or redact before export |
| Request latency increases | Extra parse/serialize pass | Log metadata; benchmark redactor and narrow scope |

## 13. Production Checklist

- [ ] Request/response bodies are not logged by default.
- [ ] Endpoints/content types are explicitly allowlisted if body diagnostics are needed.
- [ ] Unknown fields and parse failures are omitted/redacted by default.
- [ ] Passwords, tokens, payment data, and PII never appear in telemetry.
- [ ] `ContentCachingRequestWrapper` is bounded; bodies are not consumed unintentionally.
- [ ] Multipart, binary, and streaming bodies are not buffered/logged.
- [ ] WebFlux handles `DataBuffer` and backpressure according to lifecycle rules.
- [ ] Exception/validation errors never log rejected values or `DTO.toString()`.
- [ ] APM agents, gateways, appenders, and exporters have been checked.
- [ ] Body size limits and load tests protect memory/CPU.
- [ ] Sentinel tests verify zero leakage across all sinks.
- [ ] Retention/access controls and incident response are defined.

## 14. Practice Questions

1. Why can request body logging cause data exposure?
2. Why is an allowlist generally safer than a blocklist?
3. Does `ContentCachingRequestWrapper` automatically read and mask the body?
4. What happens if a filter reads `InputStream` without replaying it?
5. Why must JSON parse failures fail closed?
6. What policy do multipart and binary payloads require?
7. Why should you not aggregate large `Flux`/`DataBuffer` streams just to log them?
8. How can validation exceptions expose rejected values?
9. How can APM agents and gateways bypass application-level masking?
10. Which telemetry sinks should sentinel tests check?
11. Why is a body size limit an availability safeguard?
12. When is metadata sufficient instead of the request body?

## References

- [Spring Framework — Logging](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/filters.html)
- [Spring Framework — ContentCachingRequestWrapper](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/util/ContentCachingRequestWrapper.html)
- [Spring Framework — WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html)
- [Spring Boot — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html)
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [OWASP — Logging Vocabulary Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Vocabulary_Cheat_Sheet.html)
- [OWASP — REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html)
- [OpenTelemetry — HTTP Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/http/)
