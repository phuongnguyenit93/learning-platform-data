# Sensitive Endpoint Filtering in Java Web Logging

## 1. Goals of Filtering Sensitive Endpoints

In a Java web application, **sensitive endpoint filtering** is the practice of identifying HTTP routes that carry or process protected data, and then **restricting what data is written to logs**. This is primarily a **privacy-aware logging policy**, not a mechanism for blocking requests or replacing Spring Security.

Typical endpoints include login, multi-factor authentication, token issuance/refresh, password reset, payments, user profiles, private documents, signed webhooks, and secret-key administration. Each endpoint can generate multiple log sources: access logs at the reverse proxy, HTTP server, Servlet filter, application logger, exception handler, tracing, and collector.

A proper policy must achieve three goals simultaneously:

1. **Do not collect secrets:** passwords, OTPs, bearer tokens, cookies, session IDs, API keys, reset codes, PAN/CVV, response bodies, or unnecessary profiles.
2. **Retain sufficient operational information:** controlled method, safe route class/template, status, duration, service, and valid request ID or trace ID.
3. **Preserve mandatory security events:** failed logins, authorization denials, token issuance, permission changes, or sensitive data operations must still emit appropriate events rather than being dropped just because payload logging is disabled.

A rule like `logging.level.root=WARN` is **not enough**: `ERROR` logs can still contain bodies or tokens, and Tomcat/gateways can write access logs completely independently of SLF4J. "Disabling sensitive logs" also does not mean turning off all evidence of authentication activity.

## 2. Classifying Endpoints by Data Risk

| Endpoint Type | Example Routes | Should Not Be Logged |
| --- | --- | --- |
| Authentication | `POST /auth/login`, `POST /auth/mfa/verify` | Password, OTP, request body |
| Token/session | `POST /oauth/token`, `POST /auth/refresh` | Access token, refresh token, session cookie |
| Recovery | `POST /password/reset`, `GET /reset/{token}` | Reset code, link containing token, raw email |
| Payment | `POST /payments`, `POST /billing/cards` | PAN, CVV, payment payload |
| Personal data | `GET /users/{id}`, `PATCH /patients/{id}` | Profile, identifier in path, response body |
| Secret/admin | `/admin/keys`, `/internal/secrets` | API key, private key, sensitive results |
| Webhook | `POST /webhooks/payment` | Signature header, payload containing PII |
| File upload/download | `POST /documents`, `GET /documents/{id}` | Binary body, document contents, sensitive filename |
| GraphQL or gRPC | `POST /graphql`, authentication RPC | Variables, operation payload, sensitive metadata |

Do not just search for `"login"` or `"token"` in the raw path. Version variants, prefixes, trailing slashes, URL encoding, route aliases, or GraphQL endpoints sharing a single path can all defeat naive string-based filters.

**Better approach:** classify using **API contracts and route metadata determined by the server/router**, with labels such as `AUTH`, `PAYMENT`, `PERSONAL_DATA`, `SECRET`, `PUBLIC_SAFE`, and `UNKNOWN`. When an endpoint's category is unknown, **do not automatically dump the raw path/query/body** "for easier debugging."

## 3. Filtering Data vs. Filtering Entire Events Are Two Different Decisions

| Approach | Meaning | Appropriate When |
| --- | --- | --- |
| Omit body/header/query | Keep a minimal access event | Login, token, payment, and most APIs handling private data |
| Replace raw path with route template | `/users/42` becomes `/users/{id}` | Need to group latency/errors without exposing IDs |
| Replace route with class label | `/auth/login` becomes `AUTH_ENDPOINT` | Want to reduce access detail for special groups |
| Allowlist safe fields | Include only approved fields in the event | Structured logging with a clear schema |
| Controlled masking/pseudonymization | Redact a field that genuinely needs to be stored | Approved business requirement with retention policy |
| Separate stream/index | Route security events to a restricted store | Audit/security logging and monitoring |
| Drop an access event completely | Do not store the event at a specific source | Only when policy allows and investigation needs are reviewed |

For example, on a failed login, keep the access event without exposing credentials:

```json
{"kind":"http_access","route_class":"AUTH_ENDPOINT","method":"POST","status":401,"duration_ms":12,"request_id":"req_01","payload_logged":false}
```

