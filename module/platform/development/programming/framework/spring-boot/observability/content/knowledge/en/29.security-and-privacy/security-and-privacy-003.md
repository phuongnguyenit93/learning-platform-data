# Never Log Access Tokens in Spring Boot

An access token is a bearer credential: whoever possesses the token can use it within its granted scope and lifetime. If a token appears in application logs, access logs, exception messages, traces, or telemetry exports, anyone with log read access can use the token to impersonate the client until the token expires or is revoked. Logs are frequently replicated to multiple systems, retained for long periods, and accessible to many teams, so a single accidental log entry can significantly expand the exposure blast radius.

The lesson **Never Log Access Tokens** belongs to the **Security and Privacy** chapter of the **SPRING_BOOT_OBSERVABILITY** module. This module guides you through setting up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing; learning context propagation, tags/cardinality, exporters, sampling, and signal correlation to investigate errors, latency, and application behavior in production environments.

After this lesson, you will be able to identify where tokens easily leak into telemetry, design allowlist-based logging, filter sensitive information at the source, apply multi-layer redaction, control MDC/trace attributes, and write tests proving synthetic tokens never appear in log output.

## 1. Why Must Access Tokens Never Appear in Logs?

A bearer token is an authentication credential. With OAuth 2.0, an access token is sent in the HTTP `Authorization` header as a `Bearer` token. Anyone holding the token can call the resource server as the client to which the token was issued, subject to scopes, audience, expiry, and server policy.

Tokens can leak through:

- Application logs recording all request headers.
- Reverse proxy, gateway, or web server access logs.
- HTTP client/server debug logs.
- Exception messages containing request/response headers.
- Logging request bodies, query parameters, or URLs containing tokens.
- MDC, structured logging fields, or custom trace/span attributes.
- APM agents, tracing exporters, support bundles, and crash diagnostics.
- CI output, test reports, terminal history, or screenshots.

Do not rely on a token's short lifetime to downplay the risk. While still valid, a token can be replayed; an accidentally logged refresh token or client secret can create even longer-term risk.

## 2. Sensitive Locations in an HTTP Request

| Location | Example | Logging Rule |
| --- | --- | --- |
| Authorization header | Bearer access token | Never log the value |
| Cookie | Session/access token | Never log cookie values |
| Query parameter | `access_token=...` | Never put tokens in URLs; filter if legacy systems force them |
| Request body | JSON containing a token or credential | Do not log body by default |
| Response body | Newly issued token | Do not log body by default |
| Exception | Client exception containing headers | Do not log verbatim if it could contain credentials |
| MDC/context | `token`, `authorization`, `credential` | Never put tokens into context fields |
| Trace attributes | `http.request.header.authorization` | Do not capture secret headers |

Example of a common valid request:

```http
GET /api/orders HTTP/1.1
Host: orders.example.internal
Authorization: Bearer <access-token>
Accept: application/json
```

The `Authorization` value only serves authentication between the client and the resource server. It is not information needed to understand how the request was processed.

Never pass access tokens in URLs. URLs can appear in browser history, proxy logs, referrer headers, analytics, and monitoring. If a legacy system forces query parameters, plan for removal and apply precise redaction before recording the request target.

## 3. Allowlist Logging Instead of Recording the Entire Request

A safe rule is to log only the fields required for operations:

| Field | Loggable? | Notes |
| --- | --- | --- |
| HTTP method | Yes | Finite set of values |
| Route template | Yes | Use template, not raw URI with IDs |
| Response status | Yes | Contains no credentials |
| Duration | Yes | Clear unit |
| Service name | Yes | Stable value |
| Trace ID/span ID | Conditionally | Per correlation policy; never use as metric tags |
| Authorization | No | Always exclude from logs |
| Cookie/Set-Cookie | No | May contain session/token |
| Request/response body | No by default | Log only sanitized structure if explicitly required |
| Password/client secret/API key | No | Credential |
| Raw query string | Avoid | May contain tokens, PII, or business data |

Structured logging helps select specific fields instead of serializing the entire request object:

```json
{
  "event": "http.server.request.completed",
  "service.name": "orders-service",
  "http.request.method": "GET",
  "http.route": "/api/orders",
  "http.response.status_code": 200,
  "event.duration_ms": 42,
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736"
}
```

This example contains only operational metadata. Do not add authorization, cookies, raw payloads, or tokens to the same event.

## 4. Never Log All Headers