A separate event **emitted by the authentication subsystem** once the outcome is known:

```json
{"kind":"security_event","event":"authentication_failed","outcome":"DENY","request_id":"req_01"}
```

Do not infer the authentication reason solely from HTTP 401; a 401 can result from a missing token, an expired token, or several other causes. Similarly, a username submitted by a client attempting to log in is not an authenticated actor.

## 4. Diagram of Log Sources That Must Be Controlled

```text
Client / Browser
    │
    ▼
CDN / WAF / Reverse Proxy ─────► Edge access log
    │
    ▼
API Gateway ───────────────────► Gateway access log
    │
    ▼
Tomcat / Jetty / Netty ────────► HTTP server access log
    │
    ▼
Servlet Filter / WebFilter ────► Request diagnostic log
    │
    ▼
Security Filter / Auth Handler ► Security / audit event
    │
    ▼
Controller / Service / Client ─► Application / exception log
    │
    ▼
Tracing / MDC / APM ───────────► Telemetry / span attributes
    │
    ▼
Collector / SIEM / Export ─────► Index / dashboard / backup
```

Modifying a `OncePerRequestFilter` in Spring does not change Tomcat's `AccessLogValve` pattern or the gateway. Setting `additivity=false` in Logback does not hide a message containing a password. Changing logger levels does not automatically remove sensitive data from trace spans or already-written log files.

**Inspect the entire pipeline** rather than checking only a single application source.

## 5. Which HTTP Data Can Enter Logs?

| Component | Risk | Default Policy |
| --- | --- | --- |
| Method | May contain arbitrary strings sent by clients | Allowlist method names and restrict characters |
| Matched route template | Generally safer than raw path | Use only trusted metadata from the router |
| Raw path/URI | IDs, emails, reset tokens | Do not log by default on sensitive routes |
| Query string | `code`, `token`, email, password | Do not log by default |
| Request headers | Authorization, Cookie, API key, signature | Do not dump the map; allowlist only if needed |
| Response headers | Set-Cookie, redirect URLs carrying codes | Do not dump the map |
| Request/response body | Passwords, PII, PAN/CVV, tokens | Do not log by default |
| Status | HTTP 2xx/4xx/5xx | Generally suitable for metadata-only |
| Duration | Time measured at a single hop | Record units and start/end points |
| Request/trace ID | Aids correlation | Validate format/length; do not treat as actor identity |
| Client IP | May be PII or a proxy IP | Log only according to purpose, policy, and trust boundary |
| User-Agent/Referer | Client-controlled data; may contain queries/control chars | Do not log verbatim by default |

**A path is not always safe even after stripping the query string.** `/reset/{token}` or `/users/{email}` contains sensitive data in path variables. Therefore, raw `getRequestURI()` is still risky. Also avoid `%r`/request line in proxies if it includes the query string.

## 6. Use Trusted Route Metadata, Do Not Manually Parse URLs

An error-prone policy:

```java
// AVOID: naive raw path matching and logging everything else.
if (!request.getRequestURI().contains("login")) {
    logger.debug("request={}", request);
}
```

This is only a snippet illustrating the risk, not a standalone program. This approach misses newly versioned endpoints, refresh tokens, upload methods, or unusual encodings; it can also invoke `toString()` on objects containing secret data.

Instead:

1. **In the route registry/controller metadata**, attach a sensitivity level to each operation.
2. **At logging time**, read the framework's matched route template if available; do not take a self-reported path string from headers/body.
3. **UNKNOWN/404** must be safe by default: log `UNMATCHED`, do not dump the raw URL.
4. **New API versions** not yet classified must have a metadata-only or fail-safe default.
5. Test HTTP methods, route aliases, reverse proxy prefixes, trailing slashes, percent-encoded paths, and URL normalization.
6. For `/graphql`, attach policies per operation or avoid logging variables/bodies across the shared route.

Manage the policy in a central layer so the request filter, audit event builder, and collector use consistent classification. However, a route labeled `PUBLIC` in metadata does not mean arbitrary bodies can be logged; each **field** still needs validation.

## 7. Standalone Java 17 Example: Keeping Access Logs Safe

The following example simulates a **matched route provided by a trusted router**. Events are classified and contain only safe fields; queries, `Authorization` headers, and bodies containing a fake canary **are excluded from the output**. For sensitive routes, the detailed route itself is replaced with a generic label.

This is a plain Java program without an HTTP server. In a real application, do not accept an arbitrary client-supplied `matchedRoute`; obtain it from the router/framework.

Save as **`SensitiveEndpointLoggingDemo.java`**:

```java
import java.util.List;
import java.util.Set;
import java.util.regex.Pattern;

public final class SensitiveEndpointLoggingDemo {
    enum Category { GENERAL, AUTH, PAYMENT, SECRET, UNKNOWN }

    record Exchange(
            String method,
            String matchedRoute,
            int status,
            long durationMs,
            String requestId,
            String query,
            String authorization,
            String body) {}

    private static final Pattern SAFE_ID =
            Pattern.compile("[A-Za-z0-9_-]{1,64}");

    private static final Set<String> SAFE_METHODS =
            Set.of("GET", "POST", "PUT", "PATCH", "DELETE");

    private static final Set<String> ROUTES = Set.of(
            "/auth/login",
            "/oauth/token",
            "/payments/{id}/confirm",
            "/orders/{id}",
            "/internal/keys");

    private static Category category(String route) {
        return switch (route) {
            case "/auth/login", "/oauth/token" -> Category.AUTH;
            case "/payments/{id}/confirm" -> Category.PAYMENT;
            case "/internal/keys" -> Category.SECRET;
            case "/orders/{id}" -> Category.GENERAL;
            default -> Category.UNKNOWN;
        };
    }

    private static String safeRoute(Category category, String route) {
        return switch (category) {
            case AUTH -> "AUTH_ENDPOINT";
            case PAYMENT -> "PAYMENT_ENDPOINT";
            case SECRET -> "SENSITIVE_ENDPOINT";
            case GENERAL -> route;
            case UNKNOWN -> "UNMATCHED";
        };
    }

    private static String safeId(String value) {
        return value != null && SAFE_ID.matcher(value).matches()
                ? value : "invalid";
    }

    private static String accessLine(Exchange e) {
        String route = ROUTES.contains(e.matchedRoute())
                ? e.matchedRoute() : "UNMATCHED";
        Category type = category(route);
        String method = SAFE_METHODS.contains(e.method())
                ? e.method() : "OTHER";
        int status = e.status() >= 100 && e.status() <= 599
                ? e.status() : 0;
        long duration = Math.max(0L, e.durationMs());

        // Do not use e.query(), e.authorization(), or e.body().
        return "kind=http_access"
                + " method=" + method
                + " route=" + safeRoute(type, route)
                + " status=" + status
                + " duration_ms=" + duration
                + " category=" + type
                + " request_id=" + safeId(e.requestId());
    }

    public static void main(String[] args) {
        List<Exchange> data = List.of(
                new Exchange(
                    "POST", "/auth/login", 401, 12, "req_01",
                    "code=SENSITIVE_CANARY_314",
                    "Bearer SENSITIVE_CANARY_314",
                    "password=SENSITIVE_CANARY_314"),
                new Exchange(
                    "GET", "/orders/{id}", 200, 8, "req_02",
                    "token=SENSITIVE_CANARY_314",
                    "Bearer SENSITIVE_CANARY_314",
                    "SENSITIVE_CANARY_314"),
                new Exchange(
                    "POST", "/payments/{id}/confirm", 200, 26, "req_03",
                    "card=SENSITIVE_CANARY_314",
                    "Bearer SENSITIVE_CANARY_314",
                    "SENSITIVE_CANARY_314"),
                new Exchange(
                    "GET", "/bad/path", 404, 3, "req_04",
                    "token=SENSITIVE_CANARY_314",
                    "Bearer SENSITIVE_CANARY_314",
                    "SENSITIVE_CANARY_314"));

        for (Exchange e : data) {
            System.out.println(accessLine(e));
        }

        // This event assumes the authentication subsystem has already determined the outcome.
        System.out.println(
                "kind=security_event event=authentication_failed"
                + " outcome=DENY request_id=req_01");
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac --release 17 SensitiveEndpointLoggingDemo.java
java SensitiveEndpointLoggingDemo
```