HTTP headers vary in operational value. Logging all headers usually creates more risk than benefit. Instead, pick a small allowlist:

```java
import java.util.Map;
import jakarta.servlet.http.HttpServletRequest;

final class SafeRequestFields {
    private SafeRequestFields() {}

    static Map<String, String> from(HttpServletRequest request) {
        return Map.of(
            "method", request.getMethod(),
            "route", safeRoute(request),
            "requestId", safeRequestId(request)
        );
    }

    private static String safeRoute(HttpServletRequest request) {
        // Use a route template supplied by handler mapping in real code.
        return request.getRequestURI();
    }

    private static String safeRequestId(HttpServletRequest request) {
        // Validate length and allowed characters before logging.
        String value = request.getHeader("X-Request-Id");
        if (value == null || !value.matches("[A-Za-z0-9_-]{1,64}")) {
            return "unavailable";
        }
        return value;
    }
}
```

This is an illustrative allowlist example, not a complete route resolver implementation. In a real application, retrieve the route template from the handler mapping after mapping completes; raw URIs may contain identifiers. Client-supplied request IDs must have length and character restrictions to prevent log injection.

Do not write code like iterating `request.getHeaderNames()` and logging every name/value pair. Header names can have different casing; a denylist checking only one casing can miss variants.

## 5. Redaction as an Additional Defense Layer

If a legacy component or framework still logs headers, apply redaction in the logging pipeline. For example, logging configuration can mask known fields:

```text
Authorization: Bearer [REDACTED]
Cookie: [REDACTED]
Set-Cookie: [REDACTED]
```

Redaction should:

- Be case-insensitive for header names.
- Recognize the `Bearer` scheme with valid whitespace/formatting.
- Mask entire cookie values, not only common cookie names.
- Handle JSON/form fields with sensitive names according to known schemas.
- Not corrupt log contents to the point that investigation becomes impossible.
- Be tested against multiple field name casing variants and token formats.

Regex redaction across entire log lines is not the only solution. Structured fields can be filtered before serialization; this is usually a clearer control point. Redaction at the collector/backend is only a last line of defense, since sensitive data has already left the process before being masked.

## 6. Spring Security: Authenticating Tokens Without Logging Them

Spring Security Resource Server can authenticate Bearer tokens via the filter chain and `JwtDecoder` or opaque token introspection. Business controllers typically only need the verified principal/claims, not the raw token.

Example controller using the principal:

```java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ProfileController {
    @GetMapping("/api/profile")
    ProfileView profile(@AuthenticationPrincipal Jwt jwt) {
        return new ProfileView(
            jwt.getSubject(),
            jwt.getClaimAsString("tenant")
        );
    }
}
```

This example shows the controller using only necessary claims after the token is authenticated. Never call `jwt.getTokenValue()` to log it. Claims can also contain PII or sensitive data; only use and log approved claims.

Do not log the entire `Authentication` object, `SecurityContext`, or `Jwt` object via `toString()`. Those objects can contain token credentials, authorities, claims, and principal details.

## 7. Filters/Interceptors and Access Logging

A servlet filter can record request completion metadata. Design it around an allowlist and do not read/serialize headers arbitrarily:

```java
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.filter.OncePerRequestFilter;

class SafeAccessLogFilter extends OncePerRequestFilter {
    private static final Logger log =
        LoggerFactory.getLogger(SafeAccessLogFilter.class);

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {
        long start = System.nanoTime();
        try {
            chain.doFilter(request, response);
        } finally {
            long elapsedMs =
                (System.nanoTime() - start) / 1_000_000;
            log.info("http_request method={} status={} duration_ms={}",
                request.getMethod(),
                response.getStatus(),
                elapsedMs);
        }
    }
}
```

This is a minimal filter illustrating safe metadata. Production access logging should retrieve an appropriate route template, distinguish async dispatches, avoid logging a single request multiple times, and coordinate with existing server/container access logs. If the framework already emits an access event, do not add a filter just to log the same information again.

## 8. Exceptions and HTTP Client Logs

HTTP client exceptions sometimes include the request URL, headers, or response body. HTTP libraries can log request details when wire logging or DEBUG logging is enabled.

Avoid:

- Enabling full request/response wire logging in production.
- Logging exception objects whose message contains the `Authorization` header.
- Logging request configuration objects or client request objects directly.
- Logging curl commands constructed from requests containing bearer tokens.

Instead, log the exception class, error category, status code, destination service, and trace correlation. If protocol debugging is needed, use a test environment with synthetic tokens, synthetic payloads, and a strictly bounded logging window.