**Exact stdout:**

```text
kind=http_access method=POST route=AUTH_ENDPOINT status=401 duration_ms=12 category=AUTH request_id=req_01
kind=http_access method=GET route=/orders/{id} status=200 duration_ms=8 category=GENERAL request_id=req_02
kind=http_access method=POST route=PAYMENT_ENDPOINT status=200 duration_ms=26 category=PAYMENT request_id=req_03
kind=http_access method=GET route=UNMATCHED status=404 duration_ms=3 category=UNKNOWN request_id=req_04
kind=security_event event=authentication_failed outcome=DENY request_id=req_01
```

**Explanation:** the canary `SENSITIVE_CANARY_314` is present in every sample query/header/body but never appears on stdout. Payment/auth routes are printed only as class labels. Unmatched paths are not printed raw. The request ID is validated against a fixed format; the security event is emitted separately rather than inferring authentication results from the status code alone.

**Limitations:** this program does not authenticate clients itself, classifies routes based on a value assumed to be supplied by the router, does not handle async requests, does not write to files, and does not guarantee auditing. It demonstrates **selecting safe log fields**, not proving that an entire pipeline is free of canary leaks.

## 8. Spring MVC Servlet: Metadata-Only Filter Example

For **Spring Boot 3+ / Spring MVC / Jakarta Servlet** applications, a `OncePerRequestFilter` can log metadata after a synchronous request completes. The following is **integration code** requiring Spring Web, SLF4J, and application configuration; it is not standalone Java:

```java
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.Set;
import java.util.concurrent.TimeUnit;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.servlet.HandlerMapping;

@Component
public class MinimalWebAccessLogFilter extends OncePerRequestFilter {
    private static final Logger LOG =
            LoggerFactory.getLogger("http.access.safe");
    private static final Set<String> METHODS =
            Set.of("GET", "POST", "PUT", "PATCH", "DELETE");

    private static String safeMethod(String raw) {
        return METHODS.contains(raw) ? raw : "OTHER";
    }

    private static String safeRoute(Object matched) {
        if (!(matched instanceof String route)) {
            return "UNMATCHED";
        }
        return switch (route) {
            case "/auth/login", "/oauth/token" -> "AUTH_ENDPOINT";
            case "/payments/{id}/confirm" -> "PAYMENT_ENDPOINT";
            case "/orders/{id}" -> "/orders/{id}";
            default -> "OTHER_ENDPOINT";
        };
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        long started = System.nanoTime();
        try {
            chain.doFilter(request, response);
        } finally {
            // Only illustrates synchronously completed requests.
            if (!request.isAsyncStarted()) {
                Object route = request.getAttribute(
                        HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE);
                long ms = TimeUnit.NANOSECONDS.toMillis(
                        System.nanoTime() - started);

                LOG.info(
                    "kind=http_access method={} route={} status={} duration_ms={}",
                    safeMethod(request.getMethod()),
                    safeRoute(route), response.getStatus(), ms);
            }
        }
    }
}
```

In this example, the logger does not read `getQueryString()`, `getHeader("Authorization")`, `getCookies()`, the request body, the response body, or the raw `getRequestURI()`. When a route has no matched pattern yet, it logs a generic label.

**Do not use as-is if you need an accurate event for every request:**

- `HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE` may be absent if a request is rejected before MVC or does not match a handler.
- With async dispatch, SSE, streaming, or WebSockets, a request can continue after `finally` runs. The code above skips logging when `isAsyncStarted()` is true and **lacks a completion hook**, so some async requests will not produce an event from this filter.
- Error handlers may change the status after the filter's `finally` block runs. Measure at a chosen completion point (the server access log or a tested lifecycle listener).
- Other filter ordering, authentication filters, and exception handling can emit independent logs.
- New routes default to `OTHER_ENDPOINT`; review policies and add tests whenever adding APIs.

If you truly need complete access events for async/error flows, use an appropriate lifecycle/`AsyncListener` mechanism, server instrumentation, or framework observability with duplicate-log protection.

## 9. `shouldNotFilter` Does Not Disable All Logging

`OncePerRequestFilter` supports `shouldNotFilter(HttpServletRequest)`. When it returns `true`, **that filter** skips the request; the controller still receives the request normally if other security/routing rules allow it.

This mechanism makes sense for a **debug payload-logging filter**, not as a reason to drop required security events or access metadata. Common misconceptions:

- `shouldNotFilter` does not disable Tomcat `AccessLogValve`, Nginx access logs, or HTTP client interceptors.
- If a request goes through multiple dispatches, do not assume "once" means a single event for the entire lifecycle. `shouldNotFilterAsyncDispatch` and `shouldNotFilterErrorDispatch` have their own defaults.
- Filters running before routing typically **do not know the route template yet**; URI string matching there requires extreme caution and does not replace a route registry policy.
- `ContentCachingRequestWrapper` does not guarantee the entire request body is available for logging, and caching payloads increases RAM usage. For sensitive endpoints, do not read the body just to redact it if you can **avoid collecting the body in the first place**.

**Spring WebFlux uses `WebFilter` or reactive stack instrumentation**, not `OncePerRequestFilter`. When inspecting reactive request bodies, incorrect subscribing or wrapping can consume the stream or alter backpressure.

## 10. `CommonsRequestLoggingFilter`: Privacy-First Configuration

Spring Framework provides `CommonsRequestLoggingFilter` with options to include metadata. When payload logging is not required, you can configure it like this:

```java
// Spring snippet: requires imports for @Bean and CommonsRequestLoggingFilter.
@Bean
CommonsRequestLoggingFilter safeRequestLoggingFilter() {
    CommonsRequestLoggingFilter filter = new CommonsRequestLoggingFilter();
    filter.setIncludeClientInfo(false);
    filter.setIncludeQueryString(false);
    filter.setIncludeHeaders(false);
    filter.setIncludePayload(false);
    return filter;
}
```

This snippet is not a standalone program; it only shows configuration options. Whether `CommonsRequestLoggingFilter` actually emits logs also depends on logger levels and the logging backend.

**Note:** enabling `setIncludePayload(true)` does not guarantee seeing the full body: the payload portion may only contain bytes already consumed/cached at the time the framework logs. `maxPayloadLength` and wrappers have their own limits. For login, token, payment, and sensitive document endpoints, avoid enabling body logging by default and relying on regexes to mask everything.

## 11. Logback and Log4j2: Routing Is Different from Redaction

Logback can separate a dedicated `http.access.safe` logger to keep access events from mixing with the application stream:

```xml
<configuration>
    <appender name="ACCESS" class="ch.qos.logback.core.ConsoleAppender">
        <encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
            <pattern>%d{ISO8601} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>
    <logger name="http.access.safe" level="INFO" additivity="false">
        <appender-ref ref="ACCESS"/>
    </logger>
    <root level="INFO"/>
</configuration>
```

This is a **minimal routing example**, not a complete production configuration. `additivity="false"` prevents the access logger from forwarding to Logback's root appenders. It does **not** protect you if code already put a password into the message. In production, clearly define application appenders, retention, write permissions, and log shippers.

`ThresholdFilter`, `LevelFilter`, or INFO/WARN levels select events by severity; they **do not understand which content is a secret**. In Log4j2, `RegexFilter` also does not replace a field allowlist; regexes struggle to catch all nested JSON, exceptions, multiple encodings, and new token formats.

The implementation rule should be: **restrict fields before creating the event -> structured encoding -> route to the right sink -> supplementary masking -> RBAC/retention**.

## 12. Embedded Tomcat Access Logs Require Separate Configuration

Spring Boot applications using embedded Tomcat can enable access logs:

```properties
server.tomcat.accesslog.enabled=true
server.tomcat.accesslog.pattern=%m %U %s %D
```

The example pattern logs the method, raw URL path, status, and duration (in milliseconds per Tomcat `AccessLogValve`). It does not explicitly log the query string or headers, but **`%U` is still the actual path**, which may contain reset tokens or email addresses. Do not call this pattern "safe for all endpoints."

If the app cannot guarantee paths are free of secrets, consider a more minimal pattern such as `%m %s %D` or a metadata access log mechanism based on route class, while verifying investigation needs. Gateways/reverse proxies must be configured similarly.

According to Tomcat documentation, `AccessLogValve` supports:

- `conditionIf="marker"`: log only when the request attribute `marker` is non-null.
- `conditionUnless="marker"`: log only when the request attribute `marker` is null.

Example **Valve configuration snippet** when managing Tomcat directly (not a snippet to paste verbatim into `application.properties`):

```xml
<Valve className="org.apache.catalina.valves.AccessLogValve"
       directory="logs"
       prefix="access"
       suffix=".log"
       pattern="%m %s %D"
       conditionUnless="omitContainerAccessLog"/>
```

A Servlet Filter can set the `omitContainerAccessLog` attribute when an organization decides **not to record container access events** for a specific group of requests, such as noisy health probes. **Do not drop all login failures or token issuances by default:** minimal security/audit events must still be emitted per policy. If a request is rejected before the filter, the marker may not be set yet; async/error dispatches must be tested.

This Valve mechanism **applies only to Tomcat** and cannot be used directly for Jetty, Undertow, Reactor Netty, or gateways. Do not conflate application log controls with container log controls.

## 13. Security Events and Audits Must Survive Payload Filtering

Security events must be generated from **security/business logic** at the exact point where the outcome is known:

| Activity | Suggested Security Event | Must Not Be Logged |
| --- | --- | --- |
| Failed login | `authentication_failed` and a safe reason code | Password, OTP, self-reported name as an authenticated actor |
| Token issued | `token_issued` with authenticated client/actor | Actual token/JWT/refresh token |
| Reset requested | `password_reset_requested` | Reset code/link, raw email if unnecessary |
| Access denied | `authorization_denied` | Raw resource secret, self-reported identity headers |
| MFA changed | `security_setting_changed` | MFA seed, recovery codes |
| Payment | `payment_attempted` / `payment_completed` | Card data, secret payload |

Do not infer `outcome=SUCCESS` solely from HTTP 200 when an API returns a job ID for asynchronous processing. Do not assign the actor from `X-User-ID` or the request body. If audit events have durability requirements, do not let them be dropped by a debug logging queue policy without prior evaluation.

**Privacy filtering must not become "erasing evidence."** You can block payloads across all loggers while still preserving minimal security events in an appropriate sink with dedicated access control and retention.

## 14. Subtle Leak Sources: Exceptions, HTTP Clients, and APM

The following is an **unsafe** example:

```java
// UNSAFE snippet; do not use with data containing secrets.
logger.error("Request failed: {}", request);
logger.debug("headers={} body={}", requestHeaders, requestBody);
logger.error("External service failed", exceptionContainingBody);
```

Risks:

- `request.toString()` or DTO `toString()` may contain passwords/tokens.
- SDK/HTTP client exceptions may carry URLs with query strings, response bodies, and headers.
- `@ControllerAdvice` and error handling may log entire exceptions/messages.
- Client debugging in HTTP libraries may activate when switching to DEBUG/TRACE levels.
- APM/tracing may capture request parameters, raw URLs, span attributes, or baggage.
- MDC containing unverified user IDs/tenants/request IDs may be copied into every log.
- Collectors/dashboards/CSV exports may display or store raw data if redaction only happens at the UI layer.

The solution is **safe event fields**, error codes, route templates, status, and duration; test both success and failure scenarios. If stack traces are needed, verify whether they contain data from requests/dependencies and restrict sink access appropriately.

## 15. HTTP URLs, Proxies, and Control Data

An account recovery URL may contain a token in the path:

```text
GET /reset/sensitive-reset-token?email=user@example.com
```

Even without logging the query string, `getRequestURI()` still contains the token. Use the route `/reset/{token}` or the label `PASSWORD_RESET_ENDPOINT` when the framework provides a trusted matched route.

`Referer` and `User-Agent` fields can also contain secret query parameters or control characters. `X-Forwarded-For` is only trustworthy after passing through a proxy configured as a trusted source and after the edge strips client-supplied forwarded headers. An IP address is not an authenticated user identity.

`X-Request-ID` and `traceparent` are correlation metadata, not proof of an actor. Validate their format/length to avoid log injection; do not use high-cardinality IDs as metric labels. With async/thread pools, MDC must be scoped properly so context does not leak between requests.

## 16. Tracing, Metrics, and Actuator Are Also Data Sources

Beyond application loggers:

- OpenTelemetry/APM may include `http.url`, queries, span attributes, or exception details, and requires separate configuration.
- Metrics should use templated `http.route` values rather than raw URIs, user IDs, or trace IDs with unbounded cardinality.
- Spring Boot Actuator `httpexchanges` can record HTTP exchange data if a repository is configured. Review its schema, retention, recorded fields, and access control.
- Management endpoints such as `/actuator/env`, `/actuator/configprops`, `/actuator/logfile`, or `/actuator/heapdump` can expose sensitive data; **restricting access/exposure** is a separate requirement from filtering their logging.
- HTTP gateways, cloud load balancers, and CDNs have their own access log systems; each source must be reviewed.
- Log exports/backups must also have retention policies and access controls; masking on a dashboard does not delete data already stored in the index.

An organization cannot claim "tokens are filtered from logs" just because no token appears in one application log file. Verification must cover **every place capable of collecting data**.

## 17. Redaction vs. Field Allowlisting: Which to Choose?

**Field allowlisting** is generally more reliable than whole-message regex blacklisting. For a payment system, you can allow events to include the payment method code and status without logging the card number:

```text
event=payment_attempted
payment.method=CARD
route=PAYMENT_ENDPOINT
status=DECLINED
duration_ms=34
request_id=req_04
```

If policy permits storing only `last4`, identify a trusted source for `last4`, how it is stored, and who can access it—do not log the full PAN and extract it with regex. Hashed data does not automatically become anonymous if the value domain is small or can be linked across multiple sources.

Fields should have constraints: type, length, character set, Unicode controls, nested objects, schema version, retention, and allowed destinations. A JSON structured encoder handles syntax escaping, but does not automatically replace HTML/CSV escaping during exports.

## 18. Fail-Safe Handling for Unknown Endpoints

A blacklist approach is risky:

```text
If path contains login or token → do not log body
Other paths                     → log full body
```

A new endpoint `/api/v3/credentials/rotate` will slip right through. **Fail-safe logging** should set these defaults:

- New/unmatched routes -> metadata-only, no raw path/query/body/headers.
- `AUTH`/`PAYMENT`/`SECRET` groups -> metadata-only, plus security events when needed.
- Only fields with an explicit policy are logged, even for routes considered public.
- If a collector parser fails -> increment a metric and quarantine per procedure; do not fall back to dumping raw payloads to stdout.
- If the audit sink fails -> behave according to the approved durability policy.
- Never allow requests to choose logger names, files, indexes, or event types.

This fail-safe rule **does not block requests**. It simply avoids outputting risky data when the policy is unknown.

## 19. End-to-End Testing with a Fake Canary

Use a fake string, never a real secret:

```text
SENSITIVE_CANARY_314
```

Inject the canary into passwords, query strings, raw paths, `Authorization`, `Cookie`, test response bodies, and test exceptions. Then search for it in:

1. Application files/stdout/stderr and server access logs.
2. Gateway, proxy, WAF, or CDN access logs.
3. HTTP client debug logs and Spring security/application exception logs.
4. APM/tracing spans and MDC-enriched events.
5. Collector buffers, backend indexes, and dashboards.
6. Exports/snapshots/backups within the authorized test scope.

**Expected result:** the canary **does not appear** in any sink not permitted to store that data. At the same time, failed logins still produce safe security events if system requirements call for them.

Additional tests:

- 200/400/401/403/500 responses, different HTTP methods, route aliases, and URL encodings.
- Async requests, SSE, error dispatches, streaming, 404s, and requests blocked before filters.
- Enabling DEBUG on HTTP clients/frameworks to check whether additional sensitive data is emitted.
- Nested JSON payloads, multipart requests, GraphQL variables, large bodies, and headers with CRLF/control characters.
- Multi-tenancy: MDC does not leak; collectors prevent tenant A from viewing tenant B's logs.
- Full queues, full disks, collector failures, dropped logs, and alerting policies.

Do not treat "no access log seen" as a PASS if critical security events are also lost. Count events per source and reconcile against actual state, not just total pipeline line counts, since a single request may be logged at multiple hops.