## 9. MDC, Tracing, and Baggage

MDC is useful for attaching correlation fields such as trace IDs to logs. However, never put access tokens into MDC. MDC can be copied across thread pools, async executors, or reactive contexts and persist longer than expected if cleanup is improper.

Do not do the following:

- `MDC.put("access_token", token)`.
- Baggage containing tokens propagated across services.
- Span attributes containing `Authorization`/`Cookie` headers.
- Metric tags containing tokens or token hashes.
- Logging trace context objects with sensitive custom fields.

A trace ID is not a credential and is normally useful for joining logs with traces. A token is a credential and must always be excluded from telemetry. Do not hash a token to log instead of redacting: a stable hash still creates a sensitive identifier, which can enable unauthorized correlation or dictionary attacks in some systems.

## 10. Reverse Proxy, Gateway, and Container Access Logs

Your application might not log `Authorization`, while the gateway, ingress, service mesh, or servlet container records request headers. Check the entire path:

1. Load balancer / ingress access logs.
2. API gateway request/response logging.
3. Service mesh proxy access logs.
4. Servlet container access log valves.
5. Spring application logging.
6. HTTP client wire logging.
7. APM agents and telemetry collectors.

Each layer has its own configuration. A policy applied only in Logback/Log4j cannot stop a gateway from recording headers. You must disable header capture or configure explicit exclusions/redaction at every layer capable of logging requests.

## 11. Testing to Detect Token Logging

An important test is creating a synthetic token with a unique marker and verifying that the marker does not appear in any log event:

```java
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.assertThat;

class AccessTokenLoggingTest {
    @Test
    void accessTokenNeverAppearsInCapturedLogs() {
        String sentinel = "test-access-token-DO-NOT-LOG-7f31";

        // Arrange a test request with:
        // Authorization: Bearer <sentinel>
        // Capture application and access-log output.
        // Invoke the secured endpoint.
        // Assert the sentinel is absent from every captured event.
        assertThat(capturedLogs()).doesNotContain(sentinel);
    }

    private String capturedLogs() {
        // Replace with the test appender / log capture implementation.
        return "";
    }
}
```

This is a test skeleton that needs to be wired to your project's test appender or log capture mechanism. A complete test suite should also cover:

- Application logs and access logs.
- HTTP client/server debug output if enabled in tests.
- Exception paths (401, 403, 5xx, timeout).
- Uppercase/lowercase header name variants.
- Cookies and legacy query parameters.
- Structured JSON fields and MDC.
- Trace/span attributes exported to an in-memory exporter.

Never use real production tokens as test fixtures. Use a synthetic sentinel that can be searched accurately and clean up/rotate test data afterward.

## 12. Logging Policy and Operational Configuration

A clear logging policy should specify:

| Data Category | Policy |
| --- | --- |
| Credentials | Never log |
| Authorization/Cookie headers | Do not capture or redact at the source |
| PII | Log only approved fields, minimize, and limit retention |
| Request/response bodies | Disabled by default; use only sanitized schemas in appropriate environments |
| Correlation IDs | Allowed per format/length policy |
| Route/method/status/duration | Allowed per allowlist |
| Exceptions | Log class/category and stack trace per policy; strip secrets from messages |
| Debug/wire logging | Enable only under strict control, synthetic tokens, short duration |

Beyond code, control log read permissions, retention, encryption at rest/in transit, export destinations, and access auditing. If a token has leaked into logs, deleting one line in the application does not remove copies in collectors, indexes, archives, backups, and downstream SIEMs.

## 13. Handling a Logged Access Token Incident

If a real token is discovered in logs, treat it as a credential exposure incident:

1. Identify the token type, issuer, audience, scope, expiry, and the scope of systems containing the logs.
2. Restrict access to the affected logs/indexes and stop further ingestion of sensitive data.
3. Revoke/invalidate the token if the issuing mechanism supports it; consider revoking related session/refresh tokens per incident policy.
4. Search for copies across application logs, proxies, collectors, SIEMs, archives, backups, and ticket attachments.
5. Delete or redact according to organizational retention/legal hold procedures; document the remediation scope.
6. Check access audits to determine whether there was unauthorized access to the logs.
7. Fix the logging source and add regression tests before reopening ingestion.

Do not rely solely on expiry while a token is still valid. If a token cannot be revoked independently, coordinate with the issuer/security team to determine appropriate invalidation measures.