## 20. Common Pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Spring logs are filtered, but reset tokens still appear | Tomcat/gateway logs raw paths | Audit patterns at every layer; use classes/templates |
| `shouldNotFilter` returns true, yet request logs still appear | Another filter/server/proxy emits them | Inventory every source |
| Enabling DEBUG exposes passwords | HTTP client, exception, or DTO `toString()` | Use safe fields; disable payload capture |
| Stripping query strings still leaks tokens | Token is in the path | Do not log raw request URIs |
| GraphQL still leaks secrets | Variables are in the body on a shared route | Do not dump GraphQL bodies by default |
| No security alert on failed login | Dropped security events along with payload logs | Emit security events separately from the auth handler |
| Async requests have no access log | `finally` runs early without a completion hook | Use lifecycle instrumentation |
| A pattern with `%U` is called "path-hidden" | `%U` is the raw path in Tomcat | Remove that field or handle safely at the source |
| Wrong actor recorded | Trusting user ID headers/client-provided data | Use the verified security principal |
| Secret leaked in exports despite dashboard masking | Original data remains in index/snapshots | Avoid collecting at the source; protect copies |
| Logger level set to WARN still leaks tokens | `ERROR` logs contain credentials or separate access logs | Filter fields, not just levels |
| Logging slows down when DEBUG increases | Queue/encoder/I/O overload | Scope debugging narrowly and measure drops/latency |
| New endpoint is unprotected | Path-based blacklist misses new routes | Use fail-safe policies and contract tests |

## 21. Implementation Workflow

1. **Inventory log sources** and storage locations: gateway, server, app, client, APM, collector, exports.
2. **Classify endpoints** using route/operation metadata and review with owners.
3. **Define a minimal event schema** including safe method, route class, status, duration, and validated correlation IDs.
4. **Strip sensitive bodies/queries/headers at the source**; do not rely on backend regexes.
5. **Keep security/audit events separate** with actor/outcome from authenticated logic.
6. **Implement on the right stack**: Servlet/`OncePerRequestFilter`, WebFlux/`WebFilter`, Tomcat `AccessLogValve`, and corresponding proxies.
7. **Test async/error/404** and requests blocked before MVC.
8. **Run pipeline-wide canary tests**, including with DEBUG enabled and exception scenarios.
9. **Protect log stores** with RBAC, encryption, retention, separate export/delete permissions, and access monitoring.
10. **Monitor logging queues/collectors** to detect drops, backlogs, or sink failures.

## 22. Completion Checklist

- [ ] Sensitive endpoint list has clear owners and policies, not just path-name matching.
- [ ] UNKNOWN/new routes default to metadata-only.
- [ ] Login/token/reset/payment/upload endpoints do not dump request or response bodies.
- [ ] Tokens, cookies, `Authorization`, OTPs, API keys, or sensitive query parameters are not logged.
- [ ] Raw paths that may contain reset tokens/PII use appropriate route templates/classes.
- [ ] Mandatory security events are still generated from auth/business handlers.
- [ ] Tomcat/proxy/gateway access logs are controlled separately from SLF4J.
- [ ] Spring Servlet filters are not confused with WebFlux; async/error dispatches are handled properly.
- [ ] Exceptions, HTTP clients, tracing, APM, MDC, and actuator have been reviewed.
- [ ] Enabling DEBUG does not bring secrets back into logs.
- [ ] Test canaries do not appear in unauthorized sinks.
- [ ] RBAC, retention, secure exports, and log drop/sink failure monitoring are in place.

**Remember:** filtering sensitive endpoints **does not mean deleting all logs for those endpoints**. **Avoid collecting secret data**, preserve **safe metadata and security events**, control **every log source**, and verify with canary tests. Log levels or a single `OncePerRequestFilter` alone cannot protect the entire flow.

### References

- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [MITRE — CWE-117](https://cwe.mitre.org/data/definitions/117.html)
- [Spring Framework — OncePerRequestFilter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html)
- [Spring Framework — Servlet async request processing](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html)
- [Spring Framework — CommonsRequestLoggingFilter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/filter/CommonsRequestLoggingFilter.html)
- [Tomcat — AccessLogValve](https://tomcat.apache.org/tomcat-10.1-doc/config/valve.html#Access_Logging)
- [Spring Boot — HTTP exchange recording](https://docs.spring.io/spring-boot/reference/actuator/http-exchanges.html)