## 14. Common Mistakes

| Symptom | Possible Cause | Remediation |
| --- | --- | --- |
| Token appears in access log | Proxy/container logs all headers | Disable header capture or configure redaction at proxy |
| Token appears in exception message | HTTP client exception serializes request | Log error category/status, not raw request |
| Token appears in MDC | Middleware copies credentials to context | Remove field, allowlist MDC keys |
| Redaction misses Authorization | Case-sensitive header name matching | Normalize header names before filtering |
| Token in trace backend | Header capture or custom span attribute | Exclude secret headers and inspect exporter payloads |
| Token in URL | Legacy query parameter or curl log | Remove token from URL and redact request target |
| Token in JSON body log | Request/response body logging | Disable body logging or use a sanitized schema |
| Token hash appears in metrics | Token hash used as a tag | Remove tag; never use token-derived identifiers |
| Log still present after app fix | Collector/index/archive kept old copies | Execute incident cleanup across all copies |
| Tests miss leak | Capturing only one appender or one status path | Expand tests across proxies, exceptions, and trace output |

## 15. Real-World Scenario: Authorization Header Appears in DEBUG Logs

**Hypothetical context:** A service enables DEBUG for its HTTP client to investigate an error calling a payment provider. The log collector captures request headers and one log line contains an `Authorization: Bearer` token.

Procedure:

1. **Stop new emissions:** disable wire/header logging or switch the logger back to a safe level.
2. **Determine scope:** search for the token marker across app logs, container logs, collectors, indexes, and archives.
3. **Revoke credential:** revoke the token if supported and evaluate related refresh/session credentials.
4. **Restrict access:** lock down read access to the log index, audit access, and coordinate security response.
5. **Fix the source:** configure the client logger not to capture `Authorization`/`Cookie`; use allowlisted metadata.
6. **Test:** send a test request with a sentinel token and verify it does not appear in appenders, proxy logs, or trace exporters.
7. **Prevent recurrence:** enforce a policy banning credential logging, automated secret scanning, and pre-production DEBUG config reviews.

A token appearing in logs is a credential exposure incident even without evidence of exploitation. Respond based on data accessibility and validity window rather than waiting to detect abuse.

## 16. Self-Check Exercises

**Exercise 1.** Why is a Bearer access token treated as a secret?

*Hint:* Whoever holds the token can use it to access resources within its granted permissions.

**Exercise 2.** Should you log all request headers to debug HTTP 401?

*Hint:* No. Log method, route, status, client category, and trace correlation; exclude `Authorization`/`Cookie`.

**Exercise 3.** Why is redaction only at the log collector insufficient?

*Hint:* The token has already left the process and may be stored in buffers, transport, or intermediate systems prior to redaction.

**Exercise 4.** Should you store a hash of the access token in MDC for correlation?

*Hint:* No. A token hash is still a sensitive identifier; use a dedicated trace ID or request ID.

**Exercise 5.** Should a controller log the entire `Jwt` object?

*Hint:* No. The object can contain the raw token and sensitive claims; use/log only allowlisted claims.

**Exercise 6.** Why must you also check gateway and servlet container logs?

*Hint:* Each layer has its own logging config; fixing the application logger does not stop proxies from capturing headers.

**Exercise 7.** How do you test that tokens never appear in logs?

*Hint:* Send a synthetic sentinel token, capture all log outputs and trace attributes, and assert the marker does not appear.

**Exercise 8.** If a real token has already been logged, what must you do?

*Hint:* Restrict log access, revoke the token, locate and remediate all copies, audit access, and fix the source with regression tests.

## 17. Takeaways

- An access token is a bearer credential; never record raw tokens in application logs, access logs, traces, metrics, MDC, or baggage.
- Use an **allowlist** for structured logging; prefer method, route template, status, duration, and validated correlation IDs.
- Never log all HTTP headers, cookies, query strings, request/response bodies, `SecurityContext`, or `Jwt` objects.
- Redaction is defense-in-depth; filter sensitive data right at the source before serialization/export.
- Check every layer capable of logging requests: gateway, ingress, service mesh, servlet container, HTTP client, APM agent, and collector.
- Never hash tokens as a substitute for redaction and never put token-derived values into metric tags.
- Use synthetic sentinel tokens in automated tests to verify zero leakage across success/error paths, structured logs, and trace exporters.
- If a real token leaks into logs, handle it as a credential exposure incident: restrict access, revoke, locate all copies, audit, and fix the emission source.
